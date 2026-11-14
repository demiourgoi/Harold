# Review — Step 4: real-process isolation, regression, and pool-remnant cleanup (uncommitted changes)

Reviewed the uncommitted diff (8 modified files, 2 new) against the "Step 4"
section of `.agents/planning/more_interpreter_bugs/implementation/plan.md` and
the design's B0–B7 bug matrix. All suites are assumed green per the task; I ran
no tests.

## What this change does

This step finishes the move from the shared worker pool to one process per
interpreter call. It adds the design's regression suite as
`tests/integration/test_process_isolation_integration.py` (the historical
B1/B2/B3 cascade, a running timeout beside a healthy peer, and shutdown with an
in-flight call leaving no orphans), pins B4 step-capture behavior and
theory-module rejection, rewrites the last pool-era test file around
`MaudeExecutor`, and removes the remaining pool wording. The only production
change is in the runner: a `_terminate_lock` that stops `kill_all()` and a
call's own `finally` from running `Process.close()` at the same time.

## Must fix

1. **The pipe close still races between a call and shutdown**
   (`src/harold_mcp/maude/runner.py:188` and `:273`)
   - **What this is:** Step 4 found that `kill_all()` and a call's own `finally`
     could enter `Process.close()` at the same time, and added `_terminate_lock`
     to serialize the kill/join/close sequence. But the pipe close,
     `parent.close()`, runs *outside* that lock at both call sites.
   - **Problem:** Python 3.14's `Connection.close()` is not safe when two
     threads call it on the same object: both pass the
     `if self._handle is not None` check, the winner sets `_handle = None`, and
     the loser then calls `os.close(None)` — a `TypeError` (verified on this
     interpreter) — or closes an already-closed fd, an uncaught `OSError`. The
     `try/finally` in `Connection.close()` suppresses neither. So the same race
     the step fixed for the process object is still open for the connection: a
     call completing at the moment of shutdown can lose its typed error to a
     raw `TypeError` (its `finally` then skips the unregister and the kill), or
     `kill_all()`'s loop can die mid-way, abort `executor.shutdown()` inside the
     lifespan's teardown, and leave the remaining children unkilled — a child
     stuck in a non-terminating Maude rewrite would then survive the server,
     because the `os._exit(0)` exit path skips multiprocessing's cleanup. No
     test pins this: the shutdown test's call is blocked in `poll`, so its
     close runs strictly after `kill_all()`'s.
   - **Fix:** Move `parent.close()` inside the existing
     `with self._terminate_lock:` block at both places. No new lock, no order
     change.
   - **If we skip it:** Shutdown overlapping a finishing call occasionally
     produces an untyped error or an orphaned child — the exact B6 failure mode
     this step was meant to close.

## Nice to have

2. **The cascade test target copies the transport's error mapping**
   (`tests/integration/test_process_isolation_integration.py:138-143`)
   - **What this is:** `_cascade_target` re-implements the
     protocol/init/remote category mapping that `transport.serve_one` uses when
     a dispatched operation raises.
   - **Problem:** If the transport's mapping changes (a new category, a renamed
     error), the test target silently diverges and the cascade tests keep
     passing against the old mapping.
   - **Fix:** Extract the mapping into a small transport helper (for example
     `transport._error_category(exc)`) and call it from both `serve_one` and
     the test target.
   - **If we skip it:** A future transport change needs a second edit in test
     code that review can easily miss.

3. **The step notes name a runner edit that did not happen**
   (`.agents/planning/more_interpreter_bugs/implementation/plan.md`, Step 4
   notes)
   - **What this is:** The notes say pool wording was removed from
     "`test_lifespan.py`, the server lifespan docstrings and the runner
     comments".
   - **Problem:** The runner diff only adds the `_terminate_lock`; the committed
     runner never had pool wording (it was created after the pool, in Step 2).
     A reader auditing the step's claims will search for a change that is not
     there.
   - **Fix:** Drop "the runner comments" from that sentence in the notes.
   - **If we skip it:** The step record keeps one false claim; harmless but
     misleading for the Step 6 documentation pass.

## Verdict

Verdict: fix 1 first.

Lean: -10 lines possible (finding 2 removes the duplicated mapping).

Not checked: test execution — the task said to assume all suites pass; I
reviewed the diff against the plan's Step 4 section and the design's B0–B7
matrix only.
