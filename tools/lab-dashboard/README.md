# Lab Control Dashboard

A local web-based operational control plane for the kubernetes-homelab.

See [ADR-0011](../../docs/architecture/decisions/0011-lab-control-dashboard.md) for the architectural rationale.

---

## What It Does

- **VM Status Panel** — real-time power state for each cluster VM (running / stopped / not provisioned), with start / stop / restart controls
- **Provision / Deprovision** — triggers the PowerShell scripts with live log streaming to the browser
- **Playbook Runner** — discovers Ansible playbooks from the filesystem (no hardcoded list), runs them individually or as a full pipeline, with live log output
- **Config Editor** — form-based editor for VM specs (CPU, RAM, IP) that writes to `vm-config.yaml`
- **Pipeline View** — visual representation of playbook execution history

---

## Prerequisites

1. **Python 3.11+** installed natively on Windows (not in WSL2)
2. **VMware Workstation Pro** with `vmrun.exe` at the path configured in `config.yaml`
3. **WSL2** with the `Ubuntu` distro and Ansible installed inside it
4. The **dashboard must run as Administrator** — it calls PowerShell scripts that require elevation

---

## Setup

From a **PowerShell terminal running as Administrator**, in the `tools/lab-dashboard/` directory:

```powershell
# 1. Create a virtual environment
python -m venv .venv

# 2. Activate it
.\.venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -r backend\requirements.txt
```

---

## Configuration

Before first run, review **`config.yaml`** in this directory. It controls all paths.

Key settings to verify:
- `vmware.vmrun_path` — path to `vmrun.exe`
- `vmware.template_vmx` — path to the template VM snapshot
- `vmware.cluster_dir` — where cloned VM directories are created
- `ansible.wsl_distro` — WSL2 distro name (run `wsl --list` to confirm)
- `ansible.ansible_dir_wsl` — the ansible directory as seen from inside WSL2

VM hardware specs (CPU, RAM, IPs) live in **`vm-config.yaml`**. Edit via the Config Editor in the UI, or directly in the file.

---

## Running the Dashboard

From a **PowerShell terminal running as Administrator**, in the `tools/lab-dashboard/` directory:

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000` in your browser.

The startup sequence validates that `vmrun.exe` and the scripts directory exist. If either is missing, the server exits with a clear error message rather than starting in a broken state.

---

## Running Scripts Standalone

The dashboard is a layer on top — not a dependency. All scripts remain fully executable without it:

```powershell
# Provision with hardcoded defaults
.\infrastructure\powershell\provision-vms.ps1

# Provision with config from vm-config.yaml (same as dashboard does)
.\infrastructure\powershell\provision-vms.ps1 -ConfigFile ".\tools\lab-dashboard\vm-config.json"

# Deprovision
.\infrastructure\powershell\deprovision-vms.ps1 -Force

# Run an Ansible playbook (from WSL2)
cd /mnt/d/kubernetes-homelab/infrastructure/ansible
ansible-playbook playbooks/01-static-networking.yml
```

---

## Architecture

```
Browser (localhost:8000)
  │
  │ HTTP + WebSocket
  │
FastAPI Backend (Python, runs as Administrator on Windows)
  │
  ├── GET  /api/vms              → vmrun.exe queries
  ├── POST /api/vms/{name}/start │
  ├── POST /api/vms/{name}/stop  │ → vmrun.exe directly
  ├── POST /api/vms/{name}/restart
  │
  ├── WS   /api/ws/provision    → provision-vms.ps1 -ConfigFile ...
  ├── WS   /api/ws/deprovision  → deprovision-vms.ps1 -Force
  │
  ├── GET  /api/playbooks        → os.listdir(playbooks_dir), sorted
  ├── WS   /api/playbooks/ws/run/{name} → wsl.exe -d Ubuntu ansible-playbook
  │
  ├── GET  /api/vm-config        → reads vm-config.yaml
  └── PUT  /api/vm-config        → writes vm-config.yaml atomically
```

**One operation at a time.** A global lock ensures concurrent executions are
rejected with a clear error. This is by design — the lab has a single operator.

---

## File Structure

```
tools/lab-dashboard/
├── config.yaml          ← all paths and environment settings
├── vm-config.yaml       ← VM specs (CPU, RAM, IPs) — source of truth
├── vm-config.json       ← machine-generated from vm-config.yaml at provision time
├── run-state.json       ← playbook last-run results (auto-generated)
├── backend/
│   ├── main.py          ← FastAPI app entry point
│   ├── config.py        ← config loader (fails loudly if broken)
│   ├── executor.py      ← subprocess runner + WebSocket streaming + lock
│   ├── requirements.txt
│   └── routers/
│       ├── vms.py
│       ├── provision.py
│       ├── playbooks.py
│       └── vm_config.py
└── frontend/
    └── index.html       ← single-page UI (htmx + Alpine.js via CDN)
```

---

## Design Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| Framework | FastAPI | Industry-standard for internal tooling APIs; WebSocket support built-in |
| Frontend | htmx + Alpine.js | No build step; CDN delivery; minimal JS for real-time updates |
| Execution | One at a time | Single operator; concurrent operations create ambiguous state |
| Config | `config.yaml` + `vm-config.yaml` | Separate path config from VM specs; both human-editable |
| YAML → JSON | Derived at provision time | PowerShell has native `ConvertFrom-Json`; no extra modules needed |
| Admin | Run entire dashboard as admin | Simplest; one UAC prompt; PowerShell scripts inherit elevation |

Full rationale in [ADR-0011](../../docs/architecture/decisions/0011-lab-control-dashboard.md).
