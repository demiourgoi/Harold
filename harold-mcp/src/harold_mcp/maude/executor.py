"""Client-side access to the Maude worker: the executor.

Runs in the MCP server process. Never imports the `maude` SWIG bindings — each
call gets its own interpreter process through `harold_mcp.maude.runner`, and
`harold_mcp.maude.transport` hosts the child side.

The error vocabulary lives in `harold_mcp.maude.worker_errors` and is re-exported
from `harold_mcp.maude`.
"""

import threading
import time
from collections.abc import Callable, Mapping
from concurrent.futures import CancelledError, ThreadPoolExecutor
from typing import Any, cast

from fastmcp.dependencies import Depends

from harold_mcp.logging import Logging
from harold_mcp.maude.runner import PipeProcessRunner, ProcessRunner
from harold_mcp.maude.session import SessionRequest, SessionResult
from harold_mcp.maude.worker import LoadDiagnosticsResult
from harold_mcp.maude.worker_errors import (
    MaudeInitError,
    MaudeWorkerCancelledError,
    MaudeWorkerCrashedError,
    MaudeWorkerError,
    MaudeWorkerTimeoutError,
)
from harold_mcp.settings import Settings, get_settings

_NO_SLOT_REASON = "Maude worker timed out waiting for an interpreter slot"

RunnerFactory = Callable[[], ProcessRunner]


