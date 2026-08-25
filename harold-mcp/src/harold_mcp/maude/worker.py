"""Interpreter side of the Maude worker: runs only in the worker process.

This module is pickled/spawn-imported by the worker process. The `maude` SWIG
bindings are imported **lazily** (inside functions), so importing this module
in the MCP server process never touches them.

Gotcha: the lazy `import maude` below is an absolute import of the
**third-party** `maude` package, not of our `harold_mcp.maude` package. Do not
change it to a relative import.
"""

import os
import re
import tempfile
from typing import TypedDict


class WarningDict(TypedDict):
    """A single parsed Maude warning."""

    line: int | None
    message: str


class LoadDiagnosticsResult(TypedDict):
    """Outcome of loading a program in the worker."""

    ok: bool
    warnings: list[WarningDict]


_maude_initialized = False


class WorkerInitError(RuntimeError):
    """Maude failed to initialize in the worker process.

    The client cannot receive this exception across the process boundary; it
    maps the resulting dead worker to `MaudeInitError`.
    """


def init_maude() -> None:
    """Initialize the Maude interpreter once per worker process.

    Uses `advise=False` to suppress advisories (warnings still print). Raises
    `WorkerInitError` on failure; the client maps the resulting dead worker to
    `MaudeInitError`.
    """
    global _maude_initialized
    if _maude_initialized:
        return
    import maude

    if not maude.init(advise=False):
        raise WorkerInitError()
    _maude_initialized = True


def ping() -> None:
    """No-op task used to warm up workers (the initializer runs before it)."""


_WARNING_RE = re.compile(r"Warning:\s+\S[^:]*,\s+line\s+(\d+)\s*(?:\([^)]*\))?:\s*(.*)")
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def _strip_ansi(text: str) -> str:
    """Remove ANSI CSI escape sequences (Maude colorizes stderr on a TTY)."""
    return _ANSI_ESCAPE_RE.sub("", text)


def _parse_warnings(text: str) -> list[WarningDict]:
    """Parse `Warning:` lines from captured stderr into structured diagnostics.

    ANSI escapes are stripped first: Maude decides at init time whether stderr
    is a TTY and then colorizes its output, so captures can contain CSI
    sequences around `Warning:` and inside messages.
    """
    warnings_out: list[WarningDict] = []
    for line in _strip_ansi(text).splitlines():
        match = _WARNING_RE.match(line)
        if match:
            warnings_out.append({"line": int(match.group(1)), "message": match.group(2)})
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

    with tempfile.TemporaryFile(mode="w+") as capture:
        saved_fd = os.dup(2)
        try:
            _ = os.dup2(capture.fileno(), 2)
            ok = bool(maude.load(path))
        finally:
            _ = os.dup2(saved_fd, 2)
            os.close(saved_fd)
        _ = capture.seek(0)
        captured_text = capture.read()
    return {"ok": ok, "warnings": _parse_warnings(captured_text)}


def _crash() -> None:
    """Test-only: abruptly terminate the worker process (SIGSEGV analogue)."""
    os._exit(1)
