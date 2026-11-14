# Review Notes

<!-- tags: review, consistency, completeness, gaps -->

Findings from the consistency and completeness review. The 2026-11-14 refresh has two
parts: the bundled-skill installer (build-time packaging plus `harold-mcp setup`) and the
per-call isolated worker architecture (one `spawn` process per call, one-shot JSON
transport, semaphore admission, shutdown cancellation) with the rich bounded error reports;
the 2026-11-12 refresh has two parts: capture completeness plus failure surfacing (the
stdio flush in `capture_streams` and detailed `maude_run` unexpected-failure messages), and
search paths in `maude_run` (`SearchStep.path`, worker `path_mode`/`max_path_steps`,
`MaudeSearchPath`, the new setting, tests and fixture, and the README/CHANGELOG updates);
the 2026-10-28 refresh covers the `maude_run` interpreter-session tool (new
`maude/session.py`, `maude/capture.py`, `server/tools/interpreter.py`, new settings, tests
and docs); the 2026-10-14 refresh covers the provider-registry FastMCP dependency; the
2026-10-12 refresh covers the `no_new_module_quirk` implementation (hermetic per-call
interpreters, the new workers default, dependency-warning attribution, path
absolutization, and the test-suite rework); the 2026-09-29 refresh covered the
heuristic-linter port. Older resolved issues are kept for the record.

## Changes absorbed into this refresh (2026-11-14, bundled-skill installer)

- **Packaging.** `make skills` copies the monorepo's `skills/maude-manual` into the
  git-ignored `src/harold_mcp/skills/maude-manual`; `.gitignore` excludes the copy;
  `pyproject.toml` adds `artifacts` to both the wheel and sdist targets (hatchling's sdist
  respects `.gitignore`, and `uv build` builds the wheel from the sdist, so the ignored
  copy must be re-included explicitly); `make build` depends on `clean-build skills`; and
  the release workflow's publish job now runs `make skills && uv build` (verified in
  `../.github/workflows/on-release-main.yml`).
- **CLI and installer.** New `harold_mcp/skill_install.py` (`SKILL_NAME`, `skill_source`,
  `install_skill`) and `main.py setup` (`--directory`, `-g/--global`; prints the installed
  path and the package version). The installer removes an existing destination before
  copying (full refresh, siblings untouched) and raises a clear `FileNotFoundError` naming
  `make skills` when the artifact lacks the copy.
- **Version and docs.** `pyproject.toml` is `0.1.0.dev0` — the first **MVP** release
  line (diagnostics + interpreter sessions + bundled skill) — with an open `[0.1.0]`
  changelog section recording the delta since 0.0.5; the README installation/update
  sections now revolve around `setup` and the MCP client JSON blocks were replaced by
  links; the `skill-installer/` PDD record documents requirements, the release-packaging
  research, design, three review rounds and the plan.
- **Tests.** `tests/unit/test_skill_install.py` covers fresh install, refresh (stale files
  dropped), stray-file replacement, sibling safety, the missing-source message, the
  packaged-source contract (skips without `make skills`) and both CLI destinations.
- **Docs consistency.** This refresh updates `codebase_info.md`, `architecture.md`,
  `components.md`, `interfaces.md`, `workflows.md`, `dependencies.md`, `index.md` and
  `AGENTS.md`; `data_models.md` and `maude-lib.md` are unchanged (the installer adds no
  models and does not touch the interpreter or prelude). The `components.md` list of
  mkdocstrings modules was corrected to match `docs/modules.md` (it was missing `errors`,
  `runner`, `transport` and `worker_errors`).

## Changes absorbed into this refresh (2026-11-14, isolated per-call workers and rich errors)

- **Per-call process architecture.** `MaudeExecutor` no longer uses a shared
  `ProcessPoolExecutor`: it owns a `PipeProcessRunner` and a
  `BoundedSemaphore(HAROLD_MAUDE_WORKERS)`. Each call spawns one child, sends one JSON
  request over a Pipe and receives one response; the child exits afterwards. Admission
  waits against the whole-call budget; `start()` runs the fail-fast init pings under one
  deadline; `shutdown()` sets a closed flag and kills/reaps every active child. A crash or
  timeout affects only its own call, so the old pool-wide cascade (`CancelledError` /
  collateral `Maude worker crashed`) cannot occur.
