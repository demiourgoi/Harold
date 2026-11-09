# Chapter 6: Meta-Programming

## Core Idea
At the meta-level, Maude modules become **data**: `META-LEVEL` (a standard library module, outside Core and Full Maude) defines sorts `Term` and `Module` that reify terms and modules, plus **descent functions** (`metaReduce`, `metaRewrite`, `metaApply`, `metaXapply`) that compute with them. "Think of a meta-represented module as a sort of voodoo doll" — you rewrite *about* PEANO-NAT instead of in it. This is how Maude implements user-defined strategies, module surgery, and self-definition.

## Frameworks Introduced

- **Metaterm encoding** (`META-TERM`) — any term flattens into `Term`:
  - constant: `'0.Nat` (name.sort, period-separated)
  - variable: `'N:Nat` (name:sort)
  - operator application: `'opname[term, term]` via `op _[_] : Qid TermList -> Term .`
  - TermLists glue with `op _,_ : TermList TermList -> TermList [assoc] .`
  So `K of Spades` becomes `'_of_['K.Number, 'Spades.Suit]` and `s(s(0)) + N` becomes `'_+_['s['s['0.Nat]], 'N:Nat]`.
- **Meta-module encoding** (`META-MODULE`) — module constructors with set arguments:
  `op fmod_is_sorts_._____endfm : Qid ImportList SortSet SubsortDeclSet OpDeclSet MembAxSet EquationSet -> FModule [ctor] .`
  and the `mod ... endm` twin carrying `RuleSet` for system modules. Conventions: sorts are quoted ids assembled with `_;_` (`'Number ; 'Suit ; 'Card`), sets bottom out in `none`, lists in `nil`, every statement carries a bracketed attribute set even if `[none]`, constants' argument lists are `nil`, labels become `[label('convert)]` attributes, and **there are no variable declarations** — variables ride inside the metaterms. Object-oriented modules are Full Maude artifacts and are not meta-represented by META-LEVEL.
- **Descent functions** — execute a module that is only *data*:
  | Function | Arguments | Returns | Does |
  |---|---|---|---|
  | `metaReduce` | Module, Term | `ResultPair {Term, Type}` | simplifies by equations |
  | `metaRewrite` | Module, Term, Bound | `ResultPair` | applies rules, `bound` `Nat` or `unbounded` |
  | `metaFrewrite` / `metaSearch` | (as their Core analogs) | various | fair rewrite / meta-search (confirms reachability) |
  | `metaApply` | Module, Term, Qid, Substitution, Nat | `ResultTriple` | applies the named rule once, **no extension** (term must match the LHS exactly, modulo attributes) |
  | `metaXapply` | Module, Term, Qid, Substitution, Nat, Bound, Nat | `Result4Tuple` | same, **with extension**: lowers/upper bounds set how deep to hunt for the match; returns a Context |
- **Substitution sort** — for pinning rule variables ahead of time: `op _<-_ : Qid Term -> Assignment [ctor prec 63] .` and `op _;_ : Substitution Substitution -> Substitution [assoc comm id: none prec 65] .` Multiple possible matches are enumerated by the final `Nat` argument: it returns the **(N+1)-th** application option (0 = first).
- **Result4Tuple's Context** — with extension you rewrite *a piece* of the term; the Context is "the rest," with the matched piece as a `[]` hole.
- **Cosmetic level-shifters** — `up(Module, expr)` returns the metaterm of an ordinary expression; `up(Module)` returns the meta-module; `down M : metaExpr` re-lowers one reflective level. Use them to write usable calls (`up(...)` instead of hand-built metaterms) and to check hand-built encodings (`red up(PEANO-NAT-MULT) .` and compare).
- **Internal strategies** — since `rew` and `frew` are just default strategies, program your own with descent functions: e.g. `rewriteExcept(M, T, 'A, N)` — strip the labeled rule from the metaterm of the module (`rmv` over the `RuleSet`), then `metaRewrite` the doctored module.
- **Statement attributes for the meta-level** — `label('qid)` names equations/memberships so `SANS`-style surgery can target them (`sans(M, QL)` removes listed rules/equations/membership axioms; use it to prove which equations are *necessary* by removing one and re-reducing); `metadata "string"` is a free annotation a meta-program can read — tag rules 'constructive'/'destructive' and let `metaXapply` prioritize.
- **Enumerate-and-loop metaApply pattern** — the finale: when one law (e.g. `buypack` over brands) has several matches, recursively call `metaApply(..., none, N)` incrementing N until `(failure).ResultTriple?`, harvesting every solution — a solver over all substitution choices. The final helper plunge: `metaRewrite`/`metaReduce` compute each candidate's answer, and the loop ranks them (cigarette-brand test → Missouri Fats wins at 10 cents per smoke).

## Key Concepts
- **Reflection levels** — meta, meta-meta, ... ; `up`/`down` move between adjacent levels.
- **`(failure).ResultTriple?`** — the error-ish result when no application exists (loop terminator).
- **Depth counting quirk** — an associative chain (`_&_`) is one level of nesting for metaXapply's bounds, not many.
- **`['MODULE]` shorthand** — if the real module is loaded, its meta-representation can be abbreviated by quoted name; otherwise pass the full meta-module as a term.
- **Metaterms are ugly by nature**: use color-coding, scratch paper, and many small auxiliary operations to keep programs intelligible.

## Mental Models
- Think of the metaterm as a voodoo doll: actions on the doll are actions on the module.
- Think of META-LEVEL as "Maude written in Maude" — like an English textbook written in English ("perfect circular logic, which is all right as long as we stay within the circle").
- Think of strategies as first-class programs: a strategy is any meta-module that rearranges or filters someone else's `RuleSet`/`EquationSet`, then descends.
- Think of `metaApply`+loop as "for each way this could go..." — an all-alternatives iterator driven by the index argument.

## Anti-patterns
- **Expecting `metaApply` to find subterm matches**: it applies without extension; switch to `metaXapply` (and mind its two depth-bound arguments).
- **Passing `unbounded` while looping on possibly non-terminating metaRewriting**: same discipline as Core Maude.
- **Hand-writing metaterms and trusting them**: verify with `up`/`down` round trips before anything else.
- **Writing one giant meta-function**: decompose; each aux operator handles one ResultPair/Triple projection (`getTerm`, `getnum`, `getbrand` in the finale).

## Code Examples

Metarepresenting a module — compare the original to its meta-form (attributes mandatory, labels as `[label(...)]`, no var decls):

```maude
fmod 'PEANO-NAT-EXTRA is
    nil sorts 'Nat . none
    op '0 : nil -> 'Nat [ctor] .
    op 's : nil -> 'Nat [ctor] .
    op '_+_ : 'Nat 'Nat -> 'Nat [none] .
    none
    eq '_+_['N:Nat, '0.Nat] = 'N:Nat [none] .
    eq '_+_['s['M:Nat], 'N:Nat] = 's['_+_['M:Nat, 'N:Nat]] [none] .
endfm
```

Descent + cosmetic functions together (Full Maude parentheses):

```text
Maude> (red metaReduce(['PEANO-NAT-EXTRA],
        up(PEANO-NAT-EXTRA, s(s(0)) + 0)) .)
result ResultPair: {'s['s['0.Nat]], 'Nat}

Maude> (down PEANO-NAT-EXTRA :
        getTerm(metaReduce(['PEANO-NAT-EXTRA],
        up(PEANO-NAT-EXTRA, s(s(0)) + 0))) .)
result Nat: s(s(0))
```

Rule surgery as an internal strategy — strip a law by label, then rewrite:

```maude
eq name(rl T1 => T2 [label(Q) A:AttrSet] .) = Q .
eq rmv(R RS, L) = if name(R) == L then RS else R rmv(RS, L) fi .
eq rmv(none, L) = none .
eq rewriteExcept(mod Q is I sorts S . SS O M E RS endm, T1, L, N)
  = metaRewrite(mod Q is I sorts S . SS O M E rmv(RS, L) endm, T1, N) .
```

The enumerate-all loop skeleton from the finale:

```maude
eq cigApply(N) = metaApply(['CIGARETTE-VENDING-MACHINE],
                          'vendor[...], 'buypack, none, N) .
eq cigTest(N) = if cigApply(N) == (failure).ResultTriple?
                then none
                else total(cigApply(N)) cigTest(N + 1) fi .
```

## Worked Example
The cigarette-brand test at a glance. `CIGARETTES-3` gives each brand a different `makenew` butt-requirement (five DROMEDARY butts... down to two MISSOURI-FATS); the vending machine's single law `rl [buypack] : vendor(B & BS) => c(B,0) c(B,0) ... .` leaves B open, so four brand substitutions are four distinct applications of one law. `CIGARETTE-TEST` walks the enumerate-and-loop: `cigApply(N)` applies `'buypack` with index N; `cigTest` recurses on `N + 1` until `failure`, accumulating a `CigTotal` per brand where `total` computes `price(B) / smoked-count` via `metaRewrite` + `metaReduce`. Running `red goTest! .` yields Dromedaries 13, Oldports 12, Scarboroughs 12, Missouri Fats 10 — "the hobo would be better off spending the extra dollar for the Missouri Fats." The metaApply index is the for-each; the descent functions are the calculator; the module-as-data is the domain.

## Key Takeaways
1. Three encodings cover everything: `'name.Sort` (constant), `'Name:Sort` (variable), `'op[terms]` (application); modules flatten into one big constructor term.
2. `metaReduce`/`metaRewrite` compute; `metaApply`/`metaXapply` choose the exact rule and substitution — `metaXapply` adds extension with explicit depth bounds and returns the unmatched Context.
3. Always bracket meta-statement attributes (`[none]` when empty); labels live as `[label('qid)]`.
4. `up`/`down` eliminate hand-built metaterms and double as unit tests for your encodings.
5. A strategy is just a function `Strategy: Module Term ... -> Result...` that edits the module data and descends — `rewriteExcept` and `SANS` are the templates.
6. Name statements (`label`) and annotate them (`metadata`) so meta-programs can discriminate without parsing your intentions.
7. The index argument turns `metaApply`/metaXapply into an all-possibilities iterator; combined with recursion until `failure`, it is the author's pattern for choice-based optimization and planning.

## Connects To
- **Ch 2**: attributes and `owise` show up *inside* meta-representations — and new statement attributes (`label`, `metadata`) finally make their entrance.
- **Ch 3**: the bridge from `rew`/`frew` "default strategy" to programmed strategies lives here via descent functions.
- **Ch 4**: sources on Full Maude — `up`/`down` run under Full Maude parentheses; omods escape META-LEVEL (Full Maude's own level, not meta).
- **Ch 5**: parameterization connected modules "from the inside"; the meta-level connects them "from the outside."
- **External**: reflection in rewriting logic (Clavel-Meseguer); Maude's `prelude.maude` file is the readable source of META-LEVEL itself; meta-programming = staged computation, strategy languages.
