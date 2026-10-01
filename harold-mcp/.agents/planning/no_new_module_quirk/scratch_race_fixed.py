"""Scratch: does `max_tasks_per_child=1` fix the race? Same run as scratch_race.py but with recycled pools."""

import multiprocessing
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

from harold_mcp.maude import MaudeExecutor, worker
from harold_mcp.server.tools.diagnostics import maude_program_diagnostics
from harold_mcp.settings import Settings

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "integration" / "fixtures"

INTERPRETER_CLEAN = {
    "hello.maude",
    "hello2.maude",
    "no_new_module.maude",
    "nonascii_apostrophe.maude",
    "string_with_specials.maude",
    "quoted_id_when_dash.maude",
    "declarations_when_dash.maude",
    "non_linear_pattern.maude",
    "capitalized_identifiers_ok.maude",
    "redeclare_prelude.maude",
    "elt_sort_declaration.maude",
}


def recycled_factory(workers: int) -> ProcessPoolExecutor:
    return ProcessPoolExecutor(
        max_workers=workers,
        mp_context=multiprocessing.get_context("spawn"),
        initializer=worker.init_maude,
        max_tasks_per_child=1,
    )


def main() -> None:
    fixtures = sorted(path.name for path in FIXTURES.glob("*.maude"))
    for workers in (1, 2, 4):
        for round_no in range(1, 4):
            executor = MaudeExecutor(
                settings=Settings(maude_workers=workers),
                executor_factory=lambda workers=workers: recycled_factory(workers),
            )
            executor.start()
            try:
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    results = list(
                        pool.map(
                            lambda name: maude_program_diagnostics(str(FIXTURES / name), maude_executor=executor),
                            fixtures,
                        )
                    )
                spurious = []
                for result in results:
                    name = Path(result.path).name
                    if name not in INTERPRETER_CLEAN:
                        continue
                    for diagnostic in result.diagnostics:
                        if diagnostic.source == "interpreter":
                            line = diagnostic.range.start.line if diagnostic.range else None
                            spurious.append((name, line, diagnostic.message))
                print(f"workers={workers} round={round_no}: {'SPURIOUS ' + str(spurious) if spurious else 'clean'}")
            finally:
                executor.shutdown()


if __name__ == "__main__":
    main()
