"""
config.py — Configuration loader for the Lab Control Dashboard.

Loads config.yaml (dashboard settings) and vm-config.yaml (VM specs) at startup.
Both files are read once and cached. The app fails loudly if either file is
missing or malformed — a misconfigured dashboard is worse than no dashboard.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Locate config files
# ---------------------------------------------------------------------------

# config.yaml lives two levels up from this file: tools/lab-dashboard/config.yaml
_DASHBOARD_ROOT = Path(__file__).parent.parent
_CONFIG_PATH = _DASHBOARD_ROOT / "config.yaml"
_VM_CONFIG_PATH: Path | None = None  # resolved after loading config.yaml


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file and return its contents as a dict.

    Raises a clear RuntimeError if the file is missing or unparseable —
    we never swallow configuration errors.
    """
    if not path.exists():
        raise RuntimeError(
            f"Required config file not found: {path}\n"
            f"Copy the example from the repository root and edit it."
        )
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if data is None:
        raise RuntimeError(f"Config file is empty: {path}")
    return data


# ---------------------------------------------------------------------------
# Load and validate config.yaml
# ---------------------------------------------------------------------------

_raw_config: dict[str, Any] = _load_yaml(_CONFIG_PATH)


def _require(d: dict, *keys: str) -> Any:
    """Walk nested dict keys; raise RuntimeError if any key is missing."""
    node = d
    for k in keys:
        if not isinstance(node, dict) or k not in node:
            raise RuntimeError(
                f"config.yaml is missing required key: {'.'.join(keys)}"
            )
        node = node[k]
    return node


# Validate required top-level sections exist
for _section in ("vmware", "ansible", "powershell", "vm_config", "server"):
    _require(_raw_config, _section)


class _VMwareConfig:
    vmrun_path: str = _require(_raw_config, "vmware", "vmrun_path")
    template_vmx: str = _require(_raw_config, "vmware", "template_vmx")
    snapshot_name: str = _require(_raw_config, "vmware", "snapshot_name")
    cluster_dir: str = _require(_raw_config, "vmware", "cluster_dir")


class _AnsibleConfig:
    wsl_distro: str = _require(_raw_config, "ansible", "wsl_distro")
    ansible_dir: str = _require(_raw_config, "ansible", "ansible_dir")
    ansible_dir_wsl: str = _require(_raw_config, "ansible", "ansible_dir_wsl")
    inventory_path: str = _require(_raw_config, "ansible", "inventory_path")


class _PowerShellConfig:
    scripts_dir: str = _require(_raw_config, "powershell", "scripts_dir")
    provision_script: str = _require(_raw_config, "powershell", "provision_script")
    deprovision_script: str = _require(_raw_config, "powershell", "deprovision_script")


class _ServerConfig:
    host: str = _require(_raw_config, "server", "host")
    port: int = _require(_raw_config, "server", "port")


# Resolve vm-config path from config.yaml
_VM_CONFIG_PATH = Path(_require(_raw_config, "vm_config", "path"))


# ---------------------------------------------------------------------------
# Convenience accessors (import these elsewhere)
# ---------------------------------------------------------------------------

vmware = _VMwareConfig()
ansible = _AnsibleConfig()
powershell = _PowerShellConfig()
server = _ServerConfig()
vm_config_path = _VM_CONFIG_PATH


# ---------------------------------------------------------------------------
# VM config loader (called on demand — it can be reloaded at runtime)
# ---------------------------------------------------------------------------

def load_vm_config() -> dict[str, Any]:
    """Load and return vm-config.yaml contents.

    Called by the routers, not at module import time, so it reflects edits
    made via the Config Editor without a server restart.
    """
    return _load_yaml(vm_config_path)


def save_vm_config(data: dict[str, Any]) -> None:
    """Write vm-config.yaml atomically.

    Writes to a .tmp file first, then renames — prevents partial writes from
    corrupting the config if the process is killed mid-write.
    """
    tmp_path = vm_config_path.with_suffix(".yaml.tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        yaml.dump(data, fh, default_flow_style=False, sort_keys=False)
    tmp_path.replace(vm_config_path)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def provision_script_path() -> str:
    return os.path.join(powershell.scripts_dir, powershell.provision_script)


def deprovision_script_path() -> str:
    return os.path.join(powershell.scripts_dir, powershell.deprovision_script)


def vm_vmx_path(vm_name: str) -> str:
    """Return the expected VMX path for a named VM."""
    return os.path.join(vmware.cluster_dir, vm_name, f"{vm_name}.vmx")
