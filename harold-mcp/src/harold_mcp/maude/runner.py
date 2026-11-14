"""Per-call child process runner: spawn, one-shot exchange, deadline and cleanup.

Runs in the MCP server process. Stdlib-only and free of `maude` imports: the
runner owns process creation and the active-process registry behind the small
`ProcessRunner` seam, so the executor does not depend on `multiprocessing`
details and its unit tests can inject a fake context.

Each call gets one dedicated `spawn` process, one request and one response over
a `multiprocessing` Pipe. Nothing is reused across calls; a crash or timeout
kills only the child that owns the call.
"""

import contextlib
import json
import logging
import multiprocessing
import threading
import time
from collections.abc import Callable, Mapping
from multiprocessing.connection import Connection
from multiprocessing.process import BaseProcess
from typing import Any, NoReturn, Protocol, cast

from harold_mcp.maude.transport import serve_one
from harold_mcp.maude.worker_errors import (
    MaudeInitError,
    MaudeWorkerCancelledError,
    MaudeWorkerCrashedError,
    MaudeWorkerProtocolError,
    MaudeWorkerRemoteError,
    MaudeWorkerSpawnError,
    MaudeWorkerTimeoutError,
)
from harold_mcp.settings import Settings

_JOIN_TIMEOUT_SECS = 5.0
_log = logging.getLogger(__name__)


class ProcessRunner(Protocol):
    """The executor's seam over process creation and the one-shot exchange."""

    # `T` appears only in the return type: the caller knows the expected result type.
    def run[T](self, operation: str, payload: Any, timeout: float, context: Mapping[str, object]) -> T:  # type: ignore[type-var]
        """Run one operation in a fresh child and return its result."""
        ...

    def kill_all(self) -> None:
        """Reject new runs and kill/reap every active child."""
        ...

    def active_count(self) -> int:
        """Number of children currently registered as active (for tests and logs)."""
        ...


def _terminate(proc: BaseProcess) -> None:
    """Kill and reap a child, tolerating a process object that is already closed.

    `ProcessLookupError` is tolerated too: `kill_all()` and a call's own `finally`
    can terminate the same child, and the loser's `kill()` finds no process. A raw
    error here would replace the typed error the call is already raising.
    """
    with contextlib.suppress(ValueError, ProcessLookupError):
        if proc.is_alive():
            proc.kill()
    try:
        proc.join(_JOIN_TIMEOUT_SECS)
    except ValueError:
        return  # already closed
    if proc.is_alive():  # pragma: no cover - kill() on a live child is reliable on Linux
        _log.warning("Maude worker process %s did not exit after kill", proc.pid)
        return
    with contextlib.suppress(ValueError):
        proc.close()


def _encode_request(operation: str, payload: Any) -> bytes:
    """Serialize the one-shot request envelope (no version field by design)."""
    return json.dumps({"operation": operation, "payload": payload}, ensure_ascii=False).encode("utf-8")


def _spawn_reason(exc: BaseException) -> str:
    """Render a process-creation failure for `MaudeWorkerSpawnError`."""
    return f"failed to start the Maude worker: {type(exc).__name__}: {exc}"


def _fail_protocol(
    message: str,
    *,
    context: Mapping[str, object],
    remote_traceback: str | None = None,
    cause: BaseException | None = None,
) -> NoReturn:
    """Raise a protocol error (keeps long messages out of raise statements)."""
    raise MaudeWorkerProtocolError(message, context=context, remote_traceback=remote_traceback) from cause


