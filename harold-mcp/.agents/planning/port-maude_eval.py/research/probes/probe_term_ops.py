"""Probe: Maude Term API semantics for the planned ``maude_run`` tool.

Answers the questions behind ``../term-api.md``:

- return values and in-place mutation of ``reduce``/``rewrite``/``frewrite``/``erewrite``
- step counts and bound semantics
- ``match`` (``MatchSearchState``) and ``search`` (``RewriteSequenceSearch``) iteration
- ``parseTerm`` success/failure values
- pretty-print fidelity and round-tripping (a result term must be re-submittable)

Run from ``harold-mcp`` with the project venv::

    .venv/bin/python .agents/planning/port-maude_eval.py/research/probes/probe_term_ops.py
"""

import maude

maude.init(loadPrelude=True, advise=False)


def section(title: str) -> None:
    print(f"\n=== {title} ===")


section("parseTerm")
nat = maude.getModule("NAT")
print("NAT:", nat, "| type:", nat.getModuleType())
t = nat.parseTerm("2 * 3")
print("ok                :", type(t).__name__, repr(str(t)), "| sort:", t.getSort())
print("bad syntax        :", repr(nat.parseTerm("2 +")))
print("undeclared op     :", repr(nat.parseTerm("nope(3)")))
print("prettyPrint(0)    :", repr(t.prettyPrint(0)))
print("prettyPrint(MIXFIX):", repr(t.prettyPrint(maude.PRINT_MIXFIX)))
print("str               :", repr(str(t)))
print("str == prettyPrint(0):", str(t) == t.prettyPrint(0))

section("reduce (equational)")
t = nat.parseTerm("2 * 3")
steps = t.reduce()
print("2 * 3      | steps:", steps, "| term after:", repr(str(t)), "| prettyPrint(0):", repr(t.prettyPrint(0)), "| sort:", t.getSort())
t = nat.parseTerm("6")
steps = t.reduce()
print("6          | steps:", steps, "| term after:", repr(str(t)))
t = nat.parseTerm("2 * 3")
kept = t.copy()
t.reduce()
print("copy kept  | original stays:", repr(str(kept)), "| reduced term:", repr(str(t)))

section("rewrite family (rule-based)")
print("input() ->", maude.input("""
mod COUNTER is
  pr NAT .
  op c : Nat -> Nat [ctor] .
  var N : Nat .
  rl [inc] : c(N) => c(N + 1) .
endm
"""))
counter = maude.getModule("COUNTER")
print("COUNTER:", counter, "| type:", counter.getModuleType(), "(SYSTEM_MODULE =", maude.Module.SYSTEM_MODULE, ")")

t = counter.parseTerm("c(0)")
steps = t.rewrite(1)
print("rewrite(1)        | steps:", steps, "| term after:", repr(str(t)))
steps = t.rewrite(5)
print("rewrite(5) again  | steps:", steps, "| term after:", repr(str(t)))

t = counter.parseTerm("c(0)")
steps = t.rewrite(0)
print("rewrite(0)        | steps:", steps, "| term after:", repr(str(t)))

t = counter.parseTerm("c(0)")
steps = t.frewrite(3)
print("frewrite(3)       | steps:", steps, "| term after:", repr(str(t)))

t = counter.parseTerm("c(0)")
result, steps = t.erewrite(3)
print("erewrite(3)       | steps:", steps, "| original:", repr(str(t)), "| result:", repr(str(result)))
print("erewrite result type:", type(result).__name__)

for gas in (0, 1, 2):
    t = counter.parseTerm("c(0)")
    steps = t.frewrite(3, gas)
    print(f"frewrite(3, gas={gas}) | steps:", steps, "| term after:", repr(str(t)))
    t = counter.parseTerm("c(0)")
    result, steps = t.erewrite(3, gas)
    print(
        f"erewrite(3, gas={gas}) | steps:",
        steps,
        "| original:",
        repr(str(t)),
        "| result:",
        repr(str(result)),
    )

section("match")
subject = counter.parseTerm("c(5)")
pattern = counter.parseTerm("c(N)")
print("subject:", subject, "| pattern:", pattern)
print("has UNBOUNDED constant:", hasattr(maude, "UNBOUNDED"))
for label, kwargs in [
    ("maxDepth=-1 (on top, no extension)", {"maxDepth": -1}),
    ("maxDepth=0 (on top, extension)", {"maxDepth": 0}),
]:
    matches = [(str(sub), context(counter.parseTerm("c(99)"))) for sub, context in subject.match(pattern, **kwargs)]
    print(f"{label}: {len(matches)} matches |", [(s, str(c)) for s, c in matches][:5])

inner_subject = counter.parseTerm("c(c(5))")
matches = [
    (str(sub), context(counter.parseTerm("c(99)")))
    for sub, context in inner_subject.match(pattern, maxDepth=getattr(maude, "UNBOUNDED", 1000))
]
print("c(c(5)) match c(N) anywhere:", len(matches), "|", [(s, str(c)) for s, c in matches][:5])

miss = list(subject.match(counter.parseTerm("c(6)"), maxDepth=0))
print("c(5) match c(6):", len(miss), "matches")

section("search")
start = counter.parseTerm("c(0)")
target = counter.parseTerm("c(N)")
for name in ("ONE_STEP", "AT_LEAST_ONE_STEP", "ANY_STEPS", "NORMAL_FORM", "BRANCH"):
    typ = getattr(maude, name)
    solutions = []
    for solution, sub, _path, rewrites in start.search(typ, target, depth=2):
        solutions.append((str(solution), str(sub), rewrites))
        if len(solutions) >= 8:
            break
    print(f"{name} (depth=2): {len(solutions)} shown |", solutions)

ground = counter.parseTerm("c(3)")
solutions = [
    (str(solution), str(sub), rewrites)
    for solution, sub, _path, rewrites in counter.parseTerm("c(2)").search(maude.ONE_STEP, ground, depth=2)
]
print("ground c(2) =>1 c(3):", solutions)
solutions = [str(solution) for solution, *_ in start.search(maude.ONE_STEP, ground, depth=2)]
print("ground c(0) =>1 c(3):", solutions)

section("round-trip fidelity")
print("input() ->", maude.input("""
fmod SEQ is
  pr NAT .
  sort Seq .
  subsort Nat < Seq .
  op nil : -> Seq [ctor] .
  op _;_ : Seq Seq -> Seq [ctor assoc id: nil] .
  op wrap : Seq -> Seq [ctor] .
endfm
"""))
seq = maude.getModule("SEQ")
for text in ("2 * 3", "1 + 2 * 3", "1 ; 2 ; 3", "wrap(1 ; 2)"):
    module = seq if ";" in text or "wrap" in text else nat
    term = module.parseTerm(text)
    term.reduce()
    printed = str(term)
    reparsed = module.parseTerm(printed)
    print(
        f"{text!r:20} -> {printed!r:16} | reparse ok: {reparsed is not None}",
        "| equal:",
        reparsed.equal(term) if reparsed is not None else None,
    )

section("variable-containing pattern round-trip")
var_term = counter.parseTerm("c(N)")
print("pattern str:", repr(str(var_term)), "| reparse:", repr(str(counter.parseTerm(str(var_term)))))
