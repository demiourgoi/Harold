"""Probe: CPython 3.14 ProcessPoolExecutor semantics used by MaudeExecutor's recovery.

Answers three questions with the installed interpreter:

1. Does ``future.cancel()`` distinguish a queued task from a running one?
2. When ``kill_workers()`` runs, what do running and pending futures report?
3. Can a future whose ``result(timeout)`` has already timed out be cancelled?

Run from ``harold-mcp``:

    UV_CACHE_DIR=/tmp/uv-cache uv run python \
        .agents/planning/more_interpreter_bugs/research/probes/probe_cpython_pool.py
"""

import concurrent.futures.process as process_module
import multiprocessing
import os
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

BASE = Path(__file__).resolve().parent
MARKERS = BASE / ".probe-markers"
TRIALS = 10


def started_task(seconds: float) -> str:
    """Touch a marker, then sleep. The marker proves the task started running."""
    marker_dir = Path(os.environ["PROBE_MARKER_DIR"])
    marker_dir.mkdir(parents=True, exist_ok=True)
    (marker_dir / f"{os.getpid()}-{time.monotonic_ns()}.started").touch()
    time.sleep(seconds)
    return "done"


def reset_markers() -> None:
    shutil.rmtree(MARKERS, ignore_errors=True)
    MARKERS.mkdir(parents=True, exist_ok=True)


def wait_for_markers(count: int, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if len(list(MARKERS.glob("*.started"))) >= count:
            return
        time.sleep(0.02)
    raise TimeoutError(f"only {len(list(MARKERS.glob('*.started')))}/{count} tasks started")


def outcome_name(future) -> str:  # noqa: ANN001 - probe script
    try:
        _ = future.result(timeout=10)
    except BaseException as exc:  # noqa: BLE001 - we want the exact exception type
        return f"{type(exc).__name__}({exc})"
    return "ok"


def scenario_cancel(ctx) -> None:  # noqa: ANN001 - probe script
    print("== scenario 1: cancel() on queued vs running futures ==")
    print(f"   EXTRA_QUEUED_CALLS={process_module.EXTRA_QUEUED_CALLS}")
    reset_markers()
    with ProcessPoolExecutor(max_workers=2, mp_context=ctx) as pool:
        running = [pool.submit(started_task, 3.0) for _ in range(2)]
        wait_for_markers(2)
        # 6 pending: the manager dispatches up to maxsize work items to the call
        # queue and marks their futures RUNNING before any worker picks them up.
        queued = [pool.submit(started_task, 0.1) for _ in range(6)]
        time.sleep(0.3)
        print("cancel queued  ->", [f.cancel() for f in queued])
        print("cancel running ->", [f.cancel() for f in running])
        try:
            _ = running[0].result(timeout=0.1)
        except TimeoutError:
            print("cancel after result(timeout=0.1) on a running task ->", running[0].cancel())
        else:
            print("WARNING: running[0] finished unexpectedly")
        for future in queued:
            print("   queued future result ->", outcome_name(future))


def scenario_kill(ctx) -> None:  # noqa: ANN001 - probe script
    print(f"== scenario 2: kill_workers() outcomes ({TRIALS} trials) ==")
    tally_running: dict[str, int] = {}
    tally_pending: dict[str, int] = {}
    for trial in range(1, TRIALS + 1):
        reset_markers()
        pool = ProcessPoolExecutor(max_workers=2, mp_context=ctx)
        try:
            running = [pool.submit(started_task, 10.0) for _ in range(2)]
            wait_for_markers(2)
            pending = [pool.submit(started_task, 0.1) for _ in range(6)]
            time.sleep(0.2)
            pool.kill_workers()
            running_out = [outcome_name(f) for f in running]
            pending_out = [outcome_name(f) for f in pending]
        finally:
            pool.shutdown(wait=False)
        for name in running_out:
            key = name.split("(", 1)[0]
            tally_running[key] = tally_running.get(key, 0) + 1
        for name in pending_out:
            key = name.split("(", 1)[0]
            tally_pending[key] = tally_pending.get(key, 0) + 1
        if trial <= 3:
            print(f"  trial {trial}: running={running_out} pending={pending_out}")
    print("  running totals:", tally_running)
    print("  pending totals:", tally_pending)


def scenario_submit_after_shutdown(ctx) -> None:  # noqa: ANN001 - probe script
    print("== scenario 3: submit() after shutdown() ==")
    pool = ProcessPoolExecutor(max_workers=1, mp_context=ctx)
    pool.shutdown()
    try:
        pool.submit(started_task, 0.1)
    except BaseException as exc:  # noqa: BLE001 - we want the exact exception type
        print("  ->", type(exc).__name__, ":", exc)
    else:
        print("  -> submit unexpectedly succeeded")


def main() -> None:
    os.environ["PROBE_MARKER_DIR"] = str(MARKERS)
    print("python:", sys.version.replace("\n", " "))
    ctx = multiprocessing.get_context("spawn")
    reset_markers()
    scenario_cancel(ctx)
    scenario_kill(ctx)
    scenario_submit_after_shutdown(ctx)
    shutil.rmtree(MARKERS, ignore_errors=True)


if __name__ == "__main__":
    main()
