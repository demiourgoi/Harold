---
name: maude-primer
description: "Knowledge base from \"Maude 2.0 Primer\" (v1.0, 2003) by Theodore McCombs. Use when writing, debugging, or explaining Maude (rewriting-logic) code: sorts, subsorts, kinds, constructors, equations and membership axioms, rewrite laws and search, Full Maude object-oriented modules, parameterized modules/theories/views, or META-LEVEL metaprogramming and internal strategies."
---

<!-- argument-hint: [topic, framework name, or chapter number] -->

# Maude 2.0 Primer
**Author**: Theodore McCombs (SRI Computer Science Laboratory) | **Pages**: ~137 | **Chapters**: 6 + exercises/answers + examples appendix | **Generated**: 2026-11-09

## How to Use This Skill

- **Without arguments** — load the core frameworks below for working reference
- **With a topic** — ask about `kinds`, `search`, `views`, or any indexed term; I read the relevant chapter file before answering
- **With a chapter** — ask for `ch03` to load that chapter's file
- **Browse** — ask "what chapters do you have?" to see the index

Chapter files are loaded on demand; the cheatsheet holds decision tables for quick reference while coding.

---

## Core Frameworks & Mental Models

**Module as algebra** — "The module is the key concept of Maude. It is essentially a set of definitions." Declare sorts (categories of values), then operations (pathways between sorts), then the statements that compute over them. Use `fmod` for pure computation, `mod` when values change state (rewrite laws), `omod` for objects/messages (Full Maude, parenthesized).

**Constructor discipline** — a constructor `[ctor]` is a value-generator: every other operation computes *from* constructor terms, and the goal of a set of equations is to reduce any expression to canonical form (constructor-only). Reserve `[ctor]` for the bare-minimum generators (Peano's `0`/`s_;` a list's `nil`/`__`) and mark conveniences (head, size) as derived.

**Equations demand direction** — `eq lhs = rhs .` only earns its keep when the RHS is strictly simpler. Write recursion as base case + peel (`eq 0 + N = N . eq s(M) + N = s(M + N) .`; `eq size(E L) = s(size(L)) .`), never as a mid-structure split. Symmetric laws (commutativity, associativity) never belong in equations — they ping-pong; use the flags `assoc`, `comm`, `id:`, `idem` (assoc+idem incompatible; write `eq E E = E .` for idempotency when you also need assoc).

**Dispatch stack** — pick statements by shape: `eq` (unconditional simplify) / `ceq ... if c1 /\ c2` (guarded) / `mb`, `cmb` (sort refinement) / `rl [label] : A => B .` (irreversible transition) / `crl`. Guard flavors: Boolean, membership (`X :: NzNat`), pattern match (`(S:String) ? := I`), even a *rewrite* (`if a(X) => b(Y)`) meaning reachability. `owise` supplies the hard-to-state complement; `if_then_else_fi` is an ordinary operator, not a keyword.

**Import policy = junk/confusion** — adding new ground terms to imported sorts is *junk*; redefining their equations is *confusion*. `protecting` forbids both, `extending` allows junk, `including` allows both. Choose per import; do not quietly violate `protecting`.

**Kinds are error recovery, not failure** — every sort brings an automatic kind `[Sort]` covering its whole connected component plus error terms. Compute *at the kind level* (`vars N M : [Dog] .`) when functions should keep working on ill-sorted input — "we can breed out the penguins." Use `mb`/`cmb` to rescue coarse results into the subsort a later operation needs (`cmb N / M : NzNat if N =/= 0 .`).

**State-transition modeling** — states are constructor facts glued by a soup operator (`op _&_ : State State -> State [ctor assoc comm id: 1] .`); rewrite laws map state patterns to state patterns, irreversibly. Neither side is "simpler," so termination is never promised: bound your runs (`rew [n]`), starve rules with `frew`, and answer "how do I get from A to B?" with `search A =>+ B-with-variables .` + `show path N .` (target final → `=>!`).

**Full Maude is Maude modeling itself** — LOOP-MODE's `op [_,_,_] : QidList State QidList -> System` is a read-eval-print machine written in Core Maude; Full Maude is that interpreter upgraded with omods and parameterization. Consequence: parenthesize everything Full Maude must see, and treat its parser as flimsier than Core's — "safe parsing": parenthesize mixfix messages (`(A borrowchairfrom B)`), backquote punctuation in operators (`'(_`,_`)`).

**Objects are records; messages are notes** — `class TABLE | occupied : Bool , chairs : Nat .`; an object is the term `< A : TABLE | occupied : false >` (read it as `op < _:_ | _ > : Oid Cid AttrSet -> Object [ctor]`); a message (`msg sit@ : Oid -> Msg .`) always takes the addressee's `Oid` first and sits beside the object until a rule consumes both. Name in each rule only the attributes that matter; the rest ride along. Oids may be computed constructor terms (grid coordinates).

**Parameterization lego** — contract (theory `fth`/`oth`) + frame (`(fmod M(X :: T) is ... endfm)`, frame sorts `S(X)`, theory sorts `X@S`) + parameter module + view (`view V from T to M is sort Node to Letter . op node1 to source .` — ops can bind to terms: `op s X to term X + 3 .`) + instantiation (`pr M(V)` / `( select M(V) . )`). Multiple parameters use `|` everywhere. Survival rules: declare all theory labels up front; keep labels on every theory-dependent sort/module (operations exempt); connect every view in the instantiation.

