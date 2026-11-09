# Chapter 7: Module Operations

## Core Idea
Maude is a module algebra: modules are built from other modules by importation (in four semantic modes), summation (`+`), renaming (`*(...)`), and parameterization with theories and views. The algebra is what turns single specifications into reusable hierarchies — partial orders of theory inclusions executed as a single flat theory.

## Frameworks Introduced
- **Four importation modes** — semantic assertions of an inclusion `M' ⊆ M` on the sort maps `q_s'`: See Reference Tables. Protecting = no junk + no confusion; extending = no confusion; generated-by = no junk; including = no promises. None are checked at runtime (proof obligations!); when unsure, use `including` so no false claim is made.
- **Default conventions under multiple importation**: transitive importation keeps the intermediary's mode unless overridden; diamond importation resolves by "strongest wins" (protecting > extending/generated-by > including) — a conjunction reading. Since "extending" often *means* "extending and not protecting", overrule explicitly when needed.
- **Summation** `A + B` (+ is AC, flattened): new module importing both summands; functional iff both are. Not equivalent to `protecting A . protecting B .` when summands share sorts/operators (their identifications fuse differently); `including A + B .` *is* equivalent to the two including-importations.
- **Renaming** `M * (maps, ...)` — sorts, operators (by name, by typing, with attribute-set limited to `prec`/`gather`/`format`), labels, and (for omods) classes/attrs/msgs. Renaming propagates to every affected submodule, generating renamed copies whose names footnote the applied sub-map; types in operator maps get *canonized to kinds* (`op f : Bar -> Bar to g` may become `op f : [Foo,Bar] -> [Foo,Bar] to g` so `f : Foo -> Foo` in submodules renames consistently). `*` binds tighter than `+` and groups left; `*` does **not** distribute over `+`.
- **Theories** (`fth ... endfth`, `th ... endth`, `oth ... endoth`): loose-semantics interfaces — any satisfying algebra/theory is an acceptable parameter. Statements need not be executable; `nonexec` and extra-variable equations/rules are legal in theories. `pconst` marks parameter constants (instantiated as `X$c`). A theory cannot be imported into a module; theory-into-theory importation is `including` only. Workhorses: `TRIV` (just a sort), `TOSET`/`SPOSET`/… (order requirements), `RING`/`MONOID` (algebraic requirements).
- **Views** (`view V from S to T is maps endv`): a claimed satisfaction of theory `S` by module/theory `T`, with per-entity maps and *unchecked proof obligations*. Omitted maps default to identity — "obvious" mappings need not be written. Views compose instantiations (`TOSET`-target views between theories) and can be parameterized (`view Set{X :: TRIV} from TRIV to SET{X} ...`) for knockout reusability.
- **Parameterized modules** `M{X1 :: T1, ..., Xn :: Tn}`: the interface creates renamed copies `X :: T` with qualified names (`X$S` for sorts, `X$C` classes, `X$c` parameter constants, `X$l` labels). Declared sorts/classes/constants are themselves parameterized: `Set{X}` → `Set{Int}` under `BASIC-SET{Int}`.
- **Instantiation** `M{A1, ..., An}`: each `Ai` is (a) a parameter label — parameter stays, retargeted; (b) a view into a theory — module stays parameterized, requirement strengthened (`LIST-CONS{TOSET}`); or (c) a view into a module — parameter disappears. Parameter labeling **links parameters** through protected imports (`pr BASIC-SET{X}` inside `SET-LIST{X :: TRIV}`), instantiating them together later; functional modules instantiated with system-module views become system modules.

