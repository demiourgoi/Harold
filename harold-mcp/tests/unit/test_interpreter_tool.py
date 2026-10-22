"""Unit tests for the `maude_run` tool (`harold_mcp.server.tools.interpreter`).

The worker is faked (`FakeExecutor`): these tests cover path resolution, input
validation, the request mapping, the result adapter and the whole-call error
mapping. The real interpreter behavior is covered by the integration tests.
"""

from pathlib import Path
from typing import Any, cast

import pytest

from harold_mcp.maude import MaudeWorkerTimeoutError
from harold_mcp.maude.session import SessionRequest, SessionResult, StepOutcomeDict
from harold_mcp.server.tools.interpreter import MaudeRunError, ReduceStep, maude_run
from harold_mcp.settings import Settings


class FakeExecutor:
    """Minimal `MaudeExecutor` stand-in recording session requests and timeouts."""

    def __init__(self, result: SessionResult | None = None, exc: BaseException | None = None) -> None:
        self.result = result if result is not None else _session_result()
        self.exc = exc
        self.calls: list[tuple[SessionRequest, float]] = []

    def run_session(self, request: SessionRequest, timeout: float) -> SessionResult:
        self.calls.append((request, timeout))
        if self.exc is not None:
            raise self.exc
        return self.result


def _session_result(**overrides: Any) -> SessionResult:
    result: dict[str, Any] = {
        "load_ok": True,
        "module_found": True,
        "module_type": 0,
        "defined_modules": ["M"],
        "warnings": [],
        "load_output": {"stdout": "", "stderr": ""},
        "outcomes": [],
    }
    result.update(overrides)
    return cast(SessionResult, result)


def _outcome(**overrides: Any) -> StepOutcomeDict:
    outcome: dict[str, Any] = {
        "index": 0,
        "command": "reduce",
        "status": "ok",
        "term": "2",
        "rewrites": 2,
        "matches": None,
        "solutions": None,
        "truncated": None,
        "message": None,
        "limit": None,
        "output": {"stdout": "", "stderr": ""},
    }
    outcome.update(overrides)
    return cast(StepOutcomeDict, outcome)


def _reduce(term: str | None = None) -> ReduceStep:
    return ReduceStep(command="reduce", term=term)


@pytest.fixture
def maude_file(tmp_path: Path) -> Path:
    path = tmp_path / "hello.maude"
    _ = path.write_text("fmod M is endfm\n", encoding="utf-8")
    return path


def _settings(**overrides: Any) -> Settings:
    return Settings(maude_workers=1, **overrides)


def test_missing_path_raises_before_the_worker(tmp_path: Path) -> None:
    executor = FakeExecutor()

    with pytest.raises(MaudeRunError, match="not found or unreadable"):
        _ = maude_run(str(tmp_path / "missing.maude"), "M", [_reduce("f")], executor=executor, settings=_settings())

    assert executor.calls == []


def test_directory_path_is_rejected(tmp_path: Path) -> None:
    executor = FakeExecutor()

    with pytest.raises(MaudeRunError, match="not found or unreadable"):
        _ = maude_run(str(tmp_path), "M", [_reduce("f")], executor=executor, settings=_settings())

    assert executor.calls == []


def test_empty_steps_are_rejected(maude_file: Path) -> None:
    executor = FakeExecutor()

    with pytest.raises(MaudeRunError, match="at least one command"):
        _ = maude_run(str(maude_file), "M", [], executor=executor, settings=_settings())

    assert executor.calls == []


def test_too_many_steps_are_rejected(maude_file: Path) -> None:
    executor = FakeExecutor()
    settings = _settings(interpreter_max_steps=1)

    with pytest.raises(MaudeRunError, match="Too many steps"):
        _ = maude_run(str(maude_file), "M", [_reduce("f"), _reduce()], executor=executor, settings=settings)

    assert executor.calls == []


def test_term_longer_than_the_cap_is_rejected(maude_file: Path) -> None:
    executor = FakeExecutor()
    settings = _settings(interpreter_max_term_length=3)

    with pytest.raises(MaudeRunError, match="Step 0"):
        _ = maude_run(str(maude_file), "M", [_reduce("abcd")], executor=executor, settings=settings)

    assert executor.calls == []


def test_first_step_without_a_term_is_rejected(maude_file: Path) -> None:
    executor = FakeExecutor()

    with pytest.raises(MaudeRunError, match="Step 0 has no term"):
        _ = maude_run(str(maude_file), "M", [_reduce()], executor=executor, settings=_settings())

    assert executor.calls == []


def test_later_step_may_omit_its_term(maude_file: Path) -> None:
    executor = FakeExecutor(result=_session_result(outcomes=[_outcome(), _outcome(term="2", rewrites=0)]))

    result = maude_run(str(maude_file), "M", [_reduce("f"), _reduce()], executor=executor, settings=_settings())

    assert result.completed is True
    assert [step.term for step in result.steps] == ["2", "2"]


