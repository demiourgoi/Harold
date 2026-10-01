"""Scratch: timing + memory for warm pool vs `max_tasks_per_child=1` (worker counts 1/2/6)."""

import multiprocessing
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

from harold_mcp.maude import MaudeExecutor, worker
from harold_mcp.settings import Settings

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "integration" / "fixtures"


def rss_mb() -> float:
    with open("/proc/self/status", encoding="utf-8") as stream:
        for line in stream:
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024
    return 0.0


def recycled_factory(workers: int) -> ProcessPoolExecutor:
    return ProcessPoolExecutor(
        max_workers=workers,
        mp_context=multiprocessing.get_context("spawn"),
        initializer=worker.init_maude,
        max_tasks_per_child=1,
    )


def main() -> None:
    hello = str(FIXTURES / "hello.maude")
    n = 8

    # Warm pool, sequential (current design).
    warm = MaudeExecutor(settings=Settings(maude_workers=1))
    warm.start()
    start = time.monotonic()
    for _ in range(n):
        warm.diagnostics(hello)
    warm_seq = time.monotonic() - start
    print(f"warm pool (1 worker), {n} sequential: {warm_seq:.3f}s ({warm_seq / n:.3f}s/call)")
    warm.shutdown()

    # Recycled pool at several worker counts.
    for workers in (1, 2, 6):
        rec = MaudeExecutor(
            settings=Settings(maude_workers=workers),
            executor_factory=lambda workers=workers: recycled_factory(workers),
        )
        rec.start()
        start = time.monotonic()
        for _ in range(n):
            rec.diagnostics(hello)
        seq = time.monotonic() - start
        print(f"recycled ({workers} worker), {n} sequential: {seq:.3f}s ({seq / n:.3f}s/call)")
        start = time.monotonic()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(lambda _: rec.diagnostics(hello), range(n)))
        par = time.monotonic() - start
        print(f"recycled ({workers} worker), {n} parallel:   {par:.3f}s ({par / n:.3f}s/call)")
        future = rec.submit(rss_mb)
        print(f"recycled ({workers} worker): worker RSS after a task = {future.result(timeout=60):.1f} MB")
        rec.shutdown()

    # Warm pool with 2 workers, parallel (reference for the old design).
    warm2 = MaudeExecutor(settings=Settings(maude_workers=2))
    warm2.start()
    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: warm2.diagnostics(hello), range(n)))
    par2 = time.monotonic() - start
    print(f"warm pool (2 workers), {n} parallel: {par2:.3f}s ({par2 / n:.3f}s/call)")
    warm2.shutdown()


if __name__ == "__main__":
    main()
