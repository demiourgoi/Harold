# Chapter 3: System Modules

## Core Idea
Rewriting logic is two ideas — states and transitions. A system module (`mod ... endm`) declares states as constructor terms of an all-encompassing sort and transitions as **rewrite laws** `rl [label] : LHS => RHS .`, irreversible one-way arrows between states. "Equations are the nuts and bolts and gears and girders; rewrite laws create the machine."

## Frameworks Introduced

- **Rewrite law** — `rl [name] : stateA => stateB .` The bracketed label is optional but practically necessary (search/display refer to it). `=>` (NOT `=`) marks irreversibility: the law never runs backwards.
- **State-as-constructor discipline** — states are expressed as constructors "since the states cannot, and should not, be reduced further"; both sides of a law share one all-encompassing sort (often literally named `State`, with subsorts for specific states).
- **State combination** — binary constructor with `assoc comm id:` turns a soup of state atoms into one state term: `op _&_ : State State -> State [ctor assoc comm id: 1] .` (identity `1` declared alongside).
- **Precise-transitions pattern** — the more realistic the situation, the more factors each law's left-hand side mentions (crane laws name `empty`, `clear(X)`, `floor(X)` explicitly — four laws: `pickup`, `putdown`, `unstack`, `stack`).
- **Sequencing via data** — when a transition must also compute (count cigarettes smoked), carry data inside the state constructor arguments: `rl [smoke] : c(X) => b(X + 1) .`
- **Rewrite with applicability condition that is itself a rewrite** — `crl [r] : b(X) => c(X * 2) if a(X) => b(Y) .` The condition means "somewhere-reachable": the law fires only if some rewrite of `a(X)` can produce a `b`-state. Read the inner `=>` as a search.
- **Exploration toolkit** — bounded `rew`, fair `frew`, incremental `continue`, and `search` with pattern targets and variables (declared on-the-fly, or it won't parse).

## Key Concepts
- **rl / crl** — rewrite law, conditional rewrite law keywords (`mod ... endm`).
- **Termination is NOT promised** — a legitimate system module may loop (`rl a => b .` with `rl b => a .`); rewriting does not simplify, so always be ready with a bound.
- **rew (rewrite)** — default strategy: `rew [100] term .` applies up to N rewrite laws; without the bracket, unbounded until termination (risky).
- **frew (frewrite)** — "fair rewrite": picks laws so none is starved. Fix for the deafish default strategy that ping-pongs one law forever.
- **continue** — `continue 1 .` continues the current rewrite strategy for X more steps after a previous `rew`/`frew`.
- **search** — `search in MOD : start =>+ target .` finds rewrite paths; `=>+` = one or more steps; `=>!` = terminal target (a state that cannot be rewritten further).
- **Solution / substitution** — each search solution reports the state number and its substitution (`M:State --> ...`); `show path N .` prints the step-by-step path (omitted numbers are the dead ends).
- **strategies** — "order of operation" for applying rules; `rew` is a built-in default strategy (writing custom ones is out of the primer's scope).

## Mental Models
- Think "states are snapshots, laws are one-way doors between them" — never write `=` between states you do not consider mathematically equal.
- Think of the default `rew` strategy as having "very little imagination": it hammers the first applicable law. Use `frew` when progress stalls in a loop.
- Think of `search` as goal-driven exploration: state the start pattern and the end pattern with variables, read the solutions as witnesses, and `show path N` as the proof transcript.
- Prefer state-constructor arguments (counters, owners, weights) over side conditions when the datum naturally belongs to the state; reach for `crl` only when the condition "can't be easily expressed as a state."

## Anti-patterns
- **Confusing equations with rewrite laws**: simplification needs `eq` (RHS strictly simpler); constitutional change needs `rl` — "a cigarette butt is definitely not equal to a newly made cigarette."
- **Unbounded `rew` on non-terminating modules**: use the bracketed bound as "plan B" since valid rule sets can loop.
- **Omitting the label** on laws you intend to talk about, or variables in `search` without on-the-fly declarations.
- **Expecting default strategies to be clever**: "don't expect it to build the Tower of Hanoi" — direct behavior with `search` or bounds.

## Code Examples

The cigarette puzzle — 16 cigarettes become 21 smoked; counting moved into the state arguments:

```maude
mod COUNTING-CIGARETTES is
    protecting NAT .
    sort State .
    op c : Nat -> State [ctor] .
    op b : Nat -> State [ctor] .
    op __ : State State -> State [ctor assoc comm] .
    vars W X Y Z : Nat .
    rl [smoke]   : c(X) => b(X + 1) .
    rl [makenew] : b(W) b(X) b(Y) b(Z) => c(W + X + Y + Z) .
endm
```

The arcade crane — states are glued by `_&_` with identity `1`; four transitions over `floor/on/clear/hold/empty` facts:

```maude
mod ARCADE-CRANE is
    protecting QID .
    sorts ToyID State . subsort Qid < ToyID .
    op floor : ToyID -> State [ctor] .
    op on : ToyID ToyID -> State [ctor] .
    op clear : ToyID -> State [ctor] .
    op hold : ToyID -> State [ctor] .
    op empty : -> State [ctor] .
    op 1 : -> State [ctor] .
    op _&_ : State State -> State [ctor assoc comm id: 1] .
    vars X Y : ToyID .
    rl [pickup]   : empty & clear(X) & floor(X) => hold(X) .
    rl [putdown]  : hold(X) => empty & clear(X) & floor(X) .
    rl [unstack]  : empty & clear(X) & on(X,Y) => hold(X) & clear(Y) .
    rl [stack]    : hold(X) & clear(Y) => empty & clear(X) & on(X,Y) .
endm
```

Search with a variable target and reading the witness path:

```text
Maude> search in ARCADE-CRANE :
    empty & floor('mothergoose) & on('teddybear,'mothergoose)
    & on('soccerball,'teddybear) & clear('soccerball)
    & floor('dragondude) & clear('dragondude)
  =>+ empty & floor('teddybear) & floor('mothergoose) & M:State .

Maude> show path 69 .
```

Conditional rewrite law whose condition is a rewrite (reachability, not equality):

```maude
crl [rewrite] : b(X) => c(X * 2) if a(X) => b(Y) .
```

## Reference Tables

Rewrite-command reference:

| Command | Meaning |
|---|---|
| `rew [n] t .` / `rewrite [n] t .` | apply up to n laws with the default strategy |
| `frew [n] t .` / `frewrite [n] t .` | fair strategy — no rule starves |
| `continue n .` | continue the previous rewrite by n more steps |
| `search t1 =>+ t2 .` | all paths with at least one step |
| `search t1 =>! t2 .` | target irreducible/terminal state |
| `show path n .` | print the rewrite path that reached state n |

Legal condition forms for `crl` (all equivalent for `a(X) => b(X - 1)`):

| Form | Reads as |
|---|---|
| `if X > 0 .` | Boolean condition true |
| `if X > 0 == true .` / `if X > 0 = true .` | explicit Bool equality |
| `if X :: NzNat .` (or `:`) | membership test |
| `if s(N:Nat) := X .` | pattern match |
| `if a(X) => b(Y) .` | inner rewrite is reachable |

## Worked Example
Take the crane's Box A state: `empty & floor('mothergoose) & on('teddybear,'mothergoose) & on('soccerball,'teddybear) & clear('soccerball) & floor('dragondude) & clear('dragondude)`. `rew [2]` picks up Dragon Dude and stacks him; `rew [4]` loops the same pair forever ("all that's happening is a continual stacking and unstacking of Dragon Dude"). `frew [30]` instead frees every toy onto the floor because every rule gets a turn. To do something purposeful — swap Teddy Bear and Mother Goose — fall back to search: `search ... =>+ <target pattern>` yields `Solution 1 (state 69)`, and `show path 69 .` prints the 8-rule witness: unstack/stack/putdown/pickup choreography. Ablated: state 0 → 2 → 4 → 6 → 10 → 17 → 28 → 48 → 69, skipping dead-end ids.

## Key Takeaways
1. Use a `mod` and `rl [label] : A => B .` whenever values change constitution, not just form; states stay same-sort on both sides.
2. Represent state as constructor terms glued by an associative-commutative `_&_`-style operator with an identity — configurations become unordered soups you can pattern-match piecemeal.
3. Put counters and other evolving data inside state constructor arguments so laws compute while they transition.
4. Never trust unbounded `rew` on realistic modules — pass a bound or use `frew` when one law dominates.
5. `search` + on-the-fly variables + `show path N .` is the workspace for "how could state X ever become state Y?" questions (planning, verification-style reachability).
6. Conditions on `crl` can be equations, memberships, pattern matches, or **a rewrite itself** — the last reads as reachability.

## Connects To
- **Ch 2**: equations define the scaffolding (states, arithmetic, weights) that laws then animate; `crl` mirrors `ceq` syntax point for point.
- **Ch 4**: object-oriented modules mechanize exactly this pattern — objects + messages in a configuration soup rewritten by rules; message passing replaces fact-soup matching.
- **Ch 6**: internal strategies let you script rewrite order explicitly instead of relying on `rew`/`frew` defaults.
- **External**: rewriting logic (Meseguer); blocks-world planning; model checking via `search` is the doorway to Maude's linear temporal logic model checker (out of the primer's scope).
