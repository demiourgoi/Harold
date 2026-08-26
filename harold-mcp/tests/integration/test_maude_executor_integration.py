"""Integration tests for `MaudeExecutor` against the real interpreter."""

import os
from collections.abc import Iterator
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path

import pytest

from harold_mcp.maude import MaudeExecutor, MaudeWorkerCrashedError, worker
from harold_mcp.maude.worker import LoadDiagnosticsResult
from harold_mcp.settings import Settings

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def executor() -> Iterator[MaudeExecutor]:
    executor = MaudeExecutor()
    executor.start()
    try:
        yield executor
    finally:
        executor.shutdown()


def _diagnose(executor: MaudeExecutor, fixture_name: str) -> LoadDiagnosticsResult:
    return executor.diagnostics(str(FIXTURES_DIR / fixture_name))


def test_diagnostics_clean_program(executor: MaudeExecutor) -> None:
    result = _diagnose(executor, "hello.maude")
    assert result["ok"] is True
    assert result["warnings"] == []


def test_diagnostics_recoverable_program(executor: MaudeExecutor) -> None:
    result = _diagnose(executor, "broken-recoverable.maude")
    assert result["ok"] is True
    assert result["warnings"] == [{"line": 2, "message": "missing is keyword."}]


def test_diagnostics_non_recoverable_program(executor: MaudeExecutor) -> None:
    result = _diagnose(executor, "broken-non-recoverable.maude")
    assert result["ok"] is True
    assert len(result["warnings"]) == 12


def test_diagnostics_program_without_modules(executor: MaudeExecutor) -> None:
    result = _diagnose(executor, "no_new_module.maude")
    assert result["ok"] is True
    assert result["warnings"] == []


def test_worker_crash_is_contained_and_recovers(executor: MaudeExecutor) -> None:
    with pytest.raises(BrokenProcessPool):
        executor.submit(worker._crash).result(timeout=60)

    # The first call after the crash reports it (and replaces the pool); the
    # client retries, and the next call runs on the recreated worker.
    with pytest.raises(MaudeWorkerCrashedError):
        _diagnose(executor, "hello.maude")
    result = _diagnose(executor, "hello.maude")
    assert result["ok"] is True
    assert result["warnings"] == []


def test_two_workers_are_used_for_parallel_diagnostics() -> None:
    parallel = MaudeExecutor(settings=Settings(maude_workers=2))
    parallel.start()
    try:
        pids = {parallel.submit(os.getpid).result(timeout=60) for _ in range(8)}
        assert len(pids) >= 2
    finally:
        parallel.shutdown()
