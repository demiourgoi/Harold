"""Unit tests for the session engine's path reconstruction (`_reconstruct_path`).

The Maude bindings are faked entirely: these tests pin the assembly order, the
root-state safety rule (`getRule` on the root crashes the real process), the
over-cap early stop, and the element cap, without an interpreter.
"""

import sys
import types
from typing import Any

import pytest

from harold_mcp.maude import session as session_module
from harold_mcp.maude.session import (
    SessionRequest,
    _collect_solutions,
    _collect_step,
    _reconstruct_path,
)


class FakeRule:
    """A rule fake: `getLabel()` and `str()` are the only accessors used."""

    def __init__(self, label: str | None, text: str) -> None:
        self._label = label
        self._text = text

    def getLabel(self) -> str | None:
        return self._label

    def __str__(self) -> str:
        return self._text


class FakeIterator:
    """A linear search-graph fake: state `i` has parent `i - 1`, state 0 is the root.

    `getRule` raises for the root state (the real bindings crash the process on
    it) and records every call, so the tests can pin which states were read.
    """

    def __init__(self, rules: dict[int, FakeRule], terms: dict[int, str]) -> None:
        self._rules = rules
        self._terms = terms
        self.parent_calls = 0
        self.rule_calls: list[int] = []
        self.term_calls: list[int] = []

    def getStateParent(self, state: int) -> int:
        self.parent_calls += 1
        return state - 1 if state > 0 else -1

    def getRule(self, state: int) -> FakeRule:
        self.rule_calls.append(state)
        if state == 0:
            raise AssertionError("getRule called on the root state (crashes the real process)")  # noqa: TRY003
        return self._rules[state]

    def getStateTerm(self, state: int) -> str:
        self.term_calls.append(state)
        return self._terms[state]


def _chain_fixture() -> FakeIterator:
    """A three-transition chain `n(0) -> n(1) -> n(2) -> n(3)` with labeled rules."""
    return FakeIterator(
        rules={
            1: FakeRule("inc-a", "rl [inc-a] : n(N) => n(N + 1) ."),
            2: FakeRule("inc-b", "rl [inc-b] : n(N) => n(N + 1) ."),
            3: FakeRule("inc-c", "rl [inc-c] : n(N) => n(N + 1) ."),
        },
        terms={0: "n(0)", 1: "n(1)", 2: "n(2)", 3: "n(3)"},
    )


def test_labels_mode_assembles_the_chain_in_order() -> None:
    iterator = _chain_fixture()

    result = _reconstruct_path(iterator, 3, "labels", max_path_steps=10, max_result_length=1000)

    assert result.status == "ok"
    assert result.path == {
        "initial": "n(0)",
        "transitions": [
            {"rule": {"label": "inc-a", "text": None}, "state": None},
            {"rule": {"label": "inc-b", "text": None}, "state": None},
            {"rule": {"label": "inc-c", "text": None}, "state": None},
        ],
    }
    assert result.limit is None
    assert result.message is None
    assert iterator.rule_calls == [1, 2, 3]


def test_full_mode_includes_rule_text_and_states() -> None:
    iterator = _chain_fixture()

    result = _reconstruct_path(iterator, 3, "full", max_path_steps=10, max_result_length=1000)

    assert result.status == "ok"
    assert result.path is not None
    assert result.path["initial"] == "n(0)"
    assert result.path["transitions"] == [
        {"rule": {"label": "inc-a", "text": "rl [inc-a] : n(N) => n(N + 1) ."}, "state": "n(1)"},
        {"rule": {"label": "inc-b", "text": "rl [inc-b] : n(N) => n(N + 1) ."}, "state": "n(2)"},
        {"rule": {"label": "inc-c", "text": "rl [inc-c] : n(N) => n(N + 1) ."}, "state": "n(3)"},
    ]
    assert iterator.term_calls == [0, 1, 2, 3]


def test_zero_transition_path_never_calls_getRule_on_the_root() -> None:
    iterator = FakeIterator(rules={}, terms={0: "n(0)"})

    result = _reconstruct_path(iterator, 0, "full", max_path_steps=10, max_result_length=1000)

    assert result.status == "ok"
    assert result.path == {"initial": "n(0)", "transitions": []}
    assert iterator.rule_calls == []
    assert iterator.term_calls == [0]


def test_unlabeled_rule_has_a_null_label() -> None:
    iterator = FakeIterator(
        rules={1: FakeRule(None, "rl a => b .")},
        terms={0: "a", 1: "b"},
    )

    result = _reconstruct_path(iterator, 1, "full", max_path_steps=10, max_result_length=1000)

    assert result.status == "ok"
    assert result.path == {
        "initial": "a",
        "transitions": [{"rule": {"label": None, "text": "rl a => b ."}, "state": "b"}],
    }


