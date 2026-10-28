# Review Notes

<!-- tags: review, consistency, completeness, gaps -->

Findings from the consistency and completeness review. The 2026-10-28 refresh covers the
`maude_run` interpreter-session tool (new `maude/session.py`, `maude/capture.py`,
`server/tools/interpreter.py`, new settings, tests and docs); the 2026-10-14 refresh covers
the provider-registry FastMCP dependency; the 2026-10-12 refresh covers the
`no_new_module_quirk` implementation (hermetic per-call interpreters, the new workers
default, dependency-warning attribution, path absolutization, and the test-suite rework);
the 2026-09-29 refresh covered the heuristic-linter port. Older resolved issues are kept
for the record.

## Changes absorbed into this refresh (2026-10-28)

- **New `maude_run` tool.** `server/tools/interpreter.py` adds the MCP surface (discriminated
  step union, pydantic result models, validation, adapter, `MaudeRunError`) and
  `maude/session.py` adds the worker-side bounded session engine
  (`reduce`/`rewrite`/`frewrite`/`erewrite`/`match`/`search`, current-term threading,
  per-step `ok`/`parse-error`/`too-large` outcomes, caps, output capture). The tool is
  registered from `tools/__init__.py`, documented in `docs/modules.md`, and described in
  `README.md`; it uses the `INTERPRETER` tag (no longer reserved). Design record:
  `.agents/planning/port-maude_eval.py/` (the code now matches its design and
  implementation plan).
- **Shared capture helper.** `maude/capture.py` now owns the fd-1/fd-2 redirect, ANSI
  stripping, lossy decoding, warning parsing (`WarningDict`) and output truncation.
  `worker.load_diagnostics` uses it to parse stderr only; the diagnostics tool still
  discards stdout. This closes a latent bug where output from a `red` embedded in a loaded
  file could reach the MCP stdio transport.
- **Settings rename and new caps.** `maude_worker_timeout_secs` became
  `diagnostics_timeout_secs` (`HAROLD_DIAGNOSTICS_TIMEOUT_SECS`; the old env var is ignored
  — a pre-1.0 breaking change). New fields: `interpreter_timeout_secs` and the
  `interpreter_max_*` caps for steps, rewrite bound, solutions, term/result/output length.
  `Settings` documentation, `README.md`, `interfaces.md` and `AGENTS.md` were updated.
- **Executor and lifetime.** `MaudeExecutor.run_session(request, timeout)` is the new typed
  worker op alongside `diagnostics`; the lifespan passes
  `settings.diagnostics_timeout_secs` to `start()`. The pool remains shared, fresh per task.
- **Tests and fixtures.** New unit suites `test_maude_capture.py` and
  `test_interpreter_tool.py`; new integration suites `test_maude_session_integration.py`
  and `test_maude_run_integration.py`; 3 new fixtures (`counter.maude`,
  `assoc_match.maude`, `warns_and_prints.maude`), 29 total. `test_maude_worker.py` now
  covers stderr-only warning parsing.
- **Docs and planning.** `docs/modules.md` renders the three new modules; the knowledge
  base adds this material. `port-repair.py/` is a new early planning record (no code yet).
- **Mermaid fix.** The new `maude_run` sequence diagram had semicolons inside message text;
  Mermaid treats `;` as a statement separator, so they were replaced with commas and the
  diagram parses again.

## Changes absorbed into this refresh (2026-10-14)

- **Provider registry as a FastMCP dependency.** `server/tools/diagnostics.py` gained
  `get_diagnostic_providers(maude_executor=Depends(get_maude_executor))`, returning the
  ordered registry `(InterpreterDiagnosticProvider, HeuristicLinterProvider)`; the tool
  now takes `providers: tuple[DiagnosticProvider, ...] = Depends(...)` instead of a
  `maude_executor` parameter and builds nothing inline. The registry order remains the
  merge/tie-break order; unit and integration tests build it with
  `get_diagnostic_providers(maude_executor=<fake>)`.
- **Ordering key extracted.** `diagnostics/aggregate.py`'s sort key moved from a nested
  closure to the module-level `_order(provider_order, diagnostic)`, bound per call with
  `functools.partial`; `fallback_index` collapsed into `len(provider_order)`. Behavior
  unchanged (the ordering tests pin it).
- **Lint nuance found during the review.** Ruff's B008 does not fire on a `Depends(...)`
  default whose parameter is annotated with an immutable generic (`tuple[...]`), so the
  tool's injected `providers` parameter needs no `# noqa: B008`; the
  `get_diagnostic_providers` parameter (`MaudeExecutor`) keeps it. Documented in
  `data_models.md` and `AGENTS.md`.
- **Version bookkeeping.** 0.0.4 was released; `pyproject.toml` is now `0.0.5.dev0` with
  an open (empty) `[0.0.5]` changelog section — `codebase_info.md` updated accordingly.
- Verified unchanged: `workflows.md` (the provider-registry change does not alter any
  documented flow), `maude-lib.md` (manually maintained, still accurate) and the rest of
  this knowledge base apart from the items above and `functools` added to the stdlib list
  in `dependencies.md`.

## Changes absorbed into the 2026-10-12 refresh

- **Hermetic per-call diagnostics.** `maude/executor.py` sets `max_tasks_per_child=1` on
  the pool, so every task runs in a fresh process (no loaded modules or parser state
  survive across calls), fixing the deferred `q .`/`quit .` residue contamination.
  `start()`'s pings are now a fail-fast initialization check (the pinged processes are
  recycled), and the "last load wins" sentence is gone from the tool description, README
  and this knowledge base. Design record: `.agents/planning/no_new_module_quirk/`.
