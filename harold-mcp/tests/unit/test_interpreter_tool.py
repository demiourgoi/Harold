"""Unit tests for the `maude_run` tool (`harold_mcp.server.tools.interpreter`).

The worker is faked (`FakeExecutor`): these tests cover path resolution, input
validation, the request mapping, the result adapter and the whole-call error
mapping. The real interpreter behavior is covered by the integration tests.
"""

import inspect
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

import harold_mcp.server.tools.interpreter as interpreter_module
from harold_mcp.errors import TRUNCATION_MARKER
from harold_mcp.maude import (
    MaudeInitError,
    MaudeWorkerCancelledError,
    MaudeWorkerCrashedError,
    MaudeWorkerError,
    MaudeWorkerProtocolError,
    MaudeWorkerRemoteError,
    MaudeWorkerSpawnError,
    MaudeWorkerTimeoutError,
)
from harold_mcp.maude.session import SessionRequest, SessionResult, StepOutcomeDict
from harold_mcp.server.tools.interpreter import (
    ErewriteStep,
    FrewriteStep,
    MatchStep,
    MaudeRunError,
    ReduceStep,
    RewriteStep,
    SearchStep,
    maude_run,
)
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


class _RecordingLogger:
    """Capture `error`/`exception` calls instead of emitting them to the test log."""

    def __init__(self) -> None:
        self.errors: list[tuple[str, tuple[object, ...]]] = []
        self.exceptions: list[tuple[str, tuple[object, ...]]] = []

    def error(self, message: str, *args: object) -> None:
        self.errors.append((message, args))

    def exception(self, message: str, *args: object) -> None:
        self.exceptions.append((message, args))


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


def test_maude_run_description_does_not_mention_a_worker_pool() -> None:
    """The description must reflect per-call processes, not the removed pool."""
    description = inspect.getdoc(maude_run) or ""

    assert "worker pool" not in description
    assert "admission" in description
    assert "spawn-failure" in description
    assert "protocol-error" in description


def test_missing_path_raises_before_the_worker(tmp_path: Path) -> None:
    executor = FakeExecutor()
    missing = tmp_path / "missing.maude"

    with pytest.raises(MaudeRunError, match="not found or unreadable") as exc_info:
        _ = maude_run(str(missing), "M", [_reduce("f")], executor=executor, settings=_settings())

    message = str(exc_info.value)
    assert f"context: path={missing.resolve()}" in message
    assert "module=M" in message
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


def test_rewriting_steps_forward_bound_and_gas(maude_file: Path) -> None:
    executor = FakeExecutor(
        result=_session_result(
            outcomes=[
                _outcome(command="rewrite", term="c(0)", rewrites=0),
                _outcome(index=1, command="frewrite", term="c(1)", rewrites=2),
                _outcome(index=2, command="erewrite", term="c(1)", rewrites=2),
            ]
        )
    )
    steps = [
        RewriteStep(command="rewrite", term="c(0)", bound=0),
        FrewriteStep(command="frewrite", term="c(0)", bound=3, gas=7),
        ErewriteStep(command="erewrite", term="c(0)"),
    ]

    _ = maude_run(str(maude_file), "M", steps, executor=executor, settings=_settings())

    request = executor.calls[0][0]
    assert [(step["command"], step["bound"], step["gas"]) for step in request["steps"]] == [
        ("rewrite", 0, None),
        ("frewrite", 3, 7),
        ("erewrite", None, None),
    ]


def test_rewriting_steps_may_omit_the_term_after_the_first(maude_file: Path) -> None:
    executor = FakeExecutor(
        result=_session_result(
            outcomes=[_outcome(term="2", rewrites=2), _outcome(index=1, command="erewrite", term="2", rewrites=0)]
        )
    )
    steps = [RewriteStep(command="rewrite", term="f"), ErewriteStep(command="erewrite")]

    result = maude_run(str(maude_file), "M", steps, executor=executor, settings=_settings())

    assert result.completed is True
    assert [step.term for step in result.steps] == ["2", "2"]


