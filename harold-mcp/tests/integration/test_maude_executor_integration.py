"""Integration tests for `MaudeExecutor` against the real interpreter.

Fixture-level load behavior is asserted at the worker level
(`test_maude_worker_integration.py`, raw `load_diagnostics` shapes) and end to end at
the tool level (`test_diagnostics_integration.py`), so this file keeps only the
coverage unique to the executor: real concurrent execution across workers. Crash
recovery is covered end to end by `test_tool_reports_crash_and_recovers` (which also
asserts the chained error vocabulary).
"""

from pathlib import Path

from harold_mcp.maude import MaudeExecutor, worker
from harold_mcp.settings import Settings


def test_two_workers_are_used_for_parallel_diagnostics(tmp_path: Path) -> None:
    parallel = MaudeExecutor(settings=Settings(maude_workers=2))
    parallel.start()
    try:
        # Both tasks complete only once a peer task is running concurrently (marker
        # rendezvous), so completion proves the pool used two processes; a pool that
        # serializes them makes the first task time out and fail. Independent of pool
        # scheduling lag, unlike wall-clock or interval-overlap budgets.
        futures = [parallel.submit(worker.rendezvous_pid, str(tmp_path)) for _ in range(2)]
        pids = {future.result(timeout=45) for future in futures}
        assert len(pids) == 2
    finally:
        parallel.shutdown()
