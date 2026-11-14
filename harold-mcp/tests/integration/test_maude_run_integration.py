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
    MatchStep,
    MaudeRunError,
    MaudeRunResult,
    MaudeStep,
    ReduceStep,
    RewriteStep,
    SearchStep,
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


def test_match_and_search_thread_without_changing_the_current_term(
    environment: tuple[MaudeExecutor, Settings],
) -> None:
    result = _run(
        environment,
        "counter.maude",
        "COUNTER",
        [
            RewriteStep(command="rewrite", term="c(0)", bound=2),
            MatchStep(command="match", pattern="c(N)"),
            SearchStep(command="search", pattern="c(N)", depth=2, search_type="any-steps"),
        ],
    )

    assert result.completed is True
    match_outcome = result.steps[1]
    assert match_outcome.term is None
    assert match_outcome.matches is not None
    assert [match.model_dump() for match in match_outcome.matches] == [{"bindings": [{"variable": "N", "value": "2"}]}]
    search_outcome = result.steps[2]
    assert search_outcome.solutions is not None
    # The search starts from the current term set by the rewrite (c(2)).
    assert [solution.term for solution in search_outcome.solutions] == ["c(2)", "c(3)", "c(4)"]
    assert search_outcome.truncated is False


_SHEPHERD_LABELS = [
    "crossWithSheep",
    "crossAlone",
    "crossWithCabbage",
    "crossWithSheep",
    "crossWithDog",
    "crossAlone",
    "crossWithSheep",
]


def _shepherd_step(**overrides: object) -> SearchStep:
    fields: dict[str, object] = {
        "command": "search",
        "pattern": "st(r, r, r, r)",
        "subject": "st(l, l, l, l)",
        "search_type": "any-steps",
    }
    fields.update(overrides)
    return SearchStep(**fields)  # type: ignore[arg-type]


def test_search_path_labels_end_to_end(environment: tuple[MaudeExecutor, Settings]) -> None:
    result = _run(environment, "search_path.maude", "SHEPHERD", [_shepherd_step()])

    assert result.completed is True
    outcome = result.steps[0]
    solution = (outcome.solutions or [])[0]
    assert solution.path is not None
    assert solution.path.initial == "st(l, l, l, l)"
    assert [t.rule.label for t in solution.path.transitions] == _SHEPHERD_LABELS
    assert all(t.rule.text is None and t.state is None for t in solution.path.transitions)


def test_search_path_full_end_to_end(environment: tuple[MaudeExecutor, Settings]) -> None:
    result = _run(environment, "search_path.maude", "SHEPHERD", [_shepherd_step(path="full")])

    solution = (result.steps[0].solutions or [])[0]
    assert solution.path is not None
    assert [t.rule.label for t in solution.path.transitions] == _SHEPHERD_LABELS
    assert all(t.rule.text is not None and t.state is not None for t in solution.path.transitions)
    assert solution.path.transitions[-1].state == solution.term


def test_search_path_none_end_to_end(environment: tuple[MaudeExecutor, Settings]) -> None:
    result = _run(environment, "search_path.maude", "SHEPHERD", [_shepherd_step(path="none")])

    solution = (result.steps[0].solutions or [])[0]
    assert solution.path is None


def test_search_path_normal_form_end_to_end(environment: tuple[MaudeExecutor, Settings]) -> None:
    step = SearchStep(command="search", pattern="c", subject="a", search_type="normal-form", path="full")
    result = _run(environment, "search_path.maude", "BRANCH", [step])

    solution = (result.steps[0].solutions or [])[0]
    assert solution.path is not None
    (transition,) = solution.path.transitions
    assert (transition.rule.label, transition.state) == ("ac", "c")


def test_search_path_cap_overflow_is_a_too_large_step(environment: tuple[MaudeExecutor, Settings]) -> None:
    executor, _ = environment
    settings = Settings(maude_workers=1, interpreter_max_path_steps=2)
    result = maude_run(
        str(FIXTURES_DIR / "search_path.maude"),
        "SHEPHERD",
        [_shepherd_step()],
        executor=executor,
        settings=settings,
    )

    assert result.completed is False
    outcome = result.steps[0]
    assert (outcome.status, outcome.limit) == ("too-large", 2)
    assert outcome.message == "path exceeds interpreter_max_path_steps"
    assert outcome.solutions is None


def test_search_path_element_cap_overflow_is_a_too_large_step(
    environment: tuple[MaudeExecutor, Settings],
) -> None:
    executor, _ = environment
    settings = Settings(maude_workers=1, interpreter_max_result_length=50)
    result = maude_run(
        str(FIXTURES_DIR / "search_path.maude"),
        "SHEPHERD",
        [_shepherd_step(path="full")],
        executor=executor,
        settings=settings,
    )

    assert result.completed is False
    outcome = result.steps[0]
    assert (outcome.status, outcome.limit) == ("too-large", 50)
    assert outcome.message == "path element exceeds interpreter_max_result_length"
    assert outcome.solutions is None


def test_theory_module_is_rejected_as_a_whole_call_error(environment: tuple[MaudeExecutor, Settings]) -> None:
    with pytest.raises(MaudeRunError) as exc_info:
        _ = _run(environment, "theories.maude", "TRIV", [ReduceStep(command="reduce", term="f")])

    message = str(exc_info.value)
    assert 'Module "TRIV" is a theory' in message
    assert "select a functional or system module" in message


def test_module_next_to_a_theory_still_works(environment: tuple[MaudeExecutor, Settings]) -> None:
    result = _run(environment, "theories.maude", "USES-TRIV", [ReduceStep(command="reduce", term="f")])

    assert result.completed is True
    assert result.steps[0].term == "2"
