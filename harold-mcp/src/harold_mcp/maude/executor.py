"""Client-side access to the Maude worker: errors and executor.

Runs in the MCP server process. Never imports the `maude` SWIG bindings — the
interpreter lives in a dedicated worker process (see `harold_mcp.maude.worker`).
"""

import multiprocessing
import threading
from collections.abc import Callable
from concurrent.futures import Future, ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from typing import Any, TypeVar, cast

from fastmcp.dependencies import Depends

from harold_mcp.logging import Logging
from harold_mcp.maude import session, worker
from harold_mcp.settings import Settings, get_settings


class MaudeError(RuntimeError):
    """Base error for failures in the Maude worker subsystem."""


class MaudeInitError(MaudeError):
    """Maude failed to initialize in the worker process (surfaced at warm-up)."""

    def __init__(self) -> None:
        super().__init__("Failed to initialize the Maude interpreter in the worker process")


class MaudeWorkerError(MaudeError):
    """Base error for failures of a running Maude worker call."""

    reason: str

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class MaudeWorkerCrashedError(MaudeWorkerError):
    """The worker process died during a call; the pool was replaced."""

    def __init__(self) -> None:
        super().__init__("Maude worker crashed")


class MaudeWorkerTimeoutError(MaudeWorkerError):
    """A call timed out; the stuck worker was killed and the pool replaced."""

    def __init__(self) -> None:
        super().__init__("Maude worker timed out")


ExecutorFactory = Callable[[], ProcessPoolExecutor]


T = TypeVar("T")