**The meta-level makes modules into data** — metaterms `'c.Sort`, `'X:Sort`, `'op[terms]`; whole modules flatten into one constructor term (`sorts`, `none`-terminated sets, labels as `[label('qid)]`). Compute with them via descent functions: `metaReduce`, `metaRewrite`, `metaApply` (exact LHS match) vs `metaXapply` (extension, depth-bounded, returns Context); shift levels with `up`/`down` and verify hand-built encodings with them. Because `rew`/`frew` are just default strategies, program your own: strip labeled rules (`[label(Q) A:AttrSet]` matching), read `metadata "..."` tags, enumerate all applications of one law by looping `metaApply(..., N)` + `N + 1` until `(failure).ResultTriple?` — the author's optimization/choice-exhaustion pattern (CIGARETTE-TEST).

**Stand on the standard library** — import `NAT`/`INT`/`FLOAT`/`RAT`, `QID` ('names), `STRING`, `BOOL` (no comparison operators there — define `<`, `<=`, `>=` per sort yourself), `TRIV` (the anything-theory), `META-LEVEL`, `LOOP-MODE` before hand-rolling anything they already provide.

---

## Chapter Index

| # | Title | Key Frameworks |
|---|-------|----------------|
| [ch01](chapters/ch01-foundation.md) | Foundation | modules/sorts/subsorts, prefixes (mixfix), constructors, attributes (assoc/comm/id/idem/iter), kinds, NAT/QID/STRING |
| [ch02](chapters/ch02-functional-modules.md) | Functional Modules | equations, recursion, ceq/mb/cmb, matching conditions, prec/gather/memo/owise, junk/confusion imports, kind-level equations |
| [ch03](chapters/ch03-system-modules.md) | System Modules | rewrite laws, configuration soups, cigarettes/crane examples, rew/frew/continue, search/show path, conditional rules |
| [ch04](chapters/ch04-full-maude-object-oriented-modules.md) | Full Maude & OO Modules | LOOP-MODE, Core-vs-Full, class/subclass, messages, configuration rules, sliding-tile puzzle, safe parsing |
| [ch05](chapters/ch05-parameterization.md) | Parameterization | theories, parameterized modules, views, multiple parameters, parameterized views/theories, survival rules |
| [ch06](chapters/ch06-meta-programming.md) | Meta-Programming | Term/Module encodings, descent functions, up/down, metaApply/metaXapply, internal strategies, grand finale optimizer |
| [ch07](chapters/ch07-exercises-answers.md) | Exercises & Answers | answer nuggets: gather arrows, Oid subsort chains, oth/endoth, meta nulls grid, OPPOSITE-DAY meta-surgery |
| [ch08](chapters/ch08-appendix-examples.md) | Appendix: Examples | inventory of all runnable modules incl. NETWORK-SEARCH pathfinding and the full CIGARETTE-TEST |

## Topic Index

- **ad-hoc overloading** → ch02
- **assoc / comm / id: / idem / iter** → ch01, ch02
- **canonical form** → ch02
- **class / subclass / encapsulation** → ch04
- **configuration rewriting** → ch03, ch04
- **connected component** → ch01
- **constructor [ctor]** → ch01, ch02
- **context (meta)** → ch06
- **crl / conditional rules (incl. rewrite conditions)** → ch03
- **descent functions** → ch06
- **equations (eq / ceq)** → ch02
- **error terms / kinds** → ch01, ch02, ch07
- **fmod / mod / omod** → ch01
- **Full Maude** → ch01, ch04, ch07
- **gather (e E &) / prec** → ch02, ch07
- **graph / network parameterization example** → ch05, ch08
- **if_then_else_fi** → ch02
- **junk / confusion / imports** → ch01, ch02
- **labels / metadata**: statement attributes → ch06
- **LOOP-MODE** → ch04
- **matching condition (:=)** → ch02
- **membership axiom (mb / cmb)** → ch02
- **memo** → ch02
- **message (msg / Msg / Oid)** → ch04
- **metaApply / metaXapply** → ch06
- **META-LEVEL / META-TERM / META-MODULE** → ch06
- **mixfix notation** → ch01
- **NAT / INT / QID / STRING / BOOL** → ch01, ch02
- **owise** → ch02
- **parameterized module / theory / view** → ch05, ch07
- **pattern search (search =>+ / =>!, show path)** → ch03, ch07
- **peano notation** → ch01, ch02
- **recursion strategies** → ch02
- **rew / frew / continue** → ch03
- **rewrite law (rl)** → ch03
- **strategies (internal)** → ch06
- **subsort / substitution-overloading** → ch01, ch02
- **Substitution (meta)** → ch06
- **system module (mod)** → ch03
- **TRIV / oth-endoth** → ch05, ch07
- **up / down (reflection)** → ch06
- **variables (var / vars / on-the-fly)** → ch01, ch02

## Supporting Files

- [glossary.md](glossary.md) — every significant term, alphabetical, chapter-tagged
- [patterns.md](patterns.md) — 17 named techniques (NzSubsort-guard, config-soup, enumeration loop...) with when/how/trade-offs
- [cheatsheet.md](cheatsheet.md) — decision tables (module type, statements, flags, meta nulls) and termination/parse smells
- Source PDF: `/home/juanrh/systems/maude/manuals/maude-primer.pdf` — the origin of all citations; the Maude 2.0 Manual (same folder) covers everything this primer deliberately skips

---

## Scope & Limits

This skill covers the primer's content only: Maude 2.0 as of 2003, in the author's deliberately non-mathematical register. It does not cover the Maude 3.x changes, model checking (LTL), the full attribute list, or the manual's deeper theory — for those, pair this skill with the `Maude3.5.1-manual.pdf` in the same directory. Full Maude's "flimsy" parsing and SRI-era syntax are quoted as-is; verify against your Maude binary version when code is run.
