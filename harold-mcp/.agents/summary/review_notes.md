# Review Notes

<!-- tags: review, consistency, completeness, gaps -->

Findings from the consistency and completeness review (2026-09-04, after the cyclopts CLI,
the Maude IO lockdown, and the docs split into `DEVELOPER_GUIDE.md`). Older resolved issues
are kept for the record.

## Changes absorbed into this refresh

- The console-script entry point changed from `harold_mcp.main:run` to
  `harold_mcp.main:app` (cyclopts CLI); all knowledge-base references updated.
- `worker.init_maude` now disables Maude IO (`setAllowDir/File/Processes(False)`), covered by
  new hermetic unit tests in `tests/unit/test_maude_worker.py`.
- `maude` is pinned to `==1.6.0` and `cyclopts>=4.23.0` was added as a runtime dependency.
- Dev-environment and release docs moved out of `README.md`/`CONTRIBUTING.md` into the new
  `DEVELOPER_GUIDE.md`; the `mkdocs.yml` site URL became `https://demiourgoi.github.io/Harold/`.

## Resolved issues (historical)

- `pyproject.toml` description, CI location, `pre-commit` removal, `CONTRIBUTING.md`
  renumbering, Makefile `release` target, `logging.py` cleanup, `keywords` — all fixed in
  the initial generation.
- `harold_mcp.maude` rework and tests — superseded by the worker-process architecture
  (the old in-process `MaudeRuntime` no longer exists).
- `greet` tool placeholder — removed in v1 of the diagnostics tool.
- `server.py` untested — now covered by `tests/integration/test_lifespan.py` and the MCP
  smoke test in `tests/integration/test_diagnostics_integration.py`.
- Docs rendered only two modules — `docs/modules.md` now lists the five real modules.
- `broken-*.maude` fixtures unused — now exercised by integration tests.
- Stale `AGENTS.md` Custom Instructions note ("none of the MCP tools described above are
  implemented yet") — removed manually after this review flagged it.

## Remaining issues

1. **The synthesized `error` path has no end-to-end test.** `ok=False` only occurs for
   missing/unreadable files (pre-checked away by the tool) — empirically `maude.load`
   recovers from every parseable input. The path is unit-tested with a mocked worker
   result; acceptable, but worth knowing it can only fire via TOCTOU races.
2. **Hard-kill orphan window.** A `kill -9` of the server skips the lifespan, so workers
   exit on their own via the queue pipe rather than being killed; a worker mid-`maude.load`
   lingers until the task finishes. `prctl(PR_SET_PDEATHSIG)` in the worker initializer
   would close the gap (future hardening).
3. **The FastMCP stdio exit hang workaround relies on `os._exit`.** FastMCP 3.4.7 leaves a
   non-daemon stdin-reader thread; if a future FastMCP release fixes that, the
   `os._exit(0)` in `server.run()` could be dropped in favor of a normal exit.
4. **`README.md` env-var table is hand-maintained.** It duplicates the `Settings` defaults;
   keep it in sync when settings change.
5. **`scala-issue.md` documents a different codebase.** The new SIGSEGV/throughput analysis
   is about the Scala/Java Maude bindings (a related project), not `harold-mcp`'s Python
   bindings. Useful background for the SIGSEGV story; consider annotating it as such.

## Completeness gaps

1. **Only the diagnostics tool exists.** The planned run-Maude-programs and documentation
   RAG tools are not implemented yet (`_run_task` and the worker op pattern are the
   extension points).
2. **No timeout integration test.** The timeout mapping is unit-tested; a real hang needs
   a deliberately-stuck worker (`worker.sleep` exists but no slow fixture triggers the
   timeout path end-to-end).
3. **Advisory/`<standard input>` hardening is partial.** ANSI stripping, binary input,
   `skipped:` and `unable to locate file:` formats are pinned; multi-line Maude warning
   messages are not yet exercised (none observed).
4. **The CLI wiring is untested.** `main.py` (cyclopts app, `serve` subcommand, default
   command) has no dedicated tests; the `__main__` guard is `# pragma: no cover`.

## Language-support limitations

- Single language (Python) — no cross-language gaps.
- The `maude` bindings ship no type stubs: mypy uses `ignore_missing_imports`, so
  Maude-side code is effectively untyped beyond explicit boundary narrowing. basedpyright
  runs with all diagnostics off except `reportUnusedCallResult`.

## Recommendations

1. Keep `.agents/planning/` notes in sync with implementations — the diagnostics tool
   followed `maude-diagnostics-tool-v1/`; future tools should follow the same PDD cycle.
2. Add real tests as tools are implemented, and keep `docs/modules.md` current.
3. Re-run the codebase-summary process after significant architecture changes so this
   knowledge base does not drift from the code.
