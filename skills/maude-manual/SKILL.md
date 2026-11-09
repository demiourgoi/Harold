---
name: maude-manual
description: "Knowledge base from \"Maude Manual (Version 3.5.1)\" by Manuel Clavel, Francisco Durán, Steven Eker, Santiago Escobar, Patrick Lincoln, Narciso Martí-Oliet, José Meseguer, Rubén Rubio, and Carolyn Talcott (July 2025). Use when writing, debugging, verifying, or explaining Maude (rewriting-logic) code: functional/system/object-oriented/strategy modules, sorts-kinds-preregularity, equational attributes, module algebra (imports, renaming, theories, views, parameterization), search/rewrite strategies, unification/variants/narrowing, LTL model checking, reflection and META-LEVEL, predefined data modules, external objects and IO, or any Maude command, attribute, or trap."
---

<!-- argument-hint: [topic, framework name, command, or chapter number] -->

# Maude Manual (Version 3.5.1)
**Author**: Clavel, Durán, Eker, Escobar, Lincoln, Martí-Oliet, Meseguer, Rubio, Talcott (SRI International / UPM) | **Pages**: ~612 | **Chapters**: 21 + 2 appendices | **Generated**: 2026-11-09

## How to Use This Skill

- **Without arguments** — load the core frameworks below for reference.
- **With a topic** (`unification`, `strategies`, `assoc`, `smodelCheck`, `erewrite`) — I find the chapter via the Topic Index and read that chapter file first.
- **With a chapter** (`ch07`, `ch21`) — I load that specific chapter file.
- **Browse** — ask "what chapters do you have?" for the full index.

External-facing questions get answered from the relevant chapter; this file is the map plus the load-bearing ideas.

---

## Core Frameworks & Mental Models

**Programs are theories; computations are deductions.** A functional module `fmod` is a theory `(Σ, E ∪ A)` in membership equational logic denoting the initial algebra `T_Σ/E∪A`; a system module `mod` is a rewrite theory `R = (Σ, E ∪ A, ϕ, R)` whose initial model is a labeled transition system of *truly concurrent* computations. The interpreter computes in the canonical term algebra — agreeing with the math **iff** executable equations are Church-Rosser + terminating modulo A (admissibility) and rules are **coherent** with the equations (simplify-then-rewrite loses nothing). These executability assumptions are the user's proof obligations (MTT/CRC/SCC/ChC check them); Maude never checks at runtime.

**Equations vs rules.** Equations (`eq/ceq`) compute data deterministically (oriented left-to-right); rules (`rl/crl`) are concurrent local transitions with no determinism/confluence assumed. Never write an axiom like commutativity as an equation (infinite loops) — declare it as a `comm` attribute and let Maude match modulo A with extension-aware Ax-matching. `owise` catch-alls desugar to `enabled_f` conditionals; `strat(...)` makes operators per-operator eager/lazy.

**Sorts, kinds, partiality.** Subsort orders partition into connected components = kinds = error supersorts; terms at kind level without a sort are undefined/error data. Preregularity (unique least sorts, modulo attributes) is assumed and warned. Partiality = declare at kind (`op _;_ : [Path] [Path] -> [Path] .`) or sugar `~>`; memberships (`mb/cmb`) refine sorts, but don't mix memberships with `assoc`/`iter` operators' sort computation (declare kind-level + membership instead).

**Module algebra.** Import modes are semantic claims about the state maps: `protecting` (no junk, no confusion) > `extending` (no confusion) > `generated-by` (no junk) > `including` (no claim); diamond importation resolves strongest-wins. Module expressions: summation `A + B` (fuses; not two `protecting`s), renaming `M * (...)` (propagates to affected submodules, type-canonized to kinds), instantiation `M{V...}` via **views** — interpretations of *theories* (loose interfaces, `TRIV`/`TOSET`/etc.). Parameter labels link parameters across imports; parameterized sorts `Set{X}` qualify by view at instantiation. Views carry unchecked proof obligations.

**Execution surface.** `rew` = one top-fair run; `frew` = one position-fair run; `search [n,m] init arrow pattern such that cond` = breadth-first all-runs (arrows `=>1 =>+ =>* =>! =>#`); `srew/dsrew using α` = strategy-controlled search; `erew` = `frew` + external-event polling (suspend rather than return; needs `<>`-portal). Starvation pathology: `rew` never reaches a rule below the top (`BB-TEST`), so design top-rule shapes deliberately.

**Object-oriented Maude.** `omod` modules desugar into `mod` over `CONFIGURATION` (`< O : C | attrs >`, `__ config multiset`): classes are Cid subsorts, inheritance = subsorting, rules are completed with class variables + attribute-set variables so subclasses inherit behavior; the fair-rewriting attributes are `config`/`object`/`message` with addressee-first messages; object names must be unique per configuration. External objects (files, sockets, processes, timers, meta-interpreters) follow the manager/handle pattern (`fileManager` → `file(N)`); dangerous features are flag-gated (`-allow-files`, `-allow-processes`, `-trust`).