class PipeProcessRunner:
    """One dedicated `spawn` process per call, over a one-shot `multiprocessing.Pipe`.

    The runner is thread-safe: one lock guards the active map and the closed flag,
    and every call owns its pipe and process. `kill_all()` is idempotent; after it,
    a call that registers its child is killed before it can run and raises
    `MaudeWorkerCancelledError`.

    `target` is the integration-test seam (production uses `transport.serve_one`);
    `context` is the unit-test seam for a fake `multiprocessing` context.
    """

    _settings: Settings
    _target: Callable[[Connection], None]
    _context: Any
    _lock: threading.Lock
    _terminate_lock: threading.Lock
    _closed: threading.Event
    _active: dict[int | None, tuple[BaseProcess, Connection]]

    def __init__(
        self,
        settings: Settings,
        *,
        target: Callable[[Connection], None] = serve_one,
        context: Any | None = None,
    ) -> None:
        self._settings = settings
        self._target = target
        self._context = context if context is not None else multiprocessing.get_context("spawn")
        self._lock = threading.Lock()
        # kill_all() and a call's own finally can reap the same child; serializing the
        # pipe close and the kill/join/close sequence keeps Connection.close() and
        # Process.close() from racing themselves.
        self._terminate_lock = threading.Lock()
        self._closed = threading.Event()
        self._active = {}

    def _spawn(self, context: Mapping[str, object]) -> tuple[BaseProcess, Connection]:
        """Create the pipe and start the child; map creation failures to a spawn error."""
        try:
            parent, child = self._context.Pipe()
        except OSError as exc:
            raise MaudeWorkerSpawnError(_spawn_reason(exc), context={**context, "pid": None}) from exc
        try:
            proc: BaseProcess = self._context.Process(target=self._target, args=(child,), daemon=True)
            proc.start()
        except (OSError, RuntimeError) as exc:
            parent.close()
            child.close()
            raise MaudeWorkerSpawnError(_spawn_reason(exc), context={**context, "pid": None}) from exc
        child.close()
        return proc, parent

    # `T` appears only in the return type: the caller knows the expected result type.
    def run[T](self, operation: str, payload: Any, timeout: float, context: Mapping[str, object]) -> T:  # type: ignore[type-var]
        """Run one operation in a fresh child, bounded by `timeout` seconds.

        `timeout` is the whole exchange budget from spawn to response; the caller
        (the executor) has already subtracted its admission wait.
        """
        deadline = time.monotonic() + timeout
        request = _encode_request(operation, payload)
        proc, parent = self._spawn(context)
        try:
            with self._lock:
                cancelled = self._closed.is_set()
                if not cancelled:
                    self._active[proc.pid] = (proc, parent)
            if cancelled:
                # Registration raced with kill_all(): the closed flag was set before
                # this child was registered, so kill it instead of letting it run.
                raise MaudeWorkerCancelledError(context={**context, "pid": proc.pid})
            try:
                parent.send_bytes(request)
            except OSError as exc:
                raise MaudeWorkerCrashedError(context={**context, "pid": proc.pid}) from exc
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise MaudeWorkerTimeoutError(context={**context, "pid": proc.pid})
            try:
                ready = parent.poll(remaining)
            except OSError as exc:
                # kill_all() can close the pipe between the send and the poll.
                raise MaudeWorkerCrashedError(context={**context, "pid": proc.pid}) from exc
            if not ready:
                raise MaudeWorkerTimeoutError(context={**context, "pid": proc.pid})
            raw = self._receive(parent, context, proc.pid)
            return cast(T, self._decode_response(raw, context, proc.pid))
        finally:
            with self._lock:
                _ = self._active.pop(proc.pid, None)
            self._reap(proc, parent)

    def _reap(self, proc: BaseProcess, parent: Connection) -> None:
        """Close the pipe, then kill and reap the child; serialized per runner.

        `kill_all()` and a call's own `finally` can reap the same child; neither
        `Connection.close()` nor `Process.close()` is safe to call concurrently, so
        both the pipe close and the process teardown happen under one lock.
        """
        with self._terminate_lock:
            parent.close()
            _terminate(proc)

    def _receive(self, parent: Connection, context: Mapping[str, object], pid: int | None) -> bytes:
        """Read the response bytes, mapping EOF and the size cap to typed errors."""
        try:
            return parent.recv_bytes(maxlength=self._settings.ipc_max_response_bytes)
        except EOFError as exc:
            raise MaudeWorkerCrashedError(context={**context, "pid": pid}) from exc
        except OSError as exc:
            if "bad message length" in str(exc):
                _fail_protocol(
                    "invalid worker response: it exceeds HAROLD_IPC_MAX_RESPONSE_BYTES "
                    f"({self._settings.ipc_max_response_bytes} bytes); reduce the result "
                    '(for example lower HAROLD_INTERPRETER_MAX_SOLUTIONS or use path="labels") '
                    "or raise the cap",
                    context={**context, "pid": pid},
                    cause=exc,
                )
            # Includes "got end of file during message": the child died mid-response.
            raise MaudeWorkerCrashedError(context={**context, "pid": pid}) from exc

    def _decode_response(self, raw: bytes, context: Mapping[str, object], pid: int | None) -> Any:
        """Validate the response envelope and map its error category to an exception."""
        error_context = {**context, "pid": pid}
        try:
            envelope = json.loads(raw)
        except ValueError as exc:
            _fail_protocol(f"invalid worker response: {exc}", context=error_context, cause=exc)
        if not isinstance(envelope, dict):
            _fail_protocol("invalid worker response: envelope must be a JSON object", context=error_context)
        status = envelope.get("status")
        if status == "ok":
            if "result" not in envelope:
                _fail_protocol("invalid worker response: missing result", context=error_context)
            return envelope.get("result")
        if status != "error":
            _fail_protocol(f"invalid worker response: unknown status {status!r}", context=error_context)
        error = envelope.get("error")
        if not isinstance(error, dict):
            _fail_protocol("invalid worker response: missing error object", context=error_context)
        self._raise_worker_error(error, context=context, pid=pid)

    def _raise_worker_error(
        self,
        error: dict[str, Any],
        *,
        context: Mapping[str, object],
        pid: int | None,
    ) -> NoReturn:
        """Raise the typed exception for a child error envelope."""
        category = error.get("category")
        message = error.get("message")
        traceback_text = error.get("traceback")
        worker_context = error.get("context")
        merged = {**(worker_context if isinstance(worker_context, dict) else {}), **context, "pid": pid}
        remote_traceback = traceback_text if isinstance(traceback_text, str) else None
        if category == "init":
            if isinstance(message, str) and message:
                raise MaudeInitError(message, context=merged, remote_traceback=remote_traceback)
            raise MaudeInitError(context=merged, remote_traceback=remote_traceback)
        if category == "remote":
            remote_type = error.get("type")
            if not isinstance(remote_type, str) or not isinstance(message, str):
                _fail_protocol("invalid worker response: remote error without a type or message", context=merged)
            raise MaudeWorkerRemoteError(remote_type, message, context=merged, remote_traceback=remote_traceback)
        if category == "protocol":
            reason = message if isinstance(message, str) and message else "invalid worker response"
            raise MaudeWorkerProtocolError(reason, context=merged, remote_traceback=remote_traceback)
        _fail_protocol(f"invalid worker response: unknown error category {category!r}", context=merged)

    def kill_all(self) -> None:
        """Set the closed flag, then kill and reap every active child (idempotent).

        The flag is set and the map snapshotted under the lock, so a call that
        registers its child after the snapshot sees `_closed` in its own
        post-registration check and kills that child itself.
        """
        with self._lock:
            self._closed.set()
            active = list(self._active.values())
        for proc, parent in active:
            self._reap(proc, parent)
        with self._lock:
            self._active.clear()

    def active_count(self) -> int:
        """Number of active children (0 after every completed or failed call)."""
        with self._lock:
            return len(self._active)
