# Implementation Plan — Heuristic linter port into `maude_program_diagnostics`

> Reads with [`../design/detailed-design.md`](../design/detailed-design.md) (the design),
> [`../idea-honing.md`](../idea-honing.md) (requirements Q1–Q11 plus the 2026-09-15
> design-review decisions D1–D7) and [`../research/`](../research/) (findings and probes).
> Every step below assumes those documents are available; they are not summarized here.
> Generated 2026-09-15 (PDD step 7).

## Method

Convert the design into a series of implementation steps that will build each component in
a test-driven manner following agile best practices. Each step must result in a working,
demoable increment of functionality. Prioritize best practices, incremental progress, and
early testing, ensuring no big jumps in complexity at any stage. Make sure that each step
builds on the previous steps, and ends with wiring things together. There should be no
hanging or orphaned code that isn't integrated into a previous step.

Practical consequences:

- **Tests first, in the same step.** For each step, write or extend the failing tests
  listed under *Tests*, then implement until they pass. No step is a "tests only" step and
  no functionality is added without its tests.
- **Every step ends wired end-to-end.** If a step introduces internals, the same step makes
  them reachable through the `maude_program_diagnostics` tool (or, for Step 5's extractor,
  through the CLI that also consumes them).
- **Keep the tool's docstring honest at every step.** It is the MCP tool description; when
  a step adds a field, a rule or a severity meaning, extend the description with it. The
  final wording of design §5.6 is applied in Step 5, once the rule set is complete.
- **Conventions** (see `AGENTS.md` and the design): Python ≥ 3.14, `uv` only; run
  `UV_CACHE_DIR=/tmp/uv-cache make check` and `make test` from a sandbox (plain `make` in a
  normal environment); ruff auto-fix failures fail CI, so run `uv run ruff check` and
  `uv run ruff format` before committing; mypy strict (`disallow_untyped_defs`) and
  basedpyright `reportUnusedCallResult` (mark intentional discards with `_ = ...`);
  `Depends(...)` defaults need `# noqa: B008`; every new module gets a `::: harold_mcp.<mod>`
  entry in `docs/modules.md`; test files must have distinct basenames across
  `tests/unit/` and `tests/integration/`; the server process must never import `maude`.
- **Demo** is what you show (or capture in the PR description) at the end of the step: a
  command and its observable result.

## Progress checklist

- [ ] **Step 1** — Provider seam, aggregation and the interpreter provider behind the tool
- [ ] **Step 2** — Heuristic package, code view, and rule 1 (`non-ascii-character`) with fixes
- [ ] **Step 3** — Rules 2–4 (`when-guard`, `dash-comment`, `eq-in-term`) with lexical hardening
- [ ] **Step 4** — Rules 5–6 (`non-linear-pattern`, `undeclared-identifier`) and the declaration index
- [ ] **Step 5** — Prelude snapshot, `harold-update-prelude-sorts` CLI, and rule 7 (`prelude-sort-redeclared`)
- [ ] **Step 6** — Documentation, release metadata and full acceptance run

## Requirement coverage

| Requirement | Step | Requirement | Step |
| --- | --- | --- | --- |
| LP1 report-only | 1 (annotations), 2 (fix field, file untouched test) | LP8 `success` semantics | 1 (vocabulary), 2 (`info`-only) |
| LP2 fix payload | 2 | LP9 rule scope, hardening | 2, 3, 4, 5 |
| LP3 positions/columns | 1 (adapter), 2 (first spans), 3–5 | LP10 codes/severities | 1 (`compiler`), 2–5 (per rule) |
| LP4 one composite tool, failure semantics | 1 | LP11 prelude snapshot + CLI | 5 |
| LP5 provider seam | 1, 2 | LP12 deterministic order | 1 (sort key), 2 (both providers) |
| LP6 provenance | 1 (`source`/`code`), 2–5 (per rule) | LP13 docs and hygiene | every step, gate in 6 |
| LP7 severity model | 1 (vocabulary/summary), 2 (`info` producer) | LP14 non-goals | respected throughout |

---

## Step 1 — Provider seam, aggregation and the interpreter provider behind the tool

**Objective.** `maude_program_diagnostics` becomes a provider-based pipeline whose first
provider is the Maude interpreter, and its result gains provenance (`source`, `code`), the
`info` severity and the final result schema — with **no change** in what the interpreter
reports (v1 behavior preserved: same warnings, same synthesized error, same crash recovery).