class _OverCapGuard(FakeIterator):
    """A fake that fails loudly if any string is formatted for an over-cap chain."""

    def __init__(self, depth: int) -> None:
        super().__init__(rules={}, terms={})
        self._depth = depth

    def getStateParent(self, state: int) -> int:
        self.parent_calls += 1
        return state - 1 if state <= self._depth else -1

    def getRule(self, state: int) -> FakeRule:
        raise AssertionError("getRule called for an over-cap path (count must happen before formatting)")  # noqa: TRY003

    def getStateTerm(self, state: int) -> str:
        raise AssertionError("getStateTerm called for an over-cap path (count must happen before formatting)")  # noqa: TRY003


def test_over_cap_path_stops_early_and_formats_nothing() -> None:
    cap = 2
    iterator = _OverCapGuard(depth=50)

    result = _reconstruct_path(iterator, 50, "full", max_path_steps=cap, max_result_length=1000)

    assert result.status == "too-large"
    assert result.path is None
    assert result.limit == cap
    assert result.message == "path exceeds interpreter_max_path_steps"
    # The walk stops as soon as the chain is over cap: exactly cap + 2 parent
    # lookups, never the remaining ~50 states to the root.
    assert iterator.parent_calls == cap + 2


def test_element_cap_reports_the_result_cap() -> None:
    iterator = FakeIterator(
        rules={1: FakeRule("inc", "rl [inc] : n(N) => n(N + 1) .")},
        terms={0: "n(0)", 1: "n(1)"},
    )

    result = _reconstruct_path(iterator, 1, "full", max_path_steps=10, max_result_length=5)

    assert result.status == "too-large"
    assert result.path is None
    assert result.limit == 5
    assert result.message == "path element exceeds interpreter_max_result_length"


def test_element_cap_applies_to_the_initial_state() -> None:
    iterator = FakeIterator(rules={}, terms={0: "n(0)"})

    result = _reconstruct_path(iterator, 0, "labels", max_path_steps=10, max_result_length=2)

    assert result.status == "too-large"
    assert result.limit == 2
    assert result.message == "path element exceeds interpreter_max_result_length"


def test_element_cap_applies_to_labels_mode_strings() -> None:
    iterator = FakeIterator(
        rules={1: FakeRule("a-very-long-label", "rl a => b .")},
        terms={0: "a", 1: "b"},
    )

    result = _reconstruct_path(iterator, 1, "labels", max_path_steps=10, max_result_length=5)

    assert result.status == "too-large"
    assert result.limit == 5


def test_path_at_exactly_the_cap_is_accepted() -> None:
    iterator = _chain_fixture()

    result = _reconstruct_path(iterator, 3, "labels", max_path_steps=3, max_result_length=1000)

    assert result.status == "ok"
    assert result.path is not None
    assert len(result.path["transitions"]) == 3


class FakeSearch(FakeIterator):
    """A lazy search iterator fake: one solution per state number, in order.

    Each yielded solution positions the iterator on that solution's state, so
    `getStateNr()` resolves the current state at call time (like the bindings).
    """

    def __init__(self, solution_states: list[int], terms: dict[int, str]) -> None:
        super().__init__({}, terms)
        self._solution_states = iter(solution_states)
        self.current: int | None = None
        self.state_nr_calls = 0

    def __iter__(self) -> FakeSearch:
        return self

    def __next__(self) -> tuple[str, list[tuple[str, str]], None, int]:
        self.current = next(self._solution_states)
        return (self._terms[self.current], [], None, 1)

    def getStateNr(self) -> int:
        self.state_nr_calls += 1
        assert self.current is not None
        return self.current


class FakeSubject:
    """`subject.search(...)` fake returning the given iterator."""

    def __init__(self, iterator: FakeSearch) -> None:
        self.iterator = iterator

    def search(self, search_type: int, pattern: Any, depth: int) -> FakeSearch:
        return self.iterator


def _collect(
    iterator: FakeSearch,
    *,
    path_mode: str | None,
    max_solutions: int = 200,
    max_path_steps: int = 100,
    max_result_length: int = 1_000_000,
):
    return _collect_solutions(
        FakeSubject(iterator), 2, None, -1, max_solutions, max_result_length, path_mode, max_path_steps
    )


