"""Scratch: raw worker capture for loads_bad_dependency (confirm the dropped warning)."""

import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from harold_mcp.maude import worker

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "integration" / "fixtures"


def main() -> None:
    with ProcessPoolExecutor(
        max_workers=1, mp_context=multiprocessing.get_context("spawn"), initializer=worker.init_maude
    ) as pool:
        result = pool.submit(worker.load_diagnostics, str(FIXTURES / "loads_bad_dependency.maude")).result(timeout=60)
        print("parsed:", result)


if __name__ == "__main__":
    main()
