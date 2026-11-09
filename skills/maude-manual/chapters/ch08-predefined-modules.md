# Chapter 8: Predefined Data Modules

## Core Idea
`prelude.maude` gives every Maude user a ready data library: Boolean constants and polymorphic equality, the unbounded NAT/INT/RAT/FLOAT number tower (built on `iter` + GMP + C++ `special` hooks), strings and quoted identifiers, conversion functions, the parameterized container family (LIST/SET/MAP/ARRAY + theories TRIV/DEFAULT/order theories + standard views). Using it saves you from re-specifying data; knowing its conventions keeps your modules composable.

## Frameworks Introduced
- **Boolean stack**: `TRUTH-VALUE` (true/false as `special` built-ins) → `TRUTH` (polymorphic `if_then_else_fi [poly (2 3 0)]`, `_==_`, `_=/=_ [poly (1 2)]`, all in every module's extended signature) → `BOOL-OPS` (equational `_and_`, `_or_`, `_xor_`, `not_`, `_implies_`) → `BOOL` (= TRUTH + BOOL-OPS, included in every module by default) + `EXT-BOOL` (`_and-then_`, `_or-else_` with `strat (1 0)` short-circuit). Tune the automatic import with `set include BOOL off . set protect BOOL on .` etc.
- **Built-in equality semantics**: `u == v` reduces both sides to canonical form modulo the module's axioms and compares; `_:: S` computes the least sort and compares to `S`. No negation sneaks into membership equational logic — by Bergstra–Tucker these predicates are equationally definable anyway; they're built in for speed.
- **Number tower**: `Zero < NzNat < Nat` (NAT: `0`/`s_` constructors, decimal notation is `s_^42(0)` sugar, `set print number off` shows it) ⊂ `NzNat < NzInt, Int` (INT adds `-_`, `_-_`, `abs`, two's-complement bit ops `~_ _xor_ _&_ _|_ _>>_ _<<_` with negative-integer semantics, sign-of-quotient `_quo_`) ⊂ `NzInt < NzRat, PosRat < Rat` (RAT: `I / N` auto-reduced, `trunc`/`frac`/`floor`/`ceiling`) and parallel `FINITE-FLOAT < Float` (constants-as-data: Infinity/-Infinity; `+ - * / rem ceiling floor min max exp log sin cos tan asin acos atan pi atan2`; comparisons). Cross-type conversion lives in `CONVERSION` (`float : Rat -> Float`, `rat : FiniteFloat -> Rat`, ...).
- **Built-in partiality discipline**: `special` operators act only on well-formed number arguments; AC built-ins (gcd/lcm/min/max) reduce what they can and leave the rest symbolic (`gcd(gcd(12, X:Nat), 15)` → `gcd(X:Nat, 3)`) — user equations are tried when built-in semantics doesn't fire.
- **NAT/INT operational facts**: no subtraction on Nat (use symmetric difference `sd`); **membership axioms don't work reliably over the number sorts** (iter towers!) — refine number sorts by overloaded `s_` declarations, as in `INT-GT-3`, not by `mb`.
- **Machine integers** `MACHINE-INT{X :: BIT-WIDTH}`: a renaming of INT plus `$wrap` (sign-extension to the fixed width); views `32-BIT`/`64-BIT`; `_->_`, `_%_` (wrap), `_->_ ...` semantics; beware: `_^_` becomes **xor**, and out-of-range constants are unchecked (`NAT/{N}` in Ch 12 is the other "dependent type" example).
- **Randomness and state**: `random : Nat -> Nat` (Mersenne Twister state-cached; seed via `-random-seed=n`); the system module `COUNTER`'s built-in constant `counter` rewrites to successive naturals under rule rewriting — combine for sampling (`SAMPLES`/Bernoulli/CLOCK Monte-Carlo example with `set clear rules off .`). Counters are inactive under `search`/model checking/equational rewriting; renamed copies give independent counters.
- **Strings and qids**: `STRING`: constants; `length`, `substr(S, start, len)` (indices from 0), `find`/`rfind` (result sort `FindResult`), `ascii`/`char` (`char : Nat ~> Char` partial), lexicographic comparisons, and operator color/format notations. `QID`: `'abc` constants with `qid : String ~> Qid` / `string : Qid -> String`. Metalevel needs `NAT-LIST`, `QID-LIST`, `QID-SET` — predefined renamings of the container instantiations.
- **Theories & standard views (8.13)**: `TRIV` (just a sort; views named as the selected sort: `Bool Nat Int Rat Float String Qid`); `DEFAULT` (+ default element; views named `Sort0`: `Nat0`, ..., `Float0` (0.0), `String0` (""), `Qid0` (')); `STRICT-WEAK-ORDER` (irreflexive+transitive, transitive incomparability), `STRICT-TOTAL-ORDER` (≡ `STOSET`; views `Nat< Int< Rat< Float< String<`), `TOTAL-PREORDER`/`TOTAL-ORDER` (reflexive-transitive total ≡ `TOSET` conventions). All views carry unchecked proof obligations.
- **Container family (8.14–8.15, 8.17)**: parameterized views (`List{X}`, `Set{X}`, `Map{X, Y}`, `Array{X, Y}`, `WeaklySortableList{X}`, plus `List*`/`Set*` nestable variants) let you stack types: `LIST{Set{Nat}}`, `MAP{List{X}, Set{Y}}`.

## Key Concepts
- **`SET{X}`**: `empty`, singleton by subsort, `,` `[assoc comm id: empty]`, idempotency as equation (`idem`+`assoc` unsupported); `insert`/`union`/`delete`/`_in_` (matching + `owise`); `|_|` via accumulator `$card`; `intersection`/`_\_` via `$intersect`/`$diff`; `_subset_`/`_psubset_` with `and-then`.
- **`LIST{X}`**: `nil` + empty-syntax juxtaposition `__ [assoc id: nil prec 25]`; `head/tail/last/front` single-equation definitions exploiting identity matching; `occurs`; tail-recursive `reverse/$reverse`, `size/$size`. (Ch 7's `LIST-CONS` gives the Peano-style `[]`/`_:_` variant when free constructors are needed, e.g. for the ITP.)
- **`MAP{X, Y}`**: entries `K |-> V`, union `,` `[assoc comm id: empty]`; `insert(K, V, M)` = insert-or-update via matching + `$hasMapping`; lookup `M[K]` returns the kind-level constant `undefined` when the key is absent *or the map is ill-formed* (duplicate keys).
- **`ARRAY{X, Y :: DEFAULT}`**: sparse array with default `0`; lookups return `0` instead of `undefined`; inserts of the default are dropped.
- **Sortable lists**: stable mergesort under `STRICT-WEAK-ORDER` (or `TOTAL-PREORDER`): element pairs `(x, position)` make a strict total order `<` extended to pairs — stability by construction.
- **Generalized (nestable) containers** `LIST*`/`SET*`: explicit brackets `[_]` / `{_}` per level; `SET*` even has a powerset operator.
- **DIOPHANTINE** (8.16): built-in solver for non-negative solutions of `Mv = c`, matrices represented as `ARRAY` over `INDEX-PAIR` — approximate linear constraints without leaving Maude.

## Mental Models
- Treat numbers/strings/qids as *data with built-in accelerators*: program against them with normal constructors and equations and let the hooks handle performance; on kind-level garbage their behavior degrades gracefully.
- See the Boolean core as ambient (extended signature): `if_then_else_fi`, `_==_`, `_:: S` are always present, so conditional equations and sort tests never need a Bool import.
- Think of the prelude's theories+views as the library's API protocol: any container you write parameterized by TRIV instantly instantiates with `Nat`, `String`, `Qid`...

## Anti-patterns
- **Expecting `_==_`-style comparisons on `Float`**: floats are a constant blob — use `<`, `<=` etc.; equality comparisons are exact, not epsilon.
- **Membership axioms over number sorts**: breaks because `s_^n` towers are built-ins; refine via overloaded constructors or work at check time with `::`.
- **Unbounded NAT subtraction in equations**: doesn't exist — plan around `sd`, or move to INT.
- **Reading `random` as non-deterministic**: it's a deterministic function of its argument; variation across runs comes from the *counter* state (plus `set clear rules off .`).
- **Ignoring the `Nat0` vs `Nat` view distinction in containers**: instantiating a map vs an array with plain views vs `DEFAULT` views changes lookup semantics (`undefined` vs `0`).
- **Assuming MAP enforces functionality**: it doesn't; duplicate-key maps are the programmer's error, surfaced as `undefined` lookups (use `PFUN{X,Y}` from Sec 7.4.7 for enforced partial functions).
- **Out-of-range constants in MACHINE-INT**: e.g. writing 4294967296 in a 32-bit world is accepted as an integer constant and may misbehave under wrap-after-op semantics.

## Code Examples
```maude
fmod STRING-NAT-MAP is pr MAP{String, Nat} . endfm

Maude> red insert("one", 1, insert("two", 2, insert("three", 3, empty))) .
result Map{String,Nat}: "one" |-> 1, "three" |-> 3, "two" |-> 2
Maude> red insert("one", 1, insert("two", 2, insert("three", 3, empty)))[four] .
result [Nat]: undefined
```
- **What it demonstrates**: map entry syntax, insert-or-update via matching + `owise`, and the kind-level `undefined` for missing keys.

```maude
fmod INT-GT-3 is protecting INT .
  sorts One Two Three IntGt3 .
  subsorts One Two Three IntGt3 < NzNat .
  op s_ : Zero -> One [ctor ditto] .      --- refined overloading, not memberships
  op s_ : One -> Two [ctor ditto] .
  op s_ : Two -> Three [ctor ditto] .
  op s_ : Three -> IntGt3 [ctor ditto] .
  op s_ : IntGt3 -> IntGt3 [ctor ditto] .
endfm
Maude> red 4 . result IntGt3: 4
```
- **What it demonstrates**: subsorting into the predefined number hierarchy by overloading; `red` of a constant reveals its refined least sort.

## Reference Tables
| Module | Sorts | Highlights |
|---|---|---|
| `BOOL` (+ `EXT-BOOL`) | `Bool` | `if_then_else_fi`, `_==_`, `_=/=_`, `and/or/xor/not/implies` (+`and-then/or-else`) |
| `NAT` | `Zero NzNat Nat` | `+ * sd quo rem ^ modExp gcd lcm min max`, bit ops `xor & | >> <<`, tests `< <= > >= divides`; decimal == `s_^n(0)` |
| `RANDOM` / `COUNTER` | — (`Nat` ext) | `random(n)` twister; `counter =>` successive nats under rule rewriting |
| `INT` | `NzInt Int` | adds `- ~ _-_ abs` and 2's-complement bit ops; `quo` sign = product of arg signs |
| `RAT` | `PosRat NzRat Rat` | `I / N` (auto-reduced), `trunc frac floor ceiling`, rational `gcd lcm min max quo rem divides` |
| `FLOAT` | `FiniteFloat Float` | IEEE-754 double; `Infinity`, `-Infinity`; transcendental + trig ops; comparisons |
| `CONVERSION` | — | cross-type number/string conversions |
| `STRING` | `String Char` | `length substr find rfind ascii char`, lexicographic order, `*` concat |
| `QID` | `Qid` | `'q` + `qid : String ~> Qid`, `string : Qid -> String` |
| `LIST{X}` / `LIST*{X}` | `NeList{X} List{X}` | juxtaposition `__ [assoc id: nil]`; `head tail last front occurs reverse size` |
| `SET{X}` / `SET*{X}` | `NeSet{X} Set{X}` | `,` ✓assoc+comm, idempotent equation; `insert union delete in | | intersection \ subset psubset` (`SET*`: `{_}`, powerset) |
| `MAP{X, Y}` | `Entry{X,Y} Map{X,Y}` | `_|->_`, `,` union; `insert(K,V,M)`, `M[K]` → `undefined` if absent/ambiguous |
| `ARRAY{X, Y :: DEFAULT}` | `Entry Array` | sparse; `insert` drops `0`-mappings, `A[D]` → `0` |
| `DIOPHANTINE` | — | non-negative solutions of `Mv = c` systems |

| Standard views | From TRIV | From DEFAULT | From order theories |
|---|---|---|---|
| names | `Bool Nat Int Rat Float String Qid` | `Nat0 Int0 Rat0 Float0 String0 Qid0` | `Nat< Int< Rat< Float< String<` (strict-total `STRICT-TOTAL-ORDER`) |
| parameterized views | `List{X} Set{X} List*{X} Set*{X} Map{X,Y} Array{X,Y} WeaklySortableList{X} SortableList{X} ...` | | |

## Worked Example
Strings and numbers cooperating via CONVERSION in the SAMPLER pattern (probabilistic simulation):

```maude
mod SAMPLER is pr RANDOM . pr COUNTER . pr CONVERSION .
  op rand : -> [Float] .
  op sampleBernoulli : Float -> [Bool] .
  rl rand => float(random(counter) / 4294967295) .
  rl sampleBernoulli(P:Float) => rand < P:Float .
endm

mod CLOCK is pr SAMPLER .
  sort Clock .  op clock : Nat Float -> Clock [ctor] .  op broken : Nat Float -> Clock [ctor] .
  var T : Nat .  var C : Float .
  rl clock(T, C) => if sampleBernoulli(C / 1000.0)
                    then clock(s(T), C - (C / 1000.0)) else broken(T, C) fi .
endm

Maude> set clear rules off .   --- Monte Carlo: each run evolves different state
Maude> rewrite in CLOCK : clock(0, 1.0e+3) .
result Clock: broken(40, 9.607702107358117e+2)
```

Reading it: a rational division (`random(counter) / 2^32 − 1` in RAT) crosses to FLOAT through a CONVERSION operator; the COUNTER advances per rule application under `rewrite`; `set clear rules off` keeps that state between runs. This is the canonical pattern for simulation-meets-execution.

## Key Takeaways
1. The Boolean core is ambient; `_==_`-built-ins compare canonical forms, `_:: S` checks least sorts, `if_then_else_fi` selects lazily.
2. On the number tower, program case-analyses with `0`/`s_`-patterns; the towers implement GNU GMP behind `special` hooks; ratio/cardinal arithmetic on Nat fancier than `sd` is INT's job.
3. RANDOM/COUNTER give deterministic pseudo-randomness with rule-rewriting that advances state across applications — Monte Carlo simulation without external state threading.
4. Container instances compose into nested types via parameterized views (`LIST{Set{Nat}}`), and arrays/maps differ only in default semantics — choose `DEFAULT` views deliberately (`Nat0`).
5. Module-library conventions stand on the theory/view naming protocol (TRIV views named by sort, `Default` views by `Sort0`, order views by `Sort<`); your own parameterized modules plug in for free when you honor it.

## Connects To
- **Ch 3**: extended-signature polymorphic operators explained mechanically; structured sort names `Set{Int}` at parameter instantiation.
- **Ch 4**: `special`/`iter`/`memo`/`poly` attributes — this chapter is their exhibition hall; ACC semantics of built-ins.
- **Ch 7**: theories/views/instantiation protocol; `LIST-CONS` vs `LIST` trade-off (free ctors vs id-attr); `PFUN`.
- **Ch 12**: `NAT/{N}` and model-checking modules import order views and `Mod` views.
- **Ch 13, 14, 15**: unification/variant/narrowing ops (`unify`, `get variants`, `vu-narrow`) operate over these data modules.
- **Ch 17**: META-LEVEL imports `NAT-LIST`, `QID-LIST`, `QID-SET` — metarepresented syntax stands on this chapter.
- **Ch 21**: profiler/perf analysis; NaN surprises with decimal float literals and negative-zero.
