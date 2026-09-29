"""Experiment: does `max_tasks_per_child=1` fix the quirk, and what does it cost?

Runs the same tool-level sequence as the integration tests, first with the
current warm pool, then with a pool whose workers are recycled after every task.
Also times N sequential diagnostics in both modes, and checks the integration
test's parallel-workers budget (`two 1.0s sleeps in < 1.8s`).

Run from the harold-mcp root (needs the project environment):

    uv run python .agents/planning/no_new_module_quirk/scratch_mtc.py
"""

import multiprocessing
import os
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from harold_mcp.maude import worker
from harold_mcp.maude.executor import MaudeExecutor
from harold_mcp.server.tools.diagnostics import maude_program_diagnostics
from harold_mcp.settings import Settings

FIXTURES = str(Path(__file__).resolve().parents[3] / "tests" / "integration" / "fixtures")


def diagnose(executor: MaudeExecutor, name: str) -> str:
    result = maude_program_diagnostics(os.path.join(FIXTURES, name), maude_executor=executor)
    return f"success={result.success} diags={[(d.source, d.severity, d.message) for d in result.diagnostics]}"


def recycled_executor(n_workers: int = 1) -> MaudeExecutor:
    def factory() -> ProcessPoolExecutor:
        return ProcessPoolExecutor(
            max_workers=n_workers,
            mp_context=multiprocessing.get_context("spawn"),
            initializer=worker.init_maude,
            max_tasks_per_child=1,
        )

    return MaudeExecutor(settings=Settings(maude_workers=n_workers), executor_factory=factory)


def sequence(executor: MaudeExecutor, label: str) -> None:
    executor.start()
    try:
        for name in ["hello.maude", "no_new_module.maude", "hello.maude", "hello.maude", "no_new_module.maude"]:
            print(f"[{label}] {name}: {diagnose(executor, name)}")
    finally:
        executor.shutdown()


def timing(executor: MaudeExecutor, label: str, runs: int = 4) -> None:
    executor.start()
    try:
        start = time.perf_counter()
        for _ in range(runs):
            maude_program_diagnostics(os.path.join(FIXTURES, "hello.maude"), maude_executor=executor)
        elapsed = time.perf_counter() - start
        print(f"[{label}] {runs} sequential clean diagnostics: {elapsed:.2f}s total, {elapsed / runs:.2f}s/call")
    finally:
        executor.shutdown()


def main() -> None:
    print("=== warm pool (current design) ===")
    sequence(MaudeExecutor(settings=Settings(maude_workers=1)), "warm")

    print()
    print("=== max_tasks_per_child=1 ===")
    sequence(recycled_executor(), "recycled")

    print()
    print("=== timing ===")
    timing(MaudeExecutor(settings=Settings(maude_workers=1)), "warm")
    timing(recycled_executor(), "recycled")

    print()
    print("=== parallel sleeps with max_tasks_per_child=1 (integration test budget: < 1.8s) ===")
    parallel = recycled_executor(2)
    parallel.start()
    try:
        start = time.perf_counter()
        futures = [parallel.submit(worker.sleep, 1.0), parallel.submit(worker.sleep, 1.0)]
        pids = [future.result(timeout=30) for future in futures]
        elapsed = time.perf_counter() - start
        print(f"two 1.0s sleeps on distinct pids: {pids[0] != pids[1]} wall={elapsed:.2f}s")
    finally:
        parallel.shutdown()


if __name__ == "__main__":
    main()
