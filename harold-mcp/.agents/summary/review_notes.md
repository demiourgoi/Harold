# Review Notes

<!-- tags: review, consistency, completeness, gaps -->

Findings from the consistency and completeness review (2026-09-29, after the
heuristic-linter port landed without a knowledge-base refresh; the
`port-linter.py/summary.md` follow-up asked for this refresh). Older resolved issues are
kept for the record.

## Changes absorbed into this refresh

- New `harold_mcp.diagnostics` package — provider seam (`DiagnosticProvider` protocol,
  `SourceFile`/`ProviderDiagnostic`/`FixSuggestion` values, `DiagnosticsError`
  vocabulary) and the all-or-nothing aggregator (`collect_diagnostics`,
  `DiagnosticCollectionError`). Documented in `docs/modules.md` and tested by
  `test_diagnostics_seam.py` / `test_diagnostics_aggregate.py`.
- New `harold_mcp.heuristic` package — masked lexical layer, declaration index, the
  seven-rule registry, the generated prelude snapshot, and the
  `harold-update-prelude-sorts` CLI. Documented in `docs/modules.md` and covered by the
  `test_heuristic_*.py` unit tests plus per-rule integration fixtures.
- `maude/provider.py` — `InterpreterDiagnosticProvider`, the v1 behavior moved behind the
  seam; worker errors are wrapped as `DiagnosticProviderError` with the cause chained.
- Tool schema (breaking for exhaustive clients): `source`, `code`, optional report-only
  `fix`, exact columns for heuristic findings, `info` severity and summary count;
  `success` = no `warning`/`error`; deterministic ordering. `README.md` and the tool
  docstring describe the new contract.
- Error vocabulary: `MaudeFileNotFoundError` removed; the tool's input error is
  `SourceFileNotFoundError` and provider failures surface as `DiagnosticCollectionError`.
  Recorded in `CHANGELOG.md` `[0.0.5]` (the diagnostics layer is deliberately independent
  of `MaudeError`).
- Release bookkeeping: `pyproject.toml` bumped to `0.0.5.dev0`, `[0.0.5]` changelog
  section, `harold-update-prelude-sorts` console script, prelude-snapshot procedure in
  `DEVELOPER_GUIDE.md`, and the `update-changelog-for-release` agent skill.
- New planning record `.agents/planning/port-maude_eval.py/` (research only; paused at
  the decision point — no code changed for it).
- License changed from Apache-2.0 to GNU GPL v2 (project-level, no code impact).
- Inconsistencies resolved: `AGENTS.md` still described the single-source v1 tool (now
  refreshed); the v1 planning docs still show the old tool schema and
  `MaudeFileNotFoundError` (the `port-linter.py` design supersedes them — this knowledge
  base, not the v1 plan, is the source of truth for the current contract).

## Resolved issues (historical)

- `pyproject.toml` description, CI location, `pre-commit` removal, `CONTRIBUTING.md`
  renumbering, Makefile `release` target, `logging.py` cleanup, `keywords` — all fixed in
  the initial generation.
- `harold_mcp.maude` rework and tests — superseded by the worker-process architecture
  (the old in-process `MaudeRuntime` no longer exists).
- `greet` tool placeholder — removed in v1 of the diagnostics tool.
- `server.py` untested — now covered by `tests/integration/test_lifespan.py` and the MCP
  smoke test in `tests/integration/test_diagnostics_integration.py`.