def test_bound_above_the_cap_is_rejected(maude_file: Path) -> None:
    executor = FakeExecutor()
    settings = _settings(interpreter_max_rewrite_bound=5)
    steps = [RewriteStep(command="rewrite", term="f", bound=6)]

    with pytest.raises(MaudeRunError, match="bound is 6"):
        _ = maude_run(str(maude_file), "M", steps, executor=executor, settings=settings)

    assert executor.calls == []


def test_negative_bound_or_gas_is_rejected_by_the_model() -> None:
    with pytest.raises(ValidationError):
        _ = RewriteStep(command="rewrite", term="f", bound=-1)
    with pytest.raises(ValidationError):
        _ = FrewriteStep(command="frewrite", term="f", gas=-1)


def test_match_step_requires_a_pattern() -> None:
    with pytest.raises(ValidationError):
        _ = MatchStep(command="match")


def test_search_step_requires_a_pattern_and_a_search_type() -> None:
    with pytest.raises(ValidationError):
        _ = SearchStep(command="search", search_type="any-steps")
    with pytest.raises(ValidationError):
        _ = SearchStep(command="search", pattern="X")


@pytest.mark.parametrize("depth", [-2, 2_147_483_648])
def test_depth_outside_the_int32_range_is_rejected(depth: int) -> None:
    with pytest.raises(ValidationError):
        _ = MatchStep(command="match", pattern="X", depth=depth)


def test_depth_at_the_documented_bounds_is_accepted() -> None:
    assert MatchStep(command="match", pattern="X", depth=-1).depth == -1
    assert MatchStep(command="match", pattern="X", depth=2_147_483_647).depth == 2_147_483_647


def test_first_match_without_a_subject_is_rejected(maude_file: Path) -> None:
    executor = FakeExecutor()

    with pytest.raises(MaudeRunError, match="Step 0 has no subject"):
        _ = maude_run(
            str(maude_file), "M", [MatchStep(command="match", pattern="X")], executor=executor, settings=_settings()
        )

    assert executor.calls == []


def test_match_does_not_create_a_current_term(maude_file: Path) -> None:
    executor = FakeExecutor()
    steps = [MatchStep(command="match", pattern="X", subject="1"), ReduceStep(command="reduce")]

    with pytest.raises(MaudeRunError, match="Step 1 has no term"):
        _ = maude_run(str(maude_file), "M", steps, executor=executor, settings=_settings())

    assert executor.calls == []


def test_pattern_and_subject_lengths_are_capped(maude_file: Path) -> None:
    settings = _settings(interpreter_max_term_length=3)

    with pytest.raises(MaudeRunError, match="pattern"):
        _ = maude_run(
            str(maude_file),
            "M",
            [MatchStep(command="match", pattern="abcd")],
            executor=FakeExecutor(),
            settings=settings,
        )

    with pytest.raises(MaudeRunError, match="subject"):
        _ = maude_run(
            str(maude_file),
            "M",
            [MatchStep(command="match", pattern="x", subject="abcd")],
            executor=FakeExecutor(),
            settings=settings,
        )


def test_search_step_forwards_pattern_subject_depth_and_type(maude_file: Path) -> None:
    executor = FakeExecutor(
        result=_session_result(
            outcomes=[
                _outcome(
                    command="search",
                    term=None,
                    rewrites=None,
                    solutions=[],
                    truncated=False,
                )
            ]
        )
    )
    step = SearchStep(command="search", pattern="c(N)", subject="c(0)", depth=2, search_type="any-steps")

    _ = maude_run(str(maude_file), "M", [step], executor=executor, settings=_settings())

    assert executor.calls[0][0]["steps"] == [
        {
            "command": "search",
            "term": None,
            "pattern": "c(N)",
            "subject": "c(0)",
            "bound": None,
            "gas": None,
            "depth": 2,
            "search_type": "any-steps",
            "path_mode": "labels",
        }
    ]


def test_request_carries_the_steps_and_configured_caps(maude_file: Path) -> None:
    executor = FakeExecutor(result=_session_result(outcomes=[_outcome(), _outcome(term="2", rewrites=0)]))
    settings = _settings(
        interpreter_timeout_secs=41,
        interpreter_max_solutions=7,
        interpreter_max_result_length=11,
        interpreter_max_path_steps=3,
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
            "path_mode": None,
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
            "path_mode": None,
        },
    ]
    assert request["max_solutions"] == 7
    assert request["max_result_length"] == 11
    assert request["max_path_steps"] == 3
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


