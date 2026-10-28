"""Integration tests for the bounded interpreter session (`maude.session.run_session`).

Every call goes through `MaudeExecutor`, so these tests exercise the real spawned
worker, interpreter initialization, file loading and the per-call hermeticity
guarantee (`max_tasks_per_child=1`). The session engine supports the rewriting family
and the `match`/`search` commands.
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


def _step(
    command: str,
    term: str | None = None,
    *,
    pattern: str | None = None,
    subject: str | None = None,
    bound: int | None = None,
    gas: int | None = None,
    depth: int | None = None,
    search_type: str | None = None,
) -> StepRequest:
    return {
        "command": command,
        "term": term,
        "pattern": pattern,
        "subject": subject,
        "bound": bound,
        "gas": gas,
        "depth": depth,
        "search_type": search_type,
    }


def _reduce(term: str | None) -> StepRequest:
    return _step("reduce", term)


def _request(
    fixture_name: str,
    module: str,
    steps: list[StepRequest],
    *,
    max_solutions: int = 200,
    max_result_length: int = 1_000_000,
    max_output_length: int = 1_000_000,
) -> SessionRequest:
    return {
        "path": str(FIXTURES_DIR / fixture_name),
        "module": module,
        "steps": steps,
        "max_solutions": max_solutions,
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


def test_rewriting_family_values_and_counters(executor: MaudeExecutor) -> None:
    result = _run(
        executor,
        _request(
            "counter.maude",
            "COUNTER",
            [
                _step("reduce", "2 * 3"),
                _step("rewrite", "c(0)", bound=3),
                _step("frewrite", "c(0)", bound=3),
                _step("erewrite", "c(0)", bound=3),
            ],
        ),
    )

    outcomes = result["outcomes"]
    assert [outcome["status"] for outcome in outcomes] == ["ok"] * 4
    assert [outcome["term"] for outcome in outcomes] == ["6", "c(3)", "c(3)", "c(3)"]
    # The counter includes equational rewrites: each rule step costs 2 here.
    assert [outcome["rewrites"] for outcome in outcomes] == [1, 6, 6, 6]


def test_rewrite_bound_zero_leaves_the_term_unchanged(executor: MaudeExecutor) -> None:
    result = _run(executor, _request("counter.maude", "COUNTER", [_step("rewrite", "c(0)", bound=0)]))

    outcome = _single_outcome(result)
    assert (outcome["status"], outcome["term"], outcome["rewrites"]) == ("ok", "c(0)", 0)


def test_explicit_gas_reaches_the_interpreter(executor: MaudeExecutor) -> None:
    result = _run(
        executor,
        _request(
            "counter.maude",
            "COUNTER",
            [
                _step("frewrite", "c(0)", bound=3, gas=0),
                _step("erewrite", "c(0)", bound=3, gas=0),
            ],
        ),
    )

    outcomes = result["outcomes"]
    assert [outcome["status"] for outcome in outcomes] == ["ok", "ok"]
    # gas=0 allows no rewrites per position, so the term stays unchanged. If the
    # value were dropped (bindings default 1), both would reach c(3) with 6 rewrites.
    assert [(outcome["term"], outcome["rewrites"]) for outcome in outcomes] == [("c(0)", 0), ("c(0)", 0)]


def test_erewrite_threads_the_returned_term(executor: MaudeExecutor) -> None:
    result = _run(
        executor,
        _request("counter.maude", "COUNTER", [_step("erewrite", "c(0)", bound=3), _step("rewrite", bound=1)]),
    )

    outcomes = result["outcomes"]
    # `erewrite` leaves its subject untouched and returns a new term; the next step
    # starts from that returned term (`c(3)`), not from the original `c(0)`.
    assert [outcome["term"] for outcome in outcomes] == ["c(3)", "c(4)"]
    assert [outcome["rewrites"] for outcome in outcomes] == [6, 2]


def test_match_hit_and_miss(executor: MaudeExecutor) -> None:
    result = _run(
        executor,
        _request(
            "counter.maude",
            "COUNTER",
            [
                _step("match", pattern="c(N)", subject="c(5)"),
                _step("match", pattern="c(6)", subject="c(5)"),
            ],
        ),
    )

    hit, miss = result["outcomes"]
    assert hit["status"] == "ok"
    assert hit["matches"] == [[{"variable": "N", "value": "5"}]]
    assert hit["truncated"] is False
    assert hit["term"] is None
    assert hit["rewrites"] is None
    assert miss["matches"] == []
    assert miss["truncated"] is False


def test_match_depth_modes_on_an_assoc_module(executor: MaudeExecutor) -> None:
    result = _run(
        executor,
        _request(
            "assoc_match.maude",
            "ASSOC-MATCH",
            [
                _step("match", pattern="2 ; X", subject="1 ; 2 ; 3"),
                _step("match", pattern="2 ; X", subject="1 ; 2 ; 3", depth=0),
                _step("match", pattern="1 ; 2 ; 3", subject="wrap(1 ; 2 ; 3)"),
                _step("match", pattern="1 ; 2 ; 3", subject="wrap(1 ; 2 ; 3)", depth=2_147_483_647),
            ],
        ),
    )

    outcomes = result["outcomes"]
    # -1 matches on top without extension; 0 enables extension matching.
    assert outcomes[0]["matches"] == []
    assert outcomes[1]["matches"] == [[{"variable": "X", "value": "3"}]]
    # 2147483647 (maude.UNBOUNDED) also matches subterms anywhere.
    assert outcomes[2]["matches"] == []
    assert outcomes[3]["matches"] == [[]]


def test_match_does_not_change_the_current_term(executor: MaudeExecutor) -> None:
    result = _run(
        executor,
        _request(
            "counter.maude",
            "COUNTER",
            [
                _step("rewrite", "c(0)", bound=1),
                _step("match", pattern="c(N)"),
                _step("rewrite", bound=1),
            ],
        ),
    )

    outcomes = result["outcomes"]
    assert [outcome["term"] for outcome in outcomes] == ["c(1)", None, "c(2)"]
    assert outcomes[1]["matches"] == [[{"variable": "N", "value": "1"}]]
    # The match left the current term at c(1), so the last rewrite reaches c(2).
    assert outcomes[2]["rewrites"] == 2


def test_search_types_and_ground_targets(executor: MaudeExecutor) -> None:
    result = _run(
        executor,
        _request(
            "counter.maude",
            "COUNTER",
            [
                _step("search", pattern="c(N)", subject="c(0)", depth=2, search_type="one-step"),
                _step("search", pattern="c(N)", subject="c(0)", depth=2, search_type="at-least-one-step"),
                _step("search", pattern="c(N)", subject="c(0)", depth=2, search_type="any-steps"),
                _step("search", pattern="c(N)", subject="c(0)", depth=2, search_type="normal-form"),
                _step("search", pattern="c(N)", subject="c(0)", depth=2, search_type="branch"),
            ],
        ),
    )

    one_step, at_least_one, any_steps, normal_form, branch = result["outcomes"]
    assert one_step["solutions"] == [{"term": "c(1)", "rewrites": 2, "bindings": [{"variable": "N", "value": "1"}]}]
    assert [solution["term"] for solution in at_least_one["solutions"]] == ["c(1)", "c(2)"]
    # =>* includes the initial state, with a zero rewrite count.
    assert [solution["term"] for solution in any_steps["solutions"]] == ["c(0)", "c(1)", "c(2)"]
    assert any_steps["solutions"][0]["rewrites"] == 0
    assert normal_form["solutions"] == []
    assert branch["solutions"] == []
    assert all(outcome["term"] is None for outcome in result["outcomes"])
    assert all(outcome["truncated"] is False for outcome in result["outcomes"])

    ground = _run(
        executor,
        _request(
            "counter.maude",
            "COUNTER",
            [
                _step("search", pattern="c(3)", subject="c(2)", depth=2, search_type="one-step"),
                _step("search", pattern="c(3)", subject="c(0)", depth=2, search_type="one-step"),
            ],
        ),
    )
    assert ground["outcomes"][0]["solutions"] == [{"term": "c(3)", "rewrites": 2, "bindings": []}]
    assert ground["outcomes"][1]["solutions"] == []


def test_match_and_search_caps_set_the_truncation_flag(executor: MaudeExecutor) -> None:
    matched = _run(
        executor,
        _request(
            "assoc_match.maude",
            "ASSOC-MATCH",
            [_step("match", pattern="X", subject="1 ; 2 ; 3", depth=2_147_483_647)],
            max_solutions=2,
        ),
    )
    match_outcome = _single_outcome(matched)
    assert match_outcome["truncated"] is True
    assert len(match_outcome["matches"]) == 2

    searched = _run(
        executor,
        _request(
            "counter.maude",
            "COUNTER",
            [_step("search", pattern="c(N)", subject="c(0)", depth=5, search_type="any-steps")],
            max_solutions=1,
        ),
    )
    search_outcome = _single_outcome(searched)
    assert search_outcome["truncated"] is True
    assert len(search_outcome["solutions"]) == 1
