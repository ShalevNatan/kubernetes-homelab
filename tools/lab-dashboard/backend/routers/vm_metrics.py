"""
routers/vm_metrics.py — Per-VM resource monitoring via SSH.

Collects CPU thread count, RAM usage, disk usage, load average, and uptime
from each cluster VM by SSHing through WSL2. Everything is gathered in a
single SSH round trip per VM to minimise latency and connection overhead.

Intended use: catch a memory-pressured or disk-full node before an Ansible
playbook fails on it. This is VM-level monitoring only — not Kubernetes.

Design notes:
- All VMs are queried in parallel (ThreadPoolExecutor) so worst-case response
  time is bounded by the single slowest node, not the sum of all timeouts.
- A node that is powered off or unreachable is marked reachable=False with all
  metric fields null — the frontend renders this as "offline".
- SSH goes through WSL2 (same path Ansible uses), so no additional key or
  host configuration is required beyond what kubeadm setup already did.
- This endpoint does NOT acquire the global executor lock — metrics collection
  is read-only and must not block playbook execution.
"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

from backend import config, executor

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/vm-metrics", tags=["vm_metrics"])

# SSH user — must match the Ubuntu VM template's default user.
_SSH_USER = "ubuntu"

# Single shell command that collects all metrics in one SSH round trip.
# Order matters — _parse_output relies on nproc always being the first line.
#
#   nproc          → CPU thread count (single integer)
#   free -m        → RAM in MiB (header + Mem: + Swap: rows)
#   df -h /        → root filesystem usage, human-readable
#   /proc/loadavg  → space-separated load averages
#   uptime -p      → human-readable uptime string
_COLLECT_CMD = "nproc; free -m; df -h /; cat /proc/loadavg; uptime -p"

# SSH connection timeout in seconds. Kept short so that an offline node
# does not block the endpoint for more than this long. run_sync's timeout
# is set to +3s to allow the remote command to complete after connecting.
_SSH_CONNECT_TIMEOUT = 5


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class VMMetrics(BaseModel):
    name: str
    ip: str
    reachable: bool
    # CPU
    cpu_threads: int | None
    load_1m: float | None
    # RAM (MiB)
    ram_total_mb: int | None
    ram_used_mb: int | None
    ram_avail_mb: int | None
    # Disk (human-readable strings from df -h, plus integer percentage)
    disk_total: str | None
    disk_used: str | None
    disk_avail: str | None
    disk_use_pct: int | None
    # System
    uptime: str | None
    # Short error hint when SSH fails; null on success
    error: str | None


class VMMetricsResponse(BaseModel):
    vms: list[VMMetrics]
    collected_at: str  # ISO-8601 UTC


# ---------------------------------------------------------------------------
# SSH collection
# ---------------------------------------------------------------------------

def _collect_one(name: str, ip: str) -> VMMetrics:
    """SSH into a single VM and collect resource metrics.

    Uses WSL2 as the SSH transport — the same path Ansible takes, so no
    additional key configuration is needed.

    Returns VMMetrics with reachable=False if the connection fails or times
    out. All metric fields are None in that case.
    """
    cmd = [
        "wsl.exe", "-d", config.ansible.wsl_distro,
        "--",
        "ssh",
        "-o", f"ConnectTimeout={_SSH_CONNECT_TIMEOUT}",
        "-o", "StrictHostKeyChecking=no",
        "-o", "BatchMode=yes",   # never prompt — fail fast instead
        f"{_SSH_USER}@{ip}",
        _COLLECT_CMD,
    ]

    rc, output = executor.run_sync(cmd, timeout=_SSH_CONNECT_TIMEOUT + 3)

    if rc != 0:
        return VMMetrics(
            name=name, ip=ip, reachable=False,
            cpu_threads=None, load_1m=None,
            ram_total_mb=None, ram_used_mb=None, ram_avail_mb=None,
            disk_total=None, disk_used=None, disk_avail=None, disk_use_pct=None,
            uptime=None,
            error=(output.strip()[:200] or "SSH failed"),
        )

    return _parse_output(name, ip, output)


def _parse_output(name: str, ip: str, raw: str) -> VMMetrics:
    """Parse stdout of _COLLECT_CMD into a VMMetrics object.

    Expected output structure (blank lines stripped before processing):

        8                                       ← nproc
                  total  used  free ...
        Mem:      16000  4100  3000  ...  8800
        Swap:      2047     0  2047
        Filesystem  Size  Used Avail Use% Mounted on
        /dev/sda1    80G   12G   68G  15% /
        0.42 0.35 0.28 1/183 12345           ← /proc/loadavg
        up 2 days, 4 hours, 12 minutes       ← uptime -p
    """
    lines = [l for l in raw.strip().splitlines() if l.strip()]

    cpu_threads = None
    load_1m = None
    ram_total_mb = ram_used_mb = ram_avail_mb = None
    disk_total = disk_used = disk_avail = disk_use_pct = None
    uptime_str = None

    # nproc is always the first non-blank line — a single integer.
    try:
        cpu_threads = int(lines[0].strip())
    except (IndexError, ValueError) as exc:
        _log.warning("Could not parse nproc for %s: %s", name, exc)

    for line in lines[1:]:

        # --- RAM ---
        # free -m Mem row: "Mem:  total  used  free  shared  buff/cache  available"
        if line.startswith("Mem:"):
            parts = line.split()
            try:
                if len(parts) >= 7:
                    ram_total_mb = int(parts[1])
                    ram_used_mb  = int(parts[2])
                    ram_avail_mb = int(parts[6])
            except (IndexError, ValueError) as exc:
                _log.warning("Could not parse free -m Mem row for %s: %s", name, exc)

        # --- Disk ---
        # df -h / data row: "/dev/sda1   80G  12G  68G  15%  /"
        # Regex matches any device path, handles varying whitespace, anchors on
        # the "/" mount point to avoid matching header or other mountpoints.
        m = re.match(r'^\S+\s+(\S+)\s+(\S+)\s+(\S+)\s+(\d+)%\s+/$', line)
        if m:
            disk_total   = m.group(1)
            disk_used    = m.group(2)
            disk_avail   = m.group(3)
            disk_use_pct = int(m.group(4))

        # --- Load average ---
        # /proc/loadavg: "0.42 0.35 0.28 1/183 12345"
        m2 = re.match(r'^(\d+\.\d+)\s+\d+\.\d+\s+\d+\.\d+\s+\d+/\d+\s+\d+$', line)
        if m2:
            try:
                load_1m = float(m2.group(1))
            except ValueError:
                pass

        # --- Uptime ---
        # uptime -p: "up 2 days, 4 hours, 12 minutes"
        if line.startswith("up "):
            uptime_str = line.strip()

    return VMMetrics(
        name=name, ip=ip, reachable=True,
        cpu_threads=cpu_threads, load_1m=load_1m,
        ram_total_mb=ram_total_mb, ram_used_mb=ram_used_mb, ram_avail_mb=ram_avail_mb,
        disk_total=disk_total, disk_used=disk_used, disk_avail=disk_avail,
        disk_use_pct=disk_use_pct,
        uptime=uptime_str, error=None,
    )


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.get("", response_model=VMMetricsResponse)
def get_vm_metrics() -> VMMetricsResponse:
    """Return resource metrics for all cluster VMs.

    VMs are queried in parallel — worst-case response time is bounded by
    the single slowest/most-unreachable node (SSH timeout), not their sum.
    Response order matches the order defined in vm-config.yaml.
    """
    vm_cfg = config.load_vm_config()
    vms_to_query = [
        (vm["name"], vm.get("planned_ip", ""))
        for vm in vm_cfg.get("vms", [])
        if vm.get("planned_ip")
    ]

    if not vms_to_query:
        return VMMetricsResponse(
            vms=[],
            collected_at=datetime.now(tz=timezone.utc).isoformat(),
        )

    # Record insertion order so we can sort results back into it regardless
    # of which SSH call finishes first.
    order = {name: i for i, (name, _) in enumerate(vms_to_query)}
    results: list[VMMetrics] = []

    with ThreadPoolExecutor(max_workers=len(vms_to_query)) as pool:
        futures = {
            pool.submit(_collect_one, name, ip): name
            for name, ip in vms_to_query
        }
        for future in as_completed(futures):
            results.append(future.result())

    results.sort(key=lambda m: order.get(m.name, 99))

    return VMMetricsResponse(
        vms=results,
        collected_at=datetime.now(tz=timezone.utc).isoformat(),
    )
