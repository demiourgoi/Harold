"""Unit tests for `MaudeExecutor` with a fake `ProcessRunner`.

These tests pin the executor's contract: delegation and context, lazy runner
creation, semaphore admission, initialization pings, restart, shutdown mapping
and error propagation. Nothing spawns a process or loads Maude.
"""

import threading
from collections.abc import Mapping
from concurrent.futures import CancelledError
from typing import Any

import pytest

from harold_mcp.maude import (
    MaudeExecutor,
    MaudeInitError,
    MaudeWorkerCancelledError,
    MaudeWorkerCrashedError,
    MaudeWorkerProtocolError,
    MaudeWorkerRemoteError,
    MaudeWorkerSpawnError,
    MaudeWorkerTimeoutError,
    get_maude_executor,
)
from harold_mcp.maude.session import SessionRequest, SessionResult
from harold_mcp.maude.worker import LoadDiagnosticsResult
from harold_mcp.settings import Settings

OK_RESULT: LoadDiagnosticsResult = {"ok": True, "warnings": []}

SESSION_REQUEST: SessionRequest = {
    "path": "/abs/hello.maude",
    "module": "HELLO-WORLD",
    "steps": [],
    "max_solutions": 200,
    "max_result_length": 1_000_000,
    "max_path_steps": 100,
    "max_output_length": 1_000_000,
}

SESSION_RESULT: SessionResult = {
    "load_ok": True,
    "module_found": True,
    "module_type": 0,
    "defined_modules": ["HELLO-WORLD"],
    "warnings": [],
    "load_output": {"stdout": "", "stderr": ""},
    "outcomes": [],
}


class FakeRunner:
    """Scriptable `ProcessRunner` stand-in recording calls and concurrency."""

    def __init__(
        self,
        result: Any = None,
        exc: BaseException | None = None,
        *,
        on_run: Any = None,
    ) -> None:
        self.result = result
        self.exc = exc
        self.on_run = on_run
        self.calls: list[tuple[str, Any, float, dict[str, object]]] = []
        self.kill_count = 0
        self.active = 0
        self.max_active = 0
        self._lock = threading.Lock()

    def run(self, operation: str, payload: Any, timeout: float, context: Mapping[str, object]) -> Any:
        with self._lock:
            self.calls.append((operation, payload, timeout, dict(context)))
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            if self.on_run is not None:
                self.on_run()
            if self.exc is not None:
                raise self.exc
            return self.result
        finally:
            with self._lock:
                self.active -= 1

    def kill_all(self) -> None:
        with self._lock:
            self.kill_count += 1

    def active_count(self) -> int:
        with self._lock:
            return self.active


def make_executor(
    runner: FakeRunner | None = None,
    *,
    settings: Settings | None = None,
    factory: Any = None,
) -> tuple[MaudeExecutor, FakeRunner]:
    runner = runner if runner is not None else FakeRunner(result=OK_RESULT)
    executor = MaudeExecutor(
        settings=settings if settings is not None else Settings(maude_workers=1, diagnostics_timeout_secs=60),
        runner_factory=factory if factory is not None else (lambda: runner),
    )
    return executor, runner


def test_diagnostics_delegates_with_payload_and_context() -> None:
    executor, runner = make_executor()

    assert executor.diagnostics("hello.maude") == OK_RESULT

    operation, payload, timeout, context = runner.calls[0]
    assert operation == "diagnostics"
    assert payload == {"path": "hello.maude"}
    assert 0 < timeout <= 60
    assert context == {"path": "hello.maude"}


def test_diagnostics_uses_the_diagnostics_timeout() -> None:
    executor, runner = make_executor(settings=Settings(maude_workers=1, diagnostics_timeout_secs=42))

    _ = executor.diagnostics("hello.maude")

    assert 0 < runner.calls[0][2] <= 42


def test_run_session_delegates_with_request_timeout_and_context() -> None:
    executor, runner = make_executor(FakeRunner(result=SESSION_RESULT))

    result = executor.run_session(SESSION_REQUEST, timeout=7.5)

    assert result == SESSION_RESULT
    operation, payload, timeout, context = runner.calls[0]
    assert operation == "session"
    assert payload is SESSION_REQUEST
    assert 0 < timeout <= 7.5
    assert context == {"path": SESSION_REQUEST["path"], "module": SESSION_REQUEST["module"]}


def test_runner_is_created_lazily_and_once() -> None:
    runner = FakeRunner(result=OK_RESULT)
    created: list[FakeRunner] = []

    def factory() -> FakeRunner:
        created.append(runner)
        return runner

    executor, _ = make_executor(factory=factory)

    assert created == []
    _ = executor.diagnostics("hello.maude")
    _ = executor.diagnostics("hello.maude")
    assert created == [runner]


@pytest.mark.parametrize(
    "error",
    [
        MaudeWorkerTimeoutError(),
        MaudeWorkerCrashedError(),
        MaudeWorkerSpawnError(),
        MaudeInitError(),
        MaudeWorkerRemoteError("ValueError", "boom"),
        MaudeWorkerProtocolError(),
    ],
)
def test_runner_errors_propagate_unchanged_when_open(error: BaseException) -> None:
    executor, _ = make_executor(FakeRunner(exc=error))

    with pytest.raises(type(error)) as exc_info:
        _ = executor.diagnostics("hello.maude")

    assert exc_info.value is error


def test_stray_cancelled_error_is_mapped_to_cancelled() -> None:
    executor, _ = make_executor(FakeRunner(exc=CancelledError()))

    with pytest.raises(MaudeWorkerCancelledError):
        _ = executor.diagnostics("hello.maude")


