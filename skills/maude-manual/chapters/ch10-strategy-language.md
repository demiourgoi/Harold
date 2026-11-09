# Chapter 10: Strategy Language

## Core Idea
The strategy language is a specification *layer above* rules: the rewrite theory is untouched, and named strategy expressions — built from rule labels, tests, and control combinators — decide where/when/how rules fire. This recovers deterministic, scripted, or algorithmic execution from nondeterministic systems (and from otherwise non-executable `[nonexec]` rules) without polluting the specification.

## Frameworks Introduced
- **Strategic rewriting**: `srewrite [n] in M : T using α .` — a strategy α maps a term to a *set* of result terms (`T_Σ → P(T_Σ)`); solutions are printed "Solution 1..., No more solutions"; order is implementation-dependent. `dsrewrite` is the depth-first variant: finds solutions in fewer rewrites/less memory but can get trapped in infinite branches (precedences: rules in syntactic order, outer→inner/left→right positions, α-before-β alternatives, leaving-the-loop precedes continuing).
- **Rule application tactic**: `label[X1 <- t1, ..., Xn <- tn]{α1, ..., αm}` — optional ground substitution pins rule variables; `{αi}` supplies strategies for each *rewriting condition* of a conditional rule (`step{all}`); `all` = one step of any labeled or unlabeled rule (excludes `nonexec`, external objects, implicit rules); `top(label)` restricts application to the topmost position.
- **Tests**: `match P s.t. C` / `xmatch` (fragments of the flattened top, modulo axioms) / `amatch` (any subterm) — like the `match` commands; success returns the subject term unchanged, failure = no solution.
- **Basic combinators**: `α ; β` (sequence on each α-result), `α | β` (union of results), `α*` (zero or more), `idle` (identity), `fail` (no results), `α ? β : γ` (conditional: β on α's results; γ on the initial term if α fails). Derived: `α or-else β = α ? idle : β`, `α+ = α ; α*`, `not(α) = α ? fail : idle`, `α !` (normalize: apply until irreducible), `try(α) = α ? idle : idle`, `test(α) = not(not(α))`.
- **`matchrew P(X1,...,Xn) s.t. C by X1 using α1, ..., Xn using αn`** (flavors `matchrew`/`xmatchrew`/`amatchrew`): match the subject against P, then rewrite the subterms bound to the `Xi` *in parallel and independently*, recombining all result combinations; pattern variables stay in scope inside the substrategies (usable in nested substitutions/calls); outer-bound variables partially instantiate the pattern.
- **`one(α)`**: return only the first found solution — big performance wins when pruned early and paths are interchangeable; dangerous when paths differ (`one(move)*` on Hanoi loops forever instead of solving).
- **Strategy modules** `smod M is ... endsm`: declare `strat f : ArgSorts @ SubjectSort [metadata] .` (overloading by argument kinds; subject sort advisory — undeclared/undefined strategies behave as `fail`); define `sd f(args) := α .` / conditional `csd f(args) := α if C .` with equational conditions only; attributes `metadata`, `label`, `print`; all matching definitions are tried; auxiliary data goes in imported functional modules (e.g. `HANOI-AUX`). Import modes keep their meanings but *in terms of rewriting paths*: new definitions of imported strategies can add paths (`extending`) or cut them via conditional-failures (`including`); runtime checks: none.
- **Parameterized strategy modules & theories**: `sth T is ... endsth` (e.g. `STRIV`); view mappings gain `strat f to g .`, `strat f : S...@S' to g .`, and `strat f(vars) to expr ⟨strategy expression⟩ .`; instantiating a functional/system module with a view into a strategy module promotes the result to a strategy module. The BACKTRACKING{X :: BT-STRAT} / 8-queens example: `solve := (match S s.t. isSolution(S)) ? idle : (expand ; solve)` with `expand` bound per problem — generic algorithms as (instantiated) strategies.

## Key Concepts
- **Separation of concerns**: rules say *what can happen*; strategies say *this run's policy*; the same module gets many execution regimes (`rewrite`/`frewrite`/`srewrite`/`dsrewrite`).
- **Strategy-controlled `nonexec` rules**: rules with extra variables run when the strategy supplies substitutions (`car-rental[U <- 'C1, I <- 'A3, ...]`) — the rent-a-car store finally executes (Sec. 6.2's `nonexec` rules).
- **Recursive strategy definitions**: recursion and mutual recursion among named strategies; base cases typically `idle`, guards as `try(...)` wrappers (`INSERTION-SORT` over `ARRAY`).
- **`srew` vs `search`**: `srew` explores the *strategy-pruned* rewriting subtree; still fair (all reachable solutions eventually found); `dsroot`… `dsrew` orders the same tree depth-first.
- **Position control** summary: `top()` for topmost; `matchrew ... by X using α` for inner subterms; `amatch` to test anywhere; default rule application: anywhere.

## Mental Models
- Think of a strategy as a nondeterministic program over the rewriting tree: `;` sequences, `|` branches, `*` loops, `? :` if-then-else, `matchrew` = scoped parallel blocks.
- Read `α or-else β` as priority: "β as fallback" — the idiom for heuristics (e.g. "move to tower 2 if possible, otherwise any move") and the source of subtle semantics when combined with importation (negative branches stop being evaluated when a definition of α appears in a submodule).
- Strategy theories + views are the algorithm-library pattern: package the algorithm (backtracking, sorting, traversal) once, instantiate per problem.

## Anti-patterns
- **`one` pruning too early**: `one(move) *` discards alternative moves each iteration — a solver that loops; apply `one` only where solution multiplicity is irrelevant.
- **Expecting deterministic solution order** from `srew`: none is promised; express order explicitly or use `one`/`dsrew` deliberately.
- **Rewriting conditions in `csd`**: not allowed (conditions are equational); use rewriting inside the strategy expression instead.
- **Defining imported strategies in the importer** when `protecting` was claimed: adds/changes paths — a false protection claim (choose `extending`/`including`).
- **Undefined but declared strategies used silently**: they act as `fail`; a typo'd strategy name is indistinguishable from a failing strategy — check declarations (`smod` warnings appear only for conflicting redeclarations).
- **Relying on subject sorts** in `strat` declarations for disambiguation: they are ignored; only argument kinds matter.

## Code Examples
```maude
smod HANOI-SOLVE is
  protecting HANOI . protecting HANOI-AUX .
  strat moveAll : Nat Nat Nat @ Hanoi .
  vars S T C M : Nat .
  sd moveAll(S, S, C)           := idle .
  sd moveAll(S, T, 0)           := idle .
  sd moveAll(S, T, s(C))        := moveAll(S, third(S, T), C)
                                 ; move[S <- S, T <- T]
                                 ; moveAll(third(S, T), T, C) .
endsm
--- srew (0)[3 2 1] (1)[nil] (2)[nil] using moveAll(0, 2, 3) .
--- result Hanoi: (0)[nil] (1)[nil] (2)[3 2 1]
--- fmod HANOI-AUX: op third : Nat Nat ~> Nat uses a matching equation over {0,1,2}
```
- **What it demonstrates**: recursive strategy definitions with base cases; rule invocation with variable substitution; classic tower-transfer algorithm expressed at the strategy level, executed by `srew` even though plain `rew` loops.

```maude
--- scripting the rent-a-car store's nonexec rules (Sec. 6.2)
srew StoreConf using
  car-rental[U:Oid <- 'C1, I:Oid <- 'A3, NumDays:Int <- 2, A:Oid <- 'a0]
  ; new-day ; new-day ; on-date-car-return ; ...
```
- **What it demonstrates**: manual variable assignment making non-admissible rules executable; `;` as workflow scripting over a rule base.

## Reference Tables
| Construct | Form | Semantics |
|---|---|---|
| rule tactic | `l[x <- t]{α}` / `all` / `top(l)` | apply rule l (with substitution; condition strategies); all rules once; topmost only |
| test | `match/xmatch/amatch P s.t. C` | filter: subject passes through on match+condition |
| subterm rewrite | `matchrew/xmatchrew/amatchrew P by X using α, ...` | parallel independent rewriting of matched subterms |
| constants | `idle` / `fail` | identity / no solutions |
| control | `α ; β`, `α | β`, `α*`, `α ? β : γ` | sequence, union, closure, conditional |
| derived | `or-else`, `α+`, `not`, `α !`, `try`, `test`, `one(α)` | library of idioms built on the above |
| module | `smod ... endsm`, `strat f : τ @ S .`, `sd/csd` | named, recursive, overloadable strategies |
| parameterization | `sth ... endsth`, `strat ... to ...`, `strat ... to expr ...` | strategy theories/views/instantiation |
| commands | `srew [n] in M : T using α .` / `dsrewrite` | fair / depth-first strategic search |

## Worked Example
Counting Hanoi moves with `matchrew` + `top` (HANOI-COUNT, `< H, N >` pairs):

```
srew [1] : < (0)[3 2 1] (1)[nil] (2)[nil], 0 >
  using (matchrew < H, N > by H using move, N using top(inc)) * ; amatch (2)[3 2 1] .
result Game: < (0)[nil] (1)[nil] (2)[3 2 1], 7 >
```

Three lessons in one line: (1) `matchrew < H, N > by H using move, N using top(inc)` decomposes the top level and rewrites the Hanoi part by any move while the counter advances by `top(inc)` — without `top`, `inc` also fires inside `s(s(...))` successors and rewrites explode; (2) the whole construct iterates with `*` until the following `amatch (2)[3 2 1]` accepts the final state (test as loop guard); (3) the alternative ballet of solutions is the compiler's choice — the `[1]` bound and `one(...)` are your controls over it.

The generic `BACKTRACKING` module completes the picture: `solve := (match S s.t. isSolution(S)) ? idle : (expand ; solve)` is instantiate-able over any `State`/`isSolution`/`expand` triple — the 8-queens instance binds `expand` to `top(next) ; match L s.t. isOk(L)` and `srew ... using solve` yields the first accepted placement; `dsrew` finds it ~30× faster at equal depth risk.

## Key Takeaways
1. Strategies leave `(Σ, E∪A, ϕ, R)` untouched and add an execution policy on top — use them instead of contorting rules with control data.
2. Every combinators toolbox you expect from tactical/regular-expression languages is here: `;`, `|`, `*`, `? :`, `idle`, `fail`, plus match-and-rewrite-locality via `matchrew by`.
3. Rule tactics accept explicit substitutions, so non-admissible/nonexec rules become runnable under strategy control (the debt of nondeterminism is paid by the caller).
4. Named strategies are first-class: recursive, overloadable, importable under the same protecting/extending/including semantics — defined in terms of allowed rewriting paths.
5. Strategy theories + views make algorithm libraries (`BACKTRACKING`) instantiable; `to expr` bindings inline simple cases without a dedicated smod.
6. `srewrite` is fair over the pruned tree; `dsrewrite` trades completeness-risk for speed; `one(...)` trades diversity for early pruning.

## Connects To
- **Ch 5**: `rewrite`/`frewrite`/`search` fix one policy each; strategies generalize all three over the same module.
- **Ch 6**: rent-a-car's nonexec rules become executable (canonical strategy-use case); `top` matches the object-top discipline.
- **Ch 4**: `owise`/`strat`-based efforts to control evaluation are equations-level; strategies are the rule-level counterpart.
- **Ch 7**: module expressions, theories, views, and importation semantics replicated at the strategy level (`sd` definitions as statements, `strat` renamings).
- **Ch 17**: strategy metarepresentation (`META-STRATEGY`); internal strategies via `metaSrewrite` and `srewrite`-driven metalevel runs.
- **Ch 21**: trace/debug strategy executions (`show strategy` environments, breakpoints on labeled definitions).
