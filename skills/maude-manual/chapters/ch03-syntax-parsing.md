# Chapter 3: Syntax and Basic Parsing

## Core Idea
Everything you can write in Maude — modules, sorts, subsorts, kinds, operators, variables, terms — is defined here, together with the precedence/gathering mechanism that lets user-defined mixfix grammars parse unambiguously. Master this before writing any module.

## Frameworks Introduced
- **Identifier tokenization**: an identifier is any sequence of ASCII characters without whitespace; `{`, `}`, `(`, `)`, `[`, `]`, and `,` break a sequence into several identifiers; the backquote `'` escapes blanks/specials to keep a single identifier (`1'ab'{c',d'}ef` is one identifier; `ab{c,d}ef` is seven).
  - When to use: operator names that contain spaces or specials.
- **Mixfix operator scheme**: `op ⟨OpName⟩ : ⟨Sort-1⟩ ... ⟨Sort-k⟩ -> ⟨Sort⟩ [attrs] .`; underscores mark argument positions and their number must equal the arity (constants have none). No underscore → prefix; underscores → mixfix; bare `__` = empty syntax.
- **Kinds as error supersorts**: each connected component of the subsort order is a kind `[...]`; terms with a kind but no sort are undefined/error expressions; operators are automatically lifted to kinds.
  - How: declare partial operations at the kind level (`op _;_ : [Path] [Path] -> [Path] .`) or with the partial arrow (`op _;_ : Path Path ~> Path .` — equivalent).
- **Precedence + gathering disambiguation**: user-definable syntax parses via extended Leo's algorithm; each operator has a precedence number and a gathering pattern over `E` (argument precedence ≤), `e` (strictly <), `&` (any). Precedence default 15 (unary mixfix with one bar at an end), 41 (bars at both ends), 0 (standard form; mixfix not ending in a bar… full table below).
- **Extended signature**: besides your declarations, every module's grammar includes `(_)` parentheses, `(_).S` sort disambiguation, single-identifier prefix equivalents (`_+_(2, 3)`), flattened associative argument lists (`gcd(2, 3, 4)`), and the polymorphic/Boolean core: `if_then_else_fi`, `_==_`, `_=/=_`, sort predicate `_:: S`.
- **Preregularity**: a signature is *preregular* when every well-formed combination of argument sorts selects a least result sort among a operator's overloadings. Maude checks preregularity modulo declared axioms and warns on failure.

## Key Concepts
- **Signature Σ** = sorts + subsorts + (implicit kinds) + operators; **statements** = equations, memberships (functional) and additionally rules (system).
- **`fmod M is ... endfm`** / **`mod M is ... endm`**: module delimiters; style ALL-CAPS, hyphen-joined (`VENDING-MACHINE`).
- **`sort` / `sorts`**: `sorts A B C .` — a missing period silently declares a sort named `sort` (e.g., `sorts A B sort C .`).
- **Structured sort names**: `List{X}`, `List{Nat}` — by BNF `{}`-nesting; backquoted single-identifier form for hooks/metasyntax (`Foo'{X',Y'}`).
- **`subsort Zero < Nat .`** / `subsorts Zero NzNat < Nat .` — subsort order must be a partial order (acyclic); connected components group related data.
- **Kind naming**: bracket any sort(s) of the component: `[Nat]` ≡ `[Nat, NatSeq]`; Maude prints kinds as the component's maximal sorts.
- **Ad-hoc vs. subsort overloading**: same operator name redeclared — ad-hoc overloading crosses connected components (constants `0 : -> Nat` and `0 : -> Nat3`); subsort overloading stays in related sorts (`op _+_ : NzNat Nat -> NzNat .` and `op _+_ : Nat3 Nat3 -> Nat3 .`).
- **Variables**: on-the-fly `N:Nat`, `X:[Nat]` (sort/kind colon scanned right-to-left; scope = the occurrence) or module-wide `vars M N : Nat .` (upper case customary; no `_` in names).
- **Term**: constant | variable | application; prefix form always available (`s_(zero)`); mixfix form `s zero`; term sort = declared result + supersorts, least sort = most precise classification (`s s 0 : NzNat`).
- **Preregularity failure example**: `subsorts A < B C < D .` with `op f : B -> B .` and `op f : C -> C .` — `f(X:A)` has minimal sorts B *and* C, no least sort.
- **`parse [in M :] T .`**: parse-check a term without evaluating; on ambiguity Maude warns ("Arbitrarily taking the first as correct").

## Mental Models
- Think of each operator as coming with (precedence, gathering) that partition its parse space; `(E e)` = left-associative, `(e E)` = right-associative, `&` = don't care.
- Read kind level as "the type of an erroneous or unfinished term"; partiality = work at kind level, success = landing in a real sort.
- When a term won't parse, first run `parse`, then disambiguate explicitly with `(t).SortName`, parentheses, or the prefix form.

## Anti-patterns
- **Missing or jammed periods in declarations**: `sorts A B sort C .` silently declares four sorts; periods must be space-separated.
- **Ambiguous grammars relying on Maude's arbitrary choice**: `1 + 2 * 3` with identic precedences parses either way with only a warning — set `prec` and `gather` instead.
- **Non-preregular overloading**: incomparable result sorts for overlapping argument domains destroy the least-sort property (and thus clean typing) — expect warnings, later trouble in associativity/attributes too (Sec. 21.3).
- **Underscores in variable names**: not allowed; the underscore is exclusively an argument slot marker.

