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
import re
import tempfile
import time
from pathlib import Path
from typing import TypedDict


class WarningDict(TypedDict):
    """A single parsed Maude warning.

    `file` is the name Maude printed for the file the warning belongs to — the
    diagnosed file, a file it loaded via `load`/`in`, or `<standard input>` for
    some first-line warnings. The provider uses it to attribute the warning.
    """

    file: str
    line: int | None
    message: str


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


# `(fmod X) :` (space before the colon) is a real Maude spelling; requiring `):`
# used to drop those warnings silently. A message may contain colons, so the
# message group is greedy and last.
_WARNING_RE = re.compile(r'Warning:\s+"?([^",]+)"?,\s+line\s+(\d+)\s*(?:\([^)]*\))?\s*:\s*(.*)')
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def _strip_ansi(text: str) -> str:
    """Remove ANSI CSI escape sequences (Maude colorizes stderr on a TTY)."""
    return _ANSI_ESCAPE_RE.sub("", text)


def _parse_warnings(text: str) -> list[WarningDict]:
    """Parse `Warning:` lines from captured stderr into structured diagnostics.

    ANSI escapes are stripped first: Maude decides at init time whether stderr
    is a TTY and then colorizes its output, so captures can contain CSI
    sequences around `Warning:` and inside messages. The embedded file name is
    kept (`WarningDict.file`) so the provider can attribute warnings Maude
    raised about other files (dependencies) instead of pinning them on the
    diagnosed file.
    """
    warnings_out: list[WarningDict] = []
    for line in _strip_ansi(text).splitlines():
        match = _WARNING_RE.match(line)
        if match:
            warnings_out.append({"file": match.group(1), "line": int(match.group(2)), "message": match.group(3)})
        # Unmatched lines are ignored for v1; hardening is a final-testing item.
    return warnings_out


def load_diagnostics(path: str) -> LoadDiagnosticsResult:
    """Load `path` in the interpreter, capturing Maude's stderr output.

    Maude writes its `Warning:` lines to fd 2 directly from C++, so fd 2 is
    redirected to a temp file around `maude.load` (a regular file, not a pipe:
    no pipe-buffer blocking, and the worker is single-threaded). Nothing may
    be logged or printed while fd 2 is redirected.
    """
    # Lazy import: this module is also imported by the server process (for the
    # function references the pool pickles), and loading the SWIG bindings there
    # would break the "interpreter only lives in the worker" invariant (R17).
    import maude

    with tempfile.TemporaryFile(mode="w+b") as capture:
        saved_fd = os.dup(2)
        try:
            _ = os.dup2(capture.fileno(), 2)
            ok = bool(maude.load(path))
        finally:
            _ = os.dup2(saved_fd, 2)
            os.close(saved_fd)
        _ = capture.seek(0)
        captured_bytes = capture.read()
    # Maude writes raw C++ bytes (it may echo the file's contents into
    # warnings); decode lossily so arbitrary input cannot crash the parser.
    captured_text = captured_bytes.decode("utf-8", errors="replace")
    return {"ok": ok, "warnings": _parse_warnings(captured_text)}


def _crash() -> None:
    """Test-only: abruptly terminate the worker process (SIGSEGV analogue)."""
    os._exit(1)
