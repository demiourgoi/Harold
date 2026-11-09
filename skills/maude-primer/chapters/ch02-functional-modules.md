# Chapter 2: Functional Modules

## Core Idea
Equations are the simplification rules that give a functional module its computational power: every expression should reduce to canonical form — a term built from constructors alone. Writing equations that actually terminate is the central skill, and Maude backs it with flags (`prec`, `gather`, `memo`, `owise`, `assoc`/`comm`/`id`) that say things equations cannot say without looping.

## Frameworks Introduced

- **Equation** — `eq lhs = rhs .` A simplification rule; Maude applies it left-to-right only. Worth-it requirement: **the right-hand side must be simpler** than the left-hand side.
- **Canonical form** — the constructor-only term every expression should reduce to. "Expressions with only constructors cannot be simplified," and shouldn't be.
- **Recursive definition pattern** — nearly every equation set is recursive:
  - base case ends recursion (`eq 0 + N = N .`)
  - recursive case calls the operator again on smaller data (`eq s(M) + N = s(M + N) .`)
- **First-element-rest decomposition** — for lists, queues, decks: match `E L` (first element + the rest) and recurse on `L` in one progressive direction. Represent composite values as constructor patterns, never as a single variable.
- **Conditional equation** — `ceq lhs = rhs if cond .`, multiple conditions chained with `/\ ` (condition-concatenation). Executes the reduction only when the condition reduces to `true`.
- **Matching condition** — `Pattern := Target` matches a pattern against a term (and `T := "..."` reads as a value assignment). Powerful way to select among shapes inside conditions.
- **Membership axiom** — `mb t : S .` / `cmb t : S if cond .`. Operation and subsort declarations are just "syntactic sugar" for these. Used to: refine result sorts (`N / M : NzNat`) so dependent operations parse, carve out sub-sorts by property (wild cards, poker pairs).
- **Junk and confusion** — two ways to change an imported module's meaning:
  - junk = adding new ground terms (constants) to imported sorts
  - confusion = adding equations that redefine existing terms' reduction behavior
  - `protecting` forbids both; `extending` allows junk, forbids confusion; `including` allows both.
- **Kind-level computation** — declare equation variables at the kind level (`var N : [Dog] .`) so the same equations also reduce error terms: "we can breed out the penguins." Error recovery becomes a modeling tool.
- **Operator overloading** — same operator name, different rank:
  - subsort overloading: refined result on subsorts (`_+_` on `Nat Nat -> Nat` under `Nat Nat -> Integer`); both declarations must share equational attributes, except `ctor`
  - ad-hoc overloading: unrelated ranks (`_+_ : Note Note -> Chord`); disambiguate overloaded constants with qualified terms `(A).Letter`, `(A).Note`.

## Key Concepts
- **eq / ceq / mb / cmb** — equation, conditional equation, membership axiom, conditional membership axiom keywords.
- **On-the-fly variables** — declared inside the statement: `eq author(n N:Name t T:Title ...) = N:Name .`; no whitespace in `N:Name`; scope is that statement alone.
- **Bool** — provided sort (`true`, `false`, `==`, `=/=`, `and`, `or`, `if_then_else_fi`); comparison operators (`<`, `>`, `<=`, `>=`) are NOT provided — define them per sort.
- **`if_then_else_fi`** — an *operator*, not a statement keyword: `eq max(M, N) = if N > M then N else M fi .`
- **memo** — operator attribute caching the reduced form of expressions whose top operator it decorates; pays off when identical ground subterms recur (highly recursive number theory).
- **prec** — precedence attribute; default 41; lower number = binds tighter (`_*_ [prec 25]` beats `_+_ [prec 35]`); parentheses always override.
- **gather** — parsing pattern `gather (e E &)` per argument: `e` requires strictly greater... "the top operator involved in the argument expression must have a precedence value strictly less than that of the operator" for `e`; `E` allows less-or-equal; `&` accepts anything. Default `gather (& &)`. `gather (e E)` on `_vs_` makes `sampras vs agassi vs roddick` play right-to-left.
- **owise** — statement attribute; fires only when no other equation for that left-hand side matched — the catch-all.

## Mental Models
- Think of every ground term as data built by constructors, and every defined operation as a function computed by simplification toward canonical form.
- Use flags, not equations, for symmetric laws: commutativity/associativity written as equations do not simplify — they **do not terminate**. "Maude designates special flags for the compiler to deal with this problem."
- Prefer `id: nil` to an identity equation when recursion might split at the identity element (a `length` defined by `length(L1 L2) = length(L1) + length(L2)` loops on `nil`).
- Prefer `idem`-as-equation (`eq E E = E .`) only when you also need `assoc`, since `assoc` + `idem` flags cannot combine.
- Use `owise` when one side of a condition is much easier to state than the other.
- Kinds are a working surface, not just a junk drawer: kind-level variables salvage error terms into useful results.