**Implementation guidance.** Follow design §4.1 (seam), §4.2 (aggregation), §4.3
(interpreter provider), §4.8 (tool/models/adapter), §5.1 (wire models), §6 (errors).

- New `src/harold_mcp/diagnostics/`: `provider.py` (`Severity`, `DiagnosticSource`,
  `SourceFile` — `path: Path` + `text: str`, with its `from_path` reader — `FixEdit`,
  `FixSuggestion`, `ProviderDiagnostic` with its position invariants, `DiagnosticsError`,
  `SourceFileNotFoundError`, `DiagnosticProviderError`, the `DiagnosticProvider`
  protocol), `aggregate.py` (`ProviderFailure`, `DiagnosticCollectionError`,
  `collect_diagnostics` with the LP4 comment, the fixed message format and the stable
  ordering key), `__init__.py` (the surface shown in design §4.0).
- Move the input-file error out of the Maude subsystem: delete `MaudeFileNotFoundError`
  from `src/harold_mcp/maude/executor.py` and from the `harold_mcp/maude/__init__.py`
  exports (it is the diagnostics tool's input error, not an interpreter error; nothing else
  in `src/` uses it).
- New `src/harold_mcp/maude/provider.py`: `InterpreterDiagnosticProvider` including
  `_HARD_FAILURE_MESSAGE` and the `MaudeWorkerError → DiagnosticProviderError(...) from exc`
  translation; re-export it from `harold_mcp/maude/__init__.py`.
- Rewrite `src/harold_mcp/server/tools/diagnostics.py`: models per design §5.1
  (`severity` including `info`, `source`, `code`, `range` with nullable `column`/`end`,
  `fix`/`MaudeFix`/`MaudeTextEdit`, `summary.info`), the generic adapter (`_to_range`,
  fix conversion — write it for spans/fixes now, even though the interpreter only produces
  line-only diagnostics), `success = no warning/error diagnostic`, and the tool flow of
  §4.8 (`source = SourceFile.from_path(path)`, `collect_diagnostics`, provider tuple with
  the interpreter provider only). Keep the annotations/tags exactly as they are (LP1) and
  keep the docstring accurate: it now describes one source, its `code`, and the new fields.
- Use `pathlib` paths in the seam (`SourceFile.path: Path`) and read with
  `Path.read_text(encoding="utf-8", errors="replace")`; the interpreter provider converts at
  the boundary (`str(source.path)`) because `maude.load` and the worker take strings.
- Add the new modules to `docs/modules.md`.
- Do **not** touch `harold_mcp/maude/executor.py`, `worker.py`, `server.py` or the
  settings (design §4.10: untouched).

**Tests.** Write these first:

- `tests/unit/test_diagnostics_seam.py` — `ProviderDiagnostic` position invariants raise
  `ValueError`; `DiagnosticsError` is not a `MaudeError`, and `SourceFileNotFoundError`,
  `DiagnosticProviderError` and `DiagnosticCollectionError` are all `DiagnosticsError`s;
  `SourceFile.from_path` returns a `Path`-backed `SourceFile` for a real file, raises
  `SourceFileNotFoundError` for a missing path, a directory, a non-regular file and an
  unreadable one (chmod 000, skipped as root), decodes undecodable bytes lossily, and
  normalizes CRLF to physical `\n` lines; `FixEdit`/`FixSuggestion` shapes.
- `tests/unit/test_maude_provider.py` — warning mapping (`warning`, `compiler`, line,
  `column=None`), synthesized `error` on `ok=False`, `MaudeWorkerError` becomes a
  `DiagnosticProviderError` whose `__cause__` is the worker error.
- `tests/unit/test_diagnostics_aggregate.py` — ordering (line, provider index, whole-file
  last), provenance preserved, one and two failing providers → `DiagnosticCollectionError`
  naming each provider with its cause, **no partial results**, chained cause, an unexpected
  exception is reported rather than swallowed.
- Rewrite `tests/unit/test_diagnostics.py` — tool with `FakeMaudeExecutor`: tri-state
  mapping, `source`/`code` on every diagnostic, `fix is None`, `summary.info == 0`,
  `success` semantics, missing/unreadable file raise `SourceFileNotFoundError` before any
  provider is called, aggregate error propagates; adapter coverage for spans and fixes
  using synthetic provider diagnostics (so the machinery that Step 2 relies on is already
  tested).
