"""Probe: reproduce the pool-kill cascade and the CancelledError escape.

Uses the real ``MaudeExecutor`` with real Maude workers (Python-level, no MCP server).

Run from ``harold-mcp``::

    UV_CACHE_DIR=/tmp/uv-cache uv run python \
        .agents/planning/more_interpreter_bugs/research/probes/probe_pool_cascade.py [all|time|finite|infinite|cancel]

Scenarios:

- ``time``: calibrate how long ``reduce count(20M)`` takes on this host.
- ``finite``: attempt-4 recipe with finite slow reductions.
- ``infinite``: same shape, but the occupying calls are non-terminating.
- ``cancel``: can ``future.cancel()`` tell a queued timeout from a running one
  inside the real executor?
"""

import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from harold_mcp.maude.executor import MaudeExecutor
from harold_mcp.maude.session import SessionRequest, StepRequest, run_session
from harold_mcp.settings import Settings

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def step(**overrides: object) -> StepRequest:
    base = {
        "command": "reduce",
        "term": None,
        "pattern": None,
        "subject": None,
        "bound": None,
        "gas": None,
        "depth": None,
        "search_type": None,
        "path_mode": None,
    }
    base.update(overrides)
    return base  # type: ignore[return-value]


def request(fixture: str, module: str, steps: list[StepRequest]) -> SessionRequest:
    return {
        "path": str(FIXTURES / fixture),
        "module": module,
        "steps": steps,
        "max_solutions": 200,
        "max_result_length": 1_000_000,
        "max_path_steps": 100,
        "max_output_length": 1_000_000,
    }


SLOW = request(
    "pool_bugs.maude",
    "SLOW",
    [step(command="reduce", term="count(20000000)")],
)
LOOP = request(
    "pool_bugs.maude",
    "LOOP",
    [step(command="rewrite", term="f(a)")],
)
SPIN = request(
    "pool_bugs.maude",
    "SPIN",
    [step(command="rewrite", term="spin(0, 60000000)")],
)
SEARCH = request(
    "shepherd.maude",
    "SHEPHERD",
    [
        step(
            command="search",
            pattern="< right | right | right | right >",
            subject="initial",
            search_type="any-steps",
            path_mode="labels",
        )
    ],
)


def make_executor() -> MaudeExecutor:
    return MaudeExecutor(Settings(maude_workers=3, interpreter_timeout_secs=60))


def call(executor: MaudeExecutor, name: str, req: SessionRequest, timeout: float) -> dict[str, object]:
    started = time.monotonic()
    try:
        result = executor.run_session(req, timeout=timeout)
    except BaseException as exc:  # noqa: BLE001 - we want the exact exception type
        return {
            "call": name,
            "kind": type(exc).__name__,
            "message": str(exc),
            "cause": type(exc.__cause__).__name__ if exc.__cause__ is not None else None,
            "elapsed_s": round(time.monotonic() - started, 2),
        }
    return {
        "call": name,
        "kind": "ok",
        "load_ok": result["load_ok"],
        "steps": len(result["outcomes"]),
        "solutions": len((result["outcomes"][0]["solutions"] or [])) if result["outcomes"] else 0,
        "elapsed_s": round(time.monotonic() - started, 2),
    }


def report(title: str, results: list[dict[str, object]]) -> None:
    print(f"\n== {title} ==")
    for item in results:
        print("  ", item)


def time_slow(executor: MaudeExecutor) -> None:
    for label, req in (("reduce count(20M)", SLOW), ("rewrite spin", SPIN)):
        started = time.monotonic()
        result = executor.run_session(req, timeout=300)
        elapsed = round(time.monotonic() - started, 2)
        outcome = result["outcomes"][0] if result["outcomes"] else {}
        print(
            f"{label}: {elapsed}s, load_ok={result['load_ok']}, "
            f"status={outcome.get('status')}, rewrites={outcome.get('rewrites')}, term={outcome.get('term')!r}"
        )


def run_batch(executor: MaudeExecutor, *, occupier: SessionRequest, head_start: float) -> list[dict[str, object]]:
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(call, executor, f"occupier-{i}", occupier, 120) for i in range(3)]
        print(f"   waiting {head_start}s for the occupying calls to start...")
        time.sleep(head_start)
        futures.append(pool.submit(call, executor, "trigger", LOOP, 2))
        futures.extend(pool.submit(call, executor, f"search-{i}", SEARCH, 60) for i in range(4))
        return [future.result() for future in futures]


def scenario_finite() -> None:
    executor = make_executor()
    try:
        time_slow(executor)
        report("finite: 3 slow spins, then a 2s loop + 4 searches", run_batch(executor, occupier=SPIN, head_start=2.0))
    finally:
        executor.shutdown()


def scenario_infinite() -> None:
    executor = make_executor()
    try:
        report(
            "infinite: 3 non-terminating reductions, then a 2s loop + 4 searches",
            run_batch(executor, occupier=LOOP, head_start=2.0),
        )
    finally:
        executor.shutdown()


def scenario_cancel() -> None:
    print("\n== cancel: a queued timeout inside the real executor ==")
    executor = make_executor()
    try:
        # Occupy all three workers with non-terminating reductions.
        busy = [executor._submit(run_session, LOOP) for _ in range(3)]  # noqa: SLF001 - probe
        time.sleep(2.5)
        # Six extra calls: up to max_workers + EXTRA_QUEUED_CALLS are dispatched
        # to the call queue (future RUNNING); the rest stay pending.
        submitted = [executor._submit(run_session, LOOP) for _ in range(6)]  # noqa: SLF001 - probe
        time.sleep(0.3)
        print("   future.cancel() ->", [future.cancel() for _, future in submitted])
        for _, future in submitted:
            try:
                _ = future.result(timeout=0.05)
            except BaseException as exc:  # noqa: BLE001 - we want the exact exception type
                print("   result ->", type(exc).__name__)
            else:
                print("   result -> ok")
        print("   busy futures (expected to be killed by shutdown):", len(busy))
    finally:
        executor.shutdown()


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode in ("all", "time"):
        executor = make_executor()
        try:
            time_slow(executor)
        finally:
            executor.shutdown()
    if mode in ("all", "finite"):
        scenario_finite()
    if mode in ("all", "infinite"):
        scenario_infinite()
    if mode in ("all", "cancel"):
        scenario_cancel()


if __name__ == "__main__":
    main()