## Anti-patterns
- **Non-simplifying equations**: e.g. `N + M + O = N + O + M .` — both sides equally simple (it is *commutativity in disguise), so reduction ping-pongs forever.
- **Splitting a list in the middle**: recursion must peel one element and proceed on the rest; arbitrary `L1 L2` splits hit `nil` and loop.
- **Representing composite values as one blanket variable**: patterns like `N of S`, `E L`, `s(M) + N` do the structural work — "it really only works with constructors."
- **Redefining via `protecting`**: adding junk or confusion under a `protecting` import violates the imported module — Maude is asked to forbid it; declare `extending`/`including` instead.
- **Ad-hoc overloading constants**: ambiguous; use qualified terms and expect friction.

## Code Examples

Peano addition by recursion (`iter` on `s` for readability):

```maude
fmod PEANO-NAT-EXTRA is
    sort Nat .
    op 0 : -> Nat [ctor] .
    op s : Nat -> Nat [ctor iter] .
    op _+_ : Nat Nat -> Nat .
    vars M N : Nat .
    eq 0 + N = N .
    eq s(M) + N = s(M + N) .
endfm
```

List size — first element + the rest, one `s(...)` per step:

```maude
fmod LIST-SIZE is
    protecting LIST .
    protecting PEANO-NAT .
    op size : List -> Nat .
    var E : Elt .  var L : List .
    eq size(nil) = 0 .
    eq size(E L) = s(size(L)) .
endfm
```

Comparisons must be defined per sort; `_>_` not provided:

```maude
eq 0 <= N = true .
eq s(M) <= 0 = false .
eq s(M) <= s(N) = M <= N .
eq M > N = not(M <= N) .
```

Pattern-match condition plus `owise` catch-all (the irritable professor):

```maude
ceq reply(I) = "Questions after class, please" if (S:String) ? := I .
eq reply(I) = "Shut up!" [owise] .
```

## Reference Tables

Statement keyword map:

| Keyword | Statement |
|---|---|
| `eq lhs = rhs .` | simplification rule |
| `ceq lhs = rhs if c1 /\ c2 .` | conditional simplification |
| `mb t : S .` | membership axiom |
| `cmb t : S if cond .` | conditional membership axiom |

Importation semantics (the junk/confusion grid):

| Mode | New ground terms (junk) | Redefining reduction (confusion) |
|---|---|---|
| `protecting` | forbidden | forbidden |
| `extending` | allowed | forbidden |
| `including` | allowed | allowed |

Syntax constraints at a glance: statements end with `.`; variables in `vars x1 x2 : S .` share one sort; on-the-fly variables have no internal whitespace; gather symbols `e` (strictly smaller prec), `E` (smaller-or-equal), `&` (any); default prec 41, default gather `(& &)`.

## Worked Example
The division-parse problem, from bug to fix. With `op _/_ : Nat NzNat -> Nat .` and subsorts `Zero NzNat < Nat`, the term `3 / (3 / 1)` does not reduce: the inner `3 / 1` yields a `Nat`, but the outer division demands `NzNat` as second argument — the whole thing stalls as an error term `result [Nat]: ...`. Fix with a membership axiom that refines the result sort:

```maude
var N : Nat .  var M : NzNat .
cmb N / M : NzNat if N =/= 0 .
```

(or equivalently: `vars N M : NzNat . mb N / M : NzNat .`). Now `3 / 1` is re-parsed as `NzNat`, the outer division parses, and the expression reduces normally. Lesson: when an operation's *output sort* is too coarse to feed another application of a subsort-restricted operation, repair the sort classification with `mb`/`cmb` — not by changing the operations.

## Key Takeaways
1. Every equation must make the term strictly simpler; if you cannot say which side is simpler, it belongs in a flag (`comm`, `assoc`, `id:`, `idem`) or it doesn't belong.
2. Canonical form = constructor terms; make only value-generators constructors (Ch1 discipline) so reduction has a destination.
3. Structure recursive equations as base case + definitional case over constructor patterns (`E L`, `N of S`, `s(M)`); peel one layer per step.
4. `ceq ... if ... /\ ...` plus `:=` matching plus `owise` lets you dispatch on shape declaratively — with `if_then_else_fi` when you want branching inside the value itself.
5. Membership axioms (`mb`/`cmb`) are the sanctioned way to carve finer sorts out of computed values; they justify the "syntactic sugar" view of op/subsort declarations.
6. Choose the importation keyword by what you plan to do: `protecting` / `extending` / `including` = neither / junk / junk+confusion.
7. Kind-level variables (`var N : [Dog] .`) make equations apply to error terms too — cheapest error handling in Maude.
8. `memo` for repeated heavy subterms; `prec`/`gather` for parsing ambiguous strings; `owise` for hard-to-state complements.

## Connects To
- **Ch 1**: gives sorts, operations, constructors, kinds — all consumed here; `extending` finally gets its junk-vs-confusion definition.
- **Ch 3**: rewrite laws are equations' dynamic sibling — `crl`/`rl` mirror `ceq`/`eq`, with the crucial difference that rewriting may be nondeterministic and is not "simplification."
- **Ch 4**: configurations rewrite with the equations from here intact; `interface` of attributes on object messages.
- **Ch 5**: parameterized theories demand `protecting`-clean modules — junk and confusion are exactly what theories forbid.
- **External**: order-sorted equational logic; Maude 2.0 Manual Ch 4.4 for the full attribute list.