- Docs rendered only two modules — `docs/modules.md` now lists every application module.
- `broken-*.maude` fixtures unused — now exercised by integration tests.
- Stale `AGENTS.md` Custom Instructions note ("none of the MCP tools described above are
  implemented yet") — removed manually after an earlier review flagged it.

## Remaining issues

1. **The synthesized `error` path has no end-to-end test.** `ok=False` only occurs for
   missing/unreadable files (pre-checked away by the tool) — empirically `maude.load`
   recovers from every parseable input. The path is unit-tested with a mocked worker
   result; acceptable, but worth knowing it can only fire via TOCTOU races. The paused
   `port-maude_eval.py` project has a probe (P1) to decide whether a real hard-failure
   signal exists (`getCurrentModule()`).
2. **Hard-kill orphan window.** A `kill -9` of the server skips the lifespan, so workers
   exit on their own via the queue pipe rather than being killed; a worker mid-`maude.load`
   lingers until the task finishes. `prctl(PR_SET_PDEATHSIG)` in the worker initializer
   would close the gap (future hardening).
3. **The FastMCP stdio exit hang workaround relies on `os._exit`.** FastMCP 3.4.7 leaves a
   non-daemon stdin-reader thread; if a future FastMCP release fixes that, the
   `os._exit(0)` in `server.run()` could be dropped in favor of a normal exit.
4. **`README.md` env-var table is hand-maintained.** It duplicates the `Settings` defaults;
   keep it in sync when settings change.
5. **`scala-issue.md` documents a different codebase.** The SIGSEGV/throughput analysis
   is about the Scala/Java Maude bindings (a related project), not `harold-mcp`'s Python
   bindings. Useful background for the SIGSEGV story; consider annotating it as such.
6. **Tool tags don't reach clients yet.** With mcp SDK 1.29 (spec 2025-06-18) FastMCP
   tags are server-side only — they drive `mcp.enable`/`mcp.disable` but are not in the
   wire format (the smoke test deliberately does not assert them). Once the SDK/protocol
   revision serializes tool tags, the vocabulary is already in place (`server/tags.py`),
   and the smoke test can start asserting `tools[0]["tags"]`.
7. **Heuristic rules are line-oriented and empirically tuned.** Known limitations are
   documented in `port-linter.py/design/detailed-design.md` Appendix D: rules 2–3 fire on
   any `when`/`--` on a non-declaration code line, so a program that declares and *uses*
   an operator named `when` is still flagged (pinned by a unit test — a future refinement
   is a deliberate, visible change); multi-line statements are only partially examined;
   `True`/`False` are silenced by the ported lowercased keyword list; bracket/attribute
   spans other than labels are not masked; messages are English-only. The linter has no
   `error` severity by design (parse errors come from the interpreter).
8. **Prelude snapshot drift.** The snapshot is only as fresh as its last regeneration;
   `harold-update-prelude-sorts --check` is the signal after a Maude upgrade. Theory
   sorts are intentionally excluded, so `sort Elt .` is not reported (a theory-sort rule
   would be new work, not a snapshot change).
9. **Breaking error-vocabulary change for scripting clients.** Pre-0.0.5 callers that
   caught `MaudeFileNotFoundError` or `MaudeWorkerCrashedError` at the tool boundary must
   catch `SourceFileNotFoundError` / `DiagnosticCollectionError` instead (the Maude error
   stays reachable as the chained cause). Pre-1.0 API churn, recorded in `CHANGELOG.md`.

## Completeness gaps

1. **Only the diagnostics tool exists.** The planned run-Maude-programs and documentation
   RAG tools are not implemented yet (`_run_task` and the worker op pattern are the
   extension points; the provider seam is the diagnostics-tool extension point). Their
   tag constants (`INTERPRETER`, `DOCS`) are already defined in `server/tags.py` and
   currently unused. The `port-maude_eval.py` research record sketches the term-evaluation
   tool that would seed the interpreter capability.
2. **No timeout integration test.** The timeout mapping is unit-tested; a real hang needs
   a deliberately-stuck worker (`worker.sleep` exists but no slow fixture triggers the
   timeout path end-to-end).
3. **Advisory/`<standard input>` hardening is partial.** ANSI stripping, binary input,
   `skipped:` and `unable to locate file:` formats are pinned; multi-line Maude warning
   messages are not yet exercised (none observed).
4. **The server CLI wiring is untested.** `main.py` (cyclopts app, `serve` subcommand,
   default command) has no dedicated tests; the `__main__` guard is `# pragma: no cover`.
   The snapshot CLI, by contrast, has in-process tests in
   `tests/unit/test_prelude_extract_cli.py`.

## Language-support limitations

- Single language (Python) — no cross-language gaps.
- The `maude` bindings ship no type stubs: mypy uses `ignore_missing_imports`, so
  Maude-side code is effectively untyped beyond explicit boundary narrowing. basedpyright
  runs with all diagnostics off except `reportUnusedCallResult`.

## Recommendations

1. Keep `.agents/planning/` notes in sync with implementations — the diagnostics tool and
   the linter port followed their PDD cycles; future tools should follow the same process
   (the paused `port-maude_eval.py` record lists the probes to resume with).
2. Add real tests as tools are implemented, and keep `docs/modules.md` current.
3. Re-run the codebase-summary process after significant architecture changes so this
   knowledge base does not drift from the code.
