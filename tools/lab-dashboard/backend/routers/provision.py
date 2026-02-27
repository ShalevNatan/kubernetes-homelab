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
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend import config, executor

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


# ---------------------------------------------------------------------------
# WebSocket: /api/ws/provision
# ---------------------------------------------------------------------------

@router.websocket("/ws/provision")
async def ws_provision(websocket: WebSocket) -> None:
    """Stream provision-vms.ps1 output to the browser in real time."""
    await websocket.accept()

    if executor.is_busy():
        await websocket.send_text(
            f"[BUSY] Cannot provision: another operation is running: {executor.current_operation()}"
        )
        await websocket.close()
        return

    try:
        json_config_path = _write_provision_json()

        await executor.run_powershell(
            script_path=config.provision_script_path(),
            args=["-ConfigFile", json_config_path],
            operation_label="Provision VMs",
            websocket=websocket,
        )
    except WebSocketDisconnect:
        # Browser closed mid-run — subprocess continues on the host.
        pass
    except Exception as exc:
        try:
            await websocket.send_text(f"[ERROR] {exc}")
        except Exception:
            pass
    finally:
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
    """
    await websocket.accept()

    if executor.is_busy():
        await websocket.send_text(
            f"[BUSY] Cannot deprovision: another operation is running: {executor.current_operation()}"
        )
        await websocket.close()
        return

    try:
        await executor.run_powershell(
            script_path=config.deprovision_script_path(),
            args=["-Force"],
            operation_label="Deprovision VMs",
            websocket=websocket,
        )
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            await websocket.send_text(f"[ERROR] {exc}")
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
