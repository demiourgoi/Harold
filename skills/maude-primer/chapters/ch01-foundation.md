# Chapter 1: Foundation

## Core Idea
The module is the key concept of Maude: a set of definitions that declares an algebra (sorts plus operations on them) and the information needed to reduce and rewrite expressions. Everything else — sorts, variables, operations, constructors, kinds — is the vocabulary for writing those definitions.

## Frameworks Introduced

- **Module as algebra**: a module provides a collection of sorts and a collection of operations on those sorts. Three module types:
  - `fmod NAME is ... endfm` — functional module (declarative, defines an algebra)
  - `mod NAME is ... endm` — system module (adds rewrite laws, Ch3)
  - `omod NAME is ... endom` — object-oriented module (Full Maude only, Ch4)
- **Core vs. Full Maude**: everything in Core Maude is in Full Maude, not vice versa. Functional and system modules are Core; object-oriented modules are Full Maude, and in Full Maude all commands/modules are entered enclosed in parentheses: `(omod NAME is ... endom)`.
- **Importation modes** — when a module uses another module's declarations:
  - `protecting M .` — imported declarations used strictly as defined; nothing modified
  - `extending M .` — between protecting and including (explained further in Ch2)
  - `including M .` — the sense of imported declarations may be changed (e.g. import `INT` but redefine its `+` to multiply)
  - Every importation statement ends with a period; module definitions do not.
