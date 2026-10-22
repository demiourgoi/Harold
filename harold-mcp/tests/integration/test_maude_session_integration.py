"""Integration tests for the bounded interpreter session (`maude.session.run_session`).

Every call goes through `MaudeExecutor`, so these tests exercise the real spawned
worker, interpreter initialization, file loading and the per-call hermeticity
guarantee (`max_tasks_per_child=1`). The session engine itself only supports
`reduce` for now.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest

from harold_mcp.maude import MaudeExecutor
from harold_mcp.maude.capture import TRUNCATION_MARKER
from harold_mcp.maude.session import SessionRequest, SessionResult, StepOutcomeDict, StepRequest
from harold_mcp.settings import Settings

FIXTURES_DIR = Path(__file__).parent / "fixtures"
CALL_TIMEOUT_SECS = 60


@pytest.fixture(scope="module")
def executor() -> Iterator[MaudeExecutor]:
    settings = Settings(maude_workers=1)
    resolved = MaudeExecutor(settings=settings)
    resolved.start(settings.diagnostics_timeout_secs)
    try:
        yield resolved
    finally:
        resolved.shutdown()


def _run(executor: MaudeExecutor, request: SessionRequest) -> SessionResult:
    return executor.run_session(request, timeout=CALL_TIMEOUT_SECS)


def _reduce(term: str | None) -> StepRequest:
    return {
        "command": "reduce",
        "term": term,
        "pattern": None,
        "subject": None,
        "bound": None,
        "gas": None,
        "depth": None,
        "search_type": None,
    }


def _request(
    fixture_name: str,
    module: str,
    steps: list[StepRequest],
    *,
    max_result_length: int = 1_000_000,
    max_output_length: int = 1_000_000,
) -> SessionRequest:
    return {
        "path": str(FIXTURES_DIR / fixture_name),
        "module": module,
        "steps": steps,
        "max_solutions": 200,
        "max_result_length": max_result_length,
        "max_output_length": max_output_length,
    }


def _single_outcome(result: SessionResult) -> StepOutcomeDict:
    assert len(result["outcomes"]) == 1
    return result["outcomes"][0]


def test_reduce_hello_world(executor: MaudeExecutor) -> None:
    result = _run(executor, _request("hello.maude", "HELLO-WORLD", [_reduce("f")]))

    assert result["load_ok"] is True
    assert result["module_found"] is True
    assert result["module_type"] == 0  # FUNCTIONAL_MODULE
    assert result["defined_modules"] == ["HELLO-WORLD"]
    assert result["warnings"] == []
    assert result["load_output"] == {"stdout": "", "stderr": ""}
    outcome = _single_outcome(result)
    assert outcome["status"] == "ok"
    assert outcome["term"] == "2"
    assert isinstance(outcome["rewrites"], int)
    assert outcome["rewrites"] > 0
    assert outcome["output"] == {"stdout": "", "stderr": ""}


def test_reduce_without_a_term_uses_the_current_term(executor: MaudeExecutor) -> None:
    result = _run(executor, _request("hello.maude", "HELLO-WORLD", [_reduce("100 * 100"), _reduce(None)]))

    assert [outcome["status"] for outcome in result["outcomes"]] == ["ok", "ok"]
    assert [outcome["term"] for outcome in result["outcomes"]] == ["10000", "10000"]
    # The second reduction is a no-op on an already-normal term.
    assert result["outcomes"][1]["rewrites"] == 0


def test_parse_error_is_an_outcome_not_a_whole_call_failure(executor: MaudeExecutor) -> None:
    result = _run(executor, _request("hello.maude", "HELLO-WORLD", [_reduce("nope(3)")]))

    assert result["load_ok"] is True
    outcome = _single_outcome(result)
    assert outcome["status"] == "parse-error"
    assert outcome["term"] is None
    message = str(outcome["message"])
    assert "bad token nope" in message
    assert "no parse for term." in message


def test_missing_module_reports_the_defined_modules(executor: MaudeExecutor) -> None:
    result = _run(executor, _request("hello.maude", "NOPE", []))

    assert result["load_ok"] is True
    assert result["module_found"] is False
    assert result["defined_modules"] == ["HELLO-WORLD"]
    assert result["outcomes"] == []


def test_load_warnings_are_reported_and_evaluation_proceeds(executor: MaudeExecutor) -> None:
    result = _run(executor, _request("broken-recoverable.maude", "HELLO-WORLD", [_reduce("f")]))

    assert result["warnings"] == [{"file": "broken-recoverable.maude", "line": 2, "message": "missing is keyword."}]
    assert result["module_found"] is True
    outcome = _single_outcome(result)
    assert outcome["status"] == "ok"
    assert outcome["term"] == "2"


def test_embedded_red_output_appears_in_the_load_capture(executor: MaudeExecutor) -> None:
    result = _run(executor, _request("warns_and_prints.maude", "WARNS-AND-PRINTS", []))

    stdout = result["load_output"]["stdout"]
    assert "reduce in WARNS-AND-PRINTS : f ." in stdout
    assert "result NzNat: 2" in stdout
    assert "Warning:" not in stdout
    assert result["warnings"] == [{"file": "warns_and_prints.maude", "line": 2, "message": "missing is keyword."}]


def test_too_large_result_is_an_outcome(executor: MaudeExecutor) -> None:
    result = _run(executor, _request("hello.maude", "HELLO-WORLD", [_reduce("100 * 100")], max_result_length=1))

    outcome = _single_outcome(result)
    assert outcome["status"] == "too-large"
    assert outcome["limit"] == 1
    assert outcome["term"] is None


def test_output_truncation_does_not_hide_warnings(executor: MaudeExecutor) -> None:
    result = _run(executor, _request("warns_and_prints.maude", "WARNS-AND-PRINTS", [], max_output_length=10))

    stdout = result["load_output"]["stdout"]
    assert stdout.endswith(TRUNCATION_MARKER)
    assert len(stdout) == 10 + len(TRUNCATION_MARKER)
    # Warnings are parsed from the full stderr, before the returned capture is truncated.
    assert result["warnings"] == [{"file": "warns_and_prints.maude", "line": 2, "message": "missing is keyword."}]


def test_sessions_are_hermetic(executor: MaudeExecutor) -> None:
    first = _run(executor, _request("hello.maude", "HELLO-WORLD", [_reduce("f")]))
    assert first["module_found"] is True
    assert first["defined_modules"] == ["HELLO-WORLD"]

    # HELLO-WORLD was defined by the previous call, but nothing survives across calls.
    second = _run(executor, _request("warns_and_prints.maude", "HELLO-WORLD", []))
    assert second["module_found"] is False
    assert second["defined_modules"] == ["WARNS-AND-PRINTS"]
