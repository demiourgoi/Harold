"""Scratch: actual `file` values for broken-non-recoverable and the dep fixture."""

import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from harold_mcp.maude import worker

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "integration" / "fixtures"


def main() -> None:
    with ProcessPoolExecutor(
        max_workers=1, mp_context=multiprocessing.get_context("spawn"), initializer=worker.init_maude
    ) as pool:
        for name in ("broken-non-recoverable.maude", "loads_bad_dependency.maude"):
            result = pool.submit(worker.load_diagnostics, str(FIXTURES / name)).result(timeout=60)
            print(f"=== {name}: ok={result['ok']}")
            for warning in result["warnings"]:
                print("   ", warning)


if __name__ == "__main__":
    main()
