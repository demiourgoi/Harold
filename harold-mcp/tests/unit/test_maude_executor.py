"""Unit tests for `MaudeExecutor` using fake executors and futures."""

import threading
from concurrent.futures.process import BrokenProcessPool
from typing import Any

import pytest

from harold_mcp.maude import (
    MaudeExecutor,
    MaudeInitError,
    MaudeWorkerCrashedError,
    MaudeWorkerError,
    MaudeWorkerTimeoutError,
    get_maude_executor,
)
from harold_mcp.maude import worker as worker_module
from harold_mcp.maude.worker import LoadDiagnosticsResult, ping
from harold_mcp.settings import Settings

OK_RESULT: LoadDiagnosticsResult = {"ok": True, "warnings": []}


class FakeFuture:
    """Minimal future: returns a preset result or raises a preset exception."""

    def __init__(self, result: Any = None, exc: BaseException | None = None) -> None:
        self._result = result
        self._exc = exc

    def result(self, timeout: float | None = None) -> Any:
        if self._exc is not None:
            raise self._exc
        return self._result


class FakeExecutor:
    """Minimal ProcessPoolExecutor stand-in with scriptable behaviors."""

    def __init__(
        self,
        *,
        fail_submit: bool = False,
        futures: list[FakeFuture] | None = None,
    ) -> None:
        self.fail_submit = fail_submit
        self._futures = list(futures or [])
        self.submit_calls: list[tuple[Any, tuple[Any, ...]]] = []
        self.killed = False

    def submit(self, fn: Any, *args: Any) -> FakeFuture:
        self.submit_calls.append((fn, args))
        if self.fail_submit:
            raise BrokenProcessPool()
        if self._futures:
            return self._futures.pop(0)
        return FakeFuture(result=OK_RESULT)

    def kill_workers(self) -> None:
        self.killed = True


def make_executor(factory: Any, *, settings: Settings | None = None) -> MaudeExecutor:
    return MaudeExecutor(
        settings=settings or Settings(maude_workers=1, maude_worker_timeout_secs=60),
        executor_factory=factory,
    )


def test_diagnostics_delegates_and_returns_worker_result() -> None:
    fake = FakeExecutor(futures=[FakeFuture(result=OK_RESULT)])
    executor = make_executor(lambda: fake)

    result = executor.diagnostics("hello.maude")

    assert result == OK_RESULT
    fn, args = fake.submit_calls[0]
    assert fn is worker_module.load_diagnostics
    assert args == ("hello.maude",)


def test_diagnostics_lazily_starts_executor() -> None:
    fake = FakeExecutor(futures=[FakeFuture(result=OK_RESULT)])
    executor = make_executor(lambda: fake)

    assert executor.diagnostics("hello.maude") == OK_RESULT


def test_submit_on_broken_pool_replaces_and_raises() -> None:
    calls = {"n": 0}

    def factory() -> FakeExecutor:
        calls["n"] += 1
        return FakeExecutor(fail_submit=True) if calls["n"] == 1 else FakeExecutor()

    executor = make_executor(factory)

    with pytest.raises(MaudeWorkerCrashedError):
        executor.submit(ping)
    assert calls["n"] == 2  # the broken pool was replaced eagerly; no resubmit


def test_diagnostics_worker_crash_raises_and_replaces() -> None:
    calls = {"n": 0}

    def factory() -> FakeExecutor:
        calls["n"] += 1
        return FakeExecutor(futures=[FakeFuture(exc=BrokenProcessPool())])

    executor = make_executor(factory)

    with pytest.raises(MaudeWorkerCrashedError):
        executor.diagnostics("hello.maude")
    assert calls["n"] == 2  # eager replacement


def test_diagnostics_timeout_raises_and_kills_worker() -> None:
    calls = {"n": 0}
    first = FakeExecutor(futures=[FakeFuture(exc=TimeoutError())])

    def factory() -> FakeExecutor:
        calls["n"] += 1
        return first if calls["n"] == 1 else FakeExecutor()

    executor = make_executor(factory)

    with pytest.raises(MaudeWorkerTimeoutError):
        executor.diagnostics("stuck.maude")
    assert calls["n"] == 2
    assert first.killed  # the stuck worker was killed, not just shut down


def test_worker_task_exceptions_propagate_without_replacement() -> None:
    calls = {"n": 0}

    def factory() -> FakeExecutor:
        calls["n"] += 1
        return FakeExecutor(futures=[FakeFuture(exc=ValueError("boom"))])

    executor = make_executor(factory)

    with pytest.raises(ValueError, match="boom"):
        executor.diagnostics("hello.maude")
    assert calls["n"] == 1


def test_next_call_succeeds_after_crash() -> None:
    calls = {"n": 0}

    def factory() -> FakeExecutor:
        calls["n"] += 1
        if calls["n"] == 1:
            return FakeExecutor(futures=[FakeFuture(exc=BrokenProcessPool())])
        return FakeExecutor(futures=[FakeFuture(result=OK_RESULT)])

    executor = make_executor(factory)

    with pytest.raises(MaudeWorkerCrashedError):
        executor.diagnostics("broken.maude")
    assert executor.diagnostics("hello.maude") == OK_RESULT


def test_start_warms_up_one_ping_per_worker() -> None:
    fake = FakeExecutor()
    executor = make_executor(lambda: fake, settings=Settings(maude_workers=2))

    executor.start()

    assert len(fake.submit_calls) == 2
    assert all(fn is ping for fn, _ in fake.submit_calls)


def test_start_init_failure_raises_maude_init_error() -> None:
    calls = {"n": 0}
    failed = FakeExecutor(futures=[FakeFuture(exc=BrokenProcessPool())])

    def factory() -> FakeExecutor:
        calls["n"] += 1
        return failed

    executor = make_executor(factory)

    with pytest.raises(MaudeInitError):
        executor.start()
    # The failed pool is discarded and killed, not eagerly replaced with a doomed worker.
    assert calls["n"] == 1
    assert failed.killed


def test_start_timeout_raises_maude_init_error() -> None:
    executor = make_executor(lambda: FakeExecutor(futures=[FakeFuture(exc=TimeoutError())]))

    with pytest.raises(MaudeInitError):
        executor.start()


def test_shutdown_is_idempotent() -> None:
    fake = FakeExecutor()
    executor = make_executor(lambda: fake)

    executor.start()
    executor.shutdown()
    executor.shutdown()

    assert fake.killed


def test_concurrent_crash_detection_replaces_exactly_once() -> None:
    calls = {"n": 0}
    broken = FakeExecutor(futures=[FakeFuture(exc=BrokenProcessPool()), FakeFuture(exc=BrokenProcessPool())])
    healthy = FakeExecutor(futures=[FakeFuture(result=OK_RESULT) for _ in range(10)])

    def factory() -> FakeExecutor:
        calls["n"] += 1
        return broken if calls["n"] == 1 else healthy

    executor = make_executor(factory)
    barrier = threading.Barrier(2)
    outcomes: list[object] = []

    def run() -> None:
        barrier.wait()
        try:
            executor.diagnostics("hello.maude")
            outcomes.append(OK_RESULT)
        except MaudeWorkerError as exc:
            outcomes.append(exc)

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert calls["n"] == 2  # one initial executor + exactly one replacement
    assert len(outcomes) == 2


def test_get_maude_executor_returns_singleton() -> None:
    resolved = Settings(maude_workers=1, maude_worker_timeout_secs=60)
    assert get_maude_executor(resolved) is get_maude_executor(resolved)
