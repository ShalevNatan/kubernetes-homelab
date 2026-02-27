"""
routers/vms.py — VM status and power control endpoints.

VM state is determined by querying vmrun.exe and checking the filesystem:
  - "not_provisioned": VMX file does not exist on disk
  - "stopped":         VMX file exists but VM is not in vmrun list
  - "running":         VM appears in vmrun list output

Individual start / stop / restart actions call vmrun directly (not via the
full provision script — these are runtime power operations, not provisioning).
"""

from __future__ import annotations

import os
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend import config, executor

router = APIRouter(prefix="/api/vms", tags=["vms"])

VMState = Literal["running", "stopped", "not_provisioned"]


class VMStatus(BaseModel):
    name: str
    role: str
    planned_ip: str
    state: VMState
    vmx_path: str


class VMStatusResponse(BaseModel):
    vms: list[VMStatus]
    busy: bool
    current_operation: str | None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_running_vmx_paths() -> set[str]:
    """Return a set of VMX paths that vmrun reports as running."""
    rc, output = executor.run_sync([config.vmware.vmrun_path, "list"])
    if rc != 0:
        # vmrun is not available or not running — treat as empty
        return set()

    lines = output.strip().splitlines()
    # First line is "Total running VMs: N" — skip it
    return {line.strip().lower() for line in lines[1:] if line.strip().endswith(".vmx")}


def _vm_state(vm_name: str, running_paths: set[str]) -> VMState:
    vmx = config.vm_vmx_path(vm_name)
    if not os.path.exists(vmx):
        return "not_provisioned"
    if vmx.lower() in running_paths:
        return "running"
    return "stopped"


# ---------------------------------------------------------------------------
# GET /api/vms — list all VMs with current state
# ---------------------------------------------------------------------------

@router.get("", response_model=VMStatusResponse)
def get_vm_status() -> VMStatusResponse:
    """Return current power state for all cluster VMs.

    VM list is read from vm-config.yaml — never hardcoded here.
    """
    vm_cfg = config.load_vm_config()
    running_paths = _get_running_vmx_paths()

    vms = []
    for vm in vm_cfg.get("vms", []):
        name = vm["name"]
        state = _vm_state(name, running_paths)
        vms.append(VMStatus(
            name=name,
            role=vm.get("role", "unknown"),
            planned_ip=vm.get("planned_ip", ""),
            state=state,
            vmx_path=config.vm_vmx_path(name),
        ))

    return VMStatusResponse(
        vms=vms,
        busy=executor.is_busy(),
        current_operation=executor.current_operation(),
    )


# ---------------------------------------------------------------------------
# POST /api/vms/{name}/start
# ---------------------------------------------------------------------------

@router.post("/{name}/start")
def start_vm(name: str) -> dict:
    """Start a single VM by name (must already be provisioned)."""
    vmx = config.vm_vmx_path(name)
    if not os.path.exists(vmx):
        raise HTTPException(status_code=404, detail=f"VM '{name}' is not provisioned (VMX not found)")

    if executor.is_busy():
        raise HTTPException(status_code=409, detail=f"Another operation is running: {executor.current_operation()}")

    rc, output = executor.run_sync(
        [config.vmware.vmrun_path, "start", vmx, "nogui"],
        timeout=30,
    )
    if rc != 0:
        raise HTTPException(status_code=500, detail=f"vmrun start failed: {output.strip()}")

    return {"status": "ok", "vm": name, "action": "start"}


# ---------------------------------------------------------------------------
# POST /api/vms/{name}/stop
# ---------------------------------------------------------------------------

@router.post("/{name}/stop")
def stop_vm(name: str) -> dict:
    """Gracefully stop a single VM. Falls back to hard stop if soft fails."""
    vmx = config.vm_vmx_path(name)
    if not os.path.exists(vmx):
        raise HTTPException(status_code=404, detail=f"VM '{name}' is not provisioned")

    if executor.is_busy():
        raise HTTPException(status_code=409, detail=f"Another operation is running: {executor.current_operation()}")

    # Try graceful shutdown first
    rc, output = executor.run_sync(
        [config.vmware.vmrun_path, "stop", vmx, "soft"],
        timeout=30,
    )
    if rc != 0:
        # Graceful failed — force it
        rc, output = executor.run_sync(
            [config.vmware.vmrun_path, "stop", vmx, "hard"],
            timeout=15,
        )
        if rc != 0:
            raise HTTPException(status_code=500, detail=f"vmrun stop failed: {output.strip()}")

    return {"status": "ok", "vm": name, "action": "stop"}


# ---------------------------------------------------------------------------
# POST /api/vms/{name}/restart
# ---------------------------------------------------------------------------

@router.post("/{name}/restart")
def restart_vm(name: str) -> dict:
    """Restart a running VM."""
    vmx = config.vm_vmx_path(name)
    if not os.path.exists(vmx):
        raise HTTPException(status_code=404, detail=f"VM '{name}' is not provisioned")

    if executor.is_busy():
        raise HTTPException(status_code=409, detail=f"Another operation is running: {executor.current_operation()}")

    rc, output = executor.run_sync(
        [config.vmware.vmrun_path, "reset", vmx, "soft"],
        timeout=30,
    )
    if rc != 0:
        raise HTTPException(status_code=500, detail=f"vmrun reset failed: {output.strip()}")

    return {"status": "ok", "vm": name, "action": "restart"}