- **Child transport.** `maude/transport.py` redirects fds 0/1/2 to `/dev/null`, validates
  one request, always initializes Maude first and dispatches `ping`/`diagnostics`/`session`,
  sending ok/error envelopes (`protocol`/`init`/`remote`). `maude/runner.py` maps EOF,
  mid-message/send failures, deadlines, malformed/oversized responses and child envelopes
  to the typed worker errors; `_reap` serializes the pipe close and process teardown.
- **Error model and formatter.** The hierarchy moved to `maude/worker_errors.py`
  (`MaudeWorkerError` with `category`/`context`/`remote_traceback`, plus spawn/remote/
  cancelled/protocol errors; `MaudeInitError` is now a `MaudeWorkerError`). The stdlib-only
  `harold_mcp.errors.format_error_report` renders the stable category line, merged context,
  cause chain, originating traceback and truncation marker. Both tools log the uncapped
  report and return the capped one; the diagnostics aggregation renders one section per
  failing provider.
- **Settings.** `HAROLD_ERROR_DETAIL_MAX_CHARS` (4000) and
  `HAROLD_IPC_MAX_RESPONSE_BYTES` (2 GiB).
- **Tests.** New `test_errors.py`, `test_maude_runner.py`, `test_maude_transport.py`,
  `test_maude_transport_integration.py` and `test_process_isolation_integration.py`; the
  executor tests were rewritten around a fake runner, the worker integration tests now go
  through `MaudeExecutor`, and the B0-B7 matrix is pinned (cascade, crash isolation,
  timeout, capture, init/spawn/protocol mapping, bounded-search EOF).
- **Docs.** `docs/modules.md` lists the new modules; README has the new settings and
  per-call timeout semantics; the `maude_run` description was updated; the CHANGELOG
  `[0.0.5]` section records the architecture and error changes. This knowledge base was
  refreshed in place (targeted edits); a full `codebase-summary` re-run remains the
  recommended follow-up if a complete re-audit is wanted.

## Changes absorbed into this refresh (2026-11-12, capture flush and failure surfacing)

- **Complete captured output.** `maude/capture.py` gained `_flush_stdio()`: it flushes
  Python's `sys.stdout`/`sys.stderr` and the C/C++ stdio buffer (`libc.fflush(NULL)` via
  `ctypes`), suppressing every failure so flushing can never change a phase result. It
  runs before the fd redirect (keeping pre-existing buffered bytes out of the capture) and
  in the `finally` while the capture fds are still in place. Without the final flush,
  libmaude's independently buffered output was restored to the real fds before being
  written: a load whose last command is a bounded `search` that stops at its bound lost
  that result block, and the bytes could surface in a later phase or on the worker's
  inherited stdout (the MCP stdio transport).
- **Diagnosable unexpected failures.** A non-`MaudeWorkerError` from the worker now reaches
  the client as `MaudeRunError` with the exception type and message appended
  (`_exception_detail`; an empty message yields just the type). The tool logs the
  traceback server-side with the resolved path and module, and keeps the original
  exception as `__cause__`.
- **Tests and fixtures.** Unit tests pin the C-buffer flush (buffered output captured and
  not leaked to the restored stdout) and the suppression of failing Python/libc flushes;
  `test_interpreter_tool.py` asserts the `ValueError: boom` / bare-type message and the
  logging call. The integration fixture `bounded_search_last.maude` plus
  `test_bounded_search_at_the_end_of_the_load_is_captured` cover the original tail-loss
  case against the real interpreter.
- **Planning record.** `.agents/planning/Unexpected_failure_during_search/` is now a
  tracked, complete PDD cycle (`rough-idea.md`, `research/` incl. executable probes,
  `design/`, `implementation/plan.md`, `pdd_review-1.md`, `summary.md`). It confirms the
  flush defect, records that the generic whole-call error was not reproduced on this
  checkout, and documents the two fixes above. Its `summary.md` item 2 (this refresh) is
  now done; the original failure remains open pending reproduction on the original host.
- **Changelog.** Two `Fixed` entries under `[0.0.5]` record complete captured output and
  diagnosable unexpected failures. The version stays `0.0.5.dev0` (the release is still
  unreleased).