## Key Concepts
- **No junk / no confusion**: surjectivity/injectivity of the canonical-form map; the vocabulary behind all importation modes; error-junk at the kind level is explicitly *allowed* under protecting (e.g. `3 + 7/0` in `RAT` over `NAT`).
- **Kind-canonizing renamings**: renaming by type may affect deeper overloadings than visible; Maude widens the typing to the connected component.
- **View operator maps to terms**: `op X:Elt < Y:Elt to term X:Int <= Y:Int and X:Int =/= Y:Int` — the source term must parse uniquely in the source theory, the target term in the target; view-local variables alias differently on each side of the map.
- **Proof obligations of a view**: each source axiom translated must hold in the target (e.g. SPOSET's irreflexivity/transitivity/antisymmetry after `SPosetToInt`'s translation) — user's job, ITP/induction tools.
- **Interface sharing**: split `VENDING-MACHINE-SIGNATURE` / `VENDING-MACHINE`, `DATA-AGENTS-INTERFACE{K,V}` / `DATA-AGENTS{K,V}` — same static vocabulary reused by several rule sets.
- **Sorted subsorts via memberships** (`SortedList{X}`): the expressiveness membership equational logic adds over order-sorted — and with it, precise typings like `insertion-sort : List{TOSET}{X} -> SortedList{X}`.
- **Parameterized view + parameterized module idioms**: `PFUN{X,Y}` — partial functions as sets of pairs with a functional-domain membership axiom; `MAP ... * (sort Map{K,V} to Dict{K,V}, op _[_] to lookup, op insert to update)`.

## Mental Models
- Treat importation modes as *documentation with proof obligations*: truthful, checkable by theorem proving, invisible at runtime.
- Think of views as interpretations (theory morphisms): the same theory has many possible views into one module (`IntAsToset`, reverse-order views…), and each is a distinct instantiation choice.
- Think of parameter labels as *wires*: `X` in `pr BASIC-SET{X}` and in the interface `{X :: TRIV}` ties the submodule's parameter to the enclosing module's, so one instantiation binds them all.

## Anti-patterns
- **`protecting A + B .` assumed equal to two protecting imports**: shared sorts get fused into one construct — interactions can violate protection; state the importations separately or use `including`.
- **Renaming that "obviously" misses submodule operators**: sub-overloadings belong to a kind, and renamings canonize to the kind; check `show desugared`/module names if unsure what got renamed.
- **Instantiating away a parameter that still appears in imported parameterized sorts**: free-parameter modules cannot be imported; bind the parameter first.
- **Naming TRIV views randomly**: conventions (`Int` = view sending `Elt` to `Int`; inclusion views named as the target theory) make `{...}`-qualification readable — `Set{Int}`, not `Set{SomeRandomName}`.
- **Renaming a parameterized module touching parameter-theory sorts/ops**: forbidden; rename the *body's* entities only.
- **Non-final instantiation scope errors**: instantiations passing enclosing-module parameters (`POLYNOMIAL{X, POSET}{Y}`) are illegal; instantiate step-by-step.

## Code Examples
```maude
view RingToRat from RING to RAT is
  sort Ring to Rat .
  op e to term 1 .       --- 1 is s_^1(0), not a constant: needs a to-term map
  op z to 0 .
endv

fmod QID-RAT-POLY is
  pr RAT-POLY{Qid} .     --- RING-view + TRIV-view instantiation chain
endfm
--- red in QID-RAT-POLY : ((2/3)(('X ^ 2)('Y ^ 3))) ++ ((7/5)(('Y ^ 2)('Z ^ 5))) ...
```
- **What it demonstrates**: views with to-term maps, then composed instantiations (poly arithmetic over Qids with rational coefficients).

```maude
view TOSET from TRIV to TOSET is endv   --- inclusion view keeps the parameter free

fmod SORTED-LIST{X :: TOSET} is
  protecting LIST-CONS{TOSET}{X} .
  sorts SortedList{X} NeSortedList{X} .
  subsorts NeSortedList{X} < SortedList{X} < List{TOSET}{X} .
  var N : X$Elt .  var NEOL : NeSortedList{X} .
  mb [] : SortedList{X} .
  mb (N : []) : NeSortedList{X} .
  cmb (N : NEOL) : NeSortedList{X} if N <= head(NEOL) .
  op insertion-sort : List{TOSET}{X} -> SortedList{X} .
  ...
endfm
```
- **What it demonstrates**: partial instantiation (`{TOSET}{X}`), membership-defined subsort of sorted lists, sort-refined sorting operators.

