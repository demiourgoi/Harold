# Review — implementation plan vs detailed design (`more_interpreter_bugs`)

Reviewed: `implementation/plan.md` against the normative
`design/detailed-design.md` (the revision that absorbed all three review
rounds), with the current sources re-checked (`maude/executor.py`,
`maude/worker.py`, `maude/session.py`, `maude/provider.py`,
`diagnostics/aggregate.py`, `server/tools/interpreter.py`,
`server/tools/diagnostics.py`, `settings.py`).

**What this change does:** The plan turns the approved design into six
test-driven steps: rich errors first (still on the current pool), then the
one-shot pipe transport and process runner, then the executor swap, real
process isolation and regression tests, diagnostics parity, and
documentation. This review checks whether the plan schedules everything the
final design requires, contrads nothing in it, and carries the design's test
plan.

**Compliance summary:** The plan tracks the post-review-3 design on every
point the reviews fought over: the `<category>: <message>` first line, the
remote cause as the final chain element, the uncapped log vs capped client
text, the fresh-runner restart, the crash-to-cancelled re-map, the
stdio-redirect failure path, and the pool-helper removals. Component
coverage is complete except one production change (finding 1). The step
order keeps every increment testable, and the completion criteria enforce
the design's end state. The gaps are omissions, not contradictions.

## Must fix

1. **The session phase annotation has no step** (design §4.4; plan Step 2)
   - **What this is:** The design requires `session.run_session` to annotate
     unexpected exceptions with `{"phase": "load"}` around the load and
     `{"phase": "step", "step": index, "command": command}` around each
     step, read by `transport.serve_one` through `_worker_context(exc)`.
   - **Problem:** The plan lists `_worker_context` in Step 2's transport
     module but never schedules the writer: no step touches
     `maude/session.py`. Followed literally, `_worker_context` reads an
     attribute nothing sets, remote exceptions lose the step context that
     ER-3/FR-7 and the §6.2 example promise, and two design tests are left
     unscheduled — §7.1's "Session phase annotation" unit test and
     review-finding-9's `test_load_failure_has_phase_load` (Step 4 references
     "the review findings" only generically).
   - **Fix:** Add one bullet to Step 2's guidance (annotate load/step phases
     in `session.run_session`; the transport reads the annotation) and the
     phase unit test to Step 2's test requirements.
   - **If we skip it:** the step context silently never reaches clients, and
     the gap surfaces mid-Step-4 as a failing test with no plan home.

## Should fix

2. **The `pid` context key is never mentioned** (design ER-3, §4.5, §6.2;
   plan Steps 1–2)
   - **What this is:** The design's context line includes the worker pid
     (`context: path=..., module=M, step=2 (rewrite), timeout=60s,
     pid=12345`), and §4.5 names pid as a worker-specific key carried in the
     exception's own context.
   - **Problem:** The plan's Step 1 tool context is "(resolved path, module,
     step count, timeout)" and Step 2's runner guidance never says
     constructed errors carry `pid`. The runner is the only component that
     knows the child pid; no plan test asserts it.
   - **Fix:** One clause in Step 2's runner guidance (errors carry
     `pid=proc.pid` in their context) and a context assertion in a Step 1/2
     test.
   - **If we skip it:** every whole-call failure is missing the pid ER-3
     promises, and the §6.2 example cannot be reproduced.

3. **Step 2 drops the envelope-mapping and fake-dispatch unit tests**
   (design §7.1, §5.5; plan Step 2)
   - **What this is:** The design's transport test list includes "child
     error envelope mapping by `category`" (init → `MaudeInitError`, remote →
     `MaudeWorkerRemoteError`, protocol → `MaudeWorkerProtocolError`) and
     "`serve_one` dispatch with a fake operation (no Maude import)".
   - **Problem:** The plan's Step 2 test list has neither, and no other step
     covers the mapping: Step 1's tool tests fake the executor, Step 3's
     executor tests fake the runner, and the real children in Step 4 only
     produce crash/timeout. The `init`, `remote` and `protocol` envelope
     mappings would ship untested.
   - **Fix:** Add the two test bullets to Step 2 (a fake connection
     returning error envelopes per category; a dispatch test with the
     dispatch seam faked so no Maude import happens).
   - **If we skip it:** a mapping regression (say `remote` mislabeled
     `protocol`) reaches clients with no test failing.

4. **Step 1 drops the cycle guard and the truncation marker** (design §4.5,
   §6.3, §7.1, ER-4; plan Step 1)
   - **What this is:** The formatter must walk `__cause__`/`__context__`
     with an identity set — a `__context__` cycle would loop a naive walk
     forever — and append a truncation marker whenever the cap shortens the
     text. Both have named §7.1 tests.
   - **Problem:** The plan's Step 1 guidance ("cause chain starting with the
     exception itself, then `__cause__`/`__context__`...") and its test list
     ("truncation order, huge-first-line last resort") omit both. The marker
     is what tells the client the server log holds the rest (ER-4).
   - **Fix:** Add "with a cycle guard" to the guidance and "cycle guard" +
     "marker" to the test list.
   - **If we skip it:** the chain walk hangs on a cyclic exception, or the
     marker is forgotten and the truncation note points nowhere.

5. **Input errors do not gain the context line** (design §4.6, §6.1; plan
   Step 1)
   - **What this is:** The design says input errors (missing file, missing
     module, theory module) "keep their specific messages and gain the same
     context line", and §6.2 says the context line is present for every
     whole-call failure.
   - **Problem:** The plan's Step 1 only rewrites the two except branches
     (`_exception_detail` at `interpreter.py:489`/`:656`). The input-error
     raise sites (`interpreter.py:328`–`:382` for path/steps validation,
     `:509`–`:518` for load/module/theory checks) are outside those branches,
     are not touched by any step, and no test covers their context.
   - **Fix:** One bullet in Step 1's guidance (input-error raises gain the
     context line) plus a test assertion.
   - **If we skip it:** the most common failure class stays context-free and
     §6.2's "context line is present for every whole-call failure" is
     violated.

## Nice to have

6. **Settings tests are not scheduled** (design §7.1; plan Steps 1–2). The
   design lists "Settings: the two new fields and their defaults"; the plan
   adds both fields but lists no settings test. `tests/unit/test_settings.py`
   exists — add the two default assertions.
7. **Step 2's dispatch summary omits "init first"** (design §4.3; plan
   Step 2). `_dispatch` must call `worker.init_maude()` before every
   operation — that is what makes `ping` a real initialization check
   (FR-9). The plan says only "dispatch ping/diagnostics/session with lazy
   worker/session imports"; if ping skips init, `start()`'s fail-fast is
   vacuous and no plan test notices. One clause.

## Verdict

**Verdict: fix 1 before starting; batch 2–5 (one-line plan edits) into the
same pass.** The plan is otherwise a faithful schedule of the final design:
all review-3 fixes are reflected, the step order keeps every increment
testable, and the completion criteria enforce the design's end state (no
pool remnants, no `maude` import in the server, full gate green).

**Not checked:** the research probes' recorded outputs (taken at face value,
as in the design reviews); `idea-honing.md` wording (review 3 already tracks
its two stale sentences; the plan correctly follows the design where the two
documents differ).
