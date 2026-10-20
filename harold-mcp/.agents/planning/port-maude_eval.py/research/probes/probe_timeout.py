"""Probe: what a non-terminating reduction does to the worker pool.

Answers the questions behind ``../worker-behavior.md`` §Timeouts:

- does ``future.result(timeout=...)`` catch a hung ``reduce()`` (C++ never returns)?
- how long does ``kill_workers()`` take on a hung pool?
- does a fresh pool work after the kill (the executor's recovery path)?
- what happens to concurrent/queued healthy calls when a sibling hangs or the
  pool is killed?

The pool setup mirrors ``MaudeExecutor`` (spawn context, ``initializer``,
``max_tasks_per_child=1``) without importing harold_mcp.

Run from ``harold-mcp`` with the project venv::

    .venv/bin/python .agents/planning/port-maude_eval.py/research/probes/probe_timeout.py
"""

import multiprocessing
import time
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool

LOOP_MODULE = """
fmod LOOP is
  pr NAT .
  op f : Nat -> Nat .
  var N : Nat .
  eq f(N) = f(s N) .
endfm
"""


def init_maude() -> None:
    import maude

    if not maude.init(loadPrelude=True, advise=False):
        raise RuntimeError("maude.init failed")
    maude.setAllowDir(False)
    maude.setAllowFiles(False)
    maude.setAllowProcesses(False)


def hang() -> str:
    import maude

    maude.input(LOOP_MODULE)
    module = maude.getModule("LOOP")
    term = module.parseTerm("f(0)")
    term.reduce()  # never returns
    return "finished"


def ok() -> str:
    import maude

    return str(maude.getModule("NAT").parseTerm("2 + 2").reduce())


def sleep_ok(seconds: float) -> str:
    time.sleep(seconds)
    return "slept"


def make_pool(workers: int) -> ProcessPoolExecutor:
    return ProcessPoolExecutor(
        max_workers=workers,
        mp_context=multiprocessing.get_context("spawn"),
        initializer=init_maude,
        max_tasks_per_child=1,
    )


def main() -> None:
    print("=== 1. hung call on a one-worker pool, timeout=5s ===")
    pool = make_pool(1)
    started = time.monotonic()
    future = pool.submit(hang)
    try:
        print("  unexpected result:", future.result(timeout=5))
    except TimeoutError:
        print(f"  TimeoutError after {time.monotonic() - started:.2f}s")
    started = time.monotonic()
    pool.kill_workers()
    print(f"  kill_workers took {time.monotonic() - started:.2f}s")

    print("\n=== 2. fresh pool works after the kill ===")
    fresh = make_pool(1)
    started = time.monotonic()
    print("  result:", fresh.submit(ok).result(timeout=60), f"({time.monotonic() - started:.2f}s)")
    fresh.shutdown()

    print("\n=== 3. queued call behind a hung worker (one-worker pool) ===")
    queued_pool = make_pool(1)
    hang_future = queued_pool.submit(hang)
    queued_future = queued_pool.submit(ok)
    started = time.monotonic()
    try:
        print("  unexpected queued result:", queued_future.result(timeout=5))
    except TimeoutError:
        print(f"  queued call timed out after {time.monotonic() - started:.2f}s (worker is stuck)")
    queued_pool.kill_workers()

    print("\n=== 4. concurrent healthy call on a two-worker pool ===")
    two = make_pool(2)
    hang_future = two.submit(hang)
    started = time.monotonic()
    print("  healthy call while sibling hangs:", two.submit(ok).result(timeout=60), f"({time.monotonic() - started:.2f}s)")
    sleep_future = two.submit(sleep_ok, 30)
    time.sleep(3)
    try:
        hang_future.result(timeout=1)
        print("  unexpected hung result")
    except TimeoutError:
        print("  hung call still running (expected)")
    started = time.monotonic()
    two.kill_workers()
    print(f"  kill_workers took {time.monotonic() - started:.2f}s")
    try:
        print("  in-flight healthy call returned:", sleep_future.result())
    except BrokenProcessPool:
        print("  in-flight healthy call raised BrokenProcessPool (the whole pool was killed)")


if __name__ == "__main__":
    main()
