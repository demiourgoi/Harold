# Chapter 15: Narrowing

## Core Idea
Narrowing is rewriting with logical variables: matching is replaced by variant-based unification, so a rule can apply to instances of a symbolic state you haven't materialized. Maude's `vu-narrow` command performs symbolic reachability analysis — "what instantiations of the initial term can reach the target pattern?" — over system modules whose rules are tagged `[narrowing]`, using the Ch 14 unification engine at every step.

## Frameworks Introduced
- **The narrowing step**: `t ⇝_{σ,p,R,E∪Ax} t'` at a non-variable position `p` with rule `l → r` and unifier `σ ∈ CSU_{E∪Ax}(t|p = l)` of the *whole equation* (not just pattern) modulo variant equations + axioms; `t' = σ(t[r]p)`. Sequences accumulate substitutions; answers pair an **accumulated substitution** (from the start) with a **variant unifier** (matching the end to the target) — *you compose them by hand* for the final instance.
- **The command** (`vu` = variant-unification):
  ```maude
  {fold|vfold|path} vu-narrow {filter|delay} [n, m] in M : T1 =>{1|+|*|!} T2 .
  ```
  `[n]` solutions / `[,]` depth bounds as in `search`; the target is *unified* (not matched) with the reached state, and may share variables with the start. `=>!` means strongly irreducible final terms (cannot be narrowed further).
- **The `[narrowing]` attribute** (rules): mirrors Ch 14's `[variant]` for equations — only `rl` (unconditional), LHS not a single variable (wrap the state in a unary symbol if needed), rules must be **Ax-coherent**; conditional rules and non-tagged rules are ignored by narrowing. Extra RHS variables are fine **iff** the rule also carries `[nonexec]` (narrowing ignores `nonexec`); frozen arguments keep their context-sensitive meaning.
- **Theories**: `mod (Σ, G ∪ E ∪ Ax, R ∪ H)` — `E` = `[variant]` equations (Ch 14 restrictions), `R` the `[narrowing]` rules, `G`/`H` unrestricted leftovers. After each narrowing step, `G` equations simplify the term (built-ins like `+` survive this way!) — but note: **narrowing + extra simplification is incomplete** (complete symbol-level narrowing uses only `E ∪ Ax`).
- **Completeness (15.3)**: for linear reachability goals and top-rewrite theories, narrowing computes *all* `ρ` solutions: any concrete rewrite sequence `ρ(t) →* ...` is captured by some narrowing substitution σ with `ρ =_Ax σ; τ`. Applications: equational unification, symbolic reachability, protocol verification, functional-logic programming, termination proofs.
- **Folding (15.6.3–4)**: `{fold}` (axioms only) / `{vfold}` (+ variant equations) fold the reachability *tree* into a *graph*, merging a new state into an old one when it is an instance modulo `E ∪ Ax` — potentially finite graphs from infinite trees. Abbreviation: `fvu-narrow`. After folding, `show most general states` lists unfolded states; `show frontier states` lists open leaves (both also available unfolded).
- **Path tracing (15.6.5)**: `{path} vu-narrow ...` records the sequence; then `show narrow path n .` / variants print labeled rule applications and substitutions per step — the debugging/demonstration medium for symbolic runs.
- **Multiple initial terms (15.6.6)**: start from a *disjunction* of terms `_\/_`-joined, e.g. `< q X:Marking > \/ < $ X:Marking >`, covering several families of initial states in one command.

## Key Concepts
- **Symbolic reachability**: `∃vars s →* t` solved by narrowing breadth-first; compare rewrite-based `search` (instantiate-then-rewrite only).
- **Standardized apart**: every rule/equation is renamed with fresh variables (`#n`, `%n`, `@n` counters) per application — results independent of name choices.
- **Strong irreducibility** (`=>!`): narrowing ends in terms that *no narrowing rule* applies to — stronger than `search`'s rewrite-irreducibility; non-terminating narrowings can hide solutions that exist (`vending machine never narrows to a "final"` case) — reformulate with tighter sorts (`C:Coin`) or consuming-style rules.
- **Fold-friendly rule style**: rules that *consume/reduce information* (`< M $ c > => < M >`) fold nicely; rules that only *add* (`M => M q`) make every state an instance of the start — folding collapses the solution space instead.
- **`{filter,delay}`**: invoke filtered variant unification at each narrowing step (Ch 14), trimming the unifier sets per step — a major performance lever combined with folding.

## Mental Models
- Read `vu-narrow` as "search over an unspecified initial state": the accumulated substitution *is your answer* — the constraint on the initial variables that reaches the target.
- Read narrowing results modulo the E ∪ A reading of states: `< a c #1:Money >` in a solution *denotes a whole family* of concrete rewrites — narrowing is symbolic simulation of every instance at once.
- Read `[narrowing]`/`[variant]/[nonexec]` as the tagging triad that partitions your module into the symbolic machinery and the executable rest — attributes, not separate modules, hold the boundary.

## Anti-patterns
- **Forgetting to combine accumulated substitution + variant unifier**: each solution's real instance is their composition; the printed parts alone under-specify the concrete run.
- **Expecting completeness with `G`-simplification or conditional rules in the path**: incomplete by construction (documented); keep the symbolic core inside `E ∪ R`.
- **Variable lefthand sides**: forbidden ([narrowing] without a proper pattern) — wrap the whole state with an extra symbol/kind.
- **`=>!` queries on non-terminating symbolic models**: no narrow-final state exists — either bound the search, retry with consuming-style rules, or tighten sorts.
- **Unfolding folded semantics**: folded-state solutions are "most general" modulo instantiation — a folded frontier is not exhaustive concrete states; don't double-count or misread `show frontier states` as failure.
- **Plain `vu-narrow` on spec styles inherently infinite** (adding-only rules, big Logical-variable sorts): prefer bounded or folding variants before blaming the engine.