def test_request_carries_the_steps_and_configured_caps(maude_file: Path) -> None:
    executor = FakeExecutor(result=_session_result(outcomes=[_outcome(), _outcome(term="2", rewrites=0)]))
    settings = _settings(
        interpreter_timeout_secs=41,
        interpreter_max_solutions=7,
        interpreter_max_result_length=11,
        interpreter_max_output_length=13,
    )

    _ = maude_run(str(maude_file), "M", [_reduce("f"), _reduce()], executor=executor, settings=settings)

    request, timeout = executor.calls[0]
    assert request["path"] == str(maude_file.resolve())
    assert request["module"] == "M"
    assert request["steps"] == [
        {
            "command": "reduce",
            "term": "f",
            "pattern": None,
            "subject": None,
            "bound": None,
            "gas": None,
            "depth": None,
            "search_type": None,
        },
        {
            "command": "reduce",
            "term": None,
            "pattern": None,
            "subject": None,
            "bound": None,
            "gas": None,
            "depth": None,
            "search_type": None,
        },
    ]
    assert request["max_solutions"] == 7
    assert request["max_result_length"] == 11
    assert request["max_output_length"] == 13
    assert timeout == 41


def test_timeout_secs_overrides_the_setting(maude_file: Path) -> None:
    executor = FakeExecutor(result=_session_result(outcomes=[_outcome()]))
    settings = _settings(interpreter_timeout_secs=41)

    _ = maude_run(str(maude_file), "M", [_reduce("f")], timeout_secs=9, executor=executor, settings=settings)

    assert executor.calls[0][1] == 9


def test_ok_result_is_adapted(maude_file: Path) -> None:
    session = _session_result(
        warnings=[{"file": "hello.maude", "line": 2, "message": "missing is keyword."}],
        load_output={"stdout": "load out", "stderr": "load err"},
        outcomes=[
            _outcome(
                term="2",
                rewrites=3,
                output={"stdout": "step out", "stderr": "step err"},
            )
        ],
    )

    result = maude_run(str(maude_file), "M", [_reduce("f")], executor=FakeExecutor(session), settings=_settings())

    assert result.path == str(maude_file.resolve())
    assert result.module == "M"
    assert result.completed is True
    assert [warning.model_dump() for warning in result.load.warnings] == [
        {"file": "hello.maude", "line": 2, "message": "missing is keyword."}
    ]
    assert result.load.output.model_dump() == {"stdout": "load out", "stderr": "load err"}
    outcome = result.steps[0]
    assert (outcome.index, outcome.command, outcome.status) == (0, "reduce", "ok")
    assert (outcome.term, outcome.rewrites, outcome.message, outcome.limit) == ("2", 3, None, None)
    assert outcome.output.model_dump() == {"stdout": "step out", "stderr": "step err"}


def test_parse_error_outcome_is_adapted(maude_file: Path) -> None:
    session = _session_result(
        outcomes=[_outcome(status="parse-error", term=None, rewrites=None, message="no parse for term.")]
    )

    result = maude_run(str(maude_file), "M", [_reduce("nope(3)")], executor=FakeExecutor(session), settings=_settings())

    assert result.completed is False
    outcome = result.steps[0]
    assert (outcome.status, outcome.term, outcome.message) == ("parse-error", None, "no parse for term.")


def test_too_large_outcome_is_adapted(maude_file: Path) -> None:
    session = _session_result(outcomes=[_outcome(status="too-large", term=None, rewrites=None, limit=1)])

    result = maude_run(str(maude_file), "M", [_reduce("f")], executor=FakeExecutor(session), settings=_settings())

    assert result.completed is False
    outcome = result.steps[0]
    assert (outcome.status, outcome.limit) == ("too-large", 1)


def test_load_failure_is_a_whole_call_error(maude_file: Path) -> None:
    session = _session_result(load_ok=False, load_output={"stdout": "", "stderr": "boom"}, outcomes=[])

    with pytest.raises(MaudeRunError, match="boom"):
        _ = maude_run(str(maude_file), "M", [_reduce("f")], executor=FakeExecutor(session), settings=_settings())


def test_missing_module_error_lists_the_defined_modules(maude_file: Path) -> None:
    session = _session_result(module_found=False, defined_modules=["A", "B"], outcomes=[])

    with pytest.raises(MaudeRunError) as exc_info:
        _ = maude_run(str(maude_file), "NOPE", [_reduce("f")], executor=FakeExecutor(session), settings=_settings())

    message = str(exc_info.value)
    assert 'Module "NOPE"' in message
    assert "A, B" in message
    assert "maude_program_diagnostics" in message


def test_missing_module_error_reports_when_nothing_was_defined(maude_file: Path) -> None:
    session = _session_result(module_found=False, defined_modules=[], outcomes=[])

    with pytest.raises(MaudeRunError, match="none"):
        _ = maude_run(str(maude_file), "NOPE", [_reduce("f")], executor=FakeExecutor(session), settings=_settings())


def test_theory_module_is_rejected(maude_file: Path) -> None:
    session = _session_result(module_type=2, outcomes=[])

    with pytest.raises(MaudeRunError, match="theory"):
        _ = maude_run(str(maude_file), "TRIV", [_reduce("f")], executor=FakeExecutor(session), settings=_settings())


def test_worker_error_is_chained(maude_file: Path) -> None:
    cause = MaudeWorkerTimeoutError()
    executor = FakeExecutor(exc=cause)

    with pytest.raises(MaudeRunError, match="timed out") as exc_info:
        _ = maude_run(str(maude_file), "M", [_reduce("f")], executor=executor, settings=_settings())

    assert exc_info.value.__cause__ is cause


def test_unexpected_exception_is_chained(maude_file: Path) -> None:
    cause = ValueError("boom")
    executor = FakeExecutor(exc=cause)

    with pytest.raises(MaudeRunError, match="Unexpected failure") as exc_info:
        _ = maude_run(str(maude_file), "M", [_reduce("f")], executor=executor, settings=_settings())

    assert exc_info.value.__cause__ is cause