- **Docs consistency.** This refresh updates `codebase_info.md`, `architecture.md`,
  `components.md`, `interfaces.md`, `data_models.md`, `workflows.md`, `dependencies.md`
  (stdlib list gains `contextlib`/`ctypes`/`sys`) and `maude-lib.md` (capture scope), plus
  `AGENTS.md`; no other knowledge-base file changed.

## Changes absorbed into this refresh (2026-11-12, search paths)

- **Search paths in `maude_run`.** `SearchStep.path` (`"none" | "labels" | "full"`,
  default `"labels"`) is exposed through the tool; solutions now carry
  `MaudeSearchPath {initial, transitions: [{rule: {label, text}, state}]}`. Labels mode is
  the compact default; full mode adds rule text and intermediate states; `none` restores
  the previous payload shape. Unlabeled rules have `label=null`; reflexive `=>*` and
  branching `=>#` solutions have zero transitions.
- **Worker protocol and reconstruction.** `StepRequest` gained `path_mode`, `SessionRequest`
  gained `max_path_steps`, and `SolutionDict` gained `path`; the new `PathRuleDict`,
  `PathTransitionDict` and `PathDict` TypedDicts cross the process boundary. The session
  engine reads `iterator.getStateNr()` while the iterator is positioned (the bindings'
  path thunk is lazy and would return the wrong state), walks `getStateParent()`
  iteratively (the bindings' `pathTo` is recursive), calls `getRule()` only for non-root
  states (`getRule(0)` SIGSEGVs), and stops at the cap before formatting strings.
- **New setting `HAROLD_INTERPRETER_MAX_PATH_STEPS`** (default `100`), plus named
  `too-large` messages: a path over the cap reports
  `path exceeds interpreter_max_path_steps`; an over-long path element reports
  `path element exceeds interpreter_max_result_length`. Rewriting/match/search `too-large`
  outcomes now carry a message naming `interpreter_max_result_length`.
- **Tests and fixture.** New `tests/integration/fixtures/search_path.maude` (`SHEPHERD`,
  `UNLABELED`, `CHAIN`, `BRANCH`); unit tests cover the path contract, fake iterators and
  adapter; integration tests cover labels/full/none, zero-transition paths, unlabeled
  rules, per-solution laziness, `max_solutions=1`, exact and over-cap paths, deep
  1500-step searches, and the end-to-end tool path.
- **Docs and planning.** `README.md` and `CHANGELOG.md` already documented the feature;
  this refresh brings the knowledge base and `AGENTS.md` in line. The
  `.agents/planning/maude_eval_search_path/` PDD record contains the requirements,
  bindings research (lazy state numbers, `getRule(0)` crash, recursive `pathTo`), three
  design-review rounds, revision 4 of the design and a five-step TDD plan. The `Makefile`
  `review` target and its `DEVELOPER_GUIDE.md` prompts are now documented in
  `workflows.md` and `AGENTS.md`.

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
  and `test_maude_run_integration.py`; new fixtures (`counter.maude`,
  `assoc_match.maude`, `warns_and_prints.maude`). `test_maude_worker.py` now
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
  an open `[0.0.5]` changelog section (empty at the time of the 2026-10-14 refresh; it now
  records `maude_run`, search paths, the capture layer and the settings rename) —
  `codebase_info.md` updated accordingly.
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
  new fixtures; the `heuristic_executor` workaround is gone;
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
11. **The search-path planning summary is stale.**
    `.agents/planning/maude_eval_search_path/summary.md` still says "Implementation has not
    started" although `SearchStep.path`, the worker reconstruction, the fixture and the
    tests are in the tree. Treat the design and implementation plan as the record, or
    update the summary banner.
12. **The original search failure is still open; its two side issues are fixed.** The
    planning record `.agents/planning/Unexpected_failure_during_search/`
    reproduces the missing load output (unflushed libmaude stdio buffers), now fixed with
    unit and integration regressions. The tool also surfaces non-`MaudeWorkerError`
    exception details (type and message) and logs the traceback, so an MCP client can
    diagnose the next occurrence. The generic whole-call error itself has not been
    reproduced on HEAD; it remains tied to the original (less powerful) host.

## Completeness gaps

1. **The documentation RAG tool does not exist yet.** Both in-scope MCP tools
   (`maude_program_diagnostics`, `maude_run`) are implemented, and the bundled
   `maude-manual` skill ships with the 0.1.0 MVP; the planned Maude-documentation vector
   index is not. Its tag constant (`DOCS`) is defined in `server/tags.py` and currently
   unused. The `port-repair.py/` planning record sketches a possible repair tool but has
   no design or code.
2. **Timeout integration coverage.** Both timeout mappings are unit-tested and now also
   exercised end to end: a diagnostics timeout (sleeping runner target) and a real
   non-terminating `maude_run` rewrite with a healthy peer and a follow-up call.
3. **Advisory/`<standard input>` hardening is mostly resolved.** ANSI stripping, binary
   input, `skipped:`/`unable to locate file:` formats and the `(fmod X) :` spelling are
   pinned; `<standard input>` warnings are attributed to the diagnosed file; multi-line
   Maude warning messages are still not exercised (none observed). The capture helper now
   handles both streams and flushes C/C++ stdio before restoring the fds; the bounded-search
   regression pins the previously lost tail, and diagnostics intentionally ignores stdout.
4. **The server CLI wiring is still untested.** `main.py`'s default command and `serve`
   subcommand have no dedicated tests; the `__main__` guard is `# pragma: no cover`. The
   `setup` command is covered in `tests/unit/test_skill_install.py`, and the snapshot CLI
   in `tests/unit/test_prelude_extract_cli.py`.
5. **No MCP output-schema assertion for `maude_run`.** The stdio smoke test asserts the
   interpreter tool's input schema, description and annotations, but not its output schema
   (the search-path field descriptions) or the search-path sentences in the description;
   those models are covered by unit and integration tests. Worth extending when the smoke
   test is next touched.
6. **`docs/modules.md` omits the installer (and other thin modules).** It renders no
   `::: harold_mcp.skill_install` entry (nor `main`, `resources` or `logging`), so the
   mkdocstrings site does not document the `setup` API; `make docs-test` passes because
   the omission is not an error. Add the entry if the installer API should be published.
7. **No automated wheel-content test for the bundled skill.** The `skill-installer`
   design deliberately avoids a slow build test, so `test_packaged_skill_source` skips
   when `src/harold_mcp/skills` is absent. The release workflow (`make skills && uv build`)
   and a manual `make skills && uv build` are the current safeguards against shipping an
   artifact without the skill.

## Language-support limitations

- Single language (Python) — no cross-language gaps.
- The `maude` bindings ship no type stubs: mypy uses `ignore_missing_imports`, so
  Maude-side code is effectively untyped beyond explicit boundary narrowing. basedpyright
  runs with all diagnostics off except `reportUnusedCallResult`.

## Recommendations

1. Keep `.agents/planning/` notes in sync with implementations — the diagnostics tool, the
   linter port, `maude_run`, the search-path feature and the capture-flush/failure-surfacing
   fixes followed their PDD cycles; future tools should follow the same process
   (`port-repair.py/` is the next candidate). Update stale status banners
   (`maude_eval_search_path/summary.md`).
2. Add real tests as tools are implemented, and keep `docs/modules.md` current.
3. Re-run the codebase-summary process after significant architecture changes so this
   knowledge base does not drift from the code.
4. The `[0.1.0]` changelog records the `setup` command and bundled-skill packaging for the
   first MVP release; `[0.0.5]` records `maude_run`, search paths, the shared capture
   layer, the capture flush and diagnosable unexpected failures. Consider adding an MVP
   scope sentence to the `[0.1.0]` changelog intro (diagnostics + interpreter + skill),
   and review both sections before tagging. The release workflow builds with
   `make skills && uv build`, so the artifacts include the skill; a manual pre-release
   check is `make build` (it runs `skills` first). The
   `Unexpected_failure_during_search/` investigation is tracked and its two side issues
   are fixed; archive it or retry the original call on its host to close it.
5. If the installer API should be published, add `::: harold_mcp.skill_install` to
   `docs/modules.md`; otherwise leave the thin CLI/packaging modules off the API site.
