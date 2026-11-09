# Chapter 11: Model Checking Invariants Through Search

## Core Idea
Invariants — "nothing bad ever happens" — are the most common safety properties, and Maude model-checks them with the plain `search` command: looking for a reachable state that *negates* the invariant. On a finite state space this is a decision procedure; on infinite state spaces it is a semi-decision procedure (a violated invariant is always found; a satisfied one loops forever), and bounded/abstraction techniques restore confidence or full verification.

## Frameworks Introduced
- **Invariant checking by search**: an invariant `I` of the system `R` with initial state `init` holds (`R, init |= □I`) iff the violating search has *no solutions*:
  ```maude
  search init =>* x:Kind such that I(x:Kind) =/= true .
  --- equivalently, if I is total (owise!): search init =>* x:Kind such that not I(x:Kind) .
  ```
  Soundness needs `E` ground Church-Rosser + terminating, rules ground coherent with `E`, and purely equational rule conditions — the module-algebra contract of Ch 4-5.
- **Bounded model checking**: append a depth bound — `search [1, d] in M : init =>* <pattern> .` explores only states within `d` transitions. Incomplete (bugs may hide deeper) but terminates and finds shallow counterexamples fast; scale-friendly tuning: declare the successor `s_ [ctor iter]` for gigantic speedups (`READERS-WRITERS` at depth 10^5: from hours to sub-second).
- **Deadlock-freedom style checks need no predicate**: a dangling final state *is* the counterexample — `search init =>! x:State .` (terminal states); if a violation is characterized by a *structural pattern* (`< s(N), s(M) >` = readers and writers simultaneously), search for the pattern directly.
- **Explicit enabledness predicates** (alternative): extend the module with `enabled : State -> Bool` defined by matching equations + `owise`, and search `... such that enabled(X:State) =/= true .`
- **Abstraction = adding equations** (11.4): collapse the infinite reachable set to a finite one by an equational theory extension `A = (Σ, E ∪ G, ϕ, R)`, then model check `A`. Requirements: `G` keeps `E ∪ G` ground Church-Rosser/terminating, rules ground coherent, and `G` is **invariant-preserving** (identical `=_{E∪G}` states agree on `I` — guaranteed when the abstraction *protects Bool*, i.e. true/false remain the only canonical forms). Key implications:
  - validated invariant on `A` ⇒ invariant holds on the concrete system `R`;
  - a counterexample in `A` may be *spurious* — refine by removing equations from `G`.
- **The invariant-protection checklist** (all tool-supported): (i) no equations with `true`/`false` on the left; (ii) **MTT** (termination, AProVE backend); (iii) **CRC** (ground confluence + sort-decreasing: "all critical pairs joined"); (iv) **SCC** (sufficient completeness of defined functions); plus the **ChC** (coherence checker) for rule-vs-equation critical pairs — with reasoning by cases/search to close ground-coherence gaps manually.

