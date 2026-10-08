"""Scratch: current tool output for the new dependency/isolation fixtures (assertion design)."""

from pathlib import Path

from harold_mcp.maude import MaudeExecutor
from harold_mcp.server.tools.diagnostics import maude_program_diagnostics
from harold_mcp.settings import Settings

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "integration" / "fixtures"

ORDER = [
    "loads_dependency.maude",
    "loads_missing_dependency.maude",
    "loads_bad_dependency.maude",
    "q_with_trailing_text.maude",
    "quit_command.maude",
    "loads_dependency_q.maude",
]


def main() -> None:
    executor = MaudeExecutor(settings=Settings(maude_workers=1))
    executor.start()
    try:
        for name in ORDER:
            result = maude_program_diagnostics(str(FIXTURES / name), maude_executor=executor)
            print(f"=== {name}: success={result.success} summary={result.summary.model_dump()}")
            for d in result.diagnostics:
                line = d.range.start.line if d.range is not None else None
                print(f"    [{d.source}/{d.severity}/{d.code}] line={line} msg={d.message!r}")
            # consume any residue this file may have scheduled (red phase hygiene)
            _ = maude_program_diagnostics(str(FIXTURES / "hello.maude"), maude_executor=executor)
    finally:
        executor.shutdown()


if __name__ == "__main__":
    main()