- Extend `tests/integration/test_diagnostics_integration.py` — the existing expectations
  gain `source == "interpreter"` / `code == "compiler"`; the binary-file regression keeps
  passing; `test_tool_reports_crash_and_recovers` now asserts `DiagnosticCollectionError`
  whose message names `interpreter` and the crash cause, then that the next call recovers;
  the MCP smoke test asserts the new schema fields (`source`, `code`, `summary.info`).

**Integration.** This step introduces the seam the whole port hangs from; the tool already
uses it, so nothing is orphaned. The interpreter provider replaces the previous inline
mapping (the `ok`/`warnings` tri-state logic moves into it), and the old
`_build_result`/`_range_for_line` helpers disappear.

**Demo.** `UV_CACHE_DIR=/tmp/uv-cache make test` is green, and the MCP smoke path shows:

- `broken-recoverable.maude` → one diagnostic with `"source": "interpreter"`,
  `"code": "compiler"`, `"severity": "warning"`, `"fix": null`, `success=false`,
  `summary = {info: 0, warning: 1, error: 0}`;
- `hello.maude` → `success=true`, no diagnostics;
- a crashed worker → the tool fails with
  `Diagnostics failed: interpreter (Maude worker crashed)`, and the following call succeeds.

---

## Step 2 — Heuristic package, code view, and rule 1 (`non-ascii-character`) with fixes

**Objective.** The heuristic linter exists as its own package behind the same seam, running
in the server process, and the tool returns `heuristic-linter` diagnostics: one `info` per
offending non-ASCII character, with a precise span and an applyable fix — while never
writing to the file.

**Implementation guidance.** Follow design §4.4 (lexical layer), §4.6 (rules: registry,
rule 1, messages), §4.7 (provider), §5.4 (ordering).

- New `src/harold_mcp/heuristic/`: `lexical.py` (`CodeLine`, `code_view` masking comments
  (`***`/`---`) and **string literals** — length-preserving, so columns map 1:1),
  `rules.py` (`RuleFinding`, `Rule`, `RULES` with only rule 1 for now, `UNICODE_FIXES`
  ported verbatim, the rule-1 message), `provider.py` (`HeuristicLinterProvider` with the
  injectable registry), `__init__.py`.
- Rule 1 details: per-occurrence diagnostics, span = the character, fix = one `FixEdit`
  when the character is in `UNICODE_FIXES`, and **no finding for U+FFFD** (lossy-decode
  artifact, design §6).
- Tool: add `HeuristicLinterProvider()` to the provider tuple (interpreter first,
  heuristic second) and let the adapter populate `fix`; `success` now also drops to `false`
  for heuristic `warning`/`error` (no such rule yet, so only `info` appears).
- Add `docs/modules.md` entries.
- Leave the quoted-identifier and statement-label masks for Steps 3–4, where their rules
  arrive (each mask lands with the failing test that needs it).

**Tests.** Write these first:

- `tests/unit/test_heuristic_lexical.py` — comment masking (trailing `***`/`---`, text
  after a marker dropped) and string masking (including `***`, `---`, `--` and non-ASCII
  inside a string); every masked line keeps the original length so a character's index
  equals its 1-based column.
- `tests/unit/test_heuristic_rules.py` — rule 1 positive: line, exact `column`/`end_column`
  span, `info`, message naming the character, `fix.description` and one edit with exclusive
  end; negatives: ASCII-only input, non-ASCII inside a string literal, a non-ASCII
  character with no substitution (finding without `fix`), U+FFFD (no finding).
- `tests/unit/test_heuristic_provider.py` — stamping `source`/`code`/`severity` from the
  registry, a custom rule subset, idempotence over the same text.
- Extend `tests/unit/test_diagnostics.py` — `fix` mapping (`MaudeTextEdit` with exclusive
  `range.end`), `info`-only ⇒ `success=true`, same-line ordering (interpreter first), and
  the diagnosed file is byte-identical after a call that returned fixes.
- Extend `tests/integration/test_diagnostics_integration.py` with the new fixtures
  `nonascii_apostrophe.maude` (1 `info` with a 1-char fix, interpreter silent,
  `success=true`) and `string_with_specials.maude` (clean, no diagnostics at all).

**Integration.** Depends on Step 1's seam, adapter and `SourceFile` (the tool already reads
the text lossily). It is the first producer of `info` diagnostics and of `fix` payloads, so
it completes the parts of the model that Step 1 only declared.