## Code Examples
```maude
mod NARROWING-VENDING-MACHINE is
  ... sorts/op __ [assoc comm id: empty] as before ...
  var M : Marking .
  rl [buy-c] : < M $ > => < M c > [narrowing] .
  rl [buy-a] : < M $ > => < M a q > [narrowing] .
  eq [change] : q q q q M = $ M [variant] .
endm

Maude> vu-narrow [1] : < M:Money > =>* < a c > .
Solution 1
  state: < a c #1:Money >
  accumulated substitution: M:Money --> $ q q q #1:Money
  variant unifier:        #1:Money --> empty
--- hand-composed: M ↦ $ q q q  (a dollar and three quarters buys an apple and a cake)
```
- **What it demonstrates**: the full narrowing answer structure, the [narrowing]/[variant] tags, and the dollar-equivalence flowing in through the change equation.

```maude
--- consuming-style: rules remove information => foldable to a finite graph
rl [buy-c] : < M $ c > => < M >    [narrowing] .
rl [buy-a] : < M $ a > => < M q >  [narrowing] .

Maude> fvu-narrow : < M:Marking c c > =>* < empty > .
Solution 1  state: < %1:Marking >
  accumulated substitution: M:Marking --> $ $ %1:Marking
  variant unifier: %1:Marking --> empty
No more solutions.   --- finite graph; the plain vu-narrow does not stop
```
- **What it demonstrates**: the logic-programming-style consumption pattern that makes `{fold}` finite and the answer crisp ("two dollars cover two cakes").

## Reference Tables
| Element | Narrowing-legal form |
|---|---|
| rules (`R`) | `rl ... [narrowing]` — unconditional, non-variable LHS, Ax-coherent; `+ [nonexec]` allows extra RHS variables |
| equations (`E`) | `eq ... [variant]` per Ch 14 (confluent/terminating/sort-decreasing/coherent) |
| axioms (`Ax`) | Ch 13 supported set |
| other rules/equations (`H`, `G`) | ignored by narrowing; `G` used for post-step simplification (incomplete combo) |
| frozen arguments | honored — no narrowing below a frozen position |

| Option prefix | Meaning |
|---|---|
| (none) | breadth-first narrow, tree |
| `{fold}` / `fvu-narrow` | fold modulo axioms |
| `{vfold}` | fold modulo axioms + variant equations |
| `{path}` | record narrow trace for `show narrow path` |
| `{filter}` / `{delay}` | filtered variant unification at each step |

## Worked Example
"Can any combination of four coins buy an apple and a cake with useless-change left over?" — a single `=>!` narrowing question:

```maude
vu-narrow in NARROWING-VENDING-MACHINE :
  < C1:Coin C2:Coin C3:Coin C4:Coin > =>! < M:Money a c > .
Solution 1  acc: C1-->q C2-->q C3-->q C4-->$   unifier: M:Money --> empty
Solutions 2-4: the same multiset in every order
No more solutions.
```

The mechanics: (1) the initial kind (`Coin`, exactly four) prevents the non-terminating "unknown money" formulation; (2) `=>!` correctly demands strong irreducibility — nothing left the machine can use (here `M ↦ empty`, but e.g. a lone `q` wouldn't survive either); (3) the four order-variant solutions reflect ACU-multiset matching of the coins — semantically one answer, and `show frontier states` then reports `*** frontier is empty ***` confirming the symbolic tree terminated. This is the pattern for real symbolic queries: **constrain the initial shape, pick the arrow by what "done" means, and let variant unification reason modulo the change equation.**

## Key Takeaways
1. `vu-narrow` = `search` lifted past concretization: solve `∃ x̄ s →* t` symbolically, with unifiers instead of matches.
2. Tag your rules `[narrowing]` and your equations `[variant]`; everything else stays executable Maude untouched (and `G`-equations still simplify after each step, incompletely but usefully).
3. Answers have two parts (accumulated substitution + variant unifier) — compose them yourself.
4. Folding (`{fold}`/`{vfold}`, esp. with `{filter}`) can turn infinite narrow-trees into finite graphs — if your rules consume information; adding-only rule styles defeat folding.
5. Extra RHS variables (+ `[nonexec]`) are narrowing's logic-programming features — giving generators/co-inductive behaviors.
6. The narrowing solution space is breadth-first and non-terminating unless bounded, folded, or inherently finite: bound everything you explore.

## Connects To
- **Ch 13 / 14**: the unification stack underneath (Ax CSUs, then variant-based `E ∪ Ax`); the same completeness warnings apply inside steps.
- **Ch 5**: `search` is the rewriting counterpart (matching, not unification); `vu-narrow` shares the arrow vocabulary.
- **Ch 10**: strategies control one narrowing is *not* strategy-driven (yet) — you control by attributes and formulation.
- **Ch 16**: `vu-narrow` + SMT reasoning combine to reach impossible states modulo arithmetic.
- **Ch 17**: `metaNarrow`* ... narrowing results reachable at the metalevel for meta-programmed symbolic analysis.
- **Cryptographic protocol verification**: the flagship application — reachability modulo an equational theory of the attacker's capabilities, over symbolic messages exactly as here.
