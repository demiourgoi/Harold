"""Probe: the search-path data exposed by the Python bindings.

Answers the questions behind exposing paths from `maude_run` search steps:

- the exact shape of what ``EasyTerm.search`` yields (a zero-argument path thunk,
  not a list);
- the layout of the path returned by ``pathTo``: states interleaved with rules;
- how a rule serializes: ``getLabel()`` vs ``str(rule)``, labeled vs unlabeled;
- whether the path thunk captures the state at yield time or at call time
  (a correctness trap for lazy iterators);
- state numbers (``getStateNr``/``getStateParent``) vs Maude's
  ``Solution N (state M)`` output, and how they relate to ``show path``;
- paths for all five search types, including a reflexive ``=>*`` solution at the
  initial state and ``=>#`` branching states;
- the size of a long path, to inform the result-length caps.

Run from ``harold-mcp`` with the project venv::

    .venv/bin/python .agents/planning/maude_eval_search_path/research/probes/probe_search_path.py
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import maude

HERE = Path(__file__).resolve().parent


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def label_of(element: Any) -> Any:
    """Return the rule label, or ``<n/a>`` for terms."""
    getter = getattr(element, "getLabel", None)
    return getter() if getter is not None else "<n/a>"


def describe(path: list[Any]) -> None:
    for position, element in enumerate(path):
        print(f"  [{position}] {type(element).__name__}: {str(element)!r} | label={label_of(element)!r}")


def labels(path_thunk: Any) -> list[Any]:
    return [label_of(element) for element in path_thunk() if label_of(element) != "<n/a>"]


maude.init(loadPrelude=True, advise=False)
print("load:", maude.load(str(HERE / "search_path.maude")))

shepherd = maude.getModule("SHEPHERD")
unlabeled = maude.getModule("UNLABELED")
chain = maude.getModule("CHAIN")
branch = maude.getModule("BRANCH")

section("search iterator and path thunk shape")
subject = shepherd.parseTerm("st(l, l, l, l)")
target = shepherd.parseTerm("st(r, r, r, r)")
it = subject.search(maude.ANY_STEPS, target, depth=7)
print("iterator type:", type(it).__name__)
solution, substitution, path_thunk, rewrites = next(it)
print("solution:", str(solution), "| substitution:", str(substitution), "| rewrites:", rewrites)
print("path thunk type:", type(path_thunk).__name__)
path = path_thunk()
print("path type:", type(path).__name__, "| length:", len(path))
describe(path)

section("state numbers match Maude's `Solution N (state M)`")
print("solution state number:", it.getStateNr())
state = it.getStateNr()
state_chain = []
while state >= 0:
    state_chain.append(state)
    state = it.getStateParent(state)
print("state chain (root first):", list(reversed(state_chain)))
print("getStateTerm(root state 0):", repr(str(it.getStateTerm(0))))
print("pathTo(same state) labels:", labels(path_thunk))

section("path thunk captures the current state at call time")
chain_subject = chain.parseTerm("n(0)")
chain_pattern = chain.parseTerm("n(N)")
it = chain_subject.search(maude.ANY_STEPS, chain_pattern, depth=5)
first = next(it)
print("after first next: state", it.getStateNr(), "| labels now:", labels(first[2]))
second = next(it)
print("after second next: state", it.getStateNr(), "| labels now:", labels(second[2]))
print("first thunk called late:", labels(first[2]), "-> points at state", it.getStateNr())
print("second thunk called late:", labels(second[2]), "-> points at state", it.getStateNr())

section("reflexive solution at the initial state (=>*)")
it = chain_subject.search(maude.ANY_STEPS, chain.parseTerm("n(0)"), depth=3)
solution, substitution, path_thunk, rewrites = next(it)
path = path_thunk()
print("solution:", str(solution), "| state:", it.getStateNr(), "| path length:", len(path))
describe(path)

section("all five search types")
search_types = (
    ("ONE_STEP", shepherd, "st(l, l, l, l)", "st(r, l, l, r)", 3),
    ("AT_LEAST_ONE_STEP", shepherd, "st(l, l, l, l)", "st(r, r, r, r)", 7),
    ("ANY_STEPS", shepherd, "st(l, l, l, l)", "st(r, r, r, r)", 7),
    ("NORMAL_FORM", branch, "a", "c", 3),
    ("BRANCH", branch, "a", "X:S", 3),
)
for name, module, subject_text, target_text, depth in search_types:
    it = module.parseTerm(subject_text).search(getattr(maude, name), module.parseTerm(target_text), depth=depth)
    results = []
    for solution, _substitution, path_thunk, rewrites in it:
        results.append((it.getStateNr(), rewrites, labels(path_thunk), len(path_thunk())))
        if len(results) >= 4:
            break
    print(f"{name}: {len(results)} solution(s) | (state, rewrites, labels, path len) = {results}")

section("unlabeled rules")
it = unlabeled.parseTerm("a").search(maude.AT_LEAST_ONE_STEP, unlabeled.parseTerm("c"), depth=5)
solution, substitution, path_thunk, rewrites = next(it)
print("solution:", str(solution), "| state:", it.getStateNr())
describe(path_thunk())

section("long path size")
it = chain.parseTerm("n(0)").search(maude.ANY_STEPS, chain.parseTerm("n(100)"), depth=100)
solution, substitution, path_thunk, rewrites = next(it)
path = path_thunk()
terms = [str(element) for element in path if type(element).__name__ == "Term"]
rules = [str(element) for element in path if type(element).__name__ == "Rule"]
print("path elements:", len(path), "| terms:", len(terms), "| rules:", len(rules))
print("max term length:", max((len(text) for text in terms), default=0))
print("max rule length:", max((len(text) for text in rules), default=0))
print("total rule text length:", sum(map(len, rules)))
print("rewrite counter:", rewrites, "| state:", it.getStateNr())

section("path survives the iterator")
path = path_thunk()
del it
print("path elements after deleting the iterator:", [str(element) for element in path][:3], "...")