**Demo.** `maude_program_diagnostics` on `nonascii_apostrophe.maude` returns
`success=true` plus one diagnostic: `source="heuristic-linter"`, `code="non-ascii-character"`,
`severity="info"`, a span with both columns, and a fix whose single edit is
`{"range": …, "new_text": "'"}`; applying that edit by hand turns the file into ASCII and a
second call reports nothing. `string_with_specials.maude` reports nothing.

---

## Step 3 — Rules 2–4 (`when-guard`, `dash-comment`, `eq-in-term`) with lexical hardening

**Objective.** The three heuristics for mistakes Maude reports only as terse parse errors
become `warning` diagnostics, with the Q9(b) hardening: silence inside string literals,
quoted identifiers, declaration lines and statement labels.

**Implementation guidance.** Follow design §4.6 (rules 2–4, messages, "declaration line"
definition) and §4.4 (masking table).

- Extend `code_view` with **quoted-identifier masking** (a `'` at a token boundary — i.e.
  not preceded by identifier material — masks to the next whitespace) and **statement-label
  masking** (the `[...]` slot after `eq`/`ceq`/`rl`/`crl`); both grounded in the probes in
  `../research/probes/lexical_probe.py` and Appendix B of the design.
- Add rules 2–4 to `RULES`: whole-word `when` (skip declaration lines), `--` with the
  source linter's boundary regex `(^|\s)--(?!-)(\s|$)` in the code view (skip declaration
  lines), and every lone `=` inside an `if … then` span with the source linter's
  context exclusions. One finding per occurrence, spans on the offending token.
- Keep the tool description in sync (three more codes, and the note that heuristic findings
  may be false positives).

**Tests.** Write these first:

- Extend `tests/unit/test_heuristic_lexical.py` — quoted-identifier masking (`'when`,
  `'--`, `'a b`) and that `A'`/`A'b` stay identifier material; label masking
  (`eq [Rewrite] : …` leaves no capitalised token behind).
- Extend `tests/unit/test_heuristic_rules.py` — positives with exact spans for rules 2–4,
  per-occurrence behaviour, and negatives: `when`/`--`/`=` inside strings and quoted
  identifiers, `op when`/`op _--_`/`var when` on declaration lines, a label; plus the
  documented false positive pinned as an assertion (`eq when(B) = B .` fires `when-guard`,
  Appendix D.7).
- Integration fixtures and assertions: `when_guard.maude` (adapted from improve-rag
  `repeated.maude`), `dash_comment.maude` (adapted from `simple-list.maude`, without the
  U+2019 name so it isolates rule 3), `eq_in_if.maude` (research appendix), plus the
  negatives `quoted_id_when_dash.maude` and `declarations_when_dash.maude` (declaration
  lines only) — each with its heuristic and interpreter expectations from design §7.2.

**Integration.** Builds on Step 2's package, registry and masking infrastructure; the new
`warning`-severity findings now make `success=false` from the heuristic source alone, which
the fixtures assert.

**Demo.** The tool on the three adapted improve-rag fixtures reports the corresponding
`warning` (with exact columns) alongside the interpreter's own warnings, with
`success=false`; on `quoted_id_when_dash.maude` and `declarations_when_dash.maude` a full
run reports no heuristic findings.

---

## Step 4 — Rules 5–6 (`non-linear-pattern`, `undeclared-identifier`) and the declaration index

**Objective.** The ported taxonomy is complete: the two "legal but suspicious" heuristics
fire on real generated-code smells and stay quiet on legitimate Maude.

**Implementation guidance.** Follow design §4.5 (declaration reader), §4.4
(`declaration_index`, `Declarations`, `SourceView` extension), §4.6 (rules 5–6 and their
allow-lists, including `MAUDE_KEYWORDS` kept verbatim and the `sort_bases` /
`sort_references` / `PRELUDE_SORT_BASES` handling — `PRELUDE_SORT_BASES` is wired in Step 5,
so for now the allow-list is `variables ∪ operators ∪ sort_bases ∪ sort_references ∪
MAUDE_KEYWORDS`).

- New `src/harold_mcp/heuristic/declarations.py` (`SortDeclaration`,
  `iter_sort_declarations`): module/view tracking (including `view … is endv` on one line),
  multi-line `sorts` statements, the sort-name shape check (`?` is identifier material),
  and the exclusions (view bodies, ` to ` mappings, theory bodies, `none`). Rule 6 consumes
  it here (`sort_bases`), rule 7 in Step 5.
