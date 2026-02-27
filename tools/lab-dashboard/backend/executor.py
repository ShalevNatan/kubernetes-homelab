"""
executor.py — Subprocess runner with WebSocket log streaming.

Design decisions made here:
- One operation runs at a time. A global asyncio.Lock prevents concurrent
  executions. A second request while one is in flight returns 409.
- stdout and stderr from subprocesses are merged and streamed line-by-line
  over a WebSocket connection to the browser.
- PowerShell is invoked directly (the dashboard runs as administrator).
- Ansible is invoked via wsl.exe with an explicit distro name.
- Errors in the subprocess surface as log lines to the browser — the server
  does not crash, and the operator can see exactly what failed.
"""

from __future__ import annotations

import asyncio
import subprocess
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import AsyncIterator

# ---------------------------------------------------------------------------
# Global execution lock
# ---------------------------------------------------------------------------

_execution_lock = asyncio.Lock()

# Human-readable label of the current operation (for status API)
_current_operation: str | None = None


def is_busy() -> bool:
    return _execution_lock.locked()


def current_operation() -> str | None:
    return _current_operation


@asynccontextmanager
async def acquire_operation(label: str) -> AsyncIterator[None]:
    """Context manager that acquires the global execution lock and sets the
    current operation label. Use this for all long-running subprocess calls
    to guarantee the lock is always released.

    Usage::

        async with executor.acquire_operation("Ansible: 01-networking.yml"):
            async for line in executor.stream_subprocess(cmd):
                await ws.send_text(line)
    """
    global _current_operation
    async with _execution_lock:
        _current_operation = label
        try:
            yield
        finally:
            _current_operation = None


# ---------------------------------------------------------------------------
# Core subprocess streamer
# ---------------------------------------------------------------------------

async def stream_subprocess(
    cmd: list[str],
    *,
    cwd: str | None = None,
    env: dict | None = None,
) -> AsyncGenerator[str, None]:
    """Run *cmd* as a subprocess and yield output lines as they arrive.

    Both stdout and stderr are merged — the operator sees everything in order.
    A final sentinel line reports the exit code.
    """
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,  # merge stderr into stdout
        cwd=cwd,
        env=env,
    )

    assert proc.stdout is not None  # guaranteed when PIPE is set

    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        yield line.decode("utf-8", errors="replace").rstrip("\r\n")

    await proc.wait()

    if proc.returncode == 0:
        yield "[EXIT] Process finished successfully (exit code 0)"
    else:
        yield f"[EXIT] Process failed with exit code {proc.returncode}"


# ---------------------------------------------------------------------------
# PowerShell runner
# ---------------------------------------------------------------------------

async def run_powershell(
    script_path: str,
    args: list[str],
    operation_label: str,
    websocket,
) -> None:
    """Run a PowerShell script and stream output to a WebSocket.

    If another operation is already running, sends a [BUSY] message and returns
    without executing. The caller is responsible for closing the WebSocket.
    """
    if is_busy():
        await websocket.send_text(
            f"[BUSY] Another operation is already running: {current_operation()}"
        )
        return

    cmd = [
        "powershell.exe",
        "-NonInteractive",
        "-ExecutionPolicy", "Bypass",
        "-File", script_path,
    ] + args

    try:
        async with acquire_operation(operation_label):
            await websocket.send_text(f"[START] {operation_label}")
            await websocket.send_text(f"[CMD] {' '.join(cmd)}")

            async for line in stream_subprocess(cmd):
                await websocket.send_text(line)

    except Exception as exc:
        await websocket.send_text(f"[ERROR] Unexpected error: {exc}")


# ---------------------------------------------------------------------------
# Non-streaming subprocess (for status queries — vmrun list, etc.)
# ---------------------------------------------------------------------------

def run_sync(cmd: list[str], timeout: int = 10) -> tuple[int, str]:
    """Run *cmd* synchronously and return (returncode, combined_output).

    Used for quick status queries (vmrun list, vmrun getGuestIPAddress).
    Not for long-running operations — use stream_subprocess + acquire_operation.
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        combined = result.stdout + result.stderr
        return result.returncode, combined
    except subprocess.TimeoutExpired:
        return -1, f"Command timed out after {timeout}s: {' '.join(cmd)}"
    except FileNotFoundError as exc:
        return -1, f"Executable not found: {exc}"
    except Exception as exc:
        return -1, f"Unexpected error running command: {exc}"
