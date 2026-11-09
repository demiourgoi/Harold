# Chapter 14: Variants and Variant Unification

## Core Idea
A term's **variants** are its simplification outcomes under all substitution instances: pairs `(canonical form, substitution)`. When a theory has the *finite variant property* (every term has finitely many most general variants), Maude turns variant generation — powered by folding-variant narrowing — into a complete, finitary `E ∪ Ax`-unification and matching engine. This is the layer that finally lets your *equations* (not just attributes) participate in symbolic solving.

## Frameworks Introduced
- **Variants**: for `E ∪ Ax` with `E` confluent/terminating/sort-decreasing/coherent modulo Ax, the variants of `t` are `(t↓, θ)` with `t↓` the canonical form of `θ(t)`; ordered by a generalization preorder (a variant is more general if the other is its instance modulo Ax). Complete set = covers every variant up to that preorder.
- **The `variant` attribute**: equations used for variant generation must be tagged — `eq [base] : 0 + Y = Y [variant] .` Use the same equation for both simplification and variants by declaring it twice (once plain, once `[variant]`). Constraints: unconditional only, no `owise`, lefthand side not a variable, no `[variant]`+`nonexec` (advisory + ignored). In system modules, other equations `G` and rules `R` are unrestricted — `(Σ, E ∪ Ax)` inside is all that matters.
- **Finite variant property (FVP)**: some terms have infinite variant sets (NAT-VARIANT's `X + s(0)`); a theory has the FVP iff each term has a finite most-general set — test it by `get irredundant variants` on a representative symbol (e.g. `__` for the vending machine's ACU-coherent `change`; `_+_` in ABELIAN-GROUP: 47 variants; `-_`: 4).
- **Commands**:
  ```maude
  get variants [n] in M : T .                 --- possibly infinite, incremental
  get irredundant variants [n] in M : T .     --- minimal; meaningful under FVP
  variant unify [n] in M : t1 =? t1' /\ ... .          --- E ∪ Ax unification
  filtered variant unify [n] in M : ... .              --- minimal complete set
  variant match [n] in M : t1 <=? t1' /\ ... .         --- one side ground
  ```
  Both may take `/\`-problems; irreducibility constraints via `such that T1, T2, ... irreducible` discard unifiers whose instantiations are reducible; fresh answer variables are `#n:Sort` (Ax-part) and `%n:Sort` (variant-part) — never use either in problems.
- **The theory-behind-the-theory**: `E ∪ Ax`-unification = variant generation of a lifted `eq(t, t')` term to `tt`; **folding variant narrowing** (Ch 15) makes it complete-and-terminating under FVP; naive strategies (e.g. basic narrowing modulo AC) are famously incomplete — the implementation only trusts the folded variant.
- **Incremental discipline**: `get variants` can be extended stepwise (`[n]` up, `cont`-like behavior) even for non-FVP theories; `variant unify` bounds count *unifiers*, not internal variants — without FVP a bounded request can hang after finding all solutions (Maude cannot know the unifier enumeration is exhausted). Incomplete A/AU situations within the variant pipeline reproduce Ch 13's warnings verbatim (infinite unifier families truncated with "Some unifiers may have been missed...").

## Key Concepts
- **Coherent-with-variables equation style**: to make an equational theory ACU-coherent for variants, add an extension variable to the lefthand side: `eq [change] : q q q q M = $ M [variant] .` — the `M` is what makes the folding variant narrowing complete across the associativity-commutativity structure.
- **Where variants beat Ax-unification**: the vending-machine `change` equivalence is invisible to `unify` (Ch 13 ignores `E`) but real to `variant unify`: the same problem `< q q X > =? < $ Y >` gains the `X ↦ q q #1, Y ↦ #1` unifier (make-change-free solutions) alongside the attribute-level one.
- **Membership axioms remain discarded**: sorts inhabited only by `mb` behave as empty for variant purposes (EXCLUSIVE-OR-MB) — though the *sort computation* of canonical forms does use memberships.
- **Unitary theories under filtering**: XOR-unification is unitary, but many raw unifiers are pairwise comparable; `filtered variant unify` returns one representative (chosen arbitrarily among ties).
- **`variant match`**: righthand sides treated as ground (variables become constants); no variant generation on the RHS — the efficient variant of Ch 4's `match` modulo a full equational theory.

## Mental Models
- Read a variant answer `(t↓, θ)` as "some *instance* of your term simplifies to `t↓`, and most-general ones look like this" — variants are the *space of evaluation outcomes*, unifiers are the slice where two terms' outcome spaces overlap.
- Equations are dual-use: declare `[variant]` copies of exactly the equations that define `E`; leave everything else to simplification — the tag is your declaration that these equations define the theory's symbolic content.
- Test FVP early: `get irredundant variants in M : X Y .` on the top symbol of each theory — a hang here predicts hangs in variant unify later.

## Anti-patterns
- **Mixing owise with `[variant]`**: rejected — factor the catch-all out of the variant-tagged part of the specification.
- **Trusting non-`filtered` unifier sets**: `variant unify` may return comparable unifiers; only `filtered variant unify` gives minimal sets (and even then, ties are arbitrary).
- **Bound-less variant unify under non-FVP theories**: the request counts unifiers, not the internal variant enumeration — Maude may grind forever *after* the true last unifier; bound it, or establish FVP first.
- **Forgetting the coherence variable**: `q q q q = $ [variant]` (no `M`) looks equivalent but breaks ACU coherence — variants will be incomplete in exactly the multiset corner cases you care about.
- **Expecting memberships in variant generation**: they are skipped out of principle; post-process sorts separately.

