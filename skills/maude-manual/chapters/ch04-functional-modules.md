# Chapter 4: Functional Modules

## Core Idea
A functional module defines an equational theory `(Σ, E ∪ A)` in membership equational logic whose intended model is the initial algebra `T_Σ/E∪A`. Executability — equations as terminating, Church-Rosser (modulo `A`) simplification rules — makes the interpreter compute exactly in the canonical term algebra, so specification and program coincide.

## Frameworks Introduced
- **Three ways to state equations**: (1) executable equations (`eq`/`ceq`) used as simplification rules left-to-right; (2) `nonexec` statements — part of the theory, ignored by the engine, usable at the metalevel (e.g. proved lemmas); (3) equational attributes (`A`) built into operators. Never write attribute equations explicitly: `eq f(X, Y) = f(Y, X) .` for commutativity loops forever; `[comm]` computes with equivalence classes instead.
- **Memberships** (`mb` / `cmb`): state that a term has a sort, possibly under conditions — the tool for partial functions and refined sorts (multiples of 3, well-formed paths).
- **Conditional statements**: `ceq l = r if C1 /\ ... /\ Ck .` with three condition kinds: ordinary equations `t = t'`, **matching equations** `u := u'` (a `let` that also searches structure modulo axioms), and **abbreviated Boolean equations** `t` (inferred `t = true`, using `_==_`, `_=/=_`, `_:: S`, Boolean combos).
- **Equational attributes catalogue** (binary operators only, domain/range kinds must match; see table below): `assoc`, `comm`, `idem`, `id:`, `left id:`, `right id:`. Restrictions: `idem`+`assoc` unsupported (idempotency must then be an ordinary equation); only one identity attribute; `comm`+one-sided identity degenerates to `id:`.
- **`ctor` + sufficient completeness**: constructors are the symbols in canonical forms; the SCC tool (and its `scc M .` command flow) checks every defined function is fully defined on constructors.
- **`strat (i1 ... ik 0)`** — operator evaluation strategies: list argument positions to simplify before trying the top (`0`); default `(1 2 ... n 0)` is eager; `(0)` is lazy. Enables lazy programming (SIEVE), short-circuiting (`_and-then_`, `_or-else_` with `(1 0)`); canonical forms become strategy-relative.
- **`memo`** — per-operator result cache: `fibo(50)` drops from 61 billion rewrites to 148; `do clear memo .` / `set clear memo on|off .` manage it.
- **`owise`** ("otherwise") equations: desugar to `ceq f(y1,...,yn) = r if enabled_f(y1,...,yn) =/= true /\ f-matching .` — a semantically conservative catch-all, applied only after all other equations for `f` fail.
- **Matching modulo `A` and extension**: rewriting modulo `assoc`/`comm`/`id:` means a lefthand side may match the subject *or any of its f-subterm fragments* ("with extension"); `xmatch` enumerates exactly those matches. Extension applies at the top theory layer only.

## Key Concepts
- **Initial algebra `T_Σ/E∪A`**: no junk, no confusion — the quotient of ground terms by provable equality; isomorphic to `Can_Σ/E∪A` iff `E` is Church-Rosser + terminating modulo `A`.
- **`M`-pattern**: term whoseσ-instances stay canonical for canonical σ; sufficient condition: no unifier between non-variable subterms and equation lefthand sides. Required in matching equations.
- **Admissibility requirements**: variables in an equation's righthand side must occur in lefthand side or be bound by its condition's matching equations; executable memberships must satisfy the same constraints; guarantees extra variables get instantiated.
- **`iter`** attribute: `f^1234567890123456789(X:Foo)` compact staff notation for huge unary stacks.
- **`special` (id-hook/op-hook/term-hook)**: binds operators to C++ built-ins in `prelude.maude` — never write these; not backward compatible between versions.
- **Frozen arguments** (`frozen` / `frozen (i1 ... im)`): blocks rule application inside subterms (functional-module effect only on import into system modules).
- **Term sharing**: occurrences of the same subterm are internally shared during simplification (traces report one application); rules force incremental unsharing since rules needn't be confluent.
- **Commands**: `reduce`/`red`, `match [n] pat <=? subj`, `xmatch [n] pat <=? subj` (extension!), `set trace on .`, `trace select <label> .`, `show module M .`, `show sorts M .`, `show components M .`.

