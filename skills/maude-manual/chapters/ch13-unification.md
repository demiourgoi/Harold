# Chapter 13: Unification

## Core Idea
Unification solves equations `t =? t'` for variable substitutions. Maude implements *order-sorted unification modulo built-in axioms* (`Ax`-unification) with a hybrid decomposition: fast algorithms for the attribute axioms you declare (`assoc`, `comm`, identities, `iter`), ignoring any additional equations `E` — which Chapter 14 then handles by variant-based unification on top.

## Frameworks Introduced
- **The problem**: `t1 =? t1' /\ ... /\ tk =? tk'` (conjunction AC); an `E`-unifier is a sort-preserving substitution making each equation provable modulo `E`. **Complete set** (every unifier is an instance of one in the set), **minimal/irredundant** finite sets, and the finitary/unitary/infinitary classification. Order-sorted syntactic unification is *finitary but not unitary* (several incomparable mgu's); AC/C-unification finitary; plain A/AU-unification infinitary in general (handled with warnings — see below).
- **Hybrid approach**: with `(Σ, E ∪ Ax)`, `Ax` = declared attributes (A, C, AC, ACU, AU, CU, U, Ul, Ur, `iter`), `E` = the rest: the `unify` command computes **Ax-unifiers and ignores `E`** (and memberships; and module-type wrapper — theories/system modules accepted transparently).
- **Supported axioms table**: free symbols + `iter` unary; binary symbols with any of `assoc`, `comm`, `assoc comm`, `assoc comm id:`, `assoc id:`, `comm id:`, `id:`, `left id:`, `right id:`; signature must be preregular modulo Ax. **Excluded at the Ax level**: `idem`, and associativity with a one-sided identity — but these have the finite-variant property, so they unify through Ch 14's variant mechanism.
- **The command**:
  ```maude
  unify [n] in M : t1 =? t1' /\ ... /\ tk =? tk' .
  irredundant unify ... .   --- filters to a minimal set of most general unifiers
  ```
  `[n]` bounds the count; output enumerates "Unifier 1 ... X:Sort --> term ...", "No unifier." on failure. Fresh variables in answers are `#n:Sort` — never use `#`-variables yourself (warning: "unsafe variable name").
- **Tolerance rules**: unsupported axioms (`idem` etc.) in a *non-ground* subterm → failure + warning; appearing only in *ground* subterms → correctly unified. Membership axioms are ignored: a sort defined only by `mb` (e.g. `Quarter`) is treated as *empty* when unification instantiates it ("No unifier" despite an obvious instance).
- **A/AU unification strategy** (where infinitary lurks): linear problems (each A-variable occurs once) → complete finitary result. Non-linear: (1) non-linearity on one side only → still complete; (2) both sides, no variable more than twice → cycle detection — spurious cycles discarded silently, real cycle detected → warning + only acyclic unifiers returned (`0 : Q =? Q : 0` has infinitely many mgu's; you get one + warnings); (3) otherwise → internal depth bound (default 7, command-line configurable) with warning and truncated solution set; `set verbose on` exposes which strategy ran.

## Key Concepts
- **Unifier composition/minimality**: complete ≠ minimal; `unify` may return redundant instances; `irredundant unify` post-filters. E.g. AC problem `X + X + Y =? A + B + C` in NAT has **381** unifiers (all minimal via `irredundant`).
- **`iter` + comm unification**: `s^1000000(X:OddNat) =? s^100000000001(Y:Int)` unifies instantly via exponent arithmetic on towers.
- **Unification modulo attributes of predefined modules**: `NAT`, `CONVERSION`, etc. participate naturally (`unify in NAT : ...`).
- **Warnings to read carefully**: "unification for its top symbol is not currently supported" (unsupported axiom in non-ground position); "may not be complete" (A/AU depth/cycle case); "unsafe variable name" (user `#`-variables).
- **What unify is for**: symbolic reachability pre-analysis, generalized pattern matching, protocol verification setups — logic-programming-style reasoning over the equational structure of your module.

## Mental Models
- Read `unify` as "unification restricted to what the attributes say": the equations you wrote with `eq` do not participate; if you need them, either encode them as attributes or go to variant unification (Ch 14).
- Read each answer as an infinite family described modulo Ax — that's why answers may look redundant and why `irredundant` exists.
- Expect combinatorial explosions in AC problems: always ask with a bound `[n]` first; count the full set only if needed.

## Anti-patterns
- **Trusting `unify` output as minimal**: only `irredundant unify` promises a minimal complete set.
- **Using `#1:Sort` variables in problems**: reserved for returned unifiers, rejected with a warning.
- **Expecting memberships to matter**: they are ignored — a sort inhabited only by an `mb` axiom is empty to the unifier (UNIF-VENDING-MACHINE-MB's `Y:Quarter` failure).
- **Expecting `E`-unification from `unify`**: extra equations are ignored — a module with `eq [change] : q q q q = $` still unifies `< q q X > =? < $ Y >` *modulo attributes only*; the change equation plays no role (variant unification handles it, Ch 14).
- **Unbounded non-linear A-unification**: silently truncated by a depth bound after a warning — check the warnings, don't reason from partial solution sets.

## Code Examples
```maude
--- ACU at work in the vending machine (Marking [assoc comm id: empty])
mod UNIF-VENDING-MACHINE is
  sorts Coin Item Marking Money State .
  subsort Coin < Money . subsort Money Item < Marking .
  op empty : -> Money .
  op __ : Money Money -> Money [assoc comm id: empty] .
  op __ : Marking Marking -> Marking [assoc comm id: empty] .
  op <_> : Marking -> State .
  ops $ q : -> Coin .  ops a c : -> Item .
  ...
  eq [change] : q q q q = $ .   --- ignored by unify; used by ch14 variant unify
endm

Maude> unify in UNIF-VENDING-MACHINE : < q q X:Marking > =? < $ Y:Marking > .
Unifier 1  X:Marking --> $        Y:Marking --> q q
Unifier 2  X:Marking --> $ #1:Marking   Y:Marking --> q q #1:Marking
Maude> irredundant unify ... .   --- singleton {Unifier 2}
```
- **What it demonstrates**: ACU unification of configurations ("could a 2-quarter purse hold what a 1-dollar purse holds?"), the redundancy of plain answers, and the minimal-set command.

```maude
Maude> unify in NAT : X:Nat + X:Nat + Y:Nat =? A:Nat + B:Nat + C:Nat .  --- [100]
--- 381 unifiers total; AC unification is where bounds matter
```
- **What it demonstrates**: AC combinatorics — 9-variable bilinear problems explode; always bound first.

## Reference Tables
| Attribute combo | Name | Unification behavior |
|---|---|---|
| (none), `iter` (unary) | free / iter | complete, finitary (instant on towers) |
| `comm` | C | finitary, complete |
| `comm id:` | CU | finitary, complete |
| `id:`, `left id:`, `right id:` | U, Ul, Ur | finitary, complete |
| `assoc comm` | AC | finitary, complete (big sets) |
| `assoc comm id:` | ACU | finitary, complete |
| `assoc` / `assoc id:` | A / AU | infinitary in general: linear = complete; else cycle detection / depth bound with warnings |
| `idem`, `assoc + left/right id:` | — | **not Ax-supported** → varben unification via Ch 14 |

| Command | Purpose |
|---|---|
| `unify [n] in M : eqs .` | all (bounded) Ax-unifiers |
| `irredundant unify [n] in M : eqs .` | minimal complete set |
| Ch 14: `variant unify`, `get variants` | unification modulo `E ∪ Ax` via variants |

## Worked Example
Symbolic analysis of the associative list module under non-linearity (UNIFICATION-EX4, `_:_ [assoc]`):

```
Maude> unify : X:NList : Y:NList : Z:NList =? P:NList : Q:NList .
--- linear in all A-variables: 5 unifiers, complete, no warnings

Maude> unify : 0 : Q:NList =? Q:NList : 0 .
Warning: ... may not be complete.
Unifier 1  Q:NList --> 0
Warning: Some unifiers may have been missed ...
```

What happened: the first problem is *linear* — every Ax-variable occurs once — so Maude's finitary A-algorithm returns a complete set (the 5 ways to split one concatenation into two). The second reuses `Q` on both sides — non-linear, cycle detection finds the true infinite family `{Q ↦ 0^n}` — and Maude honestly warns and returns only the acyclic solution. This pairing teaches the discipline of reading unification answers: **completeness depends on the problem's shape (linearity), and every warning is information, not noise**. AU (`assoc id: nil`) behaves the same with the identity folded in; and the omitted cases (`idem`, one-sided identity) are delegated to variant unification, closing the loop with Chapter 14.

## Key Takeaways
1. `unify` = order-sorted unification modulo *declared attributes only*; equations and memberships do not participate.
2. Answers use fresh `#n:Sort` variables — complete sets, possibly redundant; `irredundant unify` pays the filtering cost for minimality.
3. Supported Ax families cover A, C, AC, ACU, AU, CU, U, Ul, Ur + `iter`; `idem`/`assoc`+one-sided-identity unification exists via the variant route instead.
4. A/AU problems: linear → complete; non-linear → cycle detection or depth bound, both with explicit warnings — never assume totality of answers there.
5. Bound your AC queries; their solution sets grow brutally with variables.
6. Unsupported axioms localize gracefully: ground occurrences unify fine, non-ground ones fail loudly.

## Connects To
- **Ch 4**: equational attributes, preregularity (a precondition for the unifier to work), extension-aware matching (dual notion, one-directional).
- **Ch 14**: variant-based unification lifts this machinery through `E` (finite-variant property), and irreducibility constraints.
- **Ch 15**: narrowing = rule application modulo Ax-unification (built on this chapter's algorithms).
- **Ch 17**: `metaUnify`, fresh-variable discipline at the metalevel ('#, %, @ tokens).
- **Ch 21**: interpreting unification warnings when using search/narrowing implementations.