## Code Examples
```maude
mod VARIANT-VENDING-MACHINE is
  ... Marking [assoc comm id: empty] as in Ch 13 ...
  var M : Marking .
  rl [buy-c] : < M $ > => < M c > .
  rl [buy-a] : < M $ > => < M a q > .
  eq [change] : q q q q M = $ M [variant] .   --- ACU-coherent via extension var M
endm

Maude> variant unify in VARIANT-VENDING-MACHINE : < q q X:Marking > =? < $ Y:Marking > .
Unifier 1  X:Marking --> $ %1:Marking   Y:Marking --> q q %1:Marking
Unifier 2  X:Marking --> q q #1:Marking  Y:Marking --> #1:Marking
Maude> filtered variant unify ... .   --- singleton {Unifier 2}
```
- **What it demonstrates**: `E ∪ Ax`-unification — the change equation *participates* (Unifier 2 exists because 4 quarters ≡ 1 dollar modulo `[change]`), unlike Ch 13's `unify`; filtering removes the redundant instance.

```maude
--- irreducibility constraints prune solutions
variant unify in VARIANT-VENDING-MACHINE : < q q X:Marking > =? < $ Y:Marking >
  such that q q X:Marking, q X:Marking, X:Marking irreducible .
--- only Unifier 1 survives: instantiating X to q q ... would be reducible
```
- **What it demonstrates**: constraining unifiers to keep substituted terms in normal form — the standard trick for cryptographic-protocol-style analyses where secrets must stay irreducible.

## Reference Tables
| Requirement | Detail |
|---|---|
| signature | `(Σ, Ax)` per Ch 13 restrictions; preregular modulo Ax |
| `E` | `[variant]`-tagged, unconditional, confluent, terminating, sort-decreasing, coherent modulo Ax |
| forbidden | `owise`, variable LHS, `[variant]+[nonexec]` |
| `(G, R)` in system modules | unrestricted; ignored by variant machinery |
| FVP | needed for finite `variant unify`/`get irredundant variants`; testable per symbol |

| Command | Returns |
|---|---|
| `get variants [n] : T .` | variants, possibly infinite (incremental) |
| `get irredundant variants [n] : T .` | minimal most-general set (termination ⇒ FVP) |
| `variant unify [n] : eqs .` | `E ∪ Ax`-unifiers (complete under FVP; maybe redundant) |
| `filtered variant unify [n] : eqs .` | minimal complete set; ties arbitrary |
| `variant match [n] : eqs .` | `E ∪ Ax`-matches with ground RHS |
| any + `such that ... irreducible` | solutions with irreducible instantiations |

## Worked Example
Deciding whether a theory is fit for symbolic work — the FVP audit (ABELIAN-GROUP, Lankford's axioms):

```maude
fmod ABELIAN-GROUP is
  sort Element .
  op _+_ : Element Element -> Element [comm assoc prec 30] .
  op -_ : Element -> Element [prec 20] .
  op 0 : -> Element .
  vars X Y Z : Element .
  eq X + 0 = X [variant] .        eq X + - X = 0 [variant] .
  eq X + - X + Y = Y [variant] .  eq - - X = X [variant] .
  eq - 0 = 0 [variant] .          eq - X + - Y = -(X + Y) [variant] .
  eq -(X + Y) + Y = - X [variant] .
  eq -(- X + Y) = X + - Y [variant] .
  eq - X + - Y + Z = -(X + Y) + Z [variant] .
  eq -(X + Y) + Y + Z = - X + Z [variant] .
endfm

Maude> get irredundant variants in ABELIAN-GROUP : X + Y .   --- 47 variants
Maude> get irredundant variants in ABELIAN-GROUP : - X .    ---  4 variants
```

Both commands terminate with "No more variants." → the theory has the finite variant property → every `variant unify` problem in it is finitary and complete. Compare NAT-VARIANT (`eq [ind] : s(X) + Y = s(X + Y) [variant] .` alone): `get variants` of `X + s(0)` streams an infinite family — no FVP — so its unification must be bounded or avoided. The same audit pattern applies to any ACU-exotic theory you author: **count your variants before you trust your unifiers.**

## Key Takeaways
1. `variant unify`/`variant match` = unification modulo your *equations* — the payoff of annotating `E` with `[variant]` and accepting its strict executability requirements.
2. FVP is the health certificate: finite most-general variants ↔ finitary complete unification; audit it with `get irredundant variants` per top symbol.
3. Filtering (`filtered`, `get irredundant`) is the difference between a set of answers and *the* answers; without it, expect redundant unifiers even in unitary theories.
4. Extension-variable-coherent equations (`q q q q M = $ M`) are mandatory style for ACU variant work — and the sound vessel for pattern-matching on multisets modulo simplification.
5. Irreducibility constraints (`such that ... irreducible`) give symbolic protocol reasoning its "no accidental simplification" edge — matched only by narrowing with constraints (Ch 15).
6. Fresh-variable namespaces `#n`/`%n` are reserved; incremental enumeration is safe for variants, risky for unification without FVP.

## Connects To
- **Ch 13**: the `Ax` layer underneath; its incompleteness warnings reappear inside variant pipelines for A/AU subproblems.
- **Ch 15**: folding variant narrowing implements everything here; `vu-narrow` extends reachability, not just unification, through variants.
- **Ch 5 / 4**: rules and non-variant equations coexist peacefully with variant machinery in one system module.
- **Ch 17**: `metaGetVariant` etc.; `%`-variables and the '@' namespace at the metalevel.
- **Cryptographic-protocol practice** (e.g., XOR/Abelian-group modeling): this chapter is its executable core — unreachable states modulo equational theories, discovered symbolically.