**Strategy language.** A layer *above* rules (module untouched): rule tactics with substitutions (`move[T <- 2]`), combinators `; | * ? :`, `idle/fail`, derived `or-else/+ ! not try test one`, subterm `matchrew by`, tests `match/xmatch/amatch`; named recursive strategies in `smod` (definitions = rewriting-path semantics for importation modes); strategy theories/views instantiate generic algorithms (BACKTRACKING). Extra-variable `[nonexec]` rules become executable here. Internal strategies = equations over META-LEVEL descent functions (generic over modules, global selection, richer outputs).

**Symbolic stack.** 1) `unify` — Ax-unification (A, C, AC, ACU, AU, CU, U, Ul/Ur, `iter`; `idem` excluded): answers describe infinite families; A/AU non-linear cases return incomplete sets *with warnings*. 2) Variants — `[variant]`-tagged equations generate `(canonical form, substitution)` pairs; finite variant property ⇒ finitary complete `variant unify`/`get variants`; irreducibility constraints support protocol reasoning. 3) `vu-narrow` — symbolic reachability: unification instead of matching per step (`[narrowing]` rules), `{fold}/{vfold}` finitize by folding instances, `=>!` demands strong irreducibility.

**Model checking.** Invariants: negation-driven `search` (finite = decision procedure; infinite = semi-decision → bounded `[n,m]` or equational abstraction +G with proven Bool-protection). LTL: M + M-PREDS (`_|=_` equations on parametric `Prop`s) + `modelCheck(init, φ)` — `true` or a labeled `counterexample(prefix, loop)`; `satSolve`/`tautCheck` settle formula sanity; LTL+ adds one path-quantifier layer.

