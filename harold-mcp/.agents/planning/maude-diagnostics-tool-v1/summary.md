# Summary — Maude diagnostics tool v1 (PDD)

First real MCP tool for the `harold-mcp` server: `maude_program_diagnostics(path)` loads a
Maude source file into the interpreter and reports every problem it finds — including
recoverable warnings — as a structured, LSP-style diagnostics result.

## Artifacts

- `rough-idea.md` — the original goal and experiments.
- `idea-honing.md` — requirements Q&A (Q1–Q8) + design-review amendments + final-testing
  reminders.
- `research/` — six notes; `logging.md` superseded; `process-pool-executor.md` holds the
  empirically verified worker-transport findings.
- `design/detailed-design.md` — standalone design: architecture, components, data models,
  error handling, testing strategy, appendices.
- `implementation/plan.md` — 7 TDD steps with a progress checklist.

## Design in brief

- **Two processes**: a FastMCP server process and a dedicated Maude **worker process**
  (`ProcessPoolExecutor`, `spawn`, `max_workers` from env), chosen for stderr-isolation
  (fd-2 capture of `Warning:` lines) and SIGSEGV containment.
- **`MaudeExecutor`** client wrapper: warm-up pings, per-call timeouts, eager
  crash/timeout recovery by recreating the executor.
- **Tool** `maude_program_diagnostics(path: str)` → pydantic result
  `{path, success, summary, diagnostics[]}` with LSP-style ranges (`range=None` for
  whole-file problems); `readOnlyHint=True`; runtime injected via `Depends`.
- **Packages**: `harold_mcp/server/` (FastMCP instance + tools) and `harold_mcp/maude/`
  (executor client + worker code); registration is a side effect of importing the server
  package.
- **Config** via `pydantic-settings`: `HAROLD_MAUDE_WORKERS` (default 1),
  `HAROLD_MAUDE_WORKER_TIMEOUT_SECS` (default 60).

## Implementation plan

7 test-driven steps, each demoable: (1) package restructure + settings/errors + remove
`greet`; (2) worker capture + warning parsing; (3) `MaudeExecutor` with recovery; (4)
models + tool registration; (5) lifespan warm-up/fail-fast; (6) end-to-end integration
(fixtures, crash resilience, settings, MCP smoke test); (7) README, docs, knowledge base,
and the two final-testing reminders.

## Next steps

1. Review `design/detailed-design.md` and `implementation/plan.md`.
2. Start implementation at Step 1, ticking the checklist in
   `implementation/plan.md` as you go.
3. After implementation: re-run the codebase-summary skill (Step 7) and commit everything.

## Areas that may need refinement later

- The warning parser is deliberately simple; adversarial-format hardening is scheduled in
  Step 7.
- Lifespan behavior on the stdio transport is verified manually in Step 5 (reminder #2).
- Parallelism (`HAROLD_MAUDE_WORKERS > 1`) is safe but lightly exercised; the v1 default
  stays 1.
