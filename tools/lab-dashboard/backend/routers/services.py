"""
routers/services.py — VMware Windows host service status monitor.

Queries the status of Windows services listed in config.yaml using
PowerShell's Get-Service. Read-only — no start/stop actions here.

Design notes:
- Service list is driven entirely by config.yaml (vmware_services section).
  Add or remove services to monitor without touching this file.
- Uses executor.run_sync (short timeout, synchronous) — this is a quick
  status query, not a long-running operation.
- PowerShell ConvertTo-Json returns a single object (not an array) when
  the query matches exactly one service; we normalise that here.
- If a service name doesn't exist on this machine, Get-Service raises a
  non-terminating error that -ErrorAction SilentlyContinue suppresses;
  the loop then records status='not_found' for that entry.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter
from pydantic import BaseModel

from backend import config, executor

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/services", tags=["services"])


class ServiceInfo(BaseModel):
    name: str
    display_name: str
    status: str       # e.g. "running", "stopped", "paused", "not_found", "unknown"
    start_type: str   # e.g. "automatic", "manual", "disabled"


class ServiceStatusResponse(BaseModel):
    services: list[ServiceInfo]


def _build_ps_command(service_names: list[str]) -> str:
    """Build a PowerShell one-liner that queries each service and returns JSON.

    Handles missing services gracefully via -ErrorAction SilentlyContinue.
    ConvertTo-Json is given -InputObject on the collected array to guarantee
    array output even when only one service is returned (PS5.1 quirk).
    """
    names_ps = ", ".join(f"'{n}'" for n in service_names)
    return (
        f"$out = @();"
        f"foreach ($n in @({names_ps})) {{"
        f"$s = Get-Service -Name $n -ErrorAction SilentlyContinue;"
        f"if ($s) {{"
        f"$out += [PSCustomObject]@{{name=$s.Name; status=$s.Status.ToString(); startType=$s.StartType.ToString()}}"
        f"}} else {{"
        f"$out += [PSCustomObject]@{{name=$n; status='not_found'; startType='unknown'}}"
        f"}}}};"
        f"ConvertTo-Json -InputObject $out -Compress"
    )


@router.get("", response_model=ServiceStatusResponse)
def get_service_status() -> ServiceStatusResponse:
    """Return current status for all Windows services listed in config.yaml."""
    services_cfg = config.vmware_services

    if not services_cfg:
        return ServiceStatusResponse(services=[])

    display_names = {
        svc["name"]: svc.get("display_name", svc["name"])
        for svc in services_cfg
    }

    ps_cmd = _build_ps_command(list(display_names.keys()))
    rc, output = executor.run_sync(
        ["powershell.exe", "-NonInteractive", "-Command", ps_cmd],
        timeout=10,
    )

    if rc != 0:
        _log.warning("Get-Service query failed (rc=%d): %s", rc, output.strip())
        return _all_unknown(services_cfg)

    try:
        raw = json.loads(output.strip())
        # PS5.1 quirk: single-item result is a dict, not a list.
        if isinstance(raw, dict):
            raw = [raw]
        services = [
            ServiceInfo(
                name=item["name"],
                display_name=display_names.get(item["name"], item["name"]),
                status=item["status"].lower(),
                start_type=item["startType"].lower(),
            )
            for item in raw
        ]
    except (json.JSONDecodeError, KeyError) as exc:
        _log.warning("Failed to parse Get-Service output: %s | output: %s", exc, output.strip())
        return _all_unknown(services_cfg)

    return ServiceStatusResponse(services=services)


def _all_unknown(services_cfg: list[dict]) -> ServiceStatusResponse:
    """Return every service as 'unknown' — used when the query fails entirely."""
    return ServiceStatusResponse(services=[
        ServiceInfo(
            name=svc["name"],
            display_name=svc.get("display_name", svc["name"]),
            status="unknown",
            start_type="unknown",
        )
        for svc in services_cfg
    ])
