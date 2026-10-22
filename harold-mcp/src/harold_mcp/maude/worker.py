"""Interpreter side of the Maude worker: runs only in the worker process.

This module is pickled/spawn-imported by the worker process. The `maude` SWIG
bindings are imported **lazily** (inside functions), so importing this module
in the MCP server process never touches them.

Gotcha: the lazy `import maude` below is an absolute import of the
**third-party** `maude` package, not of our `harold_mcp.maude` package. Do not
change it to a relative import.

No thread locking is required because the worker process only runs a single thread.
"""

import os
import time
from pathlib import Path
from typing import TypedDict

from harold_mcp.maude.capture import WarningDict, capture_streams, parse_warnings


class LoadDiagnosticsResult(TypedDict):
    """Outcome of loading a program in the worker."""

    ok: bool
    warnings: list[WarningDict]


class WorkerInitError(RuntimeError):
    """Maude failed to initialize in the worker process.

    The client cannot receive this exception across the process boundary; it
    maps the resulting dead worker to `MaudeInitError`.
    """


_maude_initialized = False


def init_maude() -> None:
    """Initialize the Maude interpreter once per worker process.

    Uses `loadPrelude=True` (the default, stated explicitly) so the full
    prelude is available, and `advise=False` to suppress advisories (warnings
    still print). Raises `WorkerInitError` on failure; the client maps the
    resulting dead worker to `MaudeInitError`.
    """
    global _maude_initialized
    if _maude_initialized:
        return
    import maude

    if not maude.init(loadPrelude=True, advise=False):
        raise WorkerInitError()
    # Disable IO from Maude
    maude.setAllowDir(False)
    maude.setAllowFiles(False)
    maude.setAllowProcesses(False)
    _maude_initialized = True


def ping() -> None:
    """No-op task used to warm up workers (the initializer runs before it)."""


def sleep(seconds: float) -> int:
    """Test/timeout support: sleep and return the worker's pid.

    Slow enough to keep a worker busy, which forces the executor to spawn
    additional workers (it only spawns when no worker is idle).
    """
    time.sleep(seconds)
    return os.getpid()


def rendezvous_pid(directory: str, timeout: float = 30.0) -> int:
    """Test support: wait for a peer task to signal the same directory, then report the pid.

    Each task creates its own marker file (`<pid>.rendezvous`) and polls until a
    peer's marker appears, so a task can only complete once another task is running
    concurrently (possibly on a different process). A pool that serializes the tasks
    makes the first one time out and raise. This is schedule-independent, unlike
    wall-clock or interval-overlap budgets (each task pays spawn + init in its own
    process, see `max_tasks_per_child=1`).
    """
    marker_dir = Path(directory)
    marker = marker_dir / f"{os.getpid()}.rendezvous"
    marker.touch()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if any(peer != marker for peer in marker_dir.glob("*.rendezvous")):
            return os.getpid()
        time.sleep(0.02)
    raise TimeoutError(f"no peer task arrived in {directory!r} within {timeout}s")  # noqa: TRY003 - test support


def load_diagnostics(path: str) -> LoadDiagnosticsResult:
    """Load `path` in the interpreter, capturing Maude's stdout and stderr.

    Maude writes its `Warning:` lines to fd 2 and the output of commands
    embedded in the loaded file (for example a top-level `red`) to fd 1,
    directly from C++. Both fds are redirected to temp files around
    `maude.load` (regular files, not pipes: no pipe-buffer blocking, and the
    worker is single-threaded). The stderr capture is parsed for warnings; the
    stdout capture is discarded, which keeps that output away from the server's
    MCP stdio transport. Nothing may be logged or printed while both fds are
    redirected.
    """
    # Lazy import: this module is also imported by the server process (for the
    # function references the pool pickles), and loading the SWIG bindings there
    # would break the "interpreter only lives in the worker" invariant (R17).
    import maude

    ok, captured = capture_streams(lambda: bool(maude.load(path)))
    return {"ok": ok, "warnings": parse_warnings(captured["stderr"])}


def _crash() -> None:
    """Test-only: abruptly terminate the worker process (SIGSEGV analogue)."""
    os._exit(1)
