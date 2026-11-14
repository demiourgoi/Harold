"""Interpreter side of the Maude worker: runs only in the child process.

This module is imported by the spawned child (`transport.serve_one` dispatches to
it). The `maude` SWIG bindings are imported **lazily** (inside functions), so
importing this module in the MCP server process never touches them.

Gotcha: the lazy `import maude` below is an absolute import of the
**third-party** `maude` package, not of our `harold_mcp.maude` package. Do not
change it to a relative import.

No thread locking is required because the child process only runs a single thread.
"""

from typing import TypedDict

from harold_mcp.maude.capture import WarningDict, capture_streams, parse_warnings


class LoadDiagnosticsResult(TypedDict):
    """Outcome of loading a program in the worker."""

    ok: bool
    warnings: list[WarningDict]


class WorkerInitError(RuntimeError):
    """Maude failed to initialize in the worker process.

    The parent cannot receive this exception directly; the transport maps it to an
    `init` error envelope, and the runner raises `MaudeInitError`.
    """


_maude_initialized = False


def init_maude() -> None:
    """Initialize the Maude interpreter once per child process.

    Uses `loadPrelude=True` (the default, stated explicitly) so the full
    prelude is available, and `advise=False` to suppress advisories (warnings
    still print). Raises `WorkerInitError` on failure; the transport reports it
    as an `init` error and the runner maps it to `MaudeInitError`.
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


def load_diagnostics(path: str) -> LoadDiagnosticsResult:
    """Load `path` in the interpreter, capturing Maude's stdout and stderr.

    Maude writes its `Warning:` lines to fd 2 and the output of commands
    embedded in the loaded file (for example a top-level `red`) to fd 1,
    directly from C++. Both fds are redirected to temp files around
    `maude.load` (regular files, not pipes: no pipe-buffer blocking, and the
    child is single-threaded). The stderr capture is parsed for warnings; the
    stdout capture is discarded, which keeps that output away from the server's
    MCP stdio transport. Nothing may be logged or printed while both fds are
    redirected.
    """
    # Lazy import: this module is also imported by the server process (the transport
    # dispatches to it in the child), and loading the SWIG bindings there would break
    # the "interpreter only lives in the child" invariant.
    import maude

    ok, captured = capture_streams(lambda: bool(maude.load(path)))
    return {"ok": ok, "warnings": parse_warnings(captured["stderr"])}