**Reflection.** META-LEVEL metarepresents terms (`'f['t1, 't2]`, `'x:Sort`), modules, views, strategies as data; **descent functions** (`metaReduce`, `metaApply`/metaXapply`, `metaRewrite`, `metaSearch`, `metaSrewrite`, `metaUnify`, `metaGetVariant`, `metaNarrowing*`, `metaCheck`, `metaParse`) implement object-level work natively — the reflective tower stays cheap when every simulation is delegated down. **Meta-interpreters** are external-object interpreters with module databases — stateful, interactive, arbitrarily nested (RUSSIAN-DOLLS).

**Predefined library (Ch 8)** — use it before writing your own: BOOL(+EXT-BOOL), NAT/INT/RAT/FLOAT towers (GMP-backed; machine-int and NAT/{N} modules as dependent types), STRING/QID, conversions, LIST/SET/MAP/ARRAY (+standard views `Nat Int Rat String Qid`, `Nat0 Int0 ...` for DEFAULT; `Nat< ...` for STOSET); RANDOM/COUNTER for stateful stochastic rewriting.

**Debugging discipline.** Trace selectively (`trace select label`), color strangeness (`set print color on`), break by label, single-step with `where/step`, profile before optimizing; know the traps chapter: assoc+idem silently ignored, collapse-theory matches, bare-variable LHS nonterminating, one-sided identities' surprising matches.

---

## Chapter Index

| # | File | Title | Key frameworks |
|---|---|---|---|
| 1 | [ch01-introduction.md](chapters/ch01-introduction.md) | Introduction | theory-as-program, initial models, agreement theorem, soup rewriting |
| 2 | [ch02-using-maude.md](chapters/ch02-using-maude.md) | Using Maude | sessions, load/in, prelude, current module |
| 3 | [ch03-syntax-parsing.md](chapters/ch03-syntax-parsing.md) | Syntax and Basic Parsing | identifiers, mixfix, kinds, prec/gather, extended signature |
| 4 | [ch04-functional-modules.md](chapters/ch04-functional-modules.md) | Functional Modules | eq/ceq, memberships, attributes, owise, strat, memo, admissibility, matching modulo A |
| 5 | [ch05-system-modules.md](chapters/ch05-system-modules.md) | System Modules | rl/crl, coherence, rewrite/frewrite/search |
| 6 | [ch06-object-oriented-modules.md](chapters/ch06-object-oriented-modules.md) | Object-Oriented Modules | classes, inheritance, fair rewriting, desugaring |
| 7 | [ch07-module-operations.md](chapters/ch07-module-operations.md) | Module Operations | imports modes, +, renamings, theories/views, parameterization |
| 8 | [ch08-predefined-modules.md](chapters/ch08-predefined-modules.md) | Predefined Data Modules | numbers, strings, containers, maps/arrays, standard views |
| 9 | [ch09-external-objects-io.md](chapters/ch09-external-objects-io.md) | External Objects and IO | portals, erewrite, streams/files/sockets/processes/time |
| 10 | [ch10-strategy-language.md](chapters/ch10-strategy-language.md) | Strategy Language | combinators, smod, matchrew, parameterization, dsrew |
| 11 | [ch11-invariant-model-checking.md](chapters/ch11-invariant-model-checking.md) | Invariants via Search | negation search, bounded MC, abstraction +G |
| 12 | [ch12-ltl-model-checking.md](chapters/ch12-ltl-model-checking.md) | LTL Model Checking | LTL framework, SMC, counterexamples, LTL+ |
| 13 | [ch13-unification.md](chapters/ch13-unification.md) | Unification | Ax-unification, supported axioms, completeness warnings |
| 14 | [ch14-variants.md](chapters/ch14-variants.md) | Variants | variant attribute, FVP, variant unify/match |
| 15 | [ch15-narrowing.md](chapters/ch15-narrowing.md) | Narrowing | vu-narrow, fold/vfold, symbolic reachability |
| 16 | [ch16-smt-solving.md](chapters/ch16-smt-solving.md) | SMT Solving | check, BOOLEAN/INTEGER/REAL modules |
| 17 | [ch17-reflection-meta-level.md](chapters/ch17-reflection-meta-level.md) | Reflection & META-LEVEL | metarepresentations, descent functions, internal strategies |
| 18 | [ch18-user-interfaces.md](chapters/ch18-user-interfaces.md) | User Interfaces | metaparse dispatch, bubbles, MINI-MAUDE, LOOP-MODE |
| 19 | [ch19-meta-interpreters.md](chapters/ch19-meta-interpreters.md) | Meta-interpreters | interpreter API, Russian dolls, environments |
| 20 | [ch20-latex-support.md](chapters/ch20-latex-support.md) | LaTeX Support | -latex-log, maude.sty, [latex(...)] attribute |
| 21 | [ch21-debugging.md](chapters/ch21-debugging.md) | Debugging & Troubleshooting | tracing, coloring, debugger, profiler, traps |
| A | [ch22-commands.md](chapters/ch22-commands.md) | Appendix A: All Commands | flags + command families |
| B | [ch23-grammar.md](chapters/ch23-grammar.md) | Appendix B: Maude Grammar | BNF, precedence, synonyms |

## Topic Index

- **admissible modules** → ch04, ch05 • **ambiguity / prec / gather** → ch03
- **assoc / comm / id attributes** → ch04, ch13 • **attributes catalogue** → ch04 (op), ch08
- **bounded model checking** → ch11 • **bubbles / DSLs** → ch18
- **coherence / executability** → ch05, ch11 (tools) • **counterexamples** → ch12
- **erewrite / external objects** → ch09 • **glossary** → [glossary.md](glossary.md)
- **importation modes / diamond** → ch07 • **initial algebra / initial model** → ch01, ch04, ch05
- **kinds / partiality** → ch03, ch05 • **LOOP-MODE** → ch18
- **matching equations / t := t'** → ch04 • **memberships** → ch04, ch21 (traps)
- **object-oriented (classes, messages)** → ch06 • **owise** → ch04
- **patterns (M-pattern)** → ch04 • **patterns (program design)** → [patterns.md](patterns.md)
- **predefined modules/views** → ch08 • **preregularity** → ch03, ch21
- **renaming / summation** → ch07 • **sufficient completeness / SCC** → ch04, ch11
- **strategies** → ch10, ch17 (internal) • **strat attribute** → ch04
- **symbolic reasoning** → ch13 (unify), ch14 (variants), ch15 (narrowing)
- **smt** → ch16 • **term coloring / trace / debugger / profiler** → ch21
- **theories / views / parameterized modules** → ch07, ch10 (sth)
- **traps / known problems** → ch21 • **unification / irredundant** → ch13
- **vu-narrow / fold** → ch15 • **search command** → ch05, ch11

## Supporting Files

- [glossary.md](glossary.md) — all key terms with definitions and chapter pointers
- [patterns.md](patterns.md) — recurring design techniques (soups, symbolic tiers, accumulator-builders...) with when/how/trade-offs
- [cheatsheet.md](cheatsheet.md) — decision tables: module kinds, execution commands, unification-tier selection, smells → probes
- Full text: `/tmp/book_skill_work-maude351/full_text.txt` (session-extraction copy; may have been cleaned up) — the original PDF is `Maude3.5.1-manual.pdf` in this repository

## Scope & Limits

This skill covers the Maude 3.5.1 manual's content (all 21 chapters + both appendices). Bibliography, subject/module/view indexes are not chapter-ified (noted in ch23 where relevant). For full-formal-tools documentation (ITP, MTT internals), it points to their external docs. Combine with your project context when writing applications; for the 2.x-era pedagogy, see the sibling `maude-primer` skill.
