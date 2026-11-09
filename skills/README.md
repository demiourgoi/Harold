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
