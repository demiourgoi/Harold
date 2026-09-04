# Changelog

## [0.0.3]

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
