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

Windows asyncio note:
  asyncio.create_subprocess_exec is unreliable on Windows when running inside
  uvicorn's worker (ProactorEventLoop), producing silent failures with no
  traceback. stream_subprocess therefore uses subprocess.Popen executed in the
  default thread pool, posting output lines back to the event loop via an
  asyncio.Queue and loop.call_soon_threadsafe. This is the standard Windows-
  safe pattern for async subprocess streaming.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import traceback
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import AsyncIterator

_log = logging.getLogger(__name__)

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

    Implementation note: subprocess.Popen is run in a thread pool rather than
    using asyncio.create_subprocess_exec, which fails silently on Windows
    inside uvicorn's ProactorEventLoop worker. Lines are posted from the
    worker thread to the event loop via asyncio.Queue + call_soon_threadsafe.
    """
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    def _run_in_thread() -> None:
        """Blocking subprocess reader — runs in the default thread pool.

        Reads stdout line-by-line (stderr merged into stdout) and enqueues
        each decoded line on the asyncio event loop. Posts None as the end-of-
        stream sentinel once the process has exited.
        """
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # merge stderr into stdout
                cwd=cwd,
                env=env,
            )
            assert proc.stdout is not None  # guaranteed when PIPE is set

            for raw_line in proc.stdout:
                line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
                loop.call_soon_threadsafe(queue.put_nowait, line)

            proc.wait()

            if proc.returncode == 0:
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    "[EXIT] Process finished successfully (exit code 0)",
                )
            else:
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    f"[EXIT] Process failed with exit code {proc.returncode}",
                )

        except Exception:
            tb = traceback.format_exc()
            _log.error("stream_subprocess thread raised:\n%s", tb)
            # Surface the last line of the traceback to the browser so the
            # operator sees a meaningful message rather than an empty [ERROR].
            last_tb_line = tb.strip().splitlines()[-1]
            loop.call_soon_threadsafe(
                queue.put_nowait,
                f"[ERROR] Subprocess failed to start: {last_tb_line}",
            )

        finally:
            # None is the end-of-stream sentinel for the async consumer.
            loop.call_soon_threadsafe(queue.put_nowait, None)

    # Run the blocking reader in the default thread pool. We rely on the None
    # sentinel rather than awaiting the returned Future — any exception inside
    # _run_in_thread is caught and enqueued above.
    loop.run_in_executor(None, _run_in_thread)

    while True:
        item = await queue.get()
        if item is None:
            break
        yield item


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

    except Exception:
        tb = traceback.format_exc()
        _log.error("run_powershell raised:\n%s", tb)
        last_tb_line = tb.strip().splitlines()[-1]
        await websocket.send_text(f"[ERROR] Unexpected error: {last_tb_line}")


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
