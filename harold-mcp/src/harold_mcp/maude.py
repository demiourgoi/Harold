"""Safe access layer over the SWIG-generated `maude` Python bindings.

The Maude interpreter is not thread-safe, so all access is serialized on a
reentrant lock. Module wrappers are never cached: loading a program may
redefine its modules, so wrappers are always fetched fresh from the
interpreter (see `.agents/planning/sigsegv-under-load/issue.md`).
"""

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from threading import Lock, RLock
from typing import Any

import maude

from harold_mcp.logging import get_logger

_LOG = get_logger(__name__)


class MaudeError(RuntimeError):
    """Base error for failures in the Maude runtime wrapper."""


class MaudeInitError(MaudeError):
    """Raised when the Maude interpreter fails to initialize."""

    def __init__(self) -> None:
        super().__init__("Failed to initialize the Maude interpreter")


class MaudeLoadError(MaudeError):
    """Raised when a Maude program fails to load."""

    def __init__(self, program_path: str) -> None:
        self.program_path = program_path
        super().__init__(f"Failed to load Maude program {program_path!r}")


class MaudeModuleNotFoundError(MaudeError):
    """Raised when a requested module is not loaded."""

    def __init__(self, module_name: str) -> None:
        self.module_name = module_name
        super().__init__(f"Module {module_name!r} not found")


_INIT_LOCK = Lock()
_maude_initialized = False


def init_maude() -> None:
    """Initialize the Maude interpreter exactly once per process.

    Runs with `advise=False` to suppress advisories (e.g. `Advisory:
    redefining module X.`) on stderr. Failures raise `MaudeInitError` and are
    retried on the next call.
    """
    global _maude_initialized
    _LOG.info("Initializing Maude interpreter...")
    if _maude_initialized:
        return
    with _INIT_LOCK:
        if _maude_initialized:
            return
        if not maude.init(advise=False):
            raise MaudeInitError()
        _maude_initialized = True
        _LOG.info("Success initializing Maude interpreter!")


class MaudeRuntime:
    """Thread-safe facade over the `maude` interpreter.

    - All Maude interpreter access is serialized on a reentrant lock (the
      interpreter is not thread-safe).
    - No module wrappers are cached. A wrapper is a cheap handle over the
      interpreter-owned flat module, and loading a program may redefine its
      modules, so wrappers are always fetched fresh.
    - `load_program` loads the file on every call ("last load wins", like the
      Maude CLI), so edits to a `.maude` file are picked up by the next call.
    """

    def __init__(self) -> None:
        self._lock = RLock()

    @contextmanager
    def _maude_locked(self) -> Generator[None]:
        """Serialize Maude interpreter access and ensure it is initialized."""
        with self._lock:
            init_maude()
            yield

    def get_module(self, module_name: str) -> Any:
        """Return a wrapper for a loaded module, or raise if it is not loaded."""
        with self._maude_locked():
            module = maude.getModule(module_name)
            if module is None:
                raise MaudeModuleNotFoundError(module_name)
            return module

    def load_program(self, program_path: str | Path) -> None:
        """Load (or reload) a Maude program file, redefining its modules."""
        path = str(Path(program_path).resolve())
        with self._maude_locked():
            if not maude.load(path):
                raise MaudeLoadError(path)

    def load_module(self, program_path: str | Path, module_name: str) -> Any:
        """(Re)load the program and return a fresh wrapper for the module."""
        self.load_program(program_path)
        return self.get_module(module_name)


_RUNTIME = MaudeRuntime()


def get_runtime() -> MaudeRuntime:
    """Return the process-wide `MaudeRuntime` singleton.

    The singleton exists to share the interpreter lock across tool calls (no
    state is cached).
    """
    return _RUNTIME