## Mental Models
- Think of equations as *oriented definitions with a contract* (terminating + confluent modulo `A`); everything executable must keep the contract or the initial-algebra reading breaks.
- Use matching equations as `let`-bindings to name substructure once, and as modulo-axioms search when substitutions aren't unique (a rule with the same condition searches; an equation must match uniquely to define a function).
- Attributes are semantic declarations executed by specialized algorithms: declare the axiom (`assoc comm id: ...`), never the equation.
- Choose strategies per operator: eager by default; `(0)` for data constructors of infinite structures; `(1 0)` for short-circuit operators.

## Anti-patterns
- **`hasTwo` non-function**: `ceq hasTwo(NS) = ... if NS0 N NS1 := NS .` — several matches yield different results, so the equation is not a function; destroys Church-Rosser; inconsistent theory (in a *rule* the same condition is legitimate search).
- **Explicit attribute equations** (`f(X,Y) = f(Y,X)`): infinite simplification chains; declare `[comm]`.
- **`assoc` + `idem` attributes**: combination unsupported — `idem` is silently ignored; write `eq N ; N = N .` instead.
- **Owise + strategies subtlety**: the owise equation is tried *only after the final `0` in the strategy* — `f(b)` with `f : strat (0 1 0)` reduces to `g(c)`, not `g(b)`, because `b → c` happens first (OWISE-TEST2).
- **Non-`M`-patterns in matching equations**: matching cannot decide equality on reducible patterns → admissibility violation.
- **`__` with identity and membership axioms**: assoc + memberships interact badly (Sec. 21.3.8); same for `iter` (21.3.9).

## Code Examples
```maude
fmod SIEVE is            --- lazy primes: strat (0) constructor + force
  protecting NAT .
  sort NatList . subsort Nat < NatList .
  op nil : -> NatList .
  op _._ : NatList NatList -> NatList [assoc id: nil strat (0)] .
  op force : NatList NatList -> NatList [strat (1 2 0)] .
  op show_upto_ : NatList Nat -> NatList .
  op filter_with_ : NatList Nat -> NatList .
  op nats-from_ : Nat -> NatList .
  op sieve_ : NatList -> NatList .
  op primes : -> NatList .
  vars P I E : Nat . vars S L : NatList .
  eq force(L, S) = L . S .
  eq show nil upto I = nil .
  eq show E . S upto I = if I == 0 then nil else force(E, show S upto sd(I, 1)) fi .
  eq filter nil with P = nil .
  eq filter I . S with P = if (I rem P) == 0 then filter S with P else I . filter S with P fi .
  eq nats-from I = I . nats-from (s I) .
  eq sieve nil = nil .
  eq sieve (I . S) = I . sieve (filter S with I) .
  eq primes = sieve nats-from 2 .
endfm
--- red show primes upto 10 . => 2 . 3 . 5 . 7 . 11 . 13 . 17 . 19 . 23 . 29
```
- **What it demonstrates**: infinite lazy data via `strat (0)` constructors, an eager `force` to peel, demand-driven output.

```maude
fmod EXT-OF-BOOL is protecting BOOL .
  op _and-then_ : Bool Bool -> Bool [strat (1 0) gather (e E) prec 55] .
  var B : [Bool] .
  eq true and-then B = B .
  eq false and-then B = false .
endfm
--- red false and-then B:[Bool] .  =>  false  (B never evaluated)
```
- **What it demonstrates**: short-circuit Booleans through evaluation strategies; `red false and B:[Bool] .` would *not* terminate.