class MaudeExecutor(Logging):
    """Client for per-call Maude interpreter processes, with admission control.

    Every operation gets a dedicated `spawn` process through a `ProcessRunner`
    (`PipeProcessRunner` in production): the interpreter is fresh per call, so no
    state survives, and a crash, timeout or initialization failure affects only the
    call that owns the process. A `BoundedSemaphore(maude_workers)` admits at most
    that many concurrent interpreters; waiting for a slot counts against the call's
    timeout.

    The runner is created lazily by the first call (or by `start`) and replaced by a
    fresh one on `start`, so `shutdown` followed by `start` works. `_runner_lock`
    guards only that reference; calls themselves run concurrently up to the
    semaphore's limit.
    """

    _settings: Settings
    _runner_factory: RunnerFactory
    _runner: ProcessRunner | None
    _runner_lock: threading.Lock
    _semaphore: threading.BoundedSemaphore
    _closed: threading.Event

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        runner_factory: RunnerFactory | None = None,
    ) -> None:
        self._settings = settings if settings is not None else Settings()
        self._runner_factory = runner_factory or self._default_runner
        self._runner = None
        self._runner_lock = threading.Lock()
        self._semaphore = threading.BoundedSemaphore(self._settings.maude_workers)
        self._closed = threading.Event()

    def _default_runner(self) -> ProcessRunner:
        self._log.info(
            "Creating Maude process runner for %s concurrent interpreter(s)",
            self._settings.maude_workers,
        )
        return PipeProcessRunner(self._settings)

    def _ensure_runner(self) -> ProcessRunner:
        """Return the current runner, creating it on first use (thread-safe)."""
        with self._runner_lock:
            if self._runner is None:
                self._runner = self._runner_factory()
            return self._runner

    def start(self, timeout: float) -> None:
        """Create a fresh runner and verify every interpreter can initialize Maude.

        Runs `maude_workers` `ping` operations in parallel under one deadline (the
        caller passes the diagnostics timeout). Any failure kills the runner's
        processes, discards it and raises `MaudeInitError` chaining the first
        failure. With per-call processes this is a fail-fast initialization check,
        not a warm-up. `start` is lifecycle-only: do not call it while calls are in
        flight.
        """
        with self._runner_lock:
            previous = self._runner
            runner = self._runner_factory()
            self._runner = runner
            self._closed.clear()
        if previous is not None:
            self._log.info("Stopping the previous Maude process runner")
            previous.kill_all()

        deadline = time.monotonic() + timeout

        def ping() -> None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                # Do not spawn a doomed child when an earlier ping exhausted the budget.
                raise MaudeWorkerTimeoutError(context={"phase": "init"})
            _ = runner.run("ping", None, remaining, {"phase": "init"})

        self._log.info("Pinging Maude workers...")
        with ThreadPoolExecutor(
            max_workers=self._settings.maude_workers,
            thread_name_prefix="maude-init",
        ) as pool:
            futures = [pool.submit(ping) for _ in range(self._settings.maude_workers)]
        failures = [exc for future in futures if (exc := future.exception()) is not None]
        if failures:
            first = failures[0]
            with self._runner_lock:
                if self._runner is runner:
                    self._runner = None
            runner.kill_all()
            if isinstance(first, MaudeWorkerError):
                context: dict[str, object] = {"phase": "init", **first.context}
                remote_traceback = first.remote_traceback
            else:
                context = {"phase": "init"}
                remote_traceback = None
            raise MaudeInitError(context=context, remote_traceback=remote_traceback) from first
        self._log.info("Maude workers are ready")

    def shutdown(self) -> None:
        """Stop admitting calls and kill every active child (idempotent)."""
        self._log.info("Shutting down the Maude process runner")
        self._closed.set()
        with self._runner_lock:
            runner = self._runner
        if runner is not None:
            runner.kill_all()

    def _run_operation(
        self,
        operation: str,
        payload: Any,
        timeout: float,
        context: Mapping[str, object],
    ) -> Any:
        """Admit, run and release one operation within a whole-call deadline.

        Admission waits at most the remaining budget. A call that is still waiting
        (or starts after `shutdown`) is cancelled; a crash observed while the
        executor is closed is reported as a cancellation, because shutdown is its
        most likely cause.
        """
        deadline = time.monotonic() + timeout
        if not self._semaphore.acquire(timeout=max(deadline - time.monotonic(), 0.0)):
            raise MaudeWorkerTimeoutError(_NO_SLOT_REASON, context=context)
        try:
            if self._closed.is_set():
                raise MaudeWorkerCancelledError(context=context)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise MaudeWorkerTimeoutError(context=context)
            runner = self._ensure_runner()
            try:
                return runner.run(operation, payload, remaining, context)
            except MaudeWorkerCrashedError as exc:
                if self._closed.is_set():
                    raise MaudeWorkerCancelledError(context=exc.context) from exc
                raise
            except CancelledError as exc:
                raise MaudeWorkerCancelledError(context=context) from exc
        finally:
            self._semaphore.release()

    def diagnostics(self, path: str) -> LoadDiagnosticsResult:
        """Run `load_diagnostics` in a fresh worker, with crash/timeout mapping."""
        return cast(
            LoadDiagnosticsResult,
            self._run_operation(
                "diagnostics",
                {"path": path},
                self._settings.diagnostics_timeout_secs,
                {"path": path},
            ),
        )

    def run_session(self, request: SessionRequest, timeout: float) -> SessionResult:
        """Run a bounded interpreter session in a fresh worker.

        `timeout` is the whole-call budget (admission + spawn + prelude
        initialization + load + steps); the interpreter tool supplies the settings'
        interpreter timeout or its per-call override.
        """
        return cast(
            SessionResult,
            self._run_operation(
                "session",
                request,
                timeout,
                {"path": request["path"], "module": request["module"]},
            ),
        )


_executor: MaudeExecutor | None = None
_EXECUTOR_LOCK = threading.Lock()


def get_maude_executor(settings: Settings = Depends(get_settings)) -> MaudeExecutor:  # noqa: B008 - FastMCP dependency-injection convention
    """Return the process-wide `MaudeExecutor` singleton, created lazily.

    The singleton is initialized once, under a lock. `settings` is injected by
    FastMCP as a nested dependency on `get_settings`; direct callers pass a
    `Settings` instance explicitly.
    """
    global _executor
    if _executor is None:
        with _EXECUTOR_LOCK:
            if _executor is None:
                _executor = MaudeExecutor(settings)
    return _executor
