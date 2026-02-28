"""
routers/provision.py — Provision and deprovision endpoints.

These endpoints trigger the PowerShell scripts via WebSocket-streamed execution.
The client opens a WebSocket connection and receives log lines in real time.

Design notes:
- Provision passes -ConfigFile pointing to a JSON version of vm-config.yaml.
  PowerShell parses JSON natively (ConvertFrom-Json); no extra modules needed.
  The JSON file is derived at call time from the canonical vm-config.yaml.
- Deprovision always passes -Force (the interactive Read-Host prompt blocks
  subprocess execution — the dashboard confirmation dialog replaces it).
- Both operations are rejected if another operation is already running (409).
- On successful completion, both operations reset the playbook run-state to
  "never run": freshly provisioned VMs have no Ansible applied yet, and
  deprovisioned VMs no longer exist — stale pipeline history would be wrong
  in both cases.
"""

from __future__ import annotations

import json
import logging
import traceback
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend import config, executor
from backend.routers.playbooks import reset_run_state

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["provision"])


def _write_provision_json() -> str:
    """Derive vm-config.json from vm-config.yaml and write it to disk.

    PowerShell reads JSON natively via ConvertFrom-Json, so we convert at
    call time rather than requiring a YAML parsing module in the script.
    Returns the path to the written JSON file.
    """
    vm_cfg = config.load_vm_config()
    json_path = config.vm_config_path.with_suffix(".json")
    with json_path.open("w", encoding="utf-8") as fh:
        json.dump(vm_cfg, fh, indent=2)
    return str(json_path)


def _succeeded(last_line: str) -> bool:
    """Return True if the last streamed line signals a clean exit."""
    return last_line.startswith("[EXIT] Process finished successfully")


# ---------------------------------------------------------------------------
# WebSocket: /api/ws/provision
# ---------------------------------------------------------------------------

@router.websocket("/ws/provision")
async def ws_provision(websocket: WebSocket) -> None:
    """Stream provision-vms.ps1 output to the browser in real time.

    Resets playbook run-state on success — newly provisioned VMs start with
    no Ansible configuration applied.
    """
    await websocket.accept()

    if executor.is_busy():
        await websocket.send_text(
            f"[BUSY] Cannot provision: another operation is running: {executor.current_operation()}"
        )
        await websocket.close()
        return

    last_line = ""

    try:
        json_config_path = _write_provision_json()

        cmd = [
            "powershell.exe",
            "-NonInteractive",
            "-ExecutionPolicy", "Bypass",
            "-File", config.provision_script_path(),
            "-ConfigFile", json_config_path,
        ]

        async with executor.acquire_operation("Provision VMs"):
            await websocket.send_text("[START] Provision VMs")
            await websocket.send_text(f"[CMD] {' '.join(cmd)}")

            async for line in executor.stream_subprocess(cmd):
                await websocket.send_text(line)
                last_line = line

    except WebSocketDisconnect:
        # Browser closed mid-run — subprocess continues on the host.
        pass
    except Exception:
        tb = traceback.format_exc()
        _log.error("ws_provision raised:\n%s", tb)
        last_tb_line = tb.strip().splitlines()[-1]
        try:
            await websocket.send_text(f"[ERROR] {last_tb_line}")
        except Exception:
            pass
    finally:
        if _succeeded(last_line):
            reset_run_state()
        try:
            await websocket.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# WebSocket: /api/ws/deprovision
# ---------------------------------------------------------------------------

@router.websocket("/ws/deprovision")
async def ws_deprovision(websocket: WebSocket) -> None:
    """Stream deprovision-vms.ps1 output to the browser in real time.

    Always passes -Force to suppress the interactive confirmation prompt.
    The dashboard UI is responsible for showing a confirmation dialog before
    opening this WebSocket.

    Resets playbook run-state on success — deleted VMs have no Ansible state
    to report.
    """
    await websocket.accept()

    if executor.is_busy():
        await websocket.send_text(
            f"[BUSY] Cannot deprovision: another operation is running: {executor.current_operation()}"
        )
        await websocket.close()
        return

    last_line = ""

    try:
        cmd = [
            "powershell.exe",
            "-NonInteractive",
            "-ExecutionPolicy", "Bypass",
            "-File", config.deprovision_script_path(),
            "-Force",
        ]

        async with executor.acquire_operation("Deprovision VMs"):
            await websocket.send_text("[START] Deprovision VMs")
            await websocket.send_text(f"[CMD] {' '.join(cmd)}")

            async for line in executor.stream_subprocess(cmd):
                await websocket.send_text(line)
                last_line = line

    except WebSocketDisconnect:
        pass
    except Exception:
        tb = traceback.format_exc()
        _log.error("ws_deprovision raised:\n%s", tb)
        last_tb_line = tb.strip().splitlines()[-1]
        try:
            await websocket.send_text(f"[ERROR] {last_tb_line}")
        except Exception:
            pass
    finally:
        if _succeeded(last_line):
            reset_run_state()
        try:
            await websocket.close()
        except Exception:
            pass
