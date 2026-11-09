# Chapter 5: System Modules

## Core Idea
A system module specifies a rewrite theory `R = (Σ, E ∪ A, ϕ, R)`: the equational part `(Σ, E ∪ A)` describes the system's *statics* (states as canonical forms), the rules `R` its non-deterministic concurrent *dynamics*, and coherence lets the interpreter interleave them decidable-step by decidable-step. `mod M is ... endm` adds exactly one statement kind to functional modules: rules (plus `frozen`, which becomes effective here).

## Frameworks Introduced
- **Rules as local concurrent transitions**: `rl [label] : t => t' [attrs] .` — anywhere a `σ(t)` fragment is found (matched modulo the module's axioms `A`, with extension), the fragment becomes `σ(t')`; non-overlapping rule instances fire concurrently (truly-concurrent semantics; the sequential interpreter simulates interleavings). Statement attributes: `label`, `metadata`, `nonexec`, `print` — but **never `owise`** on rules.
- **Conditional rules**: `crl l : t => t' if C1 /\ ... /\ Ck .` — conditions may now include **rewrite conditions** `u => u'` besides equations/memberships/matching/abbreviated Boolean; evaluated left-to-right; solving a rewrite condition means *searching* (breadth-first) a proof from `σ(u)` to some canonical `w` that is an instance of `u'`.
- **Admissibility extension for rules**: everything from Ch 4 plus: if `Ci` is a rewrite `ui => u'i`, the new variables are bound by matching `u'i` as an `E(M)`-pattern against the canonical result of the search.
- **Coherence** (the executability contract of rules vs. equations): for every one-step rewrite `t —→¹_R/A t'` and canonical form `t —→!_{E/A} u`, there must exist `u —→¹_R/A u'` with `t' =_{E∪A} u'`. Coherence turns undecidable "rewrite modulo `E ∪ A`" into: simplify to canonical form, then rewrite with `R` modulo known axioms `A` — what `rewrite` and `frewrite` actually do. Checkable (for unconditional rules) via critical pairs between rule and equation lefthand sides using `A`-unification; ground coherence is the weaker, checkable-in-practice version.
- **Frozen arguments constrain every strategy**: no rewriting ever happens below a frozen position — this is part of the *initial model* semantics, not just of the interpreter.
- **Initial model `T_R`**: for each kind, a labeled transition system (a category) whose states are `E ∪ A`-classes and whose transitions are proof equivalence classes — "truly concurrent" computations.

## Key Concepts
- **Vending machine signature**: `Marking` with `__ [assoc comm id: null]` — the canonical soup pattern: coins/items floating in an order-free multiset.
- **Rule starvation** (`rewrite` vs `frewrite`): `rewrite`'s top-down, rule-fair strategy keeps rewriting at the top symbol and may never enter subterms; `frewrite`'s position-fair, breadth-first-by-depth traversal reaches "starved" rules.
- **`continue ⟨n⟩` (`cont n`)**: extend the previous rewrite/search by n more steps/solutions.
- **`show rls M .`**: print a module's rules; also `show module`, `show sorts`, `show components`.
- **Search**: breadth-first exploration of the reachable state space (not one run: all runs).

## Mental Models
- Think of `rewrite`/`frewrite` as *one run each* — a simulation trace — and `search` as the *whole state space* query engine; only search answers LTL-ish reachability questions directly.
- Rules with a rewriting condition `P => {L} P'` make operational semantics executable: CCS synchronization `[par]` is a single conditional rule using two rewrite conditions plus `frozen` operators (reads as: both sides must be able to do complementary actions).
- When a rule seems never to fire, ask which strategy is starving it before suspecting the rule.

## Anti-patterns
- **`rl null => q .` instead of `rl M => M q .`**: `null` is only a `__`-subterm of itself — no extension, the rule can never insert into a nonempty marking. Always anchor inserts with a ranging variable.
- **Trusting `rewrite` to reach a rule below the top**: in `VENDING-MACHINE`, `buy-a`/`buy-c` never fire because `add-q/add-$/change` own the top layer; `BB-TEST` shows `rewrite` looping `a↔b` forever while `frewrite` reaches `bingo` in 3 steps.
- **Ignoring the `collapse at top` advisory**: a lefthand side `$ M` also matches a term *without* the top `__` (when `M ↦ null`) — sometimes intended, never silently safe (Sec 21.3.6).
- **`frewrite` output quirks**: only the rewritten subterm is reduced, so results print `(sort not calculated)` with non-canonical grouping — not a bug.
- **Terminal-state search in a nonterminating module**: `=>!` in the coin-generating module finds nothing but burns time; use `=>+` with `[n, m]` bounds.
- **Rules with `owise`**: not allowed; owise is equations-only.

