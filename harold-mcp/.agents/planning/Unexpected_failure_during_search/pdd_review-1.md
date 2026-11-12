# Review — `Unexpected_failure_during_search` PDD vs the codebase (commit `006173f`)

What this change does: The PDD record behind the "Unexpected failure running the
Maude interpreter session" bug report turned out to contain two independent defects,
and commit `006173f` fixes both. First, `capture_streams` now flushes Python and
C/C++ stdio buffers while the capture descriptors are still installed, so a load
whose last command is a bounded `search` no longer loses its result block, and those
bytes can no longer surface later on the worker's inherited stdout (the MCP stdio
transport). Second, `maude_run`'s generic catch-all error now includes the exception
type and message and logs the traceback server-side, so the still-unreproduced
original failure becomes diagnosable the next time it occurs.

Scope reviewed: the PDD documents (`rough-idea.md`, `design/detailed-design.md`,
`implementation/plan.md`), the research record and probes, the changed code
(`maude/capture.py`, `server/tools/interpreter.py`), every caller of
`capture_streams` (`worker.load_diagnostics`, the session load phase, both step
paths), the tests, the changelog and the knowledge base.

Verification run in this review: unit suite 269 passed; session integration 37
passed (including the new bounded-search regression); remaining integration 52
passed; `make check` clean (lockfile, ruff, format, mypy, basedpyright, deptry).
`make release` (install, check, full sequential test, docs-test) is reported
passing by the user and was not re-run here.

## Design conformance (R1-R7)

- **R1 complete capture** — met. The flush runs in the `finally` before the fds are
  restored, on both the success and exception paths; the integration test proves the
  real-interpreter case (`Solution 1 (state 0)` in `load_output`).
- **R2 no leak** — met. The flush happens inside the window; the no-leak unit test
  pins the placement (it would catch a flush moved after the restore), and probe
  `test_f_no_leftover_flush_to_inherited_stdout` checks the end-to-end property.
- **R3 safe flushing** — met in code (all failures suppressed; pre-redirect flush
  keeps pre-existing output out of the capture). One test gap, finding 2.
- **R4 no semantic changes** — met. Models, outcomes, caps and hermetic behavior are
  untouched; the only wire-visible change is the richer error text, and the old
  message is a prefix of the new one, so clients matching the old string keep working.
- **R5 diagnosable errors** — met. `_exception_detail` renders `TypeName: message`
  (type only when the message is empty), the cause stays chained, and the traceback
  is logged. Two gaps, findings 3 and 4.
- **R6 regression tests** — met. All four required test groups exist and pass.
- **R7 compatibility** — met. No new dependencies; the full suite and static checks
  pass (verified here; `make release` per the user).

## Findings

### Should fix

1. **The committed knowledge base still describes this fix as not existing**
   (`.agents/summary/components.md:479-482`, `.agents/summary/review_notes.md`
   remaining issue 12 and recommendation 4, `.agents/summary/architecture.md`
   decision 14, `AGENTS.md` gotcha 21)
   - **What this is:** The repo's convention (AGENTS.md instruction 15) is that
     `.agents/summary/` is committed, trusted by agents, and refreshed after
     significant changes. This change altered the capture contract and completed the
     planning record, but the knowledge base predates it.
   - **Problem:** `components.md` still says the record is "untracked, in-progress
     ... the research/design/implementation directories are still empty. No fix or
     design yet" — every part of that is now false (the record is tracked and
     complete, and the fix is in). `review_notes.md` still calls the record
     "untracked". `architecture.md` decision 14 and AGENTS.md gotcha 21 describe the
     capture without the flush, so "stdio is flushed inside the capture window" is
     not part of the documented contract. An agent consulting the knowledge base,
     as this repo instructs, gets a wrong picture of the capture layer.
   - **Fix:** Run the codebase-summary refresh — already next-step 2 in the PDD
     `summary.md`. Until then the PDD record is the accurate one.
   - **If we skip it:** The next agent touching capture or the search-failure
     investigation trusts stale facts — it may re-diagnose the output loss as
     unfixed, or change the capture without knowing the flush is load-bearing.

2. **The flush-failure suppression has no test** (`src/harold_mcp/maude/capture.py:81-99`)
   - **What this is:** `_flush_stdio` wraps each flush in `contextlib.suppress(Exception)`
     so a flush failure can never mask the phase result or exception (design R3), and
     an unsupported platform degrades to the previous behavior instead of breaking
     every call (design Appendix D).
   - **Problem:** No test exercises a failing flush. If a later refactor removes the
     suppress blocks (for example to "stop hiding flush errors"), no test fails, and
     from then on a flush error replaces the phase result on every capture. A
     concrete trigger exists today: with `sys.stdout` set to `None` (embedded
     contexts), `sys.stdout.flush()` raises `AttributeError` — suppressed now, a
     crash after such a refactor.
   - **Fix:** One unit test: make `ctypes.CDLL` (or `sys.stdout.flush`) raise inside
     `capture_streams` and assert the callable's result and captured output still
     come back unchanged.
   - **If we skip it:** R3 rests only on the suppress blocks staying in place;
     nothing fails if they are removed.