- Extend `lexical.py` with `declaration_index` and `SourceView.from_text` carrying
  `sort_declarations`/`declarations` and the `sort_bases` property.
- Add rules 5 and 6: LHS token counts for declared variables (first-occurrence span,
  one finding per repeated variable); capitalised-token check with per-token-per-line
  deduplication in column order.
- Add `docs/modules.md` entry for `declarations.py`.

**Tests.** Write these first:

- `tests/unit/test_heuristic_declarations.py` — parameterised module headers, multi-line
  statements, inline `endv`, view bodies and `sort X to Y` mappings excluded, theory bodies
  excluded (`Elt` absent), `sorts none .` and the `endsth)` meta-term junk excluded,
  `?`-suffixed names accepted, and `name`/`line`/`column`/`module` values.
- Extend `tests/unit/test_heuristic_lexical.py` — `declaration_index`
  (`vars`/inline `X:Sort`/`ops` names/sort references) and `SourceView.sort_bases`.
- Extend `tests/unit/test_heuristic_rules.py` — positives for rules 5–6 (spans,
  deduplication, column order), and negatives: declared variables/ops/sorts, inline
  `X:List{Nat}` sort references, capitalised labels, `True` silenced by the keyword list
  (documented behaviour, Appendix D.3).
- Integration fixtures and assertions: `non_linear_pattern.maude` (adapted from
  `free-tuples.maude`; interpreter silent, heuristic warning), `undeclared_identifier.maude`,
  `capitalized_identifiers_ok.maude`.

**Integration.** Completes the six ported rules; the registry, the messages and the
code table of design §5.2 are now fully populated except for the Step-5 prelude rule.
`iter_sort_declarations` is already consumed by rule 6, so nothing is left dangling for
Step 5.

**Demo.** `non_linear_pattern.maude` reports `non-linear-pattern` and `success=false` while
the interpreter itself stays silent (the tool now finds a problem Maude does not);
`undeclared_identifier.maude` reports `undeclared-identifier`; `capitalized_identifiers_ok.maude`
reports nothing.

---

## Step 5 — Prelude snapshot, `harold-update-prelude-sorts` CLI, and rule 7

**Objective.** The new `prelude-sort-redeclared` rule reports `info` findings for sorts the
Maude prelude already declares, backed by a bundled generated snapshot whose provenance and
regeneration path are documented — and the tool description reaches its final form.

**Implementation guidance.** Follow design §4.9 (snapshot + CLI), §4.5 (theory exclusion),
§4.6 (rule 7 and its message), §4.10 (docs/packaging rows).

- New `src/harold_mcp/heuristic/prelude_extract.py`: `extract_prelude_sorts` (reusing
  `iter_sort_declarations`), `render_snapshot_module` (provenance header, exploded
  literals with a trailing comma, sorted, plus `PRELUDE_SORT_BASES`), and the cyclopts
  `App` in the style of `src/harold_mcp/main.py` (positional `prelude`, `--output`,
  `--check`, `--maude-version`, the "refuse fewer than 50 names" guard,
  `if __name__ == "__main__": app()`).
- Generate `src/harold_mcp/heuristic/prelude_sorts.py` with that CLI from the installed
  Maude 3.5.1 prelude (`/home/juanrh/systems/maude/Maude-3.5.1-linux-x86_64/prelude.maude`),
  then confirm `--check` reports it up to date. Expect **164 names from 24 modules**, no
  `Elt`, no `none`, no renamed instances — the invariant test pins this.
- Add rule 7 to `RULES` (span = the declared name, message naming the prelude module) and
  wire `PRELUDE_SORT_BASES` into rule 6's allow-list.
- `pyproject.toml`: add `harold-update-prelude-sorts = "harold_mcp.heuristic.prelude_extract:app"`
  to `[project.scripts]`; `docs/modules.md` entries for both new modules.
- Apply the final tool description (design §5.6) and add the "Maintaining the prelude sort
  snapshot" section to `DEVELOPER_GUIDE.md` (when to regenerate after a Maude upgrade, the
  command, `--check`).

**Tests.** Write these first:

- `tests/unit/test_heuristic_prelude.py` — `extract_prelude_sorts` against an inline sample
  prelude that exercises every exclusion rule (views, renamings, ` to `, theory bodies,
  `none`, `endsth)`, multi-line statements, parameterised headers); snapshot invariants
  (`Qid`→`QID`, `Nat`, `List{X}`, `State` present; `Elt` absent; no junk names; > 100
  names; bases ⊆ names modulo parameters).
