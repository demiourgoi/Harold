"""Probe: `match` depth modes and `search` types for the `maude_run` tool.

Answers the questions behind the Step 5 behavior:

- how a substitution serializes (`str(substitution)` vs iterating name/value pairs);
- how `maxDepth` selects extension/anywhere matching on an assoc module;
- the five search types, including `=>*` yielding the initial state and a ground
  `=>1` target;
- that the search/match iterators are lazy, so a client-side cap can stop them.

Run from ``harold-mcp`` with the project venv::

    .venv/bin/python .agents/planning/port-maude_eval.py/research/probes/probe_match_search.py
"""

import maude

maude.init(loadPrelude=True, advise=False)
maude.load("tests/integration/fixtures/assoc_match.maude")
maude.load("tests/integration/fixtures/counter.maude")


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def pairs(substitution: maude.Substitution) -> list[tuple[str, str]]:
    """Serialize a substitution as the name/value pairs the tool returns."""
    return [(str(variable), str(value)) for variable, value in substitution]


counter = maude.getModule("COUNTER")
assoc = maude.getModule("ASSOC-MATCH")

section("substitution serialization")
subject = counter.parseTerm("c(5)")
pattern = counter.parseTerm("c(N)")
for substitution, _context in subject.match(pattern, maxDepth=-1):
    print("str(substitution):", repr(str(substitution)), "| name/value pairs:", pairs(substitution))

section("match depth modes (assoc module)")
subject = assoc.parseTerm("1 ; 2 ; 3")
for pattern_text in ("X", "2 ; X", "1 ; X", "2"):
    pattern = assoc.parseTerm(pattern_text)
    for label, depth in (
        ("-1 (on top, no extension)", -1),
        ("0 (on top, extension)", 0),
        ("UNBOUNDED (anywhere)", maude.UNBOUNDED),
    ):
        matches = [(str(sub), str(context(subject))) for sub, context in subject.match(pattern, maxDepth=depth)]
        print(f"pattern {pattern_text!r} depth {label}: {len(matches)} matches | {matches}")

section("match anywhere through an assoc subterm")
subject = assoc.parseTerm("wrap(1 ; 2 ; 3)")
pattern = assoc.parseTerm("1 ; 2 ; 3")
for label, depth in (
    ("-1 (on top, no extension)", -1),
    ("0 (on top, extension)", 0),
    ("UNBOUNDED (anywhere)", maude.UNBOUNDED),
):
    matches = [(str(sub), str(context(subject))) for sub, context in subject.match(pattern, maxDepth=depth)]
    print(f"pattern '1 ; 2 ; 3' under wrap depth {label}: {len(matches)} matches | {matches}")

section("search types (counter, depth=2)")
start = counter.parseTerm("c(0)")
target = counter.parseTerm("c(N)")
for name in ("ONE_STEP", "AT_LEAST_ONE_STEP", "ANY_STEPS", "NORMAL_FORM", "BRANCH"):
    solutions = []
    for solution, substitution, _path, rewrites in start.search(getattr(maude, name), target, depth=2):
        solutions.append((str(solution), str(substitution), rewrites, pairs(substitution)))
        if len(solutions) >= 8:
            break
    print(f"{name} (depth=2): {len(solutions)} shown | {solutions}")

section("ground search targets (=>1)")
ground = counter.parseTerm("c(3)")
solutions = [
    (str(solution), str(substitution), rewrites, pairs(substitution))
    for solution, substitution, _path, rewrites in counter.parseTerm("c(2)").search(maude.ONE_STEP, ground, depth=2)
]
print("c(2) =>1 c(3):", solutions)
solutions = [str(solution) for solution, *_ in start.search(maude.ONE_STEP, ground, depth=2)]
print("c(0) =>1 c(3):", solutions)

section("lazy iteration cap")
lazy = start.search(maude.ANY_STEPS, target, depth=10)
first_two = []
for solution, *_ in lazy:
    first_two.append(str(solution))
    if len(first_two) == 2:
        break
print("first two solutions of an unbounded-depth any-steps search:", first_two)