### Nice to have

3. **The traceback logging is not asserted** (`src/harold_mcp/server/tools/interpreter.py:650`)
   - **What this is:** R5 requires the server to log the traceback; `_log.exception(...)`
     does it before raising `MaudeRunError`.
   - **Problem:** The wire text is tested; the log call is not. Deleting the log line
     passes the whole suite, and the server-log half of the diagnostic gap silently
     returns — the client text alone carries no traceback.
   - **Fix:** Extend one existing error test with a `caplog` assertion (or a monkeypatched
     module `_log`) that an ERROR record with the exception was emitted.
   - **If we skip it:** The client-visible half of R5 stays tested; only the log half
     is unpinned.

4. **The unexpected-failure log line carries no request context**
   (`src/harold_mcp/server/tools/interpreter.py:650-653`)
   - **What this is:** The log message is the fixed sentence; `resolved` (the path)
     and `module` are in scope at that point but are not included.
   - **Problem:** When the original failure recurs on the slower host, the traceback
     alone will not say which file or module was running; correlating the server log
     to the client's call is manual. The research note itself asks that the next
     occurrence include the request context.
   - **Fix:** Include them in the log call, e.g.
     `_log.exception("Unexpected failure running the Maude interpreter session for %s (module %s)", resolved, module)`.
   - **If we skip it:** The next occurrence is still diagnosable from the client
     transcript plus the traceback; attribution is just slower.

## General feedback on the design

- **The research record is the strongest part.** It refuted the original host's
  "missing end-of-block terminator" theory with a decisive probe (`fflush` inside the
  window recovers the block; Harold never frames load output), separated confirmed,
  refuted and unproven claims in a table, and resisted claiming the capture bug
  explained the original error — buffered output cannot raise inside the session
  engine. The two-defect framing is correct and the design acts on it.
- **The fix is minimal and at the right layer.** Appendix A's rejection of the
  alternatives is sound: transport-level filtering is too late, unbuffering fd 1
  cannot flush an existing `FILE*` buffer, and line-buffered capture changes global
  semantics. `ctypes` + `fflush(NULL)` is the smallest change that covers libmaude's
  output path with no new dependency.
- **Honest limitations, guarded by tests.** C++ iostreams are only covered when
  synchronized with C stdio (the default). If a future Maude wheel changes its output
  path, tail loss could return silently — the committed integration regression
  (bounded search as the last load command) is exactly the guard for that, keep it.
- **The error-surfacing half deliberately does not speculate.** It does not pretend
  to fix the unreproduced original failure; it makes the next occurrence actionable
  (client-visible type and message, server-side traceback). That is the right scope.
  The residual risk is that the failure never recurs on a host running the new build;
  nothing more can be done until then, and the record says so.
- **Process discipline.** The plan's working agreements were followed, and the one
  deviation (the removed step-stdout test) was investigated, explained in the plan,
  and fed back into the research record — the bindings' step APIs print nothing, so
  step stdout is empty by design. That is how a deviation should be handled.

## General feedback on the coding changes

- The diff is tight: 28 lines in `capture.py`, 19 in `interpreter.py`, plus tests.
  No new public API, no new settings, no new dependencies, no scope creep.
- `_flush_stdio`'s docstring explains the why (buffering independence of C/C++
  streams, the leak path, the suppression rationale), and the `finally` comment
  states the invariant ("flush while the capture fds are still in place"). Both will
  age well.
- The test pair is well designed: the C-buffer unit test is the discriminating
  regression (it fails without the flush), and the no-leak test pins the flush
  placement (it fails if the flush moves after the restore). The integration test
  proves the real-interpreter case end to end.
- `_exception_detail` handles the empty-message case, and the old wire text remains
  a prefix of the new one, so string-matching clients keep working.
- All four `capture_streams` call sites (worker load, session load, both step paths)
  go through the fixed helper; there is no bypass path.

Verdict: Ship.

Not checked: the research probes under
`.agents/planning/Unexpected_failure_during_search/research/probes/` were not
executed in this review (they live outside `tests/` and need the real interpreter;
the committed integration regression covers the same post-fix behavior).
`make test` (full sequential) and `make docs-test` were not re-run here; the user
reports `make release` passing, which covers both.