class MaudeExecutor(Logging):
    """Client for the Maude worker process pool, with crash/timeout recovery.

    Wraps a `ProcessPoolExecutor` (spawn context, `initializer=worker.init_maude`)
    with `max_workers` from `Settings`. Each task runs in a **fresh process**
    (`max_tasks_per_child=1`), so nothing survives across tasks: the interpreter is
    fresh per call and parser state (for example residue left by a top-level `q .`
    in a loaded file) can never leak into a later call. `max_workers` only bounds
    how many fresh interpreters may run concurrently.

    The pool is replaced when a worker dies (`BrokenProcessPool`) or a call
    times out; the failed call itself is never retried (diagnostics is
    idempotent, so the MCP client retries the tool call instead).

    Concurrency: `_executor_lock` only guards the `_executor` reference against
    replacement-vs-submit races. It does **not** serialize task execution:
    `submit` returns immediately, so with `max_workers > 1` several futures run
    in parallel inside the pool.
    """

    _settings: Settings
    _executor_factory: ExecutorFactory
    _executor: ProcessPoolExecutor | None
    _executor_lock: threading.RLock

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        executor_factory: ExecutorFactory | None = None,
    ) -> None:
        self._settings = settings if settings is not None else Settings()
        self._executor_factory = executor_factory or self._default_executor
        self._executor = None
        # Reentrant: `_submit` holds it while calling `_reset_executor`.
        self._executor_lock = threading.RLock()

    def _default_executor(self) -> ProcessPoolExecutor:
        self._log.info(
            "Launching new process pool for %s workers",
            self._settings.maude_workers,
        )
        return ProcessPoolExecutor(
            max_workers=self._settings.maude_workers,
            mp_context=multiprocessing.get_context("spawn"),
            initializer=worker.init_maude,
            # One task per process: every call gets a fresh interpreter, so parser
            # state cannot leak from one diagnosed file into the next.
            max_tasks_per_child=1,
        )

    def _reset_executor(
        self,
        *,
        replace: bool = True,
        failed: ProcessPoolExecutor | None = None,
    ) -> None:
        """Swap the current executor; optionally only if it is still `failed`.

        Kills the old pool's workers after releasing the lock. With
        `failed=None` the swap is unconditional (start/shutdown); with `failed`
        given, concurrent threads reporting the same failure perform exactly
        one swap (the others become no-ops).
        """
        with self._executor_lock:
            if failed is not None and self._executor is not failed:
                # avoid a duplicated replace due to concurrent calls
                return
            old = self._executor
            self._executor = self._executor_factory() if replace else None
        if old is not None:
            self._log.info("Killing old process pool")
            old.kill_workers()
            self._log.info("Old process pool killed")

    def start(self, timeout: float) -> None:
        """Create the pool and verify every worker can initialize Maude.

        Submits one `worker.ping` per worker (forcing spawn + `init_maude` in
        each) and awaits them with `timeout`, supplied by the caller (the
        lifespan passes the diagnostics timeout). Raises `MaudeInitError` on
        failure, discarding the failed pool so a later call can retry lazily.
        With one task per process the pings are recycled right away: this is a
        fail-fast initialization check, not a warm-up.
        """
        self._reset_executor()
        with self._executor_lock:
            if self._executor is None:  # pragma: no cover — replace=True always creates a pool
                return
            executor = self._executor
        try:
            self._log.info("Pinging Maude workers...")
            futures = [executor.submit(worker.ping) for _ in range(self._settings.maude_workers)]
            for future in futures:
                future.result(timeout=timeout)
        except (BrokenProcessPool, TimeoutError) as exc:
            self._reset_executor(replace=False, failed=executor)
            raise MaudeInitError() from exc
        self._log.info("Maude workers are ready")

    def shutdown(self) -> None:
        """Shut down the pool (idempotent)."""
        self._log.info("Shutting down Maude process pool")
        self._reset_executor(replace=False)

    def submit(self, fn: Callable[..., Any], *args: Any) -> Future[Any]:
        """Submit a worker task."""
        return self._submit(fn, *args)[1]

    def _submit(self, fn: Callable[..., Any], *args: Any) -> tuple[ProcessPoolExecutor, Future[Any]]:
        with self._executor_lock:
            if self._executor is None:
                self._executor = self._executor_factory()
            try:
                self._log.debug("Submitting task to Maude worker: %s", fn.__name__)
                return self._executor, self._executor.submit(fn, *args)
            except BrokenProcessPool as exc:
                # The pool is already known broken: replace it and let the MCP
                # client retry — there is no reason to assume a retry would succeed.
                self._log.error("Maude process pool is broken; recovering with a fresh pool")
                self._reset_executor(failed=self._executor)
                raise MaudeWorkerCrashedError() from exc

    def _run_task(self, fn: Callable[..., T], *args: Any, timeout: float) -> T:
        """Run a worker task to completion, mapping crash/timeout failures.

        `timeout` is the whole-call budget and is always chosen by the caller:
        the executor itself is not tied to any tool's timeout setting. Raises
        `MaudeWorkerCrashedError` / `MaudeWorkerTimeoutError`; the pool is
        replaced so the next call works. Other worker exceptions propagate
        unchanged.
        """
        executor, future = self._submit(fn, *args)
        # Reset here too: submit only sees failures at submission time, not a
        # worker that dies mid-task.
        try:
            return cast(T, future.result(timeout=timeout))
        except BrokenProcessPool as exc:
            self._reset_executor(failed=executor)
            raise MaudeWorkerCrashedError() from exc
        except TimeoutError as exc:
            self._reset_executor(failed=executor)
            raise MaudeWorkerTimeoutError() from exc

    def diagnostics(self, path: str) -> worker.LoadDiagnosticsResult:
        """Run `load_diagnostics` in the worker, with crash/timeout mapping."""
        return self._run_task(
            worker.load_diagnostics,
            path,
            timeout=self._settings.diagnostics_timeout_secs,
        )

    def run_session(self, request: session.SessionRequest, timeout: float) -> session.SessionResult:
        """Run a bounded interpreter session in a fresh worker.

        `timeout` is the whole-call budget (spawn + prelude initialization +
        work); the interpreter tool supplies the settings' interpreter timeout
        or its per-call override.
        """
        return self._run_task(session.run_session, request, timeout=timeout)


_executor: MaudeExecutor | None = None
_EXECUTOR_LOCK = threading.Lock()


def get_maude_executor(settings: Settings = Depends(get_settings)) -> MaudeExecutor:  # noqa: B008 - FastMCP dependency-injection convention
    """Return the process-wide `MaudeExecutor` singleton, created lazily.

    The singleton is initialized once, under a lock (like `init_maude`).
    `settings` is injected by FastMCP as a nested dependency on
    `get_settings`; direct callers pass a `Settings` instance explicitly.
    """
    global _executor
    if _executor is None:
        with _EXECUTOR_LOCK:
            if _executor is None:
                _executor = MaudeExecutor(settings)
    return _executor