@pytest.mark.parametrize(
    ("step", "command"),
    [
        (RewriteStep(command="rewrite", term="c(0)"), "rewrite"),
        (FrewriteStep(command="frewrite", term="c(0)"), "frewrite"),
        (ErewriteStep(command="erewrite", term="c(0)"), "erewrite"),
    ],
)
def test_rewriting_outcome_is_adapted(maude_file: Path, step: Any, command: str) -> None:
    session = _session_result(outcomes=[_outcome(command=command, term="c(1)", rewrites=4)])

    result = maude_run(str(maude_file), "M", [step], executor=FakeExecutor(session), settings=_settings())

    outcome = result.steps[0]
    assert (outcome.command, outcome.term, outcome.rewrites) == (command, "c(1)", 4)


def test_match_outcome_is_adapted(maude_file: Path) -> None:
    session = _session_result(
        outcomes=[
            _outcome(
                command="match",
                term=None,
                rewrites=None,
                matches=[[{"variable": "N", "value": "5"}], []],
                truncated=False,
            )
        ]
    )

    result = maude_run(
        str(maude_file),
        "M",
        [MatchStep(command="match", pattern="c(N)", subject="c(5)")],
        executor=FakeExecutor(session),
        settings=_settings(),
    )

    outcome = result.steps[0]
    assert outcome.term is None
    assert outcome.rewrites is None
    assert outcome.truncated is False
    assert [match.model_dump() for match in outcome.matches or []] == [
        {"bindings": [{"variable": "N", "value": "5"}]},
        {"bindings": []},
    ]


def test_search_outcome_is_adapted(maude_file: Path) -> None:
    session = _session_result(
        outcomes=[
            _outcome(
                command="search",
                term=None,
                rewrites=None,
                solutions=[
                    {
                        "term": "c(1)",
                        "rewrites": 2,
                        "bindings": [{"variable": "N", "value": "1"}],
                        "path": None,
                    }
                ],
                truncated=True,
            )
        ]
    )

    result = maude_run(
        str(maude_file),
        "M",
        [SearchStep(command="search", pattern="c(N)", subject="c(0)", search_type="any-steps")],
        executor=FakeExecutor(session),
        settings=_settings(),
    )

    outcome = result.steps[0]
    assert outcome.truncated is True
    assert [solution.model_dump() for solution in outcome.solutions or []] == [
        {
            "term": "c(1)",
            "rewrites": 2,
            "bindings": [{"variable": "N", "value": "1"}],
            "path": None,
        }
    ]


def test_search_step_path_defaults_to_labels_and_rejects_unknown_values() -> None:
    step = SearchStep(command="search", pattern="c(N)", search_type="any-steps")
    assert step.path == "labels"

    with pytest.raises(ValidationError):
        _ = SearchStep(command="search", pattern="c(N)", search_type="any-steps", path="bogus")


def test_search_step_forwards_the_path_mode(maude_file: Path) -> None:
    executor = FakeExecutor(
        result=_session_result(
            outcomes=[_outcome(command="search", term=None, rewrites=None, solutions=[], truncated=False)]
        )
    )

    for mode in ("full", "none"):
        step = SearchStep(command="search", pattern="c(N)", subject="c(0)", search_type="any-steps", path=mode)
        _ = maude_run(str(maude_file), "M", [step], executor=executor, settings=_settings())

    assert [call[0]["steps"][0]["path_mode"] for call in executor.calls] == ["full", "none"]