- **Constructor discipline**: a constructor (`[ctor]`) is a fundamental operation that defines the basics of the algebra — no other operation can build its values any other way. Constants are usually constructors when the value is basic to the algebra (Peano's `0` and `s`), and non-constructors otherwise (a distributive-law helper). "It's kind of tricky to decide what operations should be constructors, but only experience remedies this."
- **Equational attributes** — flags inside `[...]` on binary operators, usable with or without `ctor`:
  - `assoc` — `(L1 L2) L3` = `L1 (L2 L3)` = `L1 L2 L3`
  - `comm` — order does not matter (use for sets, not queues)
  - `id: nil` — identity element (`L1 nil` reduces to `L1`); also `left id:` and `right id:` per side
  - `idem` — repeated elements discarded (sets); **`assoc` and `idem` may not be combined**
  - `iter` — for unary operators: iterated chains written as `s_^5(0)` instead of `s s s s s 0`
- **Kinds as error containment**: whenever you declare a sort, Maude automatically defines a kind `[Sort]` — a supersort grouping the whole connected component (the graph of sorts joined by `subsort` declarations) plus error terms ("interfamilial" hybrids). Misapplication inside a component yields a term of the kind; misapplication across components does not parse at all. With multiple topmost sorts the kind is written `[Horse,Human]`.

## Key Concepts
- **Sort** — a category for values (`sort integer .`); names cannot contain whitespace, `,`, or `(` `[` `{` unless preceded by a backquote, and sort names additionally exclude periods and colons.
- **Subsort** — "qualifies as a": `subsorts Positive Negative < Integer < Rational .`
- **Variable** — an indefinite placeholder for a sort, declared `var x : number .` or `vars c1 c2 c3 : color .` (same sort required for `vars`). Never assigned or carried — only meaningful inside equations/rewrite laws.
- **Operation** — "a pathway between sorts": `op _+_ : Nat Nat -> Nat .`
- **Prefix vs. mixfix** — prefix declares `op f`, called `f(x, y)`; mixfix declares underscores as argument slots, e.g. `op _+_`, `op AddSum_+_to_`, called `AddSum x + y to List1`.
- **Constant** — an operation with no argument sorts: `op red : -> Color .`
- **Operator overloading** — allowed and powerful, but "should be handled carefully" (Ch2).
- **Qid** — quoted identifier: `'Ted`; created by an apostrophe before any word.
- **String** — characters in quote marks, concatenated with `_+_`, indexed from 0.
- **Comment** — `***` or `---` hides the rest of the line.

## Mental Models
- Think of a module as "essentially a set of definitions" of an algebra: declare the values first (sorts), then the pathways (operations).
- Read `<` in subsort declarations as "qualifies as a" — every operation defined on a sort also accepts its subsorts.
- Think of a kind as an overflow bucket per connected component: badly-typed terms inside the family land in `[Sort]` instead of failing to parse; outside the family nothing parses.
- Use constants-zero-argument-operations as the honest definition of "constant"; variables are never constants.

## Anti-patterns
- **Using a variable as a constant**: Maude variables never carry or store values — declaring `red` as a variable of sort `Color` is wrong; make it an operation `op red : -> Color .`.
- **Forgetting the trailing period**: all declarations and statements need `.` — only module definitions don't.
- **Combining `assoc` and `idem`**: not allowed in Maude.
- **Marking non-fundamental operations `[ctor]`**: constructors should capture the bare-minimum value-builders of the algebra (see Peano discussion below), not conveniences like head/size on lists.

## Code Examples

Peano naturals — both `0` and `s` are constructors because every natural is built by composing exactly these:

```maude
fmod PEANO-NAT is
    sort Nat .
    op 0 : -> Nat [ctor] .
    op s : Nat -> Nat [ctor] .
endfm
```

Bare-minimum list algebra — `nil` and concatenation `__` build everything; `assoc id: nil` gives list laws for free:

```maude
fmod BASIC-LIST is
    sorts List Elt .
    subsort Elt < List .
    op nil : -> List [ctor] .
    op __ : List List -> List [ctor assoc id: nil] .
    vars E1 E2 : Elt .
    vars L1 L2 : List .
endfm
```

Set constructor by contrast — `comm` (order-free) plus identity `none`, with `idem` as the sets-only option:

```maude
op __ : Set Set -> Set [ctor assoc comm id: none] .
```

Names via QID — no need to declare a constant per name; `'Ted` is already a term of sort `Name`:

```maude
fmod NAME is
    protecting QID .
    sort Name .
    subsort Qid < Name .
endfm
```

## Reference Tables

Module types:

| Type | Delimiters | Level | Purpose |
|---|---|---|---|
| functional | `fmod ... endfm` | Core Maude | algebra: sorts + operations + equations (Ch2) |
| system | `mod ... endm` | Core Maude | adds rewrite laws for dynamic behavior (Ch3) |
| object-oriented | `omod ... endom` | Full Maude only | objects, messages, classes (Ch4) |

Importation modes:

| Keyword | Guarantee |
|---|---|
| `protecting M .` | no imported declaration is modified in any way |
| `extending M .` | intermediate; between protecting and including |
| `including M .` | imported declarations' sense may be redefined |

Equational attribute flags (binary operators unless noted):

| Flag | Meaning | Typical use |
|---|---|---|
| `assoc` | grouping irrelevant | list/set concat |
| `comm` | argument order irrelevant | sets |
| `id: e` / `left id:` / `right id:` | identity element (per side) | `id: nil` for lists |
| `idem` | duplicates collapse | sets (NOT with `assoc`) |
| `iter` (unary) | `s_^5(0)` exponent form | Peano successor |

Common supplied modules:

| Module | Provides |
|---|---|
| `NAT` (also `INT`, `FLOAT`, `RAT`) | numeric sorts, usual operations in numeric notation (Peano also accepted); `sd`, `_quo_`, `_rem_`, ... |
| `QID` | quoted identifiers `'word` usable as names |
| `STRING` | `"..."` values, `_+_` concatenation, `substr(S, start, len)`, `find(S, pat, from)` forward search, `rfind(S, pat, from)` backward search |

## Worked Example
The `BASIC-LIST` walk-through shows the load-bearing choice: declaring `subsort Elt < List`. An element is just a singleton list, so the concatenation operator accepts `E1 E2`, `E1 L1`, and `L1 L2` alike — no separate elt-to-list coercion operation needed. Add `[ctor assoc id: nil]`: associativity means `(L1 L2) L3` is one flat list not a nest of pairs; identity means `L1 nil` silently reduces to `L1`. That is the entire bare-minimum list: two constructors (`nil`, `__`) build every list value, while head/tail/length are supporting (non-constructor) conveniences the algebra can live without.

## Key Takeaways
1. Declare sorts and operations to define an algebra; state module type (`fmod`/`mod`/`omod`) and end every declaration with `.`.
2. Prefer `protecting` imports (strict, no redefinition); reach for `including` only when you must change an imported module's sense.
3. Reserve `[ctor]` for the operations that generate the algebra's values from scratch — Peano's `{0, s}`, the list's `{nil, __}`.
4. Free yourself from list/set plumbing with equational attributes (`assoc`, `comm`, `id:`, `iter`) instead of writing equations by hand.
5. Let kinds be your error handling at the type level: bad terms inside a connected component become `[Sort]` values rather than parse failures, and Ch2 shows how to compute even over kinds.
6. Import `NAT`, `INT`, `FLOAT`, `RAT`, `QID`, `STRING` before hand-rolling numeric, name, or string sorts.

## Connects To
- **Ch 2**: equations give functional modules their computing power; `extending` gets its real definition; membership axioms compute over kinds ("we can breed out the penguins").
- **Ch 3**: constructors matter for rewriting — constructor patterns drive what rewrite laws can match.
- **Ch 4**: objects are values of a configuration sort, built exactly like these algebras.
- **Ch 6**: kinds and subsort lattices reappear as the metaterm sort lattice (`Term`, `Substitution`, etc.).
- **External**: equational logic / order-sorted algebras (Goguen-Meseguer); the full standard-library story is Maude 2.0 Manual, Part I, Ch 7.
