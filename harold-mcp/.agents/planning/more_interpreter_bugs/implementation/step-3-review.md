# Review — Step 3: per-call process executor (uncommitted)

Reviewed: the uncommitted working-tree changes, which implement Step 3 of
`.agents/planning/more_interpreter_bugs/implementation/plan.md` (the checklist
now marks Steps 1-3 done). CI is assumed green and all tests confirmed passing
per the user; I did not run the suites myself.

## What this change does

It replaces the shared `ProcessPoolExecutor` with one dedicated `spawn` process
per interpreter call. `MaudeExecutor` now admits calls through a
`BoundedSemaphore(maude_workers)` — the wait for a slot counts against the
call's whole-call timeout — `start()` verifies initialization with parallel
`ping` processes under one deadline, and `shutdown()` sets a closed flag and
kills every active child. The pool-era helpers (`worker.sleep`,
`worker.rendezvous_pid`, `worker._crash`) are gone from the worker, the
executor unit tests are rewritten around a fake `ProcessRunner`, and the
integration tests move to injected crash/rendezvous targets. Worker exceptions
now cross the process boundary as typed `MaudeWorkerRemoteError`s.

Load assumed: a single IDE agent, at most 3 concurrent interpreters (the
settings cap). The historical cascade regression (B1/B2/B3) is Step 4's work.

## Should fix

1. **`worker.ping` is dead code, and the step notes say it was removed**
   (`src/harold_mcp/maude/worker.py:59-60`)
   - **What this is:** Step 3 removed the pool-only helpers. The
     implementation notes say `worker.ping` "was removed as well" because
     `transport._dispatch` handles the `ping` operation by calling
     `init_maude()` and returning `None`.
   - **Problem:** The function is still there — only its docstring changed. I
     grepped: nothing calls it. The executor sends the `"ping"` operation
     *string*, and the transport never calls `worker.ping`. So the code and
     the notes — the record Step 4 relies on — disagree about what exists.
   - **Fix:** Delete `worker.ping` (two lines). The notes' rationale is right;
     the code should match them. If you would rather keep it, fix the notes
     instead — but deleting is the lean direction.
   - **If we skip it:** Dead code stays in the worker module and the plan's
     history is wrong; a later reader wastes time confirming it is unused.

## Nice to have

2. **`start()` can spawn a doomed child when the ping deadline is exhausted**
   (`src/harold_mcp/maude/executor.py:108-110`)
   - **What this is:** Each startup ping passes `max(remaining, 0.0)` as the
     runner timeout.
   - **Problem:** When the shared deadline is used up (say the first ping
     hangs with `HAROLD_MAUDE_WORKERS=3`), pings 2 and 3 call `runner.run`
     with a zero budget: the runner spawns a child, sends the request, then
     immediately raises a timeout and kills the child. The step notes added
     exactly this guard to `_run_operation` ("instead of handing a
     zero/negative budget to the runner, which would spawn a doomed child"),
     but the ping path was left without it.
   - **Fix:** In `ping()`, raise
     `MaudeWorkerTimeoutError(context={"phase": "init"})` when
     `remaining <= 0`, before calling `runner.run`.
   - **If we skip it:** A pathological startup wastes one short-lived process
     per extra worker (each starts loading the prelude, ~100 MB, then is
     killed). No wrong result: the failure is still typed and mapped to
     `MaudeInitError`.

3. **The post-admission budget check has no test**
   (`src/harold_mcp/maude/executor.py:163-165`)
   - **What this is:** After a call wins the semaphore, `_run_operation`
     re-checks the remaining budget and raises a timeout before spawning when
     it is exhausted — a deviation the notes added.
   - **Problem:** No unit test pins this branch. A test would hold the
     semaphore until the budget is nearly gone, then assert a timeout and
     that the fake runner recorded no call.
   - **Fix:** Add that one unit test next to
     `test_admission_timeout_names_the_slot`.
   - **If we skip it:** If the check is ever dropped, the visible behavior
     barely changes (the runner spawns and times out anyway) — but the notes
     promise the guard, and only a test keeps it.

4. **Stale pool wording in the `Settings` docstring**
   (`src/harold_mcp/settings.py:24-26`)
   - **What this is:** The `HAROLD_MAUDE_WORKERS` bullet still says workers
     are transient "(`max_tasks_per_child=1`)".
   - **Problem:** There is no pool and no `max_tasks_per_child` any more; the
     mechanism is the per-call runner. This docstring is rendered into the
     API docs by mkdocstrings, so the stale sentence would survive Step 6's
     documentation pass unless the code is edited (Step 6 only names README,
     `docs/modules.md` and the changelog).
   - **Fix:** Reword to the fresh-process phrasing already used in
     `_default_maude_workers` ("each task runs in a fresh process").
   - **If we skip it:** The published docs describe a mechanism that no
     longer exists.

## What I checked and found solid

- Admission and timeout accounting match the design (FR-3, B3): the semaphore
  wait counts against the whole-call budget, the runner receives what
  remains, and the no-slot timeout names the slot. The semaphore is released
  in `finally` only after a successful acquire (`BoundedSemaphore` would
  catch an over-release).
- The shutdown window is closed twice, as designed (§4.1, §4.2 step 4): the
  executor's `_closed` check before the runner, and the runner's
  register-and-check under one lock. A call in flight during shutdown
  surfaces as `MaudeWorkerCancelledError` — including the crash-while-closed
  remap (which keeps the crash's pid context and cause) and the stray
  `CancelledError` mapping.
- `start()` builds a fresh runner, clears `_closed`, pings in parallel under
  one deadline, and on failure kills and discards the runner so a later call
  retries lazily; restart after shutdown works and is tested. The failure
  path preserves the first failure's context and remote traceback in the
  raised `MaudeInitError`.
- The server process still never imports the `maude` bindings (the executor
  imports `worker` only for the `LoadDiagnosticsResult` TypedDict;
  worker/session/transport keep the import lazy), and no runtime dependency
  was added (`ThreadPoolExecutor` for the pings is stdlib).
- Runner errors propagate unchanged while the executor is open. The session
  `path_mode` programming error now crosses the boundary as
  `MaudeWorkerRemoteError` with type, message and traceback preserved — the
  documented contract change (design §5.5), with the integration test
  updated to assert it.
- Unit coverage matches the plan's Step 3 list line by line (all runner error
  categories, admission timeout and serialization, start pings/failure/
  restart, shutdown idempotence, lazy creation, crash-while-closed, stray
  `CancelledError`). The rendezvous integration test proves two concurrent
  calls use two distinct processes without sleeps, and it genuinely fails if
  the executor serializes (the target times out after 30 s and the assertion
  on the result count fires).
- The remaining raw `ProcessPoolExecutor` in
  `tests/integration/test_maude_worker_integration.py` is a documented,
  plan-sanctioned deferral to Step 4 (worker-level capture coverage), not a
  remnant of the production path.

## Verdict

Verdict: Ship. Fix finding 1 when convenient — ideally before Step 4 builds
on the notes.

Lean: -2 lines possible (`worker.ping`).

Not checked: the test suites (user confirmed all passing; `make release`
assumed green); the B1/B2/B3 real-load cascade matrix, which is Step 4's
work.