## Key Concepts
- **Invariant `I`**: equationally-defined Boolean predicate over a chosen state kind + initial state; `R, init |= □I` iff `init` and all states reachable through the rule transition system satisfy `I`.
- **Search as semi-decision for infinite systems**: breadth-first search guarantees finding any *reachable* violating state in finite time (finite branching); non-violation = non-termination.
- **Transition system behind**: states are `E`-equivalence classes of terms of a chosen kind; transitions = one-step rewrites between representatives.
- **Counterexample reconstruction**: any solution to a violating search comes with its witness path (`show path N .` from Ch 5) — free debugging.
- **State explosion counters seen**: `[n, m]` bounds; `iter` towers; abstraction equations; predicate- vs pattern-characterized violations.
- **Adding equations breaks protecting claims**: declare `including` explicitly when the abstractor identifies concrete-distinct states (a protecting module earlier in a chain keeps its mode otherwise — Sec. 7.1.4's default-conventions).

## Mental Models
- Read invariant checking as "brute-force induction evidence": search examines every reachable state (up to depth/abstraction claims) — a negative result under full state-space finiteness *is* a proof.
- Read `search ... =>! pattern .` as "give me a terminal (dead) state": the shape encodes the violation; the path explains how the system got stuck.
- Treat abstraction as intentional controlled confusion: add exactly enough equations to finitize the state space but preserve the predicates you care about — then export the proof obligations to MTT/CRC/SCC/ChC.

## Anti-patterns
- **Unbounded search on infinite state spaces for a true invariant**: never terminates; always think about `[n, m]` bounds or an abstraction first.
- **Interpreting "no solutions" from an aborted/timeout bounded search as proof**: bounded checks are evidence, not proof — say so in your analysis.
- **Abstraction equations that mention `true`/`false` on the left**: destroys Bool protection and tears up invariant preservation — rework `G`.
- **Forgetting the executability re-checks after adding `G` or predicate modules**: coherence/termination violations make search results unsound regardless of how good the intuition was.
- **Unbounded deadlock search in a duplicating system** (`dupl` in PROCS-RESOURCES yields infinitely many deadlocks): give a solution bound, e.g. `search [5] ...`.
- **Reasoning search = rule search**: freeing symbol use in patterns is fine (variables), but a pattern with extra defined-function symbols gets equationally reduced — verify the pattern means what you intend by `red`ing it first.

## Code Examples
```maude
mod READERS-WRITERS is
  sort Nat . op 0 : -> Nat [ctor] . op s : Nat -> Nat [ctor] .
  sort Config . op <_,_> : Nat Nat -> Config [ctor] .
  vars R W : Nat .
  rl < 0, 0 >     => < 0, s(0) > .
  rl < R, s(W) >  => < R, W > .
  rl < R, 0 >     => < s(R), 0 > .
  rl < s(R), W >  => < R, W > .
endm
--- Pattern-characterized violations directly:
search [1, 100000] in READERS-WRITERS : < 0, 0 > =>* < s(N:Nat), s(M:Nat) > .  --- mutex
search [1, 100000] in READERS-WRITERS : < 0, 0 > =>* < N:Nat, s(s(M:Nat)) > . --- one-writer
--- both: no solution up to depth 100000 (state count 100002)
```
- **What it demonstrates**: bounded verification whose patterns are the *negated* invariants spelled structurally, plus the giant `[1, 100000]`-bound lesson (and the `[ctor iter]` speedup on `s_` when formal tools are not involved).

```maude
mod READERS-WRITERS-PREDS is protecting READERS-WRITERS .
  ops mutex one-writer : Config -> Bool [frozen] .
  eq mutex(< s(N:Nat), s(M:Nat) >) = false .
  eq mutex(< 0, N:Nat >) = true .
  eq mutex(< N:Nat, 0 >) = true .
  eq one-writer(< N:Nat, s(s(M:Nat)) >) = false .
  eq one-writer(< N:Nat, 0 >) = true .
  eq one-writer(< N:Nat, s(0) >) = true .
endm
mod READERS-WRITERS-ABS is including READERS-WRITERS-PREDS . including READERS-WRITERS .
  eq < s(s(N:Nat)), 0 > = < s(0), 0 > .   --- collapse: >1 readers, 0 writers -> one reader
endm
```
- **What it demonstrates**: explicit predicates (needed to *state* preservation) and the one-equation abstraction that finitizes the reachable set for full — tool-discharged — verification.

## Worked Example
The full abstraction workflow on READERS-WRITERS (invariant-preserving collapse):
1. Define invariant predicates (`READERS-WRITERS-PREDS`) — they name what the abstraction must not confuse.
2. Add collapsing equations (`READERS-WRITERS-ABS`); its states reduce to `< 0,0 >, < N,0 → <1,0>, < N, s(0) > → <0,1>, < N, s(s(0)) > → <0,2>/...` — a finite set.
3. Discharge proof obligations: `(check Church-Rosser ...)`, `(scc ...)`, MTT termination, `(check coherence ...)` — the ChC leaves one unrewritten critical pair, closed *by cases* with `search ... =>1 X:Config .` showing each ground instance is coherent.
4. Model check the abstraction itself: its reachable set finite ⇒ both invariant searches terminate (no solutions) ⇒ `mutex` and `one-writer` hold in the *concrete* system.

That result — a sound proof about an infinite-state system from a finite search plus tool-checked side conditions — is the archetype: **abstraction trades your obligation to check every state for Maude's obligation to evaluate cleanly the ones that remain**. Spurious counterexamples mean refine `G`; a too-weak collapse means the state space stays infinite — and the whole tool chain (MTT/CRC/SCC/ChC) exists to make the small print trustworthy.

## Key Takeaways
1. `search [init =>* violating-pattern | state such that not I]` *is* invariant model checking; no new machinery — just the Ch 5 command aimed at negations.
2. Finite reachable state space ⇒ complete decision procedure; infinite ⇒ semi-decision (violations always found, successes never confirmed); know which world you're in.
3. Bounded model checking (`[k, d]` bounds) is incomplete-but-useful evidence; use `iter` attributes to make deep searches feasible.
4. Deadlock-freedom patterns via `=>!`; enabledness predicates otherwise; both are ordinary Maude definitions.
5. Equational abstraction (`+G` equations) turns infinite-state verification into a finite one iff you can show Bool protection — use MTT, CRC, SCC, and ChC to discharge every claim mechanically.
6. Counterexamples arrive with witness paths — treat them as test cases for the fix and regression anchors.

## Connects To
- **Ch 5**: search command machinery (arrows, conditions, paths) is the substrate.
- **Ch 7**: importation modes (why the second `including` in the abstraction matters; default conventions).
- **Ch 12**: LTL model checking generalizes this chapter (`[] I` is just the simplest temporal formula), with the Kripke-structure machinery invariants alone never need.
- **Ch 17**: same invariant methodology per each metalevel cell; meta-search.
- **Formal tools ecosystem** (MTT, CRC, SCC, ChC): referenced throughout as the verification package for executability preconditions.