- `tests/unit/test_prelude_extract_cli.py` — the app in-process with
  `--output <tmp path>`: writes a loadable module, `--check` passes on the fresh result and
  fails on a modified snapshot, a junk extraction (< 50 names) is refused.
- Extend `tests/unit/test_diagnostics.py`/provider tests as needed for `PRELUDE_SORT_BASES`
  participation in rule 6.
- Integration: `redeclare_prelude.maude` → interpreter silent, exactly one
  `heuristic-linter`/`prelude-sort-redeclared`/`info`, `success=true`; new
  `elt_sort_declaration.maude` → no findings; the MCP smoke test asserts the
  `redeclare_prelude.maude` outcome and that the tool description mentions both sources.

**Integration.** Uses the declaration reader from Step 4 (same code path as rule 7, so the
snapshot and the rule can never disagree) and closes the rule table of design §5.2.

**Demo.** `uv run harold-update-prelude-sorts /home/juanrh/systems/maude/Maude-3.5.1-linux-x86_64/prelude.maude --check`
prints that the snapshot is up to date; running it without `--check` reproduces the
committed file (no diff); the MCP call on `redeclare_prelude.maude` returns `success=true`
with the single `info` finding naming module `QID`, and `elt_sort_declaration.maude` returns
nothing.

---

## Step 6 — Documentation, release metadata and full acceptance run

**Objective.** The port is documented, release-ready and validated as a whole; the
knowledge base is flagged for refresh.

**Implementation guidance.** Follow design §4.10 and Q11 items 5–9.

- `README.md`: rewrite the `maude_program_diagnostics` entry — both sources and their
  severity meanings, `info`-only results succeeding, precise columns/spans, report-only
  fixes, ordering.
- `CHANGELOG.md`: new section for the release describing the ported heuristic linter, the
  new rule, the model changes (new fields/values — a breaking change for exhaustive
  clients — and the report-only `fix`), the new console script, and the note that
  `improve-rag/improvement/linter.py` is untouched.
- `pyproject.toml`: bump `version` to `0.0.5.dev0` (design §4.10).
- Re-check `docs/modules.md` completeness and that every new module has a docstring that
  renders under mkdocstrings.
- Run the release gate, then ask the user to (a) re-run the codebase-summary skill so
  `AGENTS.md`/`.agents/summary/` match the new packages, and (b) run the
  `update-changelog-for-release` skill or review the changelog entry before releasing.

**Tests.** No new test code expected (documentation step). The test requirement is the
gate: `UV_CACHE_DIR=/tmp/uv-cache make release` (install + `check` + `test` + `docs-test`)
must pass, which exercises ruff, mypy, basedpyright, deptry, the full suite with coverage
and the strict MkDocs build over the new modules.

**Integration.** Documents and validates everything built in Steps 1–5; this is the step
that makes the change shippable.

**Demo.** `UV_CACHE_DIR=/tmp/uv-cache make release` prints "All CI tests are passing!"; the
README's tool section describes the two sources, the `info` level and the fixes; the
changelog enumerates the user-visible changes; the docs build includes the new packages.

---

## Final acceptance (definition of done, Q11)

1. Tool returns merged diagnostics with `source`, `code`, `severity`, `range`, `message`
   and `fix` where deterministic, and the description explains the sources and their
   severity meanings — Steps 1, 2, 5.
2. `warning`/`error` from either source ⇒ `success=false`; `info`-only ⇒ `true` — Steps 1, 2.
3. Fixture outcomes (clean, recoverable, unrecoverable, `redeclare_prelude.maude`) —
   Steps 1, 5.
4. One positive fixture per rule plus the hardening negatives, including an applyable fix
   with columns — Steps 2, 3, 4, 5.
5. Provider-failure semantics with the explanatory comment and next-call recovery —
   Step 1.
6. Unit and integration tests green; `make release` passes — every step, Step 6.
7. Snapshot provenance + regeneration CLI — Step 5.
8. Repo hygiene (docs, README, CHANGELOG, version, KB refresh prompt) — Steps 1–5 for
   module docs, Step 6 for README/CHANGELOG/version/prompt.
9. Non-goals respected (no separate lint tool, no mutation, improve-rag untouched,
   English-only, line-oriented, no runtime prelude read, no new dependencies) — throughout.