def test_each_solution_gets_its_own_path() -> None:
    """Laziness pin: the state is read while the iterator is positioned on each solution."""
    iterator = FakeSearch([2, 3], terms={0: "n(0)", 1: "n(1)", 2: "n(2)", 3: "n(3)"})
    iterator._rules = {
        1: FakeRule("one", "rl one ."),
        2: FakeRule("two", "rl two ."),
        3: FakeRule("three", "rl three ."),
    }

    result = _collect(iterator, path_mode="labels")

    assert result.status == "ok"
    first, second = result.items
    assert [t["rule"]["label"] for t in first["path"]["transitions"]] == ["one", "two"]
    assert [t["rule"]["label"] for t in second["path"]["transitions"]] == ["one", "two", "three"]
    assert iterator.state_nr_calls == 2


def test_extra_solution_for_truncated_gets_no_path_work() -> None:
    iterator = FakeSearch([1, 2], terms={0: "n(0)", 1: "n(1)", 2: "n(2)"})
    iterator._rules = {1: FakeRule("one", "rl one ."), 2: FakeRule("two", "rl two .")}

    result = _collect(iterator, path_mode="labels", max_solutions=1)

    assert result.status == "ok"
    assert result.truncated is True
    assert len(result.items) == 1
    assert iterator.state_nr_calls == 1


def test_transition_overflow_reports_the_path_cap() -> None:
    iterator = FakeSearch([5], terms={i: f"n({i})" for i in range(6)})

    result = _collect(iterator, path_mode="labels", max_path_steps=2)

    assert result.status == "too-large"
    assert result.items == []
    assert result.limit == 2
    assert result.message == "path exceeds interpreter_max_path_steps"


def test_element_overflow_reports_the_result_cap() -> None:
    iterator = FakeSearch([1], terms={0: "n(0)", 1: "n(1)"})
    iterator._rules = {1: FakeRule("a-very-long-label", "rl a => b .")}

    result = _collect(iterator, path_mode="labels", max_result_length=5)

    assert result.status == "too-large"
    assert result.limit == 5
    assert result.message == "path element exceeds interpreter_max_result_length"


class _NoPathAccess(FakeSearch):
    """Fails loudly if any path accessor is reached for an oversized solution term."""

    def getStateNr(self) -> int:
        raise AssertionError("getStateNr called although the solution term already exceeded the cap")  # noqa: TRY003


def test_oversized_term_is_checked_before_any_path_work() -> None:
    iterator = _NoPathAccess([5], terms={5: "n(5)"})

    result = _collect(iterator, path_mode="full", max_path_steps=2, max_result_length=2)

    assert result.status == "too-large"
    assert result.limit == 2
    assert result.message == "result exceeds interpreter_max_result_length"


def test_path_mode_none_and_none_string_skip_path_work() -> None:
    for mode in (None, "none"):
        iterator = FakeSearch([1], terms={0: "n(0)", 1: "n(1)"})

        result = _collect(iterator, path_mode=mode)

        assert result.status == "ok"
        assert result.items[0]["path"] is None
        assert iterator.state_nr_calls == 0


def test_invalid_path_mode_is_a_programming_error() -> None:
    with pytest.raises(ValueError, match="path_mode"):
        _ = _collect_step(
            "search",
            0,
            {"command": "search", "search_type": "any-steps", "path_mode": "bogus"},
            None,
            None,
            -1,
            200,
            1_000_000,
            100,
        )


class _FakeModule:
    def __init__(self, module_type: int = 0) -> None:
        self._module_type = module_type

    def getModuleType(self) -> int:
        return self._module_type


class _FakeMaude(types.ModuleType):
    """Scriptable stand-in for the lazy `import maude` inside `run_session`."""

    def __init__(self, *, load_error: BaseException | None = None) -> None:
        super().__init__("maude")
        self.load_error = load_error

    def getModules(self) -> list[object]:
        return []

    def load(self, path: str) -> bool:
        if self.load_error is not None:
            raise self.load_error
        return True

    def getModule(self, name: str) -> _FakeModule:
        return _FakeModule()


def _request() -> SessionRequest:
    return {
        "path": "program.maude",
        "module": "M",
        "steps": [
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
            }
        ],
        "max_solutions": 200,
        "max_result_length": 1_000_000,
        "max_path_steps": 100,
        "max_output_length": 1_000_000,
    }


def test_load_failure_has_phase_load(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "maude", _FakeMaude(load_error=RuntimeError("load exploded")))

    with pytest.raises(RuntimeError, match="load exploded") as exc_info:
        _ = session_module.run_session(_request())

    assert exc_info.value.worker_context == {"phase": "load"}


def test_step_failure_has_phase_step_index_and_command(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "maude", _FakeMaude())

    def boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("step exploded")  # noqa: TRY003 - test double

    monkeypatch.setattr(session_module, "_run_step", boom)

    with pytest.raises(RuntimeError, match="step exploded") as exc_info:
        _ = session_module.run_session(_request())

    assert exc_info.value.worker_context == {"phase": "step", "step": 0, "command": "reduce"}
