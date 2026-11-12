"""Probe: billiard Pool semantics for Harold's isolation requirements.

Run from ``harold-mcp`` (billiard is used ephemerally, not added to the project)::

    UV_CACHE_DIR=/tmp/uv-cache uv run --with billiard python \
        .agents/planning/more_interpreter_bugs/research/probes/probe_billiard.py [all|crash|timeout|queued|terminate-job|maxtasks|init]

Scenarios:

- ``crash``: one worker exits abruptly; does a concurrent task survive?
- ``timeout``: one task exceeds its per-job hard timeout; does a concurrent task survive?
- ``queued``: does a per-job timeout apply while the task is still queued?
- ``terminate-job``: manual ``Pool.terminate_job(pid)`` from the client.
- ``maxtasks``: ``maxtasksperchild=1`` gives a fresh process per task.
- ``init``: initializer raises (run in a subprocess, because billiard's pool
  threads call ``os._exit``/SIGTERM on the parent when restart limits are hit).
"""

import multiprocessing
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import billiard
from billiard.exceptions import TimeLimitExceeded, WorkerLostError  # noqa: F401 - documentation
from billiard.pool import Pool

BASE = Path(__file__).resolve().parent
MARKERS = BASE / ".billiard-markers"


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


def init_mark() -> None:
    mark("init")


def outcome(result, timeout: float = 120) -> str:  # noqa: ANN001 - probe script
    try:
        return f"ok({result.get(timeout=timeout)})"
    except BaseException as exc:  # noqa: BLE001 - we want the exact exception type
        inner = getattr(exc, "exc", None)
        if inner is not None:
            return f"{type(inner).__name__}({inner}) [wrapped in {type(exc).__name__}]"
        return f"{type(exc).__name__}({exc})"


def make_pool(ctx, *, processes: int = 2, initializer=init_ok, **kwargs) -> Pool:  # noqa: ANN001
    return Pool(
        processes=processes,
        maxtasksperchild=1,
        initializer=initializer,
        context=ctx,
        allow_restart=True,
        lost_worker_timeout=1.0,
        synack=True,
        enable_timeouts=True,
        **kwargs,
    )


def stop(pool: Pool) -> None:
    pool.terminate()
    pool.join()


def scenario_crash(ctx) -> None:  # noqa: ANN001 - probe script
    print("\n== crash: one worker exits abruptly ==")
    pool = make_pool(ctx, processes=2)
    try:
        doomed = pool.apply_async(crash_marked, ("doomed",))
        healthy = pool.apply_async(sleep_marked, (2.0, "healthy"))
        print("  doomed ->", outcome(doomed))
        print("  healthy ->", outcome(healthy))
        print("  after-crash ->", outcome(pool.apply_async(sleep_marked, (0.1, "after-crash"))))
    finally:
        stop(pool)


def scenario_timeout(ctx) -> None:  # noqa: ANN001 - probe script
    print("\n== timeout: one task exceeds its per-job hard timeout ==")
    pool = make_pool(ctx, processes=2)
    try:
        started = time.monotonic()
        slow = pool.apply_async(sleep_marked, (30.0, "slow"), timeout=1.0)
        healthy = pool.apply_async(sleep_marked, (2.0, "healthy"))
        print("  slow ->", outcome(slow), f"at {time.monotonic() - started:.1f}s")
        print("  healthy ->", outcome(healthy), f"at {time.monotonic() - started:.1f}s")
        print("  after-timeout ->", outcome(pool.apply_async(sleep_marked, (0.1, "after-timeout"))))
    finally:
        stop(pool)


def scenario_queued(ctx) -> None:  # noqa: ANN001 - probe script
    print("\n== queued: per-job timeout while the task is still queued ==")
    pool = make_pool(ctx, processes=1)
    try:
        started = time.monotonic()
        occupant = pool.apply_async(sleep_marked, (4.0, "occupant"))
        queued = pool.apply_async(sleep_marked, (0.1, "queued"), timeout=1.0)
        print("  queued ->", outcome(queued), f"at {time.monotonic() - started:.1f}s")
        print("  occupant ->", outcome(occupant), f"at {time.monotonic() - started:.1f}s")
        print("  queued started count:", mark_count("queued"))
    finally:
        stop(pool)


def scenario_terminate_job(ctx) -> None:  # noqa: ANN001 - probe script
    print("\n== terminate-job: manual Pool.terminate_job(pid) ==")
    pool = make_pool(ctx, processes=2)
    try:
        slow = pool.apply_async(sleep_marked, (30.0, "slow"))
        deadline = time.monotonic() + 30
        pids: list[int] = []
        while time.monotonic() < deadline:
            pids = slow.worker_pids()
            if pids:
                break
            time.sleep(0.02)
        print("  accepted:", slow.accepted(), "worker_pids:", pids)
        if pids:
            pool.terminate_job(pids[0])
        print("  slow ->", outcome(slow))
        print("  healthy ->", outcome(pool.apply_async(sleep_marked, (0.2, "healthy"))))
    finally:
        stop(pool)


def scenario_maxtasks(ctx) -> None:  # noqa: ANN001 - probe script
    print("\n== maxtasks: maxtasksperchild=1 gives a fresh process per task ==")
    pool = make_pool(ctx, processes=1, initializer=init_mark)
    try:
        results = [pool.apply_async(sleep_marked, (0.01, f"t{i}")).get(timeout=60) for i in range(3)]
        pids = [item["pid"] for item in results]
        print("  pids:", pids, "all distinct:", len(set(pids)) == len(pids))
        print("  initializer runs:", mark_count("init"))
    finally:
        stop(pool)


def init_child() -> None:
    print("  child: creating pool with a failing initializer", flush=True)
    pool = make_pool(billiard.get_context("spawn"), processes=1, initializer=init_fail)
    try:
        result = pool.apply_async(sleep_marked, (0.1, "never"))
        print("  child: task ->", outcome(result, timeout=5), flush=True)
    except BaseException as exc:  # noqa: BLE001 - probe script
        print("  child: schedule/get raised", type(exc).__name__, exc, flush=True)
    finally:
        try:
            stop(pool)
        except BaseException as exc:  # noqa: BLE001 - probe script
            print("  child: stop raised", type(exc).__name__, exc, flush=True)


def scenario_init() -> None:
    print("\n== init: initializer raises (parent survives; child exit code observed) ==")
    result = subprocess.run(  # noqa: S603 - probe script
        [sys.executable, str(Path(__file__).resolve()), "init-child"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    print("  child returncode:", result.returncode)
    for line in result.stdout.splitlines():
        print("  ", line)
    for line in result.stderr.splitlines()[-8:]:
        print("  stderr:", line)


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    shutil.rmtree(MARKERS, ignore_errors=True)
    ctx = billiard.get_context("spawn")
    print("billiard:", billiard.__version__, "python:", sys.version.split()[0])
    if mode == "init-child":
        init_child()
        shutil.rmtree(MARKERS, ignore_errors=True)
        return
    scenarios = {
        "crash": scenario_crash,
        "timeout": scenario_timeout,
        "queued": scenario_queued,
        "terminate-job": scenario_terminate_job,
        "maxtasks": scenario_maxtasks,
        "init": lambda _ctx: scenario_init(),
    }
    selected = scenarios.values() if mode == "all" else [scenarios[mode]]
    for scenario in selected:
        scenario(ctx)
    shutil.rmtree(MARKERS, ignore_errors=True)


if __name__ == "__main__":
    main()
