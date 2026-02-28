"""
routers/playbooks.py — Ansible playbook discovery and execution.

Playbooks are discovered by listing *.yml files in the playbooks directory —
never hardcoded. Adding a new playbook to the filesystem makes it appear in
the UI automatically, with no code change or restart required.

Execution state (last run status per playbook) is persisted in a JSON file
alongside the dashboard. This drives the pipeline view.
"""

from __future__ import annotations

import json
import logging
import os
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from backend import config, executor

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/playbooks", tags=["playbooks"])

# ---------------------------------------------------------------------------
# Run-state persistence
# ---------------------------------------------------------------------------

# Stored next to config.yaml in tools/lab-dashboard/
_STATE_FILE = Path(__file__).parent.parent.parent / "run-state.json"

PlaybookResult = Literal["success", "failed", "never"]


def _load_state() -> dict[str, dict]:
    """Load run-state.json, returning an empty dict if it doesn't exist."""
    if not _STATE_FILE.exists():
        return {}
    try:
        with _STATE_FILE.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(state: dict[str, dict]) -> None:
    """Atomically write run-state.json."""
    tmp = _STATE_FILE.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
    tmp.replace(_STATE_FILE)


def _record_result(playbook_name: str, result: PlaybookResult) -> None:
    state = _load_state()
    state[playbook_name] = {
        "result": result,
        "ran_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    _save_state(state)


def reset_run_state() -> None:
    """Clear all playbook run history.

    Called after provision or deprovision completes successfully — freshly
    provisioned (or just-deleted) VMs have no Ansible configuration applied,
    so stale pipeline history must not be shown.
    """
    _save_state({})


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class PlaybookInfo(BaseModel):
    name: str              # filename including .yml extension
    label: str             # human-readable label (filename without extension)
    last_result: PlaybookResult
    last_ran_at: str | None


class PlaybookListResponse(BaseModel):
    playbooks: list[PlaybookInfo]


# ---------------------------------------------------------------------------
# GET /api/playbooks — discover and return all playbooks
# ---------------------------------------------------------------------------

@router.get("", response_model=PlaybookListResponse)
def list_playbooks() -> PlaybookListResponse:
    """Return all .yml files in the playbooks directory, sorted by filename.

    The sort order ensures numbered playbooks (01-..., 02-...) appear in
    their intended execution sequence.
    """
    playbooks_dir = Path(config.ansible.ansible_dir) / "playbooks"

    if not playbooks_dir.exists():
        return PlaybookListResponse(playbooks=[])

    yml_files = sorted(
        f for f in os.listdir(playbooks_dir)
        if f.endswith(".yml") and not f.startswith(".")
    )

    state = _load_state()
    result = []

    for filename in yml_files:
        entry = state.get(filename, {})
        result.append(PlaybookInfo(
            name=filename,
            label=filename.removesuffix(".yml"),
            last_result=entry.get("result", "never"),
            last_ran_at=entry.get("ran_at"),
        ))

    return PlaybookListResponse(playbooks=result)


# ---------------------------------------------------------------------------
# WebSocket: /api/playbooks/ws/run/{playbook_name}
# ---------------------------------------------------------------------------

@router.websocket("/ws/run/{playbook_name}")
async def ws_run_playbook(websocket: WebSocket, playbook_name: str) -> None:
    """Stream ansible-playbook output to the browser in real time.

    The playbook name must match a file in the playbooks directory.
    Execution is rejected if another operation is already running.
    """
    await websocket.accept()

    # Validate the playbook exists before locking the executor
    playbooks_dir = Path(config.ansible.ansible_dir) / "playbooks"
    playbook_path = playbooks_dir / playbook_name

    if not playbook_path.exists() or not playbook_name.endswith(".yml"):
        await websocket.send_text(
            f"[ERROR] Playbook not found or invalid: {playbook_name}"
        )
        await websocket.close()
        return

    if executor.is_busy():
        await websocket.send_text(
            f"[BUSY] Another operation is running: {executor.current_operation()}"
        )
        await websocket.close()
        return

    last_line = ""

    try:
        # cd into the ansible directory before running — this ensures ansible.cfg
        # (which uses relative inventory paths) is picked up correctly.
        inner_cmd = (
            f"cd '{config.ansible.ansible_dir_wsl}' && "
            f"ansible-playbook playbooks/{playbook_name}"
        )
        cmd = [
            "wsl.exe",
            "-d", config.ansible.wsl_distro,
            "--",
            "bash", "-c", inner_cmd,
        ]

        async with executor.acquire_operation(f"Ansible: {playbook_name}"):
            await websocket.send_text(f"[START] Ansible: {playbook_name}")
            await websocket.send_text(
                f"[CMD] wsl -d {config.ansible.wsl_distro} -- bash -c "
                f"\"cd {config.ansible.ansible_dir_wsl} && ansible-playbook playbooks/{playbook_name}\""
            )

            async for line in executor.stream_subprocess(cmd):
                await websocket.send_text(line)
                last_line = line

    except WebSocketDisconnect:
        pass
    except Exception:
        tb = traceback.format_exc()
        _log.error("ws_run_playbook raised:\n%s", tb)
        last_tb_line = tb.strip().splitlines()[-1]
        try:
            await websocket.send_text(f"[ERROR] {last_tb_line}")
        except Exception:
            pass
    finally:
        # Determine result from the sentinel line emitted by stream_subprocess
        if last_line.startswith("[EXIT] Process finished successfully"):
            result = "success"
        else:
            result = "failed"

        _record_result(playbook_name, result)
        try:
            await websocket.close()
        except Exception:
            pass