def test_full_path_with_an_unlabeled_rule_is_adapted(maude_file: Path) -> None:
    session = _session_result(
        outcomes=[
            _outcome(
                command="search",
                term=None,
                rewrites=None,
                solutions=[
                    {
                        "term": "b",
                        "rewrites": 1,
                        "bindings": [],
                        "path": {
                            "initial": "a",
                            "transitions": [{"rule": {"label": None, "text": "rl a => b ."}, "state": "b"}],
                        },
                    }
                ],
                truncated=False,
            )
        ]
    )

    result = maude_run(
        str(maude_file),
        "M",
        [SearchStep(command="search", pattern="b", subject="a", search_type="one-step", path="full")],
        executor=FakeExecutor(session),
        settings=_settings(),
    )

    solution = (result.steps[0].solutions or [])[0]
    assert solution.path is not None
    assert solution.path.model_dump() == {
        "initial": "a",
        "transitions": [{"rule": {"label": None, "text": "rl a => b ."}, "state": "b"}],
    }


def test_too_large_path_cap_outcome_is_adapted(maude_file: Path) -> None:
    session = _session_result(
        outcomes=[
            _outcome(
                command="search",
                term=None,
                rewrites=None,
                status="too-large",
                solutions=None,
                limit=100,
                message="path exceeds interpreter_max_path_steps",
            )
        ]
    )

    result = maude_run(
        str(maude_file),
        "M",
        [SearchStep(command="search", pattern="c(N)", subject="c(0)", search_type="any-steps")],
        executor=FakeExecutor(session),
        settings=_settings(),
    )

    outcome = result.steps[0]
    assert outcome.status == "too-large"
    assert outcome.limit == 100
    assert outcome.message == "path exceeds interpreter_max_path_steps"
    assert outcome.solutions is None


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

    with pytest.raises(MaudeRunError, match="boom") as exc_info:
        _ = maude_run(str(maude_file), "M", [_reduce("f")], executor=FakeExecutor(session), settings=_settings())

    assert "context: path=" in str(exc_info.value)


def test_missing_module_error_lists_the_defined_modules(maude_file: Path) -> None:
    session = _session_result(module_found=False, defined_modules=["A", "B"], outcomes=[])

    with pytest.raises(MaudeRunError) as exc_info:
        _ = maude_run(str(maude_file), "NOPE", [_reduce("f")], executor=FakeExecutor(session), settings=_settings())

    message = str(exc_info.value)
    assert 'Module "NOPE"' in message
    assert "A, B" in message
    assert "maude_program_diagnostics" in message
    assert message.splitlines()[1].startswith("context: path=")
    assert "module=NOPE" in message


def test_missing_module_error_reports_when_nothing_was_defined(maude_file: Path) -> None:
    session = _session_result(module_found=False, defined_modules=[], outcomes=[])

    with pytest.raises(MaudeRunError, match="none"):
        _ = maude_run(str(maude_file), "NOPE", [_reduce("f")], executor=FakeExecutor(session), settings=_settings())


def test_theory_module_is_rejected(maude_file: Path) -> None:
    session = _session_result(module_type=2, outcomes=[])

    with pytest.raises(MaudeRunError, match="theory") as exc_info:
        _ = maude_run(str(maude_file), "TRIV", [_reduce("f")], executor=FakeExecutor(session), settings=_settings())

    message = str(exc_info.value)
    assert 'Module "TRIV" is a theory' in message
    assert message.splitlines()[1].startswith("context: path=")


def test_worker_error_is_chained(maude_file: Path) -> None:
    cause = MaudeWorkerTimeoutError()
    executor = FakeExecutor(exc=cause)

    with pytest.raises(MaudeRunError, match="timed out") as exc_info:
        _ = maude_run(str(maude_file), "M", [_reduce("f")], executor=executor, settings=_settings())

    message = str(exc_info.value)
    assert message.splitlines()[0] == "Maude interpreter session failed: timeout: Maude worker timed out"
    assert "context: path=" in message
    assert "module=M" in message
    assert "steps=1" in message
    assert "timeout=60s" in message
    assert "cause: MaudeWorkerTimeoutError: Maude worker timed out" in message
    assert exc_info.value.__cause__ is cause


