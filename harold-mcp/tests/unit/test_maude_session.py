"""Unit tests for the session engine's path reconstruction (`_reconstruct_path`).

The Maude bindings are faked entirely: these tests pin the assembly order, the
root-state safety rule (`getRule` on the root crashes the real process), the
over-cap early stop, and the element cap, without an interpreter.
"""

from harold_mcp.maude.session import _reconstruct_path


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
