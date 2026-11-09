# Chapter 12: LTL Model Checking

## Core Idea
Once you divide your world into a system level (a system module's rewrite theory) and a property level (LTL formulas over equationally-defined state predicates), Maude becomes an on-the-fly LTL model checker: it decides `M, init |= φ` on finite state spaces by searching for a counterexample — an infinite path (finite prefix + loop) in the product of the state graph with the Büchi automaton of `¬φ`, and returns it as data when found.

## Frameworks Introduced
- **LTL(AP) syntax** (`fmod LTL`): constructors `True`, `~_`, `_\/_`, `O_` (next), `_U_` (until), plus the duals needed for negative normal form (`False`, `_/\_`, `_R_`); defined operators: `->_`, `<->_`, `<>_` (eventually `= True U f`), `[]_` (henceforth `= False R f`), `_W_` (weak until), `_|->_` (leads-to `[] (f -> <> g)`), `=>_`, `<=>_`. NNF equations push negations to atoms.
- **Kripke structure from a module**: choose a state **kind** `k`; declare state predicates as **parametric operators of sort `Prop`** whose semantics are *equations over `_|=_ : State Prop ~> Bool`* in a `M-PREDS` module:
  ```maude
  mod M-PREDS is protecting M . including SATISFACTION .
    subsort Conf < State .
    op crit : Name -> Prop .
    eq [N, critical] C |= crit(N) = true .
    eq C |= P = false [owise] .
  endm
  ```
  `SATISFACTION` provides `State`, `Prop`, and the frozen partial `_|=_`; the sort subsorting identifies your states; predicates defined as true-equations + one `owise` (or explicit true/false equations when formal tools require no-owise).
- **The model-check contract**: reachable states from `init` **finite**; `E` and `E∪D` (predicate equations) ground Church-Rosser + terminating, `(Σ,E) ⊆ (Σ∪Π,E∪D)` protecting; rules ground coherent. Then `modelCheck : State Formula ~> ModelCheckResult` decides, via `B_¬φ` product emptiness (on-the-fly; see MODEL-CHECKER, `special`-implemented) — `true` or a `counterexample(prefix, loop)` term.
- **The M-CHECK pattern**:
  ```maude
  mod M-CHECK is protecting M-PREDS . including MODEL-CHECKER . including LTL-SIMPLIFIER .
    op init : -> Conf .   --- optional convenience
  endm
  ---
  red modelCheck(init, [] ~ (crit(a) /\ crit(b))) .   --- mutual exclusion
  ```
- **LTL-SIMPLIFIER** (optional include): rewrites `¬φ` to a *smaller* normal form before automaton construction (Etessami–Holzman + Somenzi–Bloem rules, plus a sub-formula `<=` entailment relation) — smaller `B_¬φ`, faster checking.
- **Counterexamples as data**: `{state, 'ruleLabel}` transitions; two `TransitionList`s = finite prefix + cycle; rule names come from statement labels (so label your rules!); `unlabeled`/`deadlock` label conventions for implicit events.
- **SAT-SOLVER**: `satSolve : Formula ~> SatSolveResult` (`model(L, C)` BDD-ish witnessing model = two FormulaLists, or `false`); `tautCheck(F) = $invert(satSolve(~F))` gives `true` or a `counterexample(L, C)` — decidable LTL satisfiability/tautology on abstract propositions (extend LTL with constant `Formula`s).
- **LTL+ (12.6)**: one layer of path quantifiers — `E f` / `A f` closed under `~`; `MODEL-CHECKER+` defines `modelCheck+ : State Formula+ ~> ModelCheck+Result` by duality: `modelCheck+(st, E f) = neg(modelCheck(st, ~f))`, `modelCheck+(st, A f) = modelCheck(st, f)`; positive results under `E` are `witness(prefix, loop)` traces. This answers reachability-with-loops questions LTL cannot express ("*is there a path on which the counters ever differ?*" `E <> ~ same.cnts(a, b)`).

## Key Concepts
- **Parametric state predicates**: propositions with arguments (`crit(N)`, `inCrit([N])`) — AP is not limited to constants; ground instances form the atomic propositions.
- **Safety vs liveness, syntax shortcuts**: `[] p` (always), `<> p` (eventually), `[]<> p` (infinitely often), `<>[] p` (eventually always), `f |-> g` (f leads to g).
- **Property-level parameterization** (12.5): define an infinite family of formulas by recursive equations — `allProcessesReenter(n)` builds the conjunction over `n` processes; `nextIter F` prepends `2*#` next-operators; instantiate per system size (`view 5 from NZNAT# to NAT is op # to term 5 .`, giving `NAT/{5}`). Round-robin's mutual exclusion `[] ~ twoInCrit` and guaranteed reentrance proved for `CHECK-RROBIN{5}`; a wrong 3-step claim yields a full 25-transition counterexample.
- **Why non-finite state spaces hang**: the MODEL-CHECK-BAD-EX lesson — a tiny infinite system (`a => f(a)`) makes `modelCheck` loop forever even for `p` without temporal operators; finiteness of the reachable set is a *precondition*, not a checkable hope.
- **Kripke totality**: transitions are made total by implicit stuttering on deadlocked states (`deadlock` label) so LTL semantics stays standard.

## Mental Models
- Two-layer thinking: keep rules and predicates in *separate modules* (M system / M-PREDS property vocabulary / M-CHECK driver) — the pattern mirrors theorem-proving's theory/interpretation split and keeps protecting/expending claims clean.
- `modelCheck` = "the best refuter you've ever used": success is silence (`true`), failure is a complete, labeled, replayable run.
- Persistence in predicate equations: pattern-match the *interesting* positive cases; let `owise` carry the negatives.

## Anti-patterns
- **Model checking an infinite-state module**: nonterminates (bad even without temporal operators); bound, abstract (Ch 11), or rethink.
- **Predicates not fully defined** (missing true or false cases): breaks Bool protection and SCC checks — either `owise` or explicit both-case equations.
- **Unlabeled rules**: counterexample transitions show `unlabeled` instead of the responsible rule — labels are documentation your future self reads in counterexample traces.
- **Omitting LTL-SIMPLIFIER on large formulas**: unnecessarily big automata; include it unless it interferes.
- **Confusing `[]<> p -> []<> q` (infinitely-often implication) with `p |-> q` (leads-to)**: they are the same here, but writing half-remembered combinations risks checking the wrong property — build formulas from the named combinators.

## Code Examples
```maude
mod MUTEX is
  sorts Name Mode Proc Token Conf . subsorts Token Proc < Conf .
  op none : -> Conf [ctor] .
  op __ : Conf Conf -> Conf [ctor assoc comm id: none] .
  ops a b : -> Name [ctor] . ops wait critical : -> Mode [ctor] .
  op [_,_] : Name Mode -> Proc [ctor] . ops * $ : -> Token [ctor] .
  rl [a-enter] : $ [a, wait] => [a, critical] .
  rl [b-enter] : * [b, wait] => [b, critical] .
  rl [a-exit] : [a, critical] => [a, wait] * .
  rl [b-exit] : [b, critical] => [b, wait] $ .
endm

mod MUTEX-CHECK is
  protecting MUTEX-PREDS . including MODEL-CHECKER . including LTL-SIMPLIFIER .
  ops initial1 initial2 : -> Conf .
  eq initial1 = $ [a, wait] [b, wait] .   --- initial2 with *
endm

red modelCheck(initial1, [] ~ (crit(a) /\ crit(b))) .    --- result Bool: true
red modelCheck(initial1, ([]<> wait(a)) -> ([]<> crit(a))) .  --- strong liveness: true
red modelCheck(initial1, [] wait(b)) .
--- result ModelCheckResult: counterexample({$ [a, wait] [b, wait], 'a-enter} ...
---                                  {* [a, wait] [b, wait], 'b-enter}, {...cycle...})
```
- **What it demonstrates**: the entire three-module pattern (system / predicates / checker-driver), safety and liveness checks, and a counterexample decomposed as (prefix; loop) with per-transition rule labels.

## Reference Tables
| Operator | Meaning | Definition |
|---|---|---|
| `O f` | next | primitive |
| `f U g` | until (strong) | primitive |
| `f R g` | release (dual of U) | primitive |
| `<> f` | eventually | `True U f` |
| `[] f` | henceforth | `False R f` |
| `f W g` | weak until | `(f U g) \/ [] f` |
| `f -> g`, `f <-> g` | Boolean | `~f \/ g`, `(f->g)/\(g->f)` |
| `f \|-> g` | leads-to | `[] (f -> <> g)` |
| `f => g`, `f <=> g` | strong implication/equiv | `[] (f -> g)`, `[] (f <-> g)` |
| `E f`, `A f` (LTL+) | exists/all path quantifier | `modelCheck+(st,E f) = neg(modelCheck(st,~f))` |

| Module (model-checker.maude) | Provides |
|---|---|
| `SATISFACTION` | `State`, `Prop`, `_|=_ : State Prop ~> Bool [frozen]` |
| `LTL` | formula syntax + NNF equations |
| `LTL-SIMPLIFIER` | `¬φ` minimization before automaton construction |
| `MODEL-CHECKER` | `modelCheck : State Formula ~> ModelCheckResult`; `counterexample(TransitionsL, TransitionsL)` |
| `SAT-SOLVER` | `satSolve(:Formula)`, `tautCheck(:Formula)` |
| `LTL+`, `MODEL-CHECKER+` | `modelCheck+`, `witness(prefix, loop)` |

## Worked Example
The round-robin scheduler (12.5) — properties that *scale with the system*:
1. `NAT/{N :: NZNAT#}` defines naturals modulo `#` — itself a "dependent type" module.
2. `omod RROBIN{N}` builds configurations of `[i] : Proc` objects passing a `go([next])` token.
3. `CHECK-RROBIN{N}` defines `inCrit : Nat/{N} -> Prop` (process `[i]` critical) and `twoInCrit` (any two critical), then defines the *infinite family* of reentrance formulas recursively: `allProcessesReenter(s N)` conjuncts `(inCrit([s N]) -> nextIter inCrit([s N]))` down to `0`, where `nextIter F` iterates `O` exactly `2 * #` times.
4. `view 5 from NZNAT# to NAT is op # to term 5 . endv` instantiates everything once: system, predicates, and formula — `CHECK-RROBIN{5}`.
5. `red modelCheck(init, [] ~ twoInCrit) .` → `true`; `red modelCheck(init, [] guaranteedReentrance) .` → `true`; a deliberately wrong property (`[] (inCrit([1]) -> O O O inCrit([1]))`) returns a labeled 10-transition counterexample traversing exactly the round-robin cycle.

The takeaway: **parameterized modules let you verify entire families of (system, property) pairs** with one proof effort per instance — and recursive equation-defined formulas are the only sane way to write "each of the n processes re-enters within 2n steps."

## Key Takeaways
1. Prose properties become checkable ones in three moves: pick the state kind, define `Prop`-sort predicates with equations, drive `modelCheck` from an M-CHECK module.
2. The algorithm is refutation: `‖φ‖` holds iff no (prefix, loop) counterexample exists; every failure comes with an executable, labeled trace.
3. Finiteness of the reachable state space is your responsibility — the checker neither checks nor recovers from its absence (it just hangs).
4. Import `LTL-SIMPLIFIER` by default; label every rule you may ever need to blame.
5. `satSolve`/`tautCheck` settle formula sanity independently of any system — use them before blaming the model.
6. LTL+ (`E`/`A`) covers existence questions LTL can't say; witnesses are counterexamples turned inside out.

## Connects To
- **Ch 5 / 11**: the rewriting machinery and invariant searches underlie the Kripke graph; bounded/abstraction methods remain the fallback for infinite systems.
- **Ch 7**: parameterized system+property verification as in RROBIN; protecting-mode discipline for predicate extensions.
- **Ch 16**: `metaCheck` moves SMT-constraint checking into formulas for numeric side conditions.
- **Ch 17**: MODEL-CHECKER internals (`special`-implemented); model checking under the metalevel/strategies.
- **Ch 21**: debugging hung model checks (the classic symptom: reachable set not finite).