def test_crash_while_closed_is_mapped_to_cancelled() -> None:
    crash = MaudeWorkerCrashedError(context={"pid": 7})
    runner = FakeRunner(exc=crash)
    executor, _ = make_executor(runner)
    runner.on_run = executor.shutdown  # close the executor while the call is in flight

    with pytest.raises(MaudeWorkerCancelledError) as exc_info:
        _ = executor.diagnostics("hello.maude")

    assert exc_info.value.context["pid"] == 7
    assert exc_info.value.__cause__ is crash


def test_shutdown_cancels_a_call_before_it_acquires_the_runner() -> None:
    executor, runner = make_executor()
    executor.shutdown()

    with pytest.raises(MaudeWorkerCancelledError):
        _ = executor.diagnostics("hello.maude")

    assert runner.calls == []


def test_admission_timeout_names_the_slot() -> None:
    executor, runner = make_executor()
    _ = executor._semaphore.acquire()
    try:
        with pytest.raises(MaudeWorkerTimeoutError, match="interpreter slot"):
            _ = executor._run_operation("diagnostics", {"path": "x"}, 0.05, {})
    finally:
        executor._semaphore.release()

    assert runner.calls == []


def test_exhausted_budget_after_admission_times_out_without_spawning() -> None:
    executor, runner = make_executor()

    with pytest.raises(MaudeWorkerTimeoutError):
        _ = executor._run_operation("diagnostics", {"path": "x"}, 0.0, {})

    assert runner.calls == []
    assert executor._semaphore.acquire(blocking=False)  # released in finally
    executor._semaphore.release()


def test_admission_serializes_calls_when_the_only_slot_is_busy() -> None:
    first_started = threading.Event()
    release = threading.Event()
    results: list[LoadDiagnosticsResult] = []

    runner = FakeRunner(result=OK_RESULT)

    def on_run() -> None:
        if not first_started.is_set():
            first_started.set()
            _ = release.wait(10)

    runner.on_run = on_run
    executor, _ = make_executor(runner)
    barrier = threading.Barrier(2)

    def call() -> None:
        barrier.wait()
        results.append(executor.diagnostics("hello.maude"))

    threads = [threading.Thread(target=call) for _ in range(2)]
    for thread in threads:
        thread.start()
    assert first_started.wait(5)
    release.set()
    for thread in threads:
        thread.join(10)

    assert results == [OK_RESULT, OK_RESULT]
    assert runner.max_active == 1  # the semaphore admitted one interpreter at a time


def test_start_pings_one_process_per_worker() -> None:
    runner = FakeRunner(result=None)
    executor, _ = make_executor(runner, settings=Settings(maude_workers=3))

    executor.start(60)

    assert [call[0] for call in runner.calls] == ["ping", "ping", "ping"]
    assert all(call[1] is None for call in runner.calls)
    assert all(call[3] == {"phase": "init"} for call in runner.calls)
    assert all(0 < call[2] <= 60 for call in runner.calls)
    assert runner.kill_count == 0


def test_start_without_a_budget_does_not_spawn_a_ping() -> None:
    runner = FakeRunner(result=None)
    executor, _ = make_executor(runner, settings=Settings(maude_workers=2))

    with pytest.raises(MaudeInitError):
        executor.start(0)

    assert runner.calls == []


@pytest.mark.parametrize(
    "error",
    [MaudeInitError(remote_traceback="remote tb"), MaudeWorkerCrashedError(), MaudeWorkerTimeoutError()],
)
def test_start_failure_raises_init_error_and_kills_the_runner(error: BaseException) -> None:
    runner = FakeRunner(exc=error)
    executor, _ = make_executor(runner, settings=Settings(maude_workers=2))

    with pytest.raises(MaudeInitError) as exc_info:
        executor.start(60)

    assert exc_info.value.__cause__ is error
    assert exc_info.value.context["phase"] == "init"
    assert runner.kill_count == 1


def test_start_failure_discards_the_runner_for_a_lazy_retry() -> None:
    failed = FakeRunner(exc=MaudeInitError())
    healthy = FakeRunner(result=OK_RESULT)
    runners = [failed, healthy]

    def factory() -> FakeRunner:
        return runners.pop(0)

    executor, _ = make_executor(factory=factory, settings=Settings(maude_workers=1))

    with pytest.raises(MaudeInitError):
        executor.start(60)

    assert executor.diagnostics("hello.maude") == OK_RESULT
    assert healthy.calls[0][0] == "diagnostics"


def test_start_after_shutdown_builds_a_fresh_runner() -> None:
    created: list[FakeRunner] = []

    def factory() -> FakeRunner:
        runner = FakeRunner(result=None)
        created.append(runner)
        return runner

    executor, _ = make_executor(factory=factory, settings=Settings(maude_workers=1))

    executor.start(60)
    executor.shutdown()
    executor.start(60)

    assert len(created) == 2
    assert created[0].kill_count >= 1
    assert [call[0] for call in created[1].calls] == ["ping"]


def test_shutdown_is_idempotent() -> None:
    runner = FakeRunner(result=None)
    executor, _ = make_executor(runner)

    executor.start(60)
    executor.shutdown()
    executor.shutdown()

    assert runner.kill_count >= 1


def test_get_maude_executor_returns_singleton() -> None:
    resolved = Settings(maude_workers=1, diagnostics_timeout_secs=60)
    assert get_maude_executor(resolved) is get_maude_executor(resolved)
