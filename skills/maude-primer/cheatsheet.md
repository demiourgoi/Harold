# Maude 2.0 Primer — Cheatsheet

## Decision Rules

**Module type**: need objects/classes/messages at the prompt-with-semantics level → `omod` (Full Maude, parentheses). Need dynamic behavior/state change → `mod`. Computing/determinate definitions → `fmod.`
  - Everything Core is in Full. omods are Full-only (`(omod ... endom)`).

**Import mode** (Ch 2): will you add new constants to imported sorts? (junk) redefine their equations? (confusion)
  - neither → `protecting` | junk only → `extending` | junk+confusion → `including`
  - LOOP-MODE consumers almost always need `including` (State/System get re-sensed).

**Statement by shape** (Ch 2, 3): simplification → `eq`; conditional simplification → `ceq ... if ... /\ ...`; sort refinement → `mb`/`cmb`; state change → `rl [label] : A => B .`; conditional transition → `crl`. Operator declaration → `op`; message → `msg ... -> Msg`; class → `class ... | ...`.

**Equation health**: RHS must be strictly simpler, or the flag instead: symmetric law → `comm`/`assoc` flags, never equations; identity → `id:` flag (equations OK for non-recursive uses); recursion → base case + ONE peeling direction (`E L`, `s(M)`), never a middle split (`L1 L2`).

**Input to message**: always an `Oid` (or computed Oid term), never an embedded object. Result sort is always `Msg`. In rule text name only attributes the rule reads/writes.

**Rewrite command**: quick check → `rew [n] t .`; rule starvation suspected → `frew [n] t .`; extend run → `continue n .`; goal-directed planning → `search t1 =>+ t2 .` (target must be final → `=>!`). Never unbounded on systems that might not terminate.

**metaApply vs metaXapply** (Ch 6): exact LHS match needed / substitution focus → `metaApply(M, T, 'label, S, N)`; match nested deep inside expr → `metaXapply(M, T, 'lab, S, lo, hi, N)` — `lo`=min depth, `hi`=max depth (`unbounded` safe default; assoc strings count ONE level).

**Parameterize when** the same structure recurs over ≥2 element types. Theory = contract only (no semantics). View binds theory→parameter, `op f to term ...` needs pattern vars. Every theory sort/op hooked? label consistent? all views in the instantiation? — the three survival rules.

## Tables

Equational attribute flags:

| Flag | Meaning | Constraint |
|---|---|---|
| `assoc` | grouping irrelevant | not with `idem` |
| `comm` | order irrelevant | — |
| `id: e` / `left id:` / `right id:` | identity element | binary ops only |
| `idem` | dupes collapse | not with `assoc`; use `eq E E = E .` instead |
| `iter` | `s_^n(x)` notation | unary ops only |
| `ctor` | value generator | subsort-overloaded twins must share other attrs |
| `memo` | cache reductions by top op | wins when same ground subterm recurs |
| `prec n` | default 41; lower n binds tighter | parens override |
| `gather (e E &)` | arg-level prec bounds; default `(& &)` | `(e E)` = nest right; `(E e)` = nest left |

Meta-level nulls/defaults (Ch 6, 7):

| Sort | Null/Default |
|---|---|
| ImportList | `nil` |
| SortSet/SubsortDeclSet/OpDeclSet/MembAxSet/EquationSet/RuleSet/AttrSet | `none` |
| Substitution | `none` |
| Nat (selector args) | `0` |
| Bound | `unbounded` |
| ResultTriple/4Tuple (no match) | `(failure).ResultTriple?` / `(failure).Result4Tuple?` |

Environment commands quick list (Ch 2–4): `load`, `red in MOD : e .`, `select MOD`, `set trace on .`, `rew/frew [n]`, `continue n`, `search ... =>+ / =>!`, `show path N .`, Full Maude wrappers: `(select M(V) .)`, `(red up(M, e) .)`.

Standard modules: `NAT`/`INT`/`FLOAT`/`RAT`, `QID` ('name), `STRING` (+"", substr/find/rfind), `BOOL`, `META-LEVEL`, `LOOP-MODE`.

## Tells & Smells

- Reduction ping-pongs between two equal-complexity terms → you wrote comm/assoc as equations; switch to flags.
- `length(L1 L2) = length(L1) + length(L2)` never terminates → split at identity; use flag or peel-one-element instead.
- Result of an operation "should be fine" but shows as `[Kind]` → output sort too coarse: add `mb`/`cmb`, or compute at the kind level deliberately.
- `rew [2]` and `rew [100]` print the same state → default strategy is looping; use `frew` or `search`.
- Parse error mentioning `MSG` or a class → check keyword case (`msg` vs `Msg`), header `class`, and surrounding parentheses around mixfix messages: `"(A switch B)"`.
- A parameterization "looks right" but explodes → check that every parameterized view is applied in the instantiation, labels recurse consistently, `X@Sort` spells appear where theory sorts go.
- Unquoted parentheses in view/qid text at Full Maude → they consumed structure — backquote them: `'_`, '`)`, '`(_`,_`)`.
- Statements report an error at declaration → probably a missing trailing period (statements need `.`; module definitions don't).