- **`HAROLD_MAUDE_WORKERS` default** — now `max(1, min(3, (os.cpu_count() or 0) // 2))`
  via `Field(default_factory=...)`; it caps concurrent per-call interpreters (≈100 MB
  each), not warm workers. Env override and `gt=0` validation unchanged.
- **Path absolutization** — `SourceFile.from_path` stores `Path.resolve()` (after the
  `is_file()` pre-check), and the tool reports the resolved absolute path instead of
  echoing the raw input; a fresh worker's cwd is not the client's.
- **Dependency-warning attribution** — `WarningDict` gained `file`; the worker regex
  accepts the `(fmod X) :` spelling (its warnings used to be dropped); the interpreter
  provider maps own-file and `<standard input>` warnings to their line and foreign-file
  warnings to whole-file diagnostics naming the dependency and suggesting this tool
  (`_to_diagnostic` / `_dependency_message`).
- **Integration suite rework** — new isolation/race/dependency regression tests and
  9 new fixtures (26 total); the `heuristic_executor` workaround is gone;
  `test_maude_executor_integration.py` keeps only real concurrency (via the
  `rendezvous_pid` marker helper, replacing interval witnesses that flaked under xdist);
  `test_mcp_smoke` kills the server if the graceful SIGTERM exit exceeds 15 s under
  parallel load.
- **Test tooling** — `pytest-xdist` dev dependency; `make test-unit` and
  `make test-integration` (`-n auto`) targets for iteration; `make test` stays the
  authoritative sequential run (CI, `make release`).
- **New manual knowledge-base file** — `maude-lib.md` (added mid-cycle at `b8809cc`)
  documents the `maude` wheel layout, prelude discovery (`MAUDE_LIB` → wheel dir → cwd),
  and prelude availability per recycled worker; it already reflects the per-call
  recycling.
- **New planning record** — `.agents/planning/no_new_module_quirk/` is a complete PDD
  cycle with the `maude-bindings-issue.md` bug report (filed upstream).
- Inconsistencies resolved: `AGENTS.md`'s workers default, executor semantics and tool
  description were refreshed; the tool description's sub-bullet indentation was
  normalized (found during this review, fixed); `README.md`'s env table and tool bullet
  now document the hermetic/whole-load semantics; `CHANGELOG.md` `[0.0.4]` records the
  fix (no separate `0.0.5` section — `0.0.4.dev0` is the WIP release).

## Changes absorbed into the previous refresh (2026-09-29)

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
  Recorded in `CHANGELOG.md` `[0.0.4]` (the diagnostics layer is deliberately independent
  of `MaudeError`).
- Release bookkeeping: `pyproject.toml` bumped to `0.0.4.dev0`, `[0.0.4]` changelog
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
   missing/unreadable files (pre-checked away by the diagnostics tool) — empirically
   `maude.load` recovers from every parseable input. The path is unit-tested with a mocked
   worker result; acceptable, but worth knowing it can only fire via TOCTOU races. The
   `maude_run` path, by contrast, treats `load_ok=False` as a whole-call failure and has a
   real integration test (`test_broken_file_fails_as_a_whole_call`, which currently
   surfaces as "module not defined" because Maude still returns `True` for that fixture).
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
9. **Breaking error-vocabulary change for scripting clients.** Pre-0.0.4 callers that
   caught `MaudeFileNotFoundError` or `MaudeWorkerCrashedError` at the tool boundary must
   catch `SourceFileNotFoundError` / `DiagnosticCollectionError` instead (the Maude error
   stays reachable as the chained cause). Pre-1.0 API churn, recorded in `CHANGELOG.md`.
10. **`maude_run` has no dedicated timeout integration test.** As with the diagnostics
    timeout path, the mapping is unit-tested only; a real non-terminating reduction is the
    documented way to trigger it, but no fixture/CI case does so.

## Completeness gaps

1. **The documentation RAG tool does not exist yet.** Both in-scope tools
   (`maude_program_diagnostics`, `maude_run`) are implemented. The planned vector index is
   not; its tag constant (`DOCS`) is defined in `server/tags.py` and currently unused. The
   `port-repair.py/` planning record sketches a possible repair tool but has no design or
   code.
2. **Timeout integration coverage.** Both timeout mappings are unit-tested; a real hang
   needs a deliberately-stuck worker (`worker.sleep` exists but no slow fixture triggers
   the timeout path end-to-end for either tool).
3. **Advisory/`<standard input>` hardening is mostly resolved.** ANSI stripping, binary
   input, `skipped:`/`unable to locate file:` formats and the `(fmod X) :` spelling are
   pinned; `<standard input>` warnings are attributed to the diagnosed file; multi-line
   Maude warning messages are still not exercised (none observed). The capture helper now
   handles both streams; diagnostics intentionally ignores stdout.
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

1. Keep `.agents/planning/` notes in sync with implementations — the diagnostics tool, the
   linter port and `maude_run` followed their PDD cycles; future tools should follow the
   same process (`port-repair.py/` is the next candidate). Update stale status banners.
2. Add real tests as tools are implemented, and keep `docs/modules.md` current.
3. Re-run the codebase-summary process after significant architecture changes so this
   knowledge base does not drift from the code.
4. Record `maude_run` and the settings rename in `CHANGELOG.md`, then bump the version
   (the session design proposed `0.1.0`) before the next release.
