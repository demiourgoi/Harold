# Chapter 16: SMT Solving

## Core Idea
Maude embeds an SMT solver (Yices2 by default; CVC4 buildable) behind a thin set of inert signatures (`BOOLEAN`, `INTEGER`, `REAL`, `REAL-INTEGER`) and one command: `check T .` returns `sat`/`unsat` for quantifier-free formulas over Booleans, Presburger/linear integer arithmetic, and rational linear arithmetic — constraint solving as a side tool inside rewrite-based analyses.

## Frameworks Introduced
- **The satisfiability view**: a QF Σ-formula φ is satisfiable in a Σ-algebra A iff some variable assignment satisfies it; valid iff ¬φ unsatisfiable. Unification (Ch 13–14) already decides satisfiability of *positive conjunctions* in initial algebras `T_Σ/G` (DNF + first-unifier per conjunct); SMT extends decidability to richer algebra fragments with a DPLL(T) engine.
- **One solver per binary**: the distributed Maude links Yices2; generic SMT-LIB notation is the exchange format, so other solvers can be compiled in. Three ways to do pure SAT: canonical forms in `BOOL-OPS`, the LTL `satSolve` (Ch 12), and this chapter's solver (fastest).
- **The four theory modules** (load `smt.maude`):
  - `BOOLEAN` — sort `Boolean` (distinct from `Bool`!): `true false not_ _and_ _xor_ _or_ _implies_`, plus SMT-flavored `_===_`, `_=/==_`, `_?_:_` (ite).
  - `INTEGER` — sort `Integer` (distinct from `Int`): integer constants `<Integers>`, `-_ _+_ _*_ _-_ _div_ _mod_`, comparisons `_<_ _<=_ _>_ _>=_`, `_===_`, `_=/==_`, `_?_:_`, and `_divisible_` (SMT-LIB argument order — reversed vs Maude's `_divides_`).
  - `REAL` — sort `Real` (rational linear arithmetic; the literal `/` in constants like `7/3` distinguishes reals): same op family plus `_/_`.
  - `REAL-INTEGER` — both plus coercions `toReal : Integer -> Real`, `toInteger : Real -> Integer`, and predicate `isInteger : Real -> Boolean`; models the `Int ⊂ Rat` subsort world.
  All operators are `special (id-hook SMT_Symbol ...)`: **inert at the Maude level** — no algebraic simplification happens in Maude; the term is shipped to the solver.
- **The command**: ``` check [in M :] T . ``` → `Result from sat solver is: sat` or `... unsat`. Formulas may mix operator families and variables of the involved sorts only.

## Key Concepts
- **Why inert signatures matter**: `Integer`/`Real`/`Boolean` are completely separate universes from Maude's `Int`/`Rat`/`Bool`; no subsorting between them, no equations — mixing them into Maude computations (or extending the sorts) is stated to cause inconsistencies.
- **Theories covered**: propositional SAT; Presburger arithmetic `(Z, 0, 1, +, >, ≥)`; rational linear arithmetic `(Q, Q, +, >, ≥)` (identical to the real-linear fragment because rational-coefficient linear systems solve over Q iff over R — sort named `Real` just to avoid clashing with `Rat`); and mixed integer+rational linear arithmetic with coercions.
- **Brittleness disclaimer (manual's own)**: only cursory query sanity checking, no exception catching — malformed `check` terms can misbehave.
- **Non-supported**: multiplication is linear-only in arithmetic (any `Integer * Integer` product is fine as a term, but the *solving* power is linear arithmetic; non-linear constraint solving is not available through this interface).

## Mental Models
- Read `check` as "an oracle next door": build the constraint term in Maude syntax, get a one-word verdict; use it inside invariant generation, guard analysis, or conjecture filtering (e.g. before a bounded model-checking run, check whether a path condition is even feasible).
- Read the four modules as *wire formats*, not datatypes: nothing computes; terms translate token-for-token into SMT-LIB.

## Anti-patterns
- **Expecting simplification or evaluation from the inert ops**: `2 + 2` inside `check` never reduces in Maude itself.
- **Mixing sorts with Maude's numeric sorts or adding subsorts**: explicitly warned against (inconsistency issues); translate explicitly.
- **Assuming exception handling / rich diagnostics**: the interface is minimal — validate terms yourself.
- **Relying on non-linear or quantified solving**: not this interface; use abstraction/refinement with Ch 11 techniques instead.

## Code Examples
```maude
load smt.maude
fmod TEST-RI is
  protecting REAL-INTEGER .
  vars W X Y Z : Boolean . vars I J K L : Integer . vars P Q R S : Real .
endfm

check toInteger(R) + toInteger(P) === toInteger(R + P) .   --- sat
check not(toInteger(R) + toInteger(P) === toInteger(R + P)) . --- sat (trunc vs sum!)
check -2 < I and -2 * I > -1 and I =/== -1 .              --- sat  (I = 0 works)
check -2 < I and -2 * I > -1 and I =/== -1 and I - I =/== I . --- unsat (I-I=0==I forces I=0, then -2*0<I? no)
```
- **What it demonstrates**: constraint style with variables, coercion semantics (`toInteger` truncation both sides satisfiable vs unsat flips), and how consecutive checks probe hypotheses (validity = check the negation).

## Worked Example
Deciding validity of a mixed-arithmetic claim by refutation:
1. Formulate the claim: `∀ I: for all integers I in (-2, ...)...` — as a QF formula by negation: to prove `f(I) ⇒ g(I)` valid, `check` the existential counterexample `f(I) and not g(I)`.
2. `check -2 < I and -2 * I > -1 and I =/== -1 .` → `sat`: a counterexample exists (I = 0); so the claim "I < -1" is false.
3. Add the missing constraint `I - I =/== I` → `unsat`: with that extra hypothesis no counterexample remains — the strengthened implication is valid over the integers.

The pattern: **SMT fills the numeric-constraint gap that rewriting and search cannot** — while all structural reasoning (multiset rewrites, protocol steps, invariants) lives in your module as elsewhere in this manual.

## Key Takeaways
1. `check [in M :] T .` ships inert formula terms to Yices2; answers: `sat`/`unsat`.
2. Four theories: Booleans, Presburger integers, rational (a.k.a. Real) linear arithmetic, and their combination with `toReal`/`toInteger`/`isInteger`.
3. The theory modules are wire formats — `Boolean/Integer/Real` intentionally disjoint from Maude's native data sorts; don't subsort or extend them.
4. Validity checks = satisfiability of the negation; combine with Ch 11/12 methods for hybrid structural+numeric verification.
5. The interface is minimal and brittle by design (solver-facing); pre-validate your terms.

## Connects To
- **Ch 8**: native `Bool/Int/Rat` sorts — translation targets/sources when moving data between Maude and SMT terms.
- **Ch 11–12**: invariant/LTL work enriched with arithmetic side conditions; abstraction predicates maybe SMT-checkable.
- **Ch 13–15**: unification/narrowing handle algebraic theories; `check` handles the linear-arithmetic fragment their output constraints might fall into.
- **Ch 17**: `metaCheck` exposes the same SMT decision procedure at the metalevel (Sec 17.6.12).
