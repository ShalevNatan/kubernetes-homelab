"""
routers/vm_config.py — Read and write vm-config.yaml via the Config Editor.

GET  /api/vm-config   → returns current VM specs
PUT  /api/vm-config   → validates and writes new VM specs atomically

Validation is intentionally minimal — we trust the operator. We do enforce
types and required fields so that a form submission with missing data doesn't
silently corrupt the config file.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from backend import config

router = APIRouter(prefix="/api/vm-config", tags=["vm-config"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class VMSpec(BaseModel):
    name: str
    cpu: int
    ram_mb: int
    planned_ip: str
    role: str

    @field_validator("cpu")
    @classmethod
    def cpu_positive(cls, v: int) -> int:
        if v < 1 or v > 32:
            raise ValueError("cpu must be between 1 and 32")
        return v

    @field_validator("ram_mb")
    @classmethod
    def ram_reasonable(cls, v: int) -> int:
        if v < 1024 or v > 65536:
            raise ValueError("ram_mb must be between 1024 and 65536")
        return v

    @field_validator("role")
    @classmethod
    def role_valid(cls, v: str) -> str:
        if v not in ("master", "worker"):
            raise ValueError("role must be 'master' or 'worker'")
        return v


class VMConfigResponse(BaseModel):
    vms: list[VMSpec]


class VMConfigUpdateRequest(BaseModel):
    vms: list[VMSpec]


# ---------------------------------------------------------------------------
# GET /api/vm-config
# ---------------------------------------------------------------------------

@router.get("", response_model=VMConfigResponse)
def get_vm_config() -> VMConfigResponse:
    """Return current VM configuration from vm-config.yaml."""
    try:
        data = config.load_vm_config()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return VMConfigResponse(vms=[VMSpec(**vm) for vm in data.get("vms", [])])


# ---------------------------------------------------------------------------
# PUT /api/vm-config
# ---------------------------------------------------------------------------

@router.put("", response_model=VMConfigResponse)
def update_vm_config(body: VMConfigUpdateRequest) -> VMConfigResponse:
    """Write new VM configuration to vm-config.yaml.

    The file is written atomically (temp file + rename).
    Provision scripts will read the new values on their next run.
    """
    if not body.vms:
        raise HTTPException(status_code=400, detail="At least one VM must be defined")

    # Ensure exactly one master exists — kubeadm requires it
    masters = [vm for vm in body.vms if vm.role == "master"]
    if len(masters) != 1:
        raise HTTPException(
            status_code=400,
            detail=f"Exactly one master is required (found {len(masters)})"
        )

    data = {
        "vms": [vm.model_dump() for vm in body.vms]
    }

    try:
        config.save_vm_config(data)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to write vm-config.yaml: {exc}")

    return VMConfigResponse(vms=body.vms)
