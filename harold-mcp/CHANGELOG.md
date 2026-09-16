# Changelog

## [0.0.5]

Heuristic linter port: `maude_program_diagnostics` now reports the Maude interpreter load
*and* Harold's heuristic checks in one call, with provenance, precise positions,
report-only fixes, and an `info` severity for findings that do not affect the load.

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
- **Failure semantics** — when any provider fails, the whole call fails with
  `DiagnosticCollectionError`, which names every failing provider and its cause (a worker
  crash or timeout is chained from the interpreter provider). Successful providers'
  findings are never returned alongside the error, because MCP cannot express
  "error + content".
- **Tool description** — rewritten to explain both sources, the severity meanings, the
  `fix` payload and the ordering. The tool keeps its read-only annotation profile
  (`readOnlyHint`, `destructiveHint=False`, `idempotentHint`, `openWorldHint=False`) and
  never modifies the diagnosed file.

### Removed

- **`MaudeFileNotFoundError`** — the tool's input-file error is now
  `harold_mcp.diagnostics.SourceFileNotFoundError`, raised by `SourceFile.from_path`
  (a missing file is a diagnostics-tool concern, not an interpreter error). `MaudeError`
  and its remaining subclasses are unchanged.

## [0.0.4]

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
