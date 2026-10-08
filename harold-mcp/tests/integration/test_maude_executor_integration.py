"""Integration tests for `MaudeExecutor` against the real interpreter.

Fixture-level load behavior is asserted at the worker level
(`test_maude_worker_integration.py`, raw `load_diagnostics` shapes) and end to end at
the tool level (`test_diagnostics_integration.py`), so this file keeps only the
coverage unique to the executor: real concurrent execution across workers. Crash
recovery is covered end to end by `test_tool_reports_crash_and_recovers` (which also
asserts the chained error vocabulary).
"""

from harold_mcp.maude import MaudeExecutor, worker
from harold_mcp.settings import Settings


def test_two_workers_are_used_for_parallel_diagnostics() -> None:
    parallel = MaudeExecutor(settings=Settings(maude_workers=2))
    parallel.start()
    try:
        # Each task sleeps 1s and reports its pid plus its monotonic start/end.
        # Overlapping intervals prove two workers ran the tasks concurrently (a
        # single worker would serialize them); distinct pids prove different
        # processes. The intervals exclude spawn+init, which each task pays per
        # process now (`max_tasks_per_child=1`), so no wall-clock budget is needed.
        futures = [parallel.submit(worker.sleep_witness, 1.0) for _ in range(2)]
        witnesses = [future.result(timeout=60) for future in futures]
        pids = {pid for pid, _, _ in witnesses}
        assert len(pids) == 2
        starts = [start for _, start, _ in witnesses]
        ends = [end for _, _, end in witnesses]
        assert max(starts) < min(ends)  # the two tasks overlapped in time
    finally:
        parallel.shutdown()
