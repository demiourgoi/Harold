# Review — Step 5: Diagnostics end-to-end and error parity (uncommitted changes)

## What this change does

Step 5 of the `more_interpreter_bugs` plan pins the diagnostics error contract end to
end. The only production change is a docstring: `InterpreterDiagnosticProvider.diagnose`
now names the full worker-error taxonomy. The step's claim that no production change
was needed holds — I verified that `provider.py` catches the `MaudeWorkerError` base
class (so every subclass wraps into `DiagnosticProviderError` with the cause chained
and the resolved path/phase context preserved), and that the tool logs the uncapped
report (`format_report(max_chars=0)`) while re-raising the capped one. Everything else
in the diff is tests: a parametrized provider unit test over five new error types,
stronger aggregation assertions (both cause chains; no partial-result leak), a tool
test that pins the capped-client/uncapped-log split, and a new integration test that
drives a real worker timeout through the tool.

## Should fix

1. **The Step 5 notes overstate what the crash test asserts** (`.agents/planning/more_interpreter_bugs/implementation/plan.md`, Step 5 Implementation notes)
   - **What this is:** The notes say the new timeout test and "the existing crash test"
     "both assert a provider-attributed section with path/phase context and the chained
     `MaudeWorker*` cause".
   - **Problem:** `test_tool_reports_crash_and_a_healthy_executor_still_works`
     (tests/integration/test_diagnostics_integration.py) asserts the section header and
     the chained cause, but not `context: path=` or `phase=load`. The planning record is
     a committed, trusted artifact in this repo (AGENTS.md item 15), so it claims a pin
     that no test enforces on the crash path.
   - **Fix:** Either reword the note ("the timeout test additionally asserts the
     path/phase context"), or add the two context assertions to the crash test — two
     lines that make the note true and strengthen the pin.
   - **If we skip it:** A future reader trusts a coverage claim that is false; a
     regression in the provider's context merge on the crash path would pass every test
     the note names.

## Nice to have

2. **The timeout integration test does not pin the pid** (`tests/integration/test_diagnostics_integration.py`, `test_tool_reports_a_worker_timeout_with_a_rich_provider_section`)
   - **What this is:** The test asserts `context: path=` and `phase=load` in the client
     report, but not `pid=`, although the design's ER-3 requires the pid in the client
     text and the runner does put it in the timeout error's context (it reaches the
     report through the provider's context merge).
   - **Problem:** The pid is pinned at the runner seam and in the provider unit tests,
     but no diagnostics end-to-end test asserts it in the rendered report.
   - **Fix:** Add `assert "pid=" in report` next to the phase assertion.
   - **If we skip it:** A change that drops the pid from the diagnostics report would be
     caught only by seam-level unit tests, not by the end-to-end one.

## What I verified beyond the diff

- The provider wrap, the tool's capped/logged split, and all-or-nothing aggregation
  are unchanged in production code and now pinned by tests, matching the plan's Step 5
  requirements and the design's FR-8/ER-7.
- The new integration test is deterministic: the child target sleeps 120 s after
  reading, so it can never reply; any spawn or import slowness still yields
  `MaudeWorkerTimeoutError` within the 1 s budget. The runner kills the child in its
  `finally` (`_reap`), and the test's own `finally: executor.shutdown()` is a second
  net — no orphan processes.
- The capped tool unit test is robust to `tmp_path` length: both truncation branches
  (traceback-first and cause-first) keep the truncation marker inside the 300-char cap.
- The parametrized provider test's context assertion matches the actual merge order in
  `provider.py` (`{"path": ..., "phase": "load", **exc.context}`), and the aggregate
  assertions match the formatter's `cause: Type: message <- ...` rendering.
- The notes' validation counts are consistent with Step 4's (382 + 5 = 387 unit,
  104 + 1 = 105 integration).
- `except EOFError, OSError:` in the new child target is PEP 758 syntax, valid on the
  repo's Python 3.14 floor and explicitly blessed by AGENTS.md item 11.

## Verdict

Verdict: Ship. Fix 1 first (one line in the plan notes, or two test lines).

Not checked: no tests were run, per instructions; CI green is assumed. The claimed
test counts were not independently verified.
