# Chapter 8: Appendix — Complete Code Examples

## Core Idea
The appendix ships runnable, commented, canonical versions of every in-book example, plus two the main text never fully presents (NETWORK-SEARCH with an actual path-finding `search`, and OPAIRLIST). Use it as the "steal this module" library: when a chapter summary gives a fragment, this is where the whole file lives (in the source PDF, pages ~130–137).

## Frameworks Introduced
(None new — reference implementations only.)

## Appendix Module Inventory

| Module | Chapter source | What it demonstrates | Notable details vs. the chapter text |
|---|---|---|---|
| `PEANO-NAT` | 1.4 | two constructors generate all naturals | minimal — exactly `{0, s}` |
| `SETS-AND-LISTS` | 1.4 | `assoc`/`comm`/`id:` attributes on `_;_` and `__` | `Elt` subsorts into BOTH Set and List |
| `ANIMALS` | 1.5 | kinds/connected components | dog lattice `Terrier Hound Toy Sporting < Dog < Animal` |
| `PEANO-NAT-EXTRA`, `PEANO-NAT-MULT` | 2.1 | recursive equations for `_+_`, `_*_` | includes a `set trace select (_*_) .` walkthrough |
| `LIST`, `LIST-SIZE` | 2.1 | first-element/rest recursion | |
| `CARD-DECK` | 2.1 | accessors picking apart a constructor (`CardNum`, `CardSuit`) | |
| `IRRITABLE-PROFESSOR` | 2.2 | pattern matching as search vs. value assignment | both `ceq`s side by side |
| `CRAZY-EIGHTS`, `SUICIDE-KING`, `CARD-PAIR` | 2.4 | membership axioms (`cmb`, `mb`) | `CARD-PAIR` uses `:= ` matching condition with `S':Suit` fresh variable per half |
| `TENNIS` | 2.5 | `prec 33 gather (e E)` on non-associative `_vs_` | also `_murders_ [prec 31]`, `_teases_ [prec 34]` interplay |
| `DOG-RACING` | 2.6 | kind-level variables `vars N M : [Dog] .` | full speed table incl. `frog`/`penguin`; `[owise]` race law |
| `CLIMATE`, `CIGARETTES` | 3.1 | first rewrite laws | |
| `COUNTING-CIGARETTES` | 3.1 | data carried inside state constructors | |
| `ARCADE-CRANE` | 3.2 | non-terminating configuration rewriting | the canonical `_&_ ... id: 1` soup |
| `CONDITIONAL-RULES` | 3.4 | every legal crl-condition form, line by line | all six variants present, five commented (`***`), one active |
| `SMILE-LOOP`, `MOOD-LOOP` | 4.1 | LOOP-MODE sub-environments | in/out laws + internal mood transitions |
| `RESTAURANT` | 4.5 | classes, subclasses, msgs, rules | appendix adds `ops One Two Three : -> Oid .` and distributes switchon/off over `OutDoorTABLE` |
| `TILE-PUZZLE` | 4.5 | computed Oids + four directional crls | backquoted coordinate constructor `(_`,_`)` |
| `GRAPH`, `NETWORK-SIMPLE`, `NETWORK-SEARCH` | 5 | complete parameterization system | **NETWORK-SEARCH** implements recursive path search (`search(NS net E ES, A, B)` walks `node1`/`node2`, builds `Pathway(X)` = `_;_` chains, `:::` set-of-paths with `null` failure edge) |
| `GREEK-GRAPH`, `Graph-Greek` | 5.2 | parameter + view | |
| `OELT`, `OPAIRLIST`, `DECK-COLOR`, `STACK`, views | 5.3–5.4 | multiple parameters, parameterized views | `DECK-COLOR` spells out the full reflexive `>=` table |
| `FUNCTION`/`FMAP`/`NEGATIVE`/`Fun-Neg` | 5.4 | parameterized theories end-to-end | the `fmap(5 9 11 2 0)` → negatives run line included |
| `REWRITE-EXCEPT`, `SANS` | 6.6 | internal strategies via descent functions | structural recursion over `RuleSet`/`EquationSet`/`MembAxSet` with `[owise]` |
| `CIGARETTES-3`, `CIGARETTE-VENDING-MACHINE`, `CIGARETTE-TEST` | 6.6 | the "grand finale" optimizer | full `getnum`/`getbrand`/`extract` helper set, metaApply index loop |

## How to Use It
- **When a chapter file shows a fragment**: the appendix version is complete and comment-bulleted (the author labels each block `*** Chapter N - Section M *** <point>`), so cross-check the exact delimiters there.
- **Two write-it-yourself candidates**: NETWORH-SEARCH's `search` is only in the appendix (Ch5 says "the implementation... is too tangential... provided in the Examples Appendix"); likewise OPAIRLIST's `top`/`add` ordering logic.
- **Diff guidance**: appendix code supersedes in-chapter typos (e.g. `IRRITABLE-PROFESSOR` marks the alternate eq as commented). When the body text and appendix disagree, trust the appendix.

## Key Takeaways
1. The appendix is the primer's standard library — 30+ loadable modules keyed to chapter and section.
2. Header comments explain intent in one line; copy that habit.
3. The network search function shows realistic parameterized recursion: `if/then/else/fi` nesting, `ceq` termination guards (`if A =/= B`), and a failure token (`null`) threaded through an associative path operator.

## Connects To
- Every chapter file in this skill references its appendix listings; treat this chapter as the table of contents for the code.
