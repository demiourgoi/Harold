"""Integration tests for the `maude_run` tool with the real interpreter.

Calls go directly to the tool function with an explicit executor and settings
(FastMCP dependency defaults are not resolved on direct calls), like the
diagnostics integration tests.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest

from harold_mcp.maude import MaudeExecutor
from harold_mcp.server.tools.interpreter import (
    MaudeRunError,
    MaudeRunResult,
    MaudeStep,
    ReduceStep,
    RewriteStep,
    maude_run,
)
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
    steps: list[MaudeStep],
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


def test_reduce_then_rewrite_pipeline_threads_the_current_term(
    environment: tuple[MaudeExecutor, Settings],
) -> None:
    result = _run(
        environment,
        "counter.maude",
        "COUNTER",
        [ReduceStep(command="reduce", term="2 * 3"), RewriteStep(command="rewrite", bound=0)],
    )

    assert result.completed is True
    assert [step.term for step in result.steps] == ["6", "6"]
    assert [step.rewrites for step in result.steps] == [1, 0]


def test_rewrite_pipeline_uses_each_previous_result(environment: tuple[MaudeExecutor, Settings]) -> None:
    result = _run(
        environment,
        "counter.maude",
        "COUNTER",
        [RewriteStep(command="rewrite", term="c(0)", bound=1), RewriteStep(command="rewrite", bound=1)],
    )

    assert result.completed is True
    assert [step.term for step in result.steps] == ["c(1)", "c(2)"]
    assert [step.rewrites for step in result.steps] == [2, 2]


def test_failing_middle_step_stops_the_run(environment: tuple[MaudeExecutor, Settings]) -> None:
    result = _run(
        environment,
        "counter.maude",
        "COUNTER",
        [
            ReduceStep(command="reduce", term="2 * 3"),
            ReduceStep(command="reduce", term="nope("),
            ReduceStep(command="reduce", term="1"),
        ],
    )

    assert result.completed is False
    assert len(result.steps) == 2
    assert [step.status for step in result.steps] == ["ok", "parse-error"]
    assert result.steps[1].message is not None
    assert "no parse for term." in result.steps[1].message