## Code Examples
```maude
mod SIMPLE-VENDING-MACHINE is
  including VENDING-MACHINE-SIGNATURE .
  rl [buy-c] : $ => c .
  rl [buy-a] : $ => a q .
  rl [change] : q q q q => $ .
endm
```
- **What it demonstrates**: terminating vending rules; `rew in SIMPLE-VENDING-MACHINE : $ $ .` gives `q a c` — equational axioms (`comm`) let fragments match wherever they sit.

```maude
--- CCS-style synchronization (rewrite conditions + frozen)
op {_}_ : Act ActProcess -> ActProcess [frozen] .
op _|_ : Process Process -> Process [frozen assoc comm] .
vars P P' Q Q' : Process . var L : Label .
crl [par] : P | Q => {tau} (P' | Q')
  if P => {L} P' /\ Q => {~ L} Q' .
```
- **What it demonstrates**: a conditional rule whose condition is itself rewriting — the semantics of a process algebra as one rule.

## Reference Tables
| Command | Strategy | Notes |
|---|---|---|
| `rewrite [n] in M : t .` | top-down, rule-fair; re-canonicalizes the whole term after each rule | may starve subterm-only rules; result carries least sort |
| `frewrite [n] in M : t .` | depth-first, position-fair (breadth within depth); reduces only the rewritten subterm | reaches starved rules; result may be `(sort not calculated)` |
| `cont ⟨n⟩ .` | continue previous rewrite/search | same strategy as before |
| `search [n, m] in M : t ⟨arrow⟩ t' [such that cond] .` | breadth-first state-space search | `n` solutions / `m` depth bounds (either optional) |

| Search arrow | Meaning |
|---|---|
| `=>1` | exactly one step |
| `=>+` | one or more steps |
| `=>*` | zero, one, or more steps |
| `=>!` | only terminal (canonical, irreducible) states |
| `=>#` | states with more than one distinct successor |

Condition syntax in `such that`: equations, memberships, abbreviated Booleans, **and rewrite conditions** (`M:Marking => a a q q /\ M:Marking => c c`).

## Worked Example
"Can one dollar and three quarters buy an apple and a cake?" — answered by pattern search over terminal states:

```
Maude> search in SIMPLE-VENDING-MACHINE : $ q q q =>! a c M:Marking .
Solution 1 (state 4)
states: 6    rewrites: 5
M:Marking --> null
No more solutions.

Maude> show path 4 .
state 0, Marking: $ q q q
  ===[ rl [buy-a] : $ => q a . ]===> state 2, Marking: q q q q a
  ===[ rl [change] : q q q q => $ . ]===> state 3, Marking: $ a
  ===[ rl [buy-c] : $ => c . ]===> state 4, Marking: a c

Maude> show path labels 4 .
buy-a change buy-c
```

Reading the machinery: search enumerates the *state graph* (`show search graph .` prints it; states get numbers), finds the matching terminal state, and `show path` reconstructs one witness run. The `such that M:Marking =/= null` variant then distinguishes *which* extra objects each final marking holds — a one-line query computing over all possible executions. This is the exact machinery Chapter 11 lifts to invariant model checking.

## Key Takeaways
1. A rule fires anywhere its lefthand side matches modulo the operator axioms, respecting frozen positions; concurrency is real in the semantics, interleaved in the implementation.
2. Coherence is the price of executability: equations define canonical forms, rules apply to canonical forms — no rewrite is lost this way, and only this way.
3. `rewrite` = one run (top-fair), `frewrite` = one run (position-fair), `search` = all runs (breadth-first with bounds `[n, m]` and rich conditions).
4. Rewrite conditions make conditions into search problems; left-to-right order matters operationally.
5. Use variables (`M => M q`) to place work inside larger structure; use explicit top operators (`$ M => c M`) to force top-level rule priority.
6. Bound your searches (`[n, m]`, `cont n`, Ctrl-C) — state spaces are infinite more often than they look.

## Connects To
- **Ch 4**: everything equational — attributes, strategies, admissibility — is the `E ∪ A` half of the theory; `frozen` was declared there, enforced here.
- **Ch 6**: objects/messages/configurations are syntax sugar over exactly this rule machinery, with fair rewrite for object-message modules.
- **Ch 7**: `including` (and `protecting`) importation modes first glimpsed in the vending machine.
- **Ch 11**: `search` + conditions = invariant model checking; `=>#` and abstraction-based checking reappear there.
- **Ch 12**: LTL model checking adds temporal conditions on top of the same reachable-state graph.
- **App A**: full syntax for `rewrite`, `frewrite`, `search`, `cont`, `show ...`, and the debugger's `abort` on interrupt.