## Reference Tables
| Importation mode | Assertion on `q_s'` | Colloquial | Checked? |
|---|---|---|---|
| `protecting` | bijective | no junk **and** no confusion | no (inductive proof) |
| `extending` | injective | no confusion (junk ok) | no |
| `generated-by` | surjective | no junk (confusion ok) | no |
| `including` | none | anything goes | (trivially) |

| Module expression | Meaning |
|---|---|
| `A + B` | summation (AC, flattened); imports both |
| `M * (sort S to S', op f : Ty -> Ty' to g, label l to l', ...)` | renamed copy; propagates through affected submodules |
| `M{V1, ..., Vn}` | instantiation by views (one per free parameter) |
| `M{T}` (view into theory) | parameter-retargeting instantiation; result still parameterized |

| View map forms | Purpose |
|---|---|
| `sort S to S' .` | sort mapping (kinds and subsorts must be preserved) |
| `op f to f' .` / `op f : S1...Sn -> T to f' .` | operator map (typings hit the whole subsort-overloaded family) |
| `op f(x-vars) to term <term>` | operator-to-term (derived op) map |
| `class C to C' .`, `attr a to b .`, `msg ... to ... .` | omod interface maps |
| (omitted) | identity mapping |

## Worked Example
Watching instantiation chemistry — from `TRIV` to polynomials:
1. `fmod MONOMIAL{X :: TRIV} is protecting NAT . ...` — monomials over parameter elements.
2. `fmod POLYNOMIAL{R :: RING, X :: TRIV} is protecting MONOMIAL{X} . ...` — the label `X` *links* the parameter to the imported module's.
3. `fmod RAT-POLY{X :: TRIV} is pr POLYNOMIAL{RingToRat, X} . endfm` — one parameter instantiated (`R`), the other bound and passed on.
4. `fmod QID-RAT-POLY is pr RAT-POLY{Qid} . endfm` — everything resolves; `Poly{RingToRat, Qid}` terms simplify by ring laws.

The pattern generalizes: **interfaces are theories, glue is views, structure is labels** — and each binding step leaves proof obligations (here: that RAT satisfies RING) that are yours to discharge, not Maude's.

The data-agents example reuses the same machinery on the object side: interface module (extending a common conf module), behavior module (including the interface), `MAP{K,V}` wrapped by renaming into an application-specific dictionary, `SET{Request}` for pending-request bookkeeping — the canonical architecture for request-reply object systems.

## Key Takeaways
1. Choose importation modes by what you can *prove*: protecting and extending make real claims; including makes none; generated-by sits between.
2. `+` fuses, `*` copies, `{...}` binds — module expressions have precedence (`*` over `+`) and evaluation semantics (renamed copies named after their sub-maps).
3. Theories = requirements with loose semantics; views = interpretations with proof obligations; both can be parameterized; labeling wires parameters through the hierarchy.
4. Parameterized sorts (`Set{X}`, `Pair{X,Y}`) are qualified by *views* at instantiation, which is why renaming collision problems almost disappear in parameterized Maude.
5. `SET-MAX{IntAsToset}`-style instantiations give maximum reuse: one sorted-list module, every totally ordered data type.
6. When in doubt: `show desugared`, `show modules`, and the importation-graph conventions (single = including, double = extending, triple = protecting) tell you what Maude actually built.

## Connects To
- **Ch 4 / 5**: protector module semantics builds on canonical forms; executable statements of theories (fth/th) reuse the admissibility vocabulary.
- **Ch 6**: class names are sort names — hence parameterizable classes; the omod desugaring interplays with importation modes (`ex CONFIGURATION` for uniform message syntax).
- **Ch 8**: every predefined module's instantiation interface (e.g. `NAT`, `STRING`, `FLOAT`, `MAP{K,V}`, `SET{X}`, and the predefined views `Int`, `Bool`, `Qid`, ... in Sec. 8.13.1).
- **Ch 13**: theory-targeted instantiation is harnessed again in unification-supported theories (`{...}` over `TH` theories).
- **Ch 17**: `META-VIEW`/`META-MODULE` metarepresent all of this chapter's objects; labels renamed by views matter for metalevel addressing.
