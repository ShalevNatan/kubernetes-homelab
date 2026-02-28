"""
main.py — Lab Control Dashboard entry point.

Run from the tools/lab-dashboard/ directory as administrator:

    python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000

The server must run as administrator because the PowerShell scripts it
invokes require elevated privileges (#Requires -RunAsAdministrator).

Startup validates that config.yaml and vm-config.yaml are present and
parseable — the server refuses to start with a broken configuration rather
than failing later at runtime with a confusing error.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend import config, executor  # config validates config.yaml at import time
from backend.routers import playbooks, provision, services, vm_config, vms

# ---------------------------------------------------------------------------
# Startup validation
# ---------------------------------------------------------------------------

def _validate_environment() -> None:
    """Fail loudly at startup if required files or paths are missing.

    A dashboard that starts successfully but fails at runtime on the first
    operation is worse than one that refuses to start with a clear error.
    """
    errors: list[str] = []

    import os
    if not os.path.exists(config.vmware.vmrun_path):
        errors.append(f"vmrun.exe not found at: {config.vmware.vmrun_path}")

    scripts_dir = Path(config.powershell.scripts_dir)
    if not scripts_dir.exists():
        errors.append(f"PowerShell scripts directory not found: {scripts_dir}")

    ansible_dir = Path(config.ansible.ansible_dir)
    if not ansible_dir.exists():
        errors.append(f"Ansible directory not found: {ansible_dir}")

    if errors:
        print("\n[STARTUP ERROR] Dashboard cannot start — configuration problems found:\n")
        for err in errors:
            print(f"  - {err}")
        print(
            "\nEdit tools/lab-dashboard/config.yaml to fix the paths above.\n"
        )
        sys.exit(1)


_validate_environment()

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Lab Control Dashboard",
    description="Operational control plane for the kubernetes-homelab.",
    version="0.1.0",
    docs_url="/docs",   # Swagger UI available for debugging
    redoc_url=None,
)

# Allow the frontend (same origin) to call the API.
# Restricted to localhost only — this tool is never exposed externally.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000", "http://localhost:8000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(vms.router)
app.include_router(provision.router)
app.include_router(playbooks.router)
app.include_router(vm_config.router)
app.include_router(services.router)

# ---------------------------------------------------------------------------
# Frontend static files
# ---------------------------------------------------------------------------

_FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

app.mount("/static", StaticFiles(directory=str(_FRONTEND_DIR)), name="static")


@app.get("/", include_in_schema=False)
def serve_index() -> FileResponse:
    """Serve the single-page frontend."""
    return FileResponse(str(_FRONTEND_DIR / "index.html"))


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/api/health", tags=["meta"])
def health() -> dict:
    return {
        "status": "ok",
        "busy": executor.is_busy(),
        "current_operation": executor.current_operation(),
    }
