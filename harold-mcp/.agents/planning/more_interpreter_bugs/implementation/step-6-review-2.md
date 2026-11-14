# Review 2 — attendance of the Step 6 review findings (uncommitted diff on top of 635c37e)

What this change does: The Step 6 work was committed as `635c37e Documentation and final validation`. The current uncommitted diff is the attendance of the Step 6 review (`step-6-review.md`): the three stale knowledge-base routes to `_exception_detail` now point at `harold_mcp.errors.format_error_report`, the README's `maude_program_diagnostics` entry documents its per-provider failure report, and the plan's Step 6 notes record the attendance. Documentation only; no production code touched.

## Attendance check

- **Finding 1 (should fix — stale `_exception_detail` routes): attended, correctly and completely.**
  - `components.md` "Unexpected failures" bullet rewritten as "Whole-call failures" describing `format_error_report`, the `error_detail_max_chars` cap, the uncapped server-side log, and `format_context` for input errors. Every claim verified against `server/tools/interpreter.py`: both except branches use the formatter (`max_chars=settings.error_detail_max_chars`, log at `max_chars=0`), `_with_context` calls `format_context`, and `_call_context` carries path/module/steps/timeout.
  - `index.md:13` and `index.md:72` now route to `harold_mcp.errors` (`format_error_report`) and the uncapped-log/capped-client split. All named destinations exist (workflows.md "Failure semantics", components.md `harold_mcp.errors` section, both planning records).
  - `review_notes.md:68` left in the dated 2026-11-12 historical section, as the review suggested. No `_exception_detail` reference remains outside that historical record.
- **Finding 2 (nice to have — README diagnostics entry): attended.** The new sentence ("one section per failing provider — category, context, cause chain and a bounded traceback — and the full detail is logged server-side") matches `diagnostics/aggregate.py` (`_format_collection` renders one section per failure) and the tool's uncapped-log/capped-raise split.
- **Plan note:** references `step-6-review.md`, which exists in `implementation/` alongside `step-1..5-review.md` (a copy of the review, consistent with the previous steps), and describes the attendance accurately.

## Findings

1. **Nice to have — the index.md Table of Contents rows still summarize the pool-era architecture** (`.agents/summary/index.md:29-30`, the `review_notes.md` row, and the "Relationships" section)
   - **What this is:** The ToC table summarizes each knowledge-base file. The `architecture.md` row still says "server + Maude worker, one task per process" (the `max_tasks_per_child=1` wording; the file now describes the MCP server plus one per-call child). The `components.md` row lists the `maude` package without `runner`, `transport`, `worker_errors` (and the flat `errors` module), and still calls the tool section "`maude_run`'s unexpected-failure detail" (the old mechanism name; the file now documents the whole-call error report). The `review_notes.md` row mentions only the 2026-11-12 refresh, not the 2026-11-14 one the file now leads with.
   - **Problem:** Same class as the original finding 1, but lesser severity: these are imprecise or incomplete summaries, not false routes — the "Example queries" entries added by the refresh route correctly, so an agent still lands in the right file.
   - **Fix:** Update the three rows and the "Relationships" line ("executor + worker" → include the new modules), or fold it into the full codebase-summary re-run the step's deviation note already recommends.
   - **If we skip it:** The ToC undersells the refreshed files; no agent is routed to a nonexistent target.

2. **Nice to have — the replacement entry at `index.md:72` is bold in a plain-quoted list**
   - **What this is:** Every "Example queries" entry is a plain quoted string; the new entry uses `**bold**`.
   - **Problem:** Formatting inconsistency in the section it was edited into.
   - **Fix:** Drop the `**`.
   - **If we skip it:** Purely cosmetic.

Verdict: Ship. The attendance is correct and complete; both findings are optional polish.

Not checked: no tests or gates were run (per instruction); the plan note's "full gate was re-run after these documentation edits and stayed green" is taken on trust.