## Code Examples
```maude
sort NatSeq .  subsort Nat < NatSeq .
op __ : NatSeq NatSeq -> NatSeq [assoc] .
--- empty-syntax juxtaposition; parses sequences: zero (s zero) (s s zero)

op [_] and then [_] : Command Command -> Command .
--- one binary operator written with eight identifiers; backquote equivalent: '[_']and'then'[_']

op _=_ (?:...): use double parens when the syntax itself contains parens:
op ((_ only after _)) : Command Command -> Command .
```
- **What it demonstrates**: empty syntax, multi-identifier mixfix, and the paren-doubling rule.

```maude
sorts Node Edge Path .  ops source target : Edge -> Node .
subsort Edge < Path .
op _;_ : Path Path ~> Path .   --- partial: total at kind level
```
- **What it demonstrates**: partiality via kind-level declaration and the `~>` sugar (Ch 4 adds `cmb (P ; Q) : Path if target(P) = source(Q) .`).

## Reference Tables
| Category | Default precedence |
|---|---|
| Constants, prefix (standard form) | 0 (user cannot change) |
| Mixfix not beginning/ending with `_` (e.g., `(_)`, `<_:_|_>`, `if_then_else_fi`) | 0 |
| Mixfix with a bar at exactly one end | 15 (unary), 41 (n-ary) |
| Mixfix with bars at both ends (`__`, `_+_`, `_*_`, `_?_:_`) | 41 |

| Argument position | Default gathering |
|---|---|
| Prefix operator argument | `&` |
| `_` between two non-bar tokens (`[_ and then _]`) | `&` |
| `_` adjacent to another `_`, or leftmost/rightmost token (`not_`, `_+_`, `__`) | `E` |
| Binary `_..._` with `assoc` | `(e E)` |
| Non-assoc binary, args+coarity in one component | subsort-based: right-assoc → `(e E)`, left-assoc → `(E e)` |

| Extended signature item | Use |
|---|---|
| `(_)` for each sort | parentheses everywhere |
| `(_).S` | disambiguate overloaded terms/consts (`(0).Nat3`, `(none).OpDeclSet`) |
| single-identifier prefix form | any operator (`_+_(2, 3)`, `if_then_else_fi(a, b, c)`) |
| flattened assoc args | `gcd(2, 3, 4)`, `_+_(2, 3, 4)` |
| `if_then_else_fi`, `_==_`, `_=/=_`, `_:: S` | from the always-imported Boolean core (Sec. 8.1) |

## Worked Example
Ambiguity resolution, the PARSING-EX series. Baseline — no attributes: two operators default to precedence 41, gathering `(E E)`:

```maude
fmod PARSING-EX1 is
  sort Nat .  ops 1 2 3 : -> Nat .
  ops _+_ _*_ : Nat Nat -> Nat .
endfm
```
```
Maude> parse 1 + 2 * 3 .
Warning: ambiguous term, two parses are:
  1 + (2 * 3) -versus- (1 + 2) * 3   [Arbitrarily taking the first]
```

Step 1 — differentiate precedence (`*` binds tighter):

```maude
op _+_ : Nat Nat -> Nat [prec 33] .
op _*_ : Nat Nat -> Nat [prec 31] .
--- parse 1 + 2 * 3 . now unambiguous; but 1 + 2 + 3 still has (E E) ambiguity
```

Step 2 — force left-associativity with gathering:

```maude
fmod PARSING-EX3 is
  sort Nat .  ops 1 2 3 : -> Nat .
  op _+_ : Nat Nat -> Nat [prec 33 gather (E e)] .
  op _*_ : Nat Nat -> Nat [prec 31 gather (E e)] .
endfm
--- parse 1 + 2 * 3 . and parse 1 + 2 + 3 . both unique
```

The same effect comes for free with `[assoc]` (PARSING-EX4) because associative binary operators default to gathering `(e E)`. The lesson: (1) precedences first, so *" binds tighter than +", (2) gathering second, so `1 + 2 + 3` has exactly one parse, (3) `parse` — never `reduce` — is the tool for checking.

## Key Takeaways
1. Declarations are cheap but punctuation-sensitive: space-separated periods, no stray tokens (`sort` is a valid sort name — by accidence).
2. Subsort inclusions must be acyclic; kinds = connected components with operator lifting as error supersorts; declare partiality with `[...]` or `~>`.
3. Give every nontrivial mixfix operator an explicit `[prec ... gather ...]`; a correct grammar is part of a correct program in Maude.
4. The extended signature means parentheses, sort casts `(t).S`, prefix forms, flattened assoc applications, and the Boolean core are always available in every module.
5. Keep signatures preregular (least result sorts on overloading); Maude warns automatically (Sec. 21.3.5).
6. Use `parse in M : T .` to test grammars before running anything.

## Connects To
- **Ch 4**: operator *attributes* (`assoc`, `comm`, …) and statements (`eq`, `ceq`, `mb`, `cmb`) complete the functional-module picture; memberships define when a kind-level path becomes a `Path`.
- **Ch 5**: `mod ... endm` module syntax and rules.
- **Ch 7**: structured sorts and `pconst` constants instantiate under parameterized modules/views.
- **Ch 8**: how predefined modules (NAT, STRING, BOOL…) use these conventions; the Boolean/`if_then_else_fi` core explained.
- **Ch 17**: metasyntax uses single-identifier forms exclusively (`'[_']and'then'[_']`).
- **Ch 21**: debugging tools for non-preregular/ambiguous declarations (Sections 21.3.4–21.3.5).