## Reference Tables
| Operator attribute | Meaning / key rule |
|---|---|
| `assoc`, `comm` | associative/commutative axiom; matching modulo, extension |
| `id: t`, `left id: t`, `right id: t` | identity element(s); `comm` promotes one-sided to two-sided |
| `idem` | idempotency — never with `assoc` |
| `ctor` | constructor (local to this typing; not inherited by ditto) |
| `iter` | `f^n(x)` exponent notation for unary stacks |
| `poly (i...)` | polymorphic arg positions, `(0)` = range; placeholder `Universal` |
| `format (...)` | print control: `d` default, `s` space, `t` tab, `i`/`n`/`+`/`-` indent-newline, colors `r g y b m c u ! o`; `set print format on|off .` |
| `ditto` | inherit attributes of a previous subsort-overloaded instance (except `ctor`/`metadata`) |
| `strat (i1 ... ik 0)` | evaluation strategy; default eager `(1 ... n 0)` |
| `memo` | memoize results per operator/constant |
| `frozen[(i...)]` | forbid rule application in (some) subterms |
| `special (...)` | C++ built-in hooks — prelude only |

| Statement attribute | Applies to |
|---|---|
| `label <id>` (sugar: `eq [id] : ...`) | equations/memberships/rules — tracing, metalevel naming |
| `metadata "..."` | statements and operator declarations; carried comment |
| `nonexec` | ignored by engine; semantics + metalevel only |
| `owise` | catch-all equations after all other equations of the same top operator fail |
| `print "..." X` | items = strings or occurring variables; needs `set print attribute on .` |

## Worked Example
Bootstrapping NUMBERS to sufficient completeness (SCC iterations):
1. `(scc NUMBERS .)` → *Failure: term `0` is a counterexample* → the constants `0 1 2 : -> Nat3` are data, not defined functions: mark them `ops 0 1 2 : -> Nat3 [ctor] .`
2. Next run → *Failure: `zero * zero`* → `_*_` was declared (without `ctor`) but never defined: add
   ```maude
   eq N * zero = zero .
   eq N * s M = (N * M) + N .
   ```
3. Next run → *Failure: `p(s N)`* → predecessor undefined on its domain: add `eq p(s N) = N [label partial-predecessor] .`
4. Final run → *Success: NUMBERS is sufficiently complete under the assumption that it is weakly-normalizing, confluent, and sort-decreasing.*

The workflow teaches the division of labor: **you** guarantee termination/confluence (possibly with Maude's CRC/MTT tools); the **SCC** systematically finds forgotten function cases. The finished NUMBERS (with `[assoc comm]` addition, `[assoc comm id: empty]` set union, `owise` membership, `nonexec` distributive lemma) is the template every functional module should resemble.

## Key Takeaways
1. Executable equations carry the Church-Rosser + termination contract; `nonexec` and attribute-declared axioms are the two lawful escape hatches.
2. Declare axioms as attributes (`assoc comm id: ...`) and let Maude synthesize matching; write only the definitional equations.
3. `owise` is semantically the `enabled_f` conditional equation — safe when the function's other equations are complete on patterns; its interplay with `strat` defers it to after the strategy's last `0`.
4. `strat` makes each operator individually eager or lazy — the SIEVE shows full lazy-functional programming inside an equational language.
5. `memo` turns exponential re-evaluation into table lookups — mandatory for divide-and-conquer definitions like Fibonacci.
6. Matching-with-extension is the engine of rewriting modulo `A`; `xmatch` exposes it; top-layer only; `iter` behaves like assoc.
7. `match`/`xmatch`, `show module/sorts/components`, selective `trace` are your window into a module's grammar, kinds, and statement usage.

## Connects To
- **Ch 3**: declarations this chapter presumes (`op`, sorts, kinds, preregularity).
- **Ch 5**: rules + coherence complete the executability story; `frozen` becomes effective; system-module versions of statements.
- **Ch 6**: class/membership syntax extends memberships and attributes (`dnt`).
- **Ch 7**: `protecting`, theories, views; `ditto` and subsort-overloaded instances across imports.
- **Ch 8**: `prelude.maude` modules (BOOL, NAT, ...), `special` hooks, `_::_` predicates. `EXT-BOOL`/`and-then`, `or-else`.
- **Ch 17**: `metaMatch`/`metaXmatch` at the metalevel; labeled statements addressable.
- **Ch 21**: traps: nonleft-linear SCC warnings; assoc/iter membership clashes (21.3.8–9); print ambiguity (21.3.10); debugging via these same tools.