@pytest.mark.parametrize(
    ("error", "category"),
    [
        (MaudeInitError(), "init-failure"),
        (MaudeWorkerCrashedError(), "crash"),
        (MaudeWorkerTimeoutError(), "timeout"),
        (MaudeWorkerSpawnError(), "spawn-failure"),
        (MaudeWorkerRemoteError("ValueError", "boom"), "remote-exception"),
        (MaudeWorkerCancelledError(), "cancelled"),
        (MaudeWorkerProtocolError(), "protocol-error"),
    ],
)
def test_worker_error_categories_reach_the_client(maude_file: Path, error: MaudeWorkerError, category: str) -> None:
    with pytest.raises(MaudeRunError) as exc_info:
        _ = maude_run(str(maude_file), "M", [_reduce("f")], executor=FakeExecutor(exc=error), settings=_settings())

    first_line = str(exc_info.value).splitlines()[0]
    assert first_line.startswith(f"Maude interpreter session failed: {category}: ")
    assert exc_info.value.__cause__ is error


def test_remote_error_report_includes_type_context_cause_and_traceback(maude_file: Path) -> None:
    remote = MaudeWorkerRemoteError(
        "ValueError",
        "boom",
        remote_traceback='Traceback (most recent call last):\n  File "worker.py", line 1\nValueError: boom\n',
        context={"phase": "step", "step": 0, "command": "reduce", "pid": 4242},
    )

    with pytest.raises(MaudeRunError) as exc_info:
        _ = maude_run(str(maude_file), "M", [_reduce("f")], executor=FakeExecutor(exc=remote), settings=_settings())

    message = str(exc_info.value)
    assert message.splitlines()[0] == "Maude interpreter session failed: remote-exception: ValueError: boom"
    assert "phase=step" in message
    assert "step=0" in message
    assert "command=reduce" in message
    assert "pid=4242" in message
    assert "cause: MaudeWorkerRemoteError: ValueError: boom <- ValueError: boom" in message
    assert "traceback:\nTraceback (most recent call last):" in message


def test_worker_error_is_capped_and_logged_in_full(maude_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    logger = _RecordingLogger()
    monkeypatch.setattr(interpreter_module, "_log", logger)
    remote = MaudeWorkerRemoteError("ValueError", "boom", remote_traceback="X" * 5000)
    prefix = "Maude interpreter session failed: "

    with pytest.raises(MaudeRunError) as exc_info:
        _ = maude_run(
            str(maude_file),
            "M",
            [_reduce("f")],
            executor=FakeExecutor(exc=remote),
            settings=_settings(error_detail_max_chars=300),
        )

    message = str(exc_info.value)
    assert len(message) <= len(prefix) + 300
    assert message.rstrip().endswith(TRUNCATION_MARKER)
    assert len(logger.errors) == 1
    full_report = cast(str, logger.errors[0][1][2])
    assert "X" * 5000 in full_report
    assert TRUNCATION_MARKER not in full_report


def test_unexpected_exception_is_chained(maude_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    logger = _RecordingLogger()
    monkeypatch.setattr(interpreter_module, "_log", logger)
    cause = ValueError("boom")
    executor = FakeExecutor(exc=cause)

    with pytest.raises(MaudeRunError, match="Unexpected failure") as exc_info:
        _ = maude_run(str(maude_file), "M", [_reduce("f")], executor=executor, settings=_settings())

    message = str(exc_info.value)
    assert message.splitlines()[0] == "Unexpected failure running the Maude interpreter session: ValueError: boom"
    assert "context: path=" in message
    assert exc_info.value.__cause__ is cause
    assert len(logger.exceptions) == 1
    log_message, log_args = logger.exceptions[0]
    assert log_message == "Unexpected failure running the Maude interpreter session for %s (module %s):\n%s"
    assert log_args[0] == maude_file.resolve()
    assert log_args[1] == "M"
    assert "ValueError: boom" in cast(str, log_args[2])


def test_unexpected_exception_without_a_message_names_its_type(maude_file: Path) -> None:
    cause = RuntimeError()
    executor = FakeExecutor(exc=cause)

    with pytest.raises(MaudeRunError) as exc_info:
        _ = maude_run(str(maude_file), "M", [_reduce("f")], executor=executor, settings=_settings())

    assert (
        str(exc_info.value).splitlines()[0] == "Unexpected failure running the Maude interpreter session: RuntimeError"
    )
    assert exc_info.value.__cause__ is cause
