# Changelog

## [0.0.5]

New `maude_run` tool: bounded Maude interpreter sessions — load one file, select a module,
and run `reduce`, `rewrite`, `frewrite`, `erewrite`, `match` and `search` steps with
REPL-style threading. A shared stream-capture layer also closes a latent stdout leak in
the diagnostics worker.

### Added

- **`maude_run` MCP tool** — runs a bounded Maude interpreter session in one hermetic
  call: one file, one explicit module, and an ordered step list of `reduce`, `rewrite`,
  `frewrite`, `erewrite`, `match` and `search`. Commands thread a current term
  REPL-style (omit a step's term/subject to use the previous result), expose Maude's
  `bound`, `gas` and `depth`, and return every intermediate result (`term`/`rewrites`,
  match substitutions, and search solutions with their bindings and rewrite counts).
  Per-step failures (`parse-error`, `too-large`) stop the run and are returned as
  outcomes; load warnings are reported while evaluation proceeds; every phase reports
  ANSI-stripped captured stdout/stderr. `match`/`search` results are capped with a
  `truncated` flag, result terms respect the configured length limit, and missing paths,
  load failures, missing/theory modules and worker crashes/timeouts fail the whole call
  with `MaudeRunError`. The tool advertises the same read-only annotation profile as the
  diagnostics tool and carries the `interpreter` tag.
- **Interpreter settings** — `HAROLD_INTERPRETER_TIMEOUT_SECS` and
  `HAROLD_INTERPRETER_MAX_STEPS`, `..._MAX_REWRITE_BOUND`, `..._MAX_SOLUTIONS`,
  `..._MAX_TERM_LENGTH`, `..._MAX_RESULT_LENGTH` and `..._MAX_OUTPUT_LENGTH`, plus the
  tool's per-call `timeout_secs` override.
- **Shared stream capture (`harold_mcp.maude.capture`)** — redirects fds 1 and 2 to temp
  files, restores them in `finally`, strips ANSI codes, decodes lossily, parses Maude's
  warnings and truncates output; used by both the diagnostics load and interpreter
  sessions.
- **Worker session engine (`harold_mcp.maude.session`)** — the bounded session
  implementation and its worker protocol types, exposed through
  `MaudeExecutor.run_session`.

### Changed

- **Breaking: `HAROLD_MAUDE_WORKER_TIMEOUT_SECS` renamed to
  `HAROLD_DIAGNOSTICS_TIMEOUT_SECS`** — it is the diagnostics timeout (and the lifespan's
  init-ping budget). The old environment variable is ignored.
- **Timeout ownership** — `MaudeExecutor` no longer picks a default timeout: diagnostics
  passes its setting, `maude_run` passes its own setting or the per-call override, and the
  lifespan passes the diagnostics timeout to the startup check. Both timeouts cover the
  whole worker call and remain best effort (a timeout kills and replaces the pool).
- **Absolute paths in both tools** — the `maude_program_diagnostics` and `maude_run`
  descriptions now state that `path` must be absolute, because the server's working
  directory is not the client's.
- **Concurrent-call wording** — `HAROLD_MAUDE_WORKERS` is documented as the cap on
  concurrent diagnostics and interpreter sessions; workers are still recycled per call.

### Fixed

- **No stdout leak from loaded files** — diagnostics now captures the worker's stdout
  around `maude.load`, so a diagnosed file's embedded REPL commands (e.g. a `red`) can no
  longer write into the MCP stdio transport. The captured output is discarded; warnings
  are still parsed from stderr.

### General fixes

- Assorted typos, formatting, documentation polish, PDD planning and review records, and
  agent-harness command allow-list updates.

## [0.0.4]

Heuristic linter port: `maude_program_diagnostics` now reports the Maude interpreter load
*and* Harold's heuristic checks in one call, with provenance, precise positions,
report-only fixes, and an `info` severity for findings that do not affect the load.
Calls are hermetic — each loads the file into a fresh Maude interpreter — so parser
state cannot leak across calls, and interpreter findings are attributed to the file they
belong to.

### Added

- **Heuristic linter inside `maude_program_diagnostics`** — the tool runs Harold's
  pattern-based checks on the file's text next to the interpreter load, so no separate
  lint tool is needed. The rules, ported from `improve-rag/improvement/linter.py` (which
  is untouched) and hardened against false positives, are `non-ascii-character`,
  `when-guard`, `dash-comment`, `eq-in-term`, `non-linear-pattern`,
  `undeclared-identifier` and the new `prelude-sort-redeclared`. Findings never come from
  inside string literals, quoted identifiers, comments, statement labels or declaration
  lines, and rule 6's allow-list knows the sorts the prelude declares.
- **`prelude-sort-redeclared` rule + bundled prelude sort snapshot** —
  `harold_mcp.heuristic.prelude_sorts` is a generated module listing the 164 sorts the
  Maude 3.5.1 prelude declares (theory sorts excluded), consumed by the rule and by rule
  6. The new `harold-update-prelude-sorts <prelude.maude> [--check]` console script
  regenerates it and verifies the committed data is fresh; see `DEVELOPER_GUIDE.md`.
- **Diagnostic provider seam** — `harold_mcp.diagnostics` defines the
  `DiagnosticProvider` protocol, the seam value types (`SourceFile`,
  `ProviderDiagnostic`, `FixSuggestion`) and the aggregator (`collect_diagnostics`), so
  future Maude linters and static analyses plug in without touching the tool. The
  interpreter provider lives in `harold_mcp.maude.provider`; the heuristic linter is its
  own `harold_mcp.heuristic` package and runs in the server process (it never imports the
  `maude` bindings).
- **Hermetic diagnostics calls (fresh interpreter per call)** — the worker pool recycles
  its processes after every call (`max_tasks_per_child=1`), fixing the deferred-`q .`
  parser-residue bug (`.agents/planning/no_new_module_quirk/`): a file containing a
  top-level `q .`/`quit .` used to leave the parser half-parsed, silently contaminating
  the *next* call with a misattributed `syntax error` (or, for relative paths, a bogus
  hard failure). Loading is now order-independent and concurrent calls cannot share
  interpreter state.
- **Honest dependency attribution** — when Maude reports a warning for a file the
  diagnosed file pulled in (`load`/`in`), the tool reports it as a whole-file diagnostic
  whose message names the dependency and suggests running `maude_program_diagnostics` on
  it; warnings spelled with `(fmod X) :` (space before the colon), previously dropped
  silently, are now kept.
- **Developer workflow** — `make test-unit` (hermetic, ~2 s) and `make test-integration`
  (parallel via pytest-xdist, `-n auto`) targets for quick iteration; `make test` stays
  the authoritative sequential run used by CI and `make release`.

### Changed

- **Diagnostics schema (breaking for exhaustive clients)** — every diagnostic now carries
  `source` (`"interpreter"` or `"heuristic-linter"`) and `code` (`"compiler"` for the
  interpreter, the rule name for heuristic findings), an optional report-only `fix`
  (description plus applyable edits with exclusive `range.end`), and exact columns for
  heuristic findings. `severity` gained `"info"` and `summary` gained `info`.
- **`success` semantics** — `success` is `true` only when no diagnostic has severity
  `warning` or `error`; `info`-only results (a shadowed prelude sort, non-ASCII
  punctuation Maude accepts) now count as success. Diagnostics are ordered by file
  position, with interpreter findings first on a line and whole-file problems last.
- **Fresh interpreter per call (breaking for session state)** — the "last load wins"
  session behavior is gone: modules loaded by a previous call are no longer visible, and
  relative input paths (resolved against the server's working directory, echoed back
  absolute) always work.
- **`HAROLD_MAUDE_WORKERS` default** — now half the logical CPUs, capped at 3
  (`max(1, min(3, cpu_count // 2))`); it bounds how many fresh interpreters may spawn
  concurrently (~100 MB each), not how many stay warm. The environment variable still
  overrides it.
- **Failure semantics** — when any provider fails, the whole call fails with
  `DiagnosticCollectionError`, which names every failing provider and its cause (a worker
  crash or timeout is chained from the interpreter provider). Successful providers'
  findings are never returned alongside the error, because MCP cannot express
  "error + content".
- **Tool description** — rewritten to explain both sources, the severity meanings, the
  `fix` payload, the ordering, the fresh-interpreter-per-call semantics and the
  whole-load/dependency behavior, and the result models document every field, so those
  descriptions reach clients through the tool's output schema. The tool keeps its
  read-only annotation profile (`readOnlyHint`, `destructiveHint=False`, `idempotentHint`,
  `openWorldHint=False`) and never modifies the diagnosed file.
- **License** — switched from Apache 2.0 to the GNU General Public License v2; the
  repository and package `LICENSE` files were updated together.
- **Python version support** — capped to the 3.14 series: `requires-python` is now
  `>=3.14,<3.15` (was `>=3.14`), because `maude` 1.6.0 ships cp314-only wheels, so a
  newer interpreter would have no wheel to install. `README.md` explains that `uvx`
  downloads 3.14 automatically when needed, or can be pointed at it explicitly, and
  `.python-version` pins the development interpreter.
- **General fixes** — assorted typos, formatting, documentation polish, and internal
  housekeeping.

### Removed

- **`MaudeFileNotFoundError`** — the tool's input-file error is now
  `harold_mcp.diagnostics.SourceFileNotFoundError`, raised by `SourceFile.from_path`
  (a missing file is a diagnostics-tool concern, not an interpreter error). `MaudeError`
  and its remaining subclasses are unchanged.

## [0.0.3]

### Added

- **Developer skill: update-changelog-for-release** — new agent skill that keeps
  `CHANGELOG.md` in sync with the commits before each release, as documented in
  `DEVELOPER_GUIDE.md`.

### Changed

- **Tool tags** — `maude_program_diagnostics` now advertises the tags `maude`,
  `programming`, and `diagnostics`, defined in the shared `harold_mcp.server.tags`
  vocabulary so future tools reuse the same strings. Tags power server-side
  visibility control (e.g. `mcp.disable(tags={"diagnostics"})`); with mcp SDK 1.29
  (spec 2025-06-18) they are not serialized to clients, but they are ready for
  protocol revisions that do.
- **Richer tool annotations** — `maude_program_diagnostics` now advertises the full
  read-only profile (`readOnlyHint=True`, `destructiveHint=False`, `idempotentHint=True`,
  `openWorldHint=False`) so clients can skip confirmations and treat the tool as safe
  to retry.
- **Maude IO disabled in the worker** — after initialization the interpreter
  forbids directory access, file access, and process spawning
  (`setAllowDir/File/Processes(False)`), so a Maude program loaded by
  `maude_program_diagnostics` cannot touch the filesystem or spawn processes
  inside the worker.
- **cyclopts-based CLI** — the `harold-mcp` console script is now a cyclopts
  app: the default command and the new `serve` subcommand both start the MCP
  server over stdio, with `--help`/`--version` support.
- **Installation via `uvx`** — `README.md` now documents installing and updating
  the server with `uvx harold-mcp` (including version pinning), and the
  Zed/opencode/Cline MCP configuration examples use `uvx harold-mcp` as the
  command.
- **Developer guide moved to `DEVELOPER_GUIDE.md`** — the developer-focused
  content (environment setup, agent-skill recommendations, release process)
  moved out of `README.md` into a dedicated `DEVELOPER_GUIDE.md`.
- **General fixes** — assorted typos, formatting, and documentation polish.

## [0.0.2] - 2026-08-27

First functional tool: `maude_program_diagnostics`.

### Added

- **`maude_program_diagnostics` MCP tool** — loads a Maude source file into the
  interpreter and reports every problem found, including recoverable warnings, as a
  structured LSP-style result (`path`, `success`, per-severity `summary`, and
  diagnostics with 1-based line ranges; `range=None` for whole-file problems).
- **Dedicated Maude worker process** — the interpreter runs in a spawned worker
  (`ProcessPoolExecutor`, spawn context): OS-level capture of Maude's `Warning:` lines
  (fd-2 redirection, ANSI stripping, lossy decoding), SIGSEGV containment, and automatic
  pool replacement on worker crash/timeout (a timed-out worker is killed — graceful
  shutdown cannot stop a hung `maude.load`).
- **`MaudeExecutor` client** — warm-up pings (fail-fast at startup), per-call timeouts,
  and a generic `_run_task` runner for future worker ops.
- **Configuration** via `pydantic-settings`: `HAROLD_MAUDE_WORKERS` (default `1`) and
  `HAROLD_MAUDE_WORKER_TIMEOUT_SECS` (default `60`).
- **Server lifecycle** — FastMCP lifespan (pool warm-up + graceful teardown) and SIGTERM
  handling with a clean exit.
- **Package reorganization** — `harold_mcp.server` (FastMCP instance + tools) and
  `harold_mcp.maude` (executor client + worker code) packages; new `harold_mcp.settings`.
- **Test suite** — 57 unit + integration tests, including a real MCP stdio smoke test.

### Removed

- Placeholder `greet` tool.
- In-process `MaudeRuntime` wrapper and its error types (`MaudeLoadError`,
  `MaudeModuleNotFoundError`).

## [0.0.1]

Initial skeleton.

- MCP server over stdio (FastMCP) with a hello-world `greet` tool.
- Thread-safe in-process wrapper over the Maude bindings (`MaudeRuntime`).
- Packaging, docs, and CI scaffolding (uv, hatchling, MkDocs, ruff/mypy/deptry).
