"""Integration tests for the `maude_run` tool with the real interpreter.

Calls go directly to the tool function with an explicit executor and settings
(FastMCP dependency defaults are not resolved on direct calls), like the
diagnostics integration tests.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest

from harold_mcp.maude import MaudeExecutor
from harold_mcp.server.tools.interpreter import MaudeRunError, MaudeRunResult, ReduceStep, maude_run
from harold_mcp.settings import Settings

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def environment() -> Iterator[tuple[MaudeExecutor, Settings]]:
    settings = Settings(maude_workers=1)
    executor = MaudeExecutor(settings=settings)
    executor.start(settings.diagnostics_timeout_secs)
    try:
        yield executor, settings
    finally:
        executor.shutdown()


def _run(
    environment: tuple[MaudeExecutor, Settings],
    fixture_name: str,
    module: str,
    steps: list[ReduceStep],
) -> MaudeRunResult:
    executor, settings = environment
    return maude_run(
        str(FIXTURES_DIR / fixture_name),
        module,
        steps,
        executor=executor,
        settings=settings,
    )


def test_reduce_end_to_end(environment: tuple[MaudeExecutor, Settings]) -> None:
    result = _run(environment, "hello.maude", "HELLO-WORLD", [ReduceStep(command="reduce", term="f")])

    assert result.path == str((FIXTURES_DIR / "hello.maude").resolve())
    assert result.module == "HELLO-WORLD"
    assert result.load.warnings == []
    assert result.load.output.model_dump() == {"stdout": "", "stderr": ""}
    assert result.completed is True
    assert len(result.steps) == 1
    outcome = result.steps[0]
    assert (outcome.index, outcome.command, outcome.status, outcome.term) == (0, "reduce", "ok", "2")
    assert outcome.rewrites is not None
    assert outcome.rewrites > 0


def test_missing_module_error_lists_the_defined_modules(environment: tuple[MaudeExecutor, Settings]) -> None:
    with pytest.raises(MaudeRunError) as exc_info:
        _ = _run(environment, "hello.maude", "NOPE", [ReduceStep(command="reduce", term="f")])

    message = str(exc_info.value)
    assert 'Module "NOPE"' in message
    assert "HELLO-WORLD" in message
    assert "maude_program_diagnostics" in message


def test_broken_file_fails_as_a_whole_call(environment: tuple[MaudeExecutor, Settings]) -> None:
    with pytest.raises(MaudeRunError, match="not defined"):
        _ = _run(environment, "broken-non-recoverable.maude", "HELLO-WORLD", [ReduceStep(command="reduce", term="f")])
