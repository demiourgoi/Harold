# Review — uncommitted Step 6 (Documentation and final validation), plan at `.agents/planning/more_interpreter_bugs/implementation/plan.md`

What this change does: This is Step 6 of the more_interpreter_bugs plan — documentation and release notes, no behavior change. The one production edit rewrites two paragraphs of the `maude_run` tool description (the stale "replaces the worker pool" sentence is gone; the error categories and the admission-covering timeout are now stated), a new unit test pins that wording, and the README env table, CHANGELOG, `docs/modules.md`, `AGENTS.md` and the `.agents/summary/` knowledge base are refreshed to the per-call process architecture. The plan's Step 6 notes record the work and two deviations (no version bump per the user's request; targeted KB edits instead of a full codebase-summary run).

Verified accurate against the code:

- The description's category list (`timeout`, `crash`, `spawn-failure`, `init-failure`, `remote-exception`, `cancelled`, `protocol-error`) matches `maude/worker_errors.py` exactly; the base `worker-failure` category is never raised.
- "The timeout covers admission … process startup, Maude initialization, the load and every step" matches `MaudeExecutor._run_operation` (deadline before the semaphore acquire, remaining budget handed to the runner).
- "Only that call's process is killed" matches the runner/executor design; the workflows.md crash flowchart matches the code (only a crash while closed is remapped to `cancelled`).
- README defaults (`HAROLD_ERROR_DETAIL_MAX_CHARS=4000`, `HAROLD_IPC_MAX_RESPONSE_BYTES=2 GiB`) match `settings.py` / `errors.py`.
- `docs/modules.md`'s four new entries (`harold_mcp.errors`, `maude.runner`, `maude.transport`, `maude.worker_errors`) all exist.
- CHANGELOG claims (isolated workers, rich errors, remote exceptions, `MaudeInitError` hierarchy, no collateral failures/orphans) match the committed code.
- KB claims spot-checked: `collect_diagnostics(..., max_chars=...)`, `DiagnosticCollectionError.format_report`, the formatter signature, the error-hierarchy table, the test inventories.

## Findings

1. **Should fix — the refreshed knowledge base still routes to `_exception_detail`, a function deleted in Step 1** (`.agents/summary/components.md:124`, `.agents/summary/index.md:13`, `.agents/summary/index.md:72`)
   - **What this is:** The KB is committed and trusted by agents (AGENTS.md gotcha 15). `components.md:124` describes the current `maude_run` unexpected-failure text as "includes `_exception_detail(exc)`", and two `index.md` routing entries point at `_exception_detail` in `tools/interpreter.py`.
   - **Problem:** `_exception_detail` was removed in Step 1 of this same plan and replaced by `harold_mcp.errors.format_error_report`; it no longer exists in `src/` or `tests/`. These lines were not touched by the refresh, so pages this step claims to have refreshed still tell the pre-Step-1 error-text story, contradicting the new gotcha 22 and the new `harold_mcp.errors` section.
   - **Fix:** Replace the three mentions with `format_error_report` (`harold_mcp.errors`). `review_notes.md:68` sits in the dated 2026-11-12 historical section and can stay.
   - **If we skip it:** An agent following the routing entry greps for a function that does not exist and misses the real error-text mechanism.

2. **Nice to have — README documents rich errors for `maude_run` but not for `maude_program_diagnostics`** (`README.md:54-66` vs the diagnostics entry above it)
   - **What this is:** The README's `maude_run` entry now ends with the error categories, context, cause chain and bounded traceback. The `maude_program_diagnostics` entry says nothing about error shape.
   - **Problem:** The diagnostics tool returns the same rich, capped, provider-attributed errors (Step 5; the CHANGELOG's "Rich, bounded tool errors" entry documents the per-provider sections). The two tool entries are inconsistent in depth, though nothing stated is false.
   - **Fix:** One sentence in the diagnostics entry, e.g. "A provider failure fails the call with a section per failing provider (category, context, cause chain, bounded traceback); the full detail is logged server-side."
   - **If we skip it:** README readers underestimate what a diagnostics failure report tells them; no incorrect behavior is documented.

Verdict: fix 1 first (three one-line edits in files this step already touches); 2 is optional.

Not checked: no tests, `make check`, `make test` or `make docs-test` were run (per instruction); the plan notes' validation numbers are taken on trust. The KB's test-inventory claims were spot-checked, not enumerated file by file.
