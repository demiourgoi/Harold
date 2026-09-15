# Summary — Porting `improve-rag/improvement/linter.py` into `maude_program_diagnostics`

> Closing document of the PDD cycle for this project (rough idea → requirements → research →
> design → implementation plan). Written 2026-09-15.

## Artifacts

| Artifact | Content |
| --- | --- |
| [`rough-idea.md`](rough-idea.md) | The initial idea: fold the `improve-rag` linter into Harold's diagnostics tool, and find out what it contributes, how the result model changes, and what the right low-level design is |
| [`idea-honing.md`](idea-honing.md) | Requirements Q&A Q1–Q11 (autofix policy, fix payload, tool shape, provider seam, provenance, severity model, prelude-redeclaration rule, `success` semantics, rule scope, snapshot source, definition of done) plus the **design-review decisions (2026-09-15)** D1–D7 and the three structural decisions |
| [`research/linter-py-analysis.md`](research/linter-py-analysis.md) | Deep analysis of `improve-rag/improvement/linter.py`: 6 textual rules, severity semantics, how `repair.py` consumes it, porting-relevant characteristics |
| [`research/harold-diagnostics-pipeline.md`](research/harold-diagnostics-pipeline.md) | How the current tool, worker, executor, models, tests and conventions fit together, and the four surfaces where linting could plug in |
| [`research/integration-options.md`](research/integration-options.md) | Options A/B/C for tool shape, the model changes linting implies, and the open questions that drove the requirements phase |
| [`research/maude-lexical.md`](research/maude-lexical.md) | Empirical Maude 3.5.1 lexical behavior: rule 1's premise is false (non-ASCII is identifier material), what each rule must skip, and a complete probe appendix |
| [`research/prelude-sorts.md`](research/prelude-sorts.md) | Structure of `prelude.maude`, the extraction rules ("only real declarations count"), the sort inventory, and the snapshot/update-script requirements (now marked superseded) |
| [`research/probes/lexical_probe.py`](research/probes/lexical_probe.py) | Re-runnable probes for the masking layer: string literals cannot span lines, `***`/`---`/`--` inside strings are literal, `A'` vs `'when`, quoted ids end at whitespace, `?` in identifiers |
| [`research/probes/extract_prelude_sorts.py`](research/probes/extract_prelude_sorts.py) | Re-runnable validation of the prelude-sort extraction: **164 names from 24 modules, no junk** (99 view mappings, 52 renamings, 8 `none`, 1 theory sort, 2 meta-term tokens excluded) |
| [`design/detailed-design.md`](design/detailed-design.md) | The standalone design: requirements LP1–LP14, architecture (provider seam + aggregator), components (`diagnostics/`, `maude/provider.py`, `heuristic/`), data models, error handling, testing strategy and appendices A–F |
| [`implementation/plan.md`](implementation/plan.md) | Six test-driven steps with a progress checklist, per-step tests, integration notes and demos, plus the Q11 acceptance mapping |

## What was designed

**One tool, two providers.** `maude_program_diagnostics` gains a heuristic linter next to
the Maude interpreter and answers with a merged, attributed diagnostic list:

- a provider seam (`DiagnosticProvider` protocol; `SourceFile`/`ProviderDiagnostic`/
  `FixSuggestion` values) so future Maude linters and static analyses plug in without
  touching the tool;
- the interpreter provider (unchanged v1 behavior, in `harold_mcp/maude/provider.py`) and
  the heuristic provider (pure text, server process, no `maude` import), which own their
  directories like `maude/` does;
- diagnostics that carry `source`, `code`, `severity` (`info`/`warning`/`error`), precise
  columns and spans for heuristic findings, and an optional, **report-only** `fix`
  (description + applyable edits) — the tool still never writes to the file;
- `success` = no `warning`/`error` from any source, with `info`-only results (a shadowed
  prelude sort, non-ASCII punctuation) still succeeding;
- seven rules: the six ported from the source linter with measured false-positive
  hardening (comments, string literals, quoted identifiers, declarations, labels, sort
  allow-lists) plus the new `prelude-sort-redeclared` rule backed by a bundled generated
  snapshot (164 prelude sorts, provenance header, theory sorts excluded) and the
  `harold-update-prelude-sorts` cyclopts console script;
- a diagnostics-layer error vocabulary (`DiagnosticsError` → `SourceFileNotFoundError` for
  the tool's input, `DiagnosticProviderError` for a failed provider,
  `DiagnosticCollectionError` for the aggregation) independent of `MaudeError`, with the
  Maude worker error kept as the chained cause; if any provider fails, the call fails and
  no partial results are returned (MCP has no partial-result semantics).

**Plan shape.** Six steps: (1) seam + aggregator + interpreter provider behind the rewired
tool; (2) heuristic package + code view + rule 1 with fixes; (3) rules 2–4 with the lexical
hardening; (4) rules 5–6 and the declaration index; (5) prelude snapshot + CLI + rule 7 and
the final tool description; (6) documentation, release metadata and the full `make release`
gate. Each step writes its tests first, ends wired end-to-end, and has an explicit demo.

## Next steps

1. Implement following [`implementation/plan.md`](implementation/plan.md) step by step,
   ticking the checklist; the design document is the reference for anything the step text
   summarizes.
2. After the implementation: run the release gate (`make release`), then update
   `CHANGELOG.md` (via the `update-changelog-for-release` skill if preferred) and bump
   `pyproject.toml` to `0.0.5.dev0` (Step 6).
3. Ask the user to re-run the **codebase-summary** skill: the new `diagnostics/` and
   `heuristic/` packages, `maude/provider.py`, the new fixture set and the console script
   all drift from the committed knowledge base (`AGENTS.md`, `.agents/summary/`).
4. Consider follow-ups that the design deliberately left out of scope:
   `improve-rag/improvement/linter.py` still carries its own linter (host-side autofix
   remains there), a `maude_program_lint`-style static-only tool is now cheap to add on the
   same seam, and the known limitations in design Appendix D (multi-line statements,
   `True`/`False`, non-label bracket spans) are candidates for future rule work.

## Points that may deserve further refinement

- **Heuristic precision is empirical.** Rules 2–3 keep the source linter's "any `when`/`--`
  on a code line" detection, so a program that declares *and uses* an operator named `when`
  is still flagged (pinned by a test, Appendix D.7). A future refinement could require the
  token to appear in a `ceq`/`crl`-style condition rather than anywhere on the line.
- **Prelude snapshot drift.** The snapshot is only as fresh as the last regeneration; after
  a Maude upgrade, `harold-update-prelude-sorts --check` is the signal to regenerate.
- **`Elt` and other theory sorts** are intentionally not reported (review D6); if users ask
  for theory-sort shadowing warnings, that is a new rule, not a snapshot change.
- **Error vocabulary changes reach users**: `MaudeFileNotFoundError` disappears (it is now
  `harold_mcp.diagnostics.SourceFileNotFoundError`, raised by `SourceFile.from_path`), so
  the tool's input error is no longer part of the Maude subsystem; a provider failure
  surfaces as `DiagnosticCollectionError` instead of `MaudeWorkerCrashedError`. Both are
  documented in the changelog (Step 6) — pre-1.0 API churn, worth a line in `README.md`'s
  tool entry only if users scripted against the exception types.
