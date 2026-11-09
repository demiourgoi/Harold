# Harold agent skills

## maude-primer

Knowledge base generated from [*Maude 2.0 Primer, Version 1.0*](https://maude.cs.illinois.edu/documentation) (Theodore McCombs, SRI Computer Science Laboratory, August 2003; 137 pp.) via the [book-to-skill](https://github.com/virgiliojr94/book-to-skill.git) converter on 2026-11-09. Technical mode, Docling layout-aware extraction (no fallback).

**Contents**
- `SKILL.md` — 11 core frameworks (module-as-algebra, constructor discipline, equation direction, junk/confusion imports, kinds, state-transition modeling, LOOP-MODE reflection, objects/messages, parameterization lego, meta-level descent functions), chapter index, topic index
- `chapters/` — 8 summaries: ch01 Foundation, ch02 Functional Modules, ch03 System Modules, ch04 Full Maude & Object-Oriented, ch05 Parameterization, ch06 Meta-Programming, ch07 Exercises & Answers, ch08 Appendix inventory
- `glossary.md` (~70 terms), `patterns.md` (17 techniques), `cheatsheet.md` (decision tables + termination/parse smells)
- Total ~113 KB (~28K tokens); files load on demand, so a session only pays for what it opens (SKILL.md ~2.7K unless a chapter is requested).

**Usage**: load `maude-primer` for the core frameworks; ask about a topic (`views`, `kinds`, `search`, `gather`) or a chapter (`ch06`) to pull just that file.

**Origin**: source of truth at `/home/juanrh/systems/maude/manuals/.agents/skills/maude-primer/` (same files copied here); extracted from `/home/juanrh/systems/maude/manuals/maude-primer.pdf`.

**Caveat**: covers Maude 2.0 as of 2003 — verify syntax against `Maude3.5.1-manual.pdf` before running code on a current Maude binary.

## maude-manual

Knowledge base generated from [*Maude Manual (Version 3.5.1)*](https://maude.cs.illinois.edu/documentation) (Clavel, Durán, Eker, Escobar, Lincoln, Martí-Oliet, Meseguer, Rubio & Talcott; SRI International, July 2025; 612 pp.) via the [book-to-skill](https://github.com/virgiliojr94/book-to-skill.git) converter on 2026-11-09. Technical mode, Docling layout-aware extraction (no fallback).

**Contents**
- `SKILL.md` — core frameworks (programs-as-theories; the executability contract: Church-Rosser + termination + coherence; equations vs rules; sorts/kinds/preregularity; module algebra: importation modes, summation, renaming, theories/views/parameterization; the symbolic reasoning stack unification → variants → narrowing; invariant and LTL model checking; reflection with META-LEVEL descent functions; object-oriented desugaring and fair rewriting; strategies; predefined data library), chapter index, topic index
- `chapters/` — 23 summaries: ch01 Introduction, ch02 Using Maude, ch03 Syntax and Basic Parsing, ch04 Functional Modules, ch05 System Modules, ch06 Object-Oriented Modules, ch07 Module Operations, ch08 Predefined Data Modules, ch09 External Objects and IO, ch10 Strategy Language, ch11 Invariants through Search, ch12 LTL Model Checking, ch13 Unification, ch14 Variants, ch15 Narrowing, ch16 SMT Solving, ch17 Reflection & META-LEVEL, ch18 User Interfaces, ch19 Meta-interpreters, ch20 LaTeX Support, ch21 Debugging, ch22 Appendix A (command reference), ch23 Appendix B (grammar)
- `glossary.md` (~60 terms), `patterns.md` (13 design techniques), `cheatsheet.md` (module-kind / execution-command / unification-tier decision tables + smells→probes)
- Total ~273 KB (~70K tokens); files load on demand, so a session only pays for what it opens (SKILL.md ~3.4K unless a chapter is requested).

**Usage**: load `maude-manual` for the core frameworks; ask about a topic (`variant unification`, `coherence`, `dsrewrite`, `erewrite`) or a chapter (`ch07`) to pull just that file. Companion to `maude-primer`: the primer gives the 2.0-era pedagogy, this covers the current 3.5.1 language in full.

**Origin**: source of truth at `/home/juanrh/systems/maude/manuals/.agents/skills/maude-manual/` (same files copied here); extracted from `/home/juanrh/systems/maude/manuals/Maude3.5.1-manual.pdf`.

**Caveat**: chapter files are synthesized summaries, not the manual's text — for exact spellings trust ch22 (Appendix A commands) / ch23 (Appendix B grammar) and grep the PDF for page-level depth they omit. Bibliography and the subject/module/view indexes are not chapter-ified. Docling dropped some cells from Appendix A's wide command tables; ch22 reconstructs those families from the section prose.
