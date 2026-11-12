"""Probe: pebble ProcessPool semantics for Harold's isolation requirements.

Run from ``harold-mcp`` (pebble is used ephemerally, not added to the project)::

    UV_CACHE_DIR=/tmp/uv-cache uv run --with pebble python \
        .agents/planning/more_interpreter_bugs/research/probes/probe_pebble.py [all|crash|timeout|queued|cancel|init|maxtasks]

Scenarios:

- ``crash``: one worker exits abruptly; does a concurrent task survive?
- ``timeout``: one task times out; does a concurrent task survive?
- ``queued``: a timeout expires while the task is still queued; is the
  occupying task killed?
- ``cancel``: cancelling a running task.
- ``init``: initializer raises.
- ``maxtasks``: ``max_tasks=1`` gives a fresh process (and initializer run) per task.
"""

import multiprocessing
import os
import shutil
import sys
import time
from concurrent.futures import TimeoutError
from pathlib import Path

from pebble import ProcessPool, ProcessExpired

BASE = Path(__file__).resolve().parent
MARKERS = BASE / ".pebble-markers"


def mark(tag: str) -> None:
    MARKERS.mkdir(parents=True, exist_ok=True)
    (MARKERS / f"{tag}-{os.getpid()}-{time.monotonic_ns()}.started").touch()


def mark_count(tag: str) -> int:
    return len(list(MARKERS.glob(f"{tag}-*.started"))) if MARKERS.exists() else 0


def sleep_marked(seconds: float, tag: str) -> dict[str, object]:
    mark(tag)
    time.sleep(seconds)
    return {"pid": os.getpid(), "tag": tag}


def crash_marked(tag: str) -> dict[str, object]:
    mark(tag)
    os._exit(7)


def init_ok() -> None:
    pass


def init_fail() -> None:
    raise RuntimeError("initializer boom")


def outcome(future, timeout: float = 60) -> str:  # noqa: ANN001 - probe script
    try:
        return f"ok({future.result(timeout=timeout)})"
    except BaseException as exc:  # noqa: BLE001 - we want the exact exception type
        extra = ""
        if isinstance(exc, ProcessExpired):
            extra = f" exitcode={exc.exitcode}"
        return f"{type(exc).__name__}({exc}){extra}"


def scenario_crash(ctx) -> None:  # noqa: ANN001 - probe script
    print("\n== crash: one worker exits abruptly ==")
    with ProcessPool(max_workers=2, max_tasks=1, context=ctx) as pool:
        doomed = pool.schedule(crash_marked, args=("doomed",))
        healthy = pool.schedule(sleep_marked, args=(2.0, "healthy"))
        print("  doomed ->", outcome(doomed))
        print("  healthy ->", outcome(healthy))
        print("  pool active:", pool.active)
        print("  after-crash task ->", outcome(pool.schedule(sleep_marked, args=(0.1, "after-crash"))))


def scenario_timeout(ctx) -> None:  # noqa: ANN001 - probe script
    print("\n== timeout: one task exceeds its budget ==")
    with ProcessPool(max_workers=2, max_tasks=1, context=ctx) as pool:
        started = time.monotonic()
        slow = pool.schedule(sleep_marked, args=(30.0, "slow"), timeout=1.0)
        healthy = pool.schedule(sleep_marked, args=(2.0, "healthy"))
        print("  slow ->", outcome(slow, timeout=20))
        print(f"  slow future resolved after {time.monotonic() - started:.1f}s")
        print("  healthy ->", outcome(healthy, timeout=20))
        print("  pool active:", pool.active)
        print("  after-timeout task ->", outcome(pool.schedule(sleep_marked, args=(0.1, "after-timeout"))))


def scenario_queued(ctx) -> None:  # noqa: ANN001 - probe script
    print("\n== queued: timeout expires while the task is still queued ==")
    with ProcessPool(max_workers=1, max_tasks=1, context=ctx) as pool:
        started = time.monotonic()
        occupant = pool.schedule(sleep_marked, args=(4.0, "occupant"))
        queued = pool.schedule(sleep_marked, args=(0.1, "queued"), timeout=1.0)
        print("  queued ->", outcome(queued, timeout=20), f"at {time.monotonic() - started:.1f}s")
        print("  occupant ->", outcome(occupant, timeout=20), f"at {time.monotonic() - started:.1f}s")
        print("  queued task started count:", mark_count("queued"))
        print("  pool active:", pool.active)


def scenario_cancel(ctx) -> None:  # noqa: ANN001 - probe script
    print("\n== cancel: ProcessFuture.cancel() on a running task ==")
    with ProcessPool(max_workers=1, max_tasks=1, context=ctx) as pool:
        future = pool.schedule(sleep_marked, args=(30.0, "cancel-me"))
        deadline = time.monotonic() + 30
        while mark_count("cancel-me") == 0 and time.monotonic() < deadline:
            time.sleep(0.02)
        print("  started:", mark_count("cancel-me") > 0)
        print("  cancel() ->", future.cancel())
        print("  future ->", outcome(future, timeout=20))
        print("  pool active:", pool.active)
        print("  after-cancel task ->", outcome(pool.schedule(sleep_marked, args=(0.1, "after-cancel"))))


def scenario_init(ctx) -> None:  # noqa: ANN001 - probe script
    print("\n== init: initializer raises ==")
    pool = ProcessPool(max_workers=1, max_tasks=1, initializer=init_fail, context=ctx)
    try:
        try:
            future = pool.schedule(sleep_marked, args=(0.1, "never"))
            print("  first ->", outcome(future, timeout=20))
        except BaseException as exc:  # noqa: BLE001 - schedule may raise synchronously
            print("  first schedule raised:", type(exc).__name__, exc)
        print("  pool active:", pool.active)
        try:
            second = pool.schedule(sleep_marked, args=(0.1, "never-2"))
            print("  second ->", outcome(second, timeout=20))
        except BaseException as exc:  # noqa: BLE001
            print("  second schedule raised:", type(exc).__name__, exc)
    finally:
        pool.stop()
        pool.join(timeout=10)


def scenario_maxtasks(ctx) -> None:  # noqa: ANN001 - probe script
    print("\n== maxtasks: max_tasks=1 gives a fresh process per task ==")
    with ProcessPool(max_workers=1, max_tasks=1, initializer=mark, initargs=("init",), context=ctx) as pool:
        first = pool.schedule(sleep_marked, args=(0.01, "t1")).result(timeout=20)
        second = pool.schedule(sleep_marked, args=(0.01, "t2")).result(timeout=20)
        print("  pids:", first["pid"], second["pid"], "distinct:", first["pid"] != second["pid"])
        print("  initializer runs:", mark_count("init"))


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    shutil.rmtree(MARKERS, ignore_errors=True)
    ctx = multiprocessing.get_context("spawn")
    scenarios = {
        "crash": scenario_crash,
        "timeout": scenario_timeout,
        "queued": scenario_queued,
        "cancel": scenario_cancel,
        "init": scenario_init,
        "maxtasks": scenario_maxtasks,
    }
    selected = scenarios.values() if mode == "all" else [scenarios[mode]]
    for scenario in selected:
        scenario(ctx)
    shutil.rmtree(MARKERS, ignore_errors=True)


if __name__ == "__main__":
    main()
