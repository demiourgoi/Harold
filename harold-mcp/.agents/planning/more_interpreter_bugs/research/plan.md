# Research plan — more interpreter bugs

Goal: reproduce **every** error observed in `reproduction_attempt-2.md`,
`reproduction_attempt-3.md` and `reproduction_attempt-4.md` on the current checkout,
pin each root cause, and gather the evidence needed to choose an isolation strategy
for the worker pool.

Scope decisions agreed with the user:

- The three reproduction attempts capture all errors found on the original host.
- **Python-level probes are authoritative.** The live MCP server would need a restart
  to reflect this checkout, and probes are faster and more flexible. Tool-surface
  checks are corroboration only.
- Primary references: the local `maude-bindings` source and the CPython 3.14 stdlib
  source (as installed in the project venv).
- Pool architecture is in scope: evaluate whether one `ProcessPoolExecutor` with
  several processes is the right design, versus several single-process pools or
  [pebble](https://github.com/noxdafox/pebble).

## Current tree

- `HEAD` = `9272529` ("rough idea for PDD project for more interpreter bugs").
- The attempt-3 instrumentation is **not applied**; it exists only as
  `reproduction_attempt-3.diff`.
- The previous PDD's fixes are present: `capture_streams` flushes C/Python stdio
  inside the capture window, and `maude_run` surfaces the exception type/message in
  its wrapper error.

## Bug inventory to verify

| ID | Symptom | Source | Code path |
| --- | --- | --- | --- |
| B1 | Generic `Unexpected failure running the Maude interpreter session: CancelledError` | attempt-4 | `CancelledError` escapes `_run_task` |
| B2 | `Maude worker crashed` in healthy concurrent calls | attempt-2, attempt-4 | `_reset_executor` → `kill_workers()` kills the shared pool |
| B3 | A queued timeout (no worker ever started) still replaces the pool | attempt-4 | `_run_task` timeout branch cannot distinguish queued from running |
| B4 | Successful `search` step returned `output.stdout == ""`; block surfaced in another step's stdout | attempt-2 | step capture / libmaude buffering |
| B5 | `MaudeInitError` would be mislabelled as "Unexpected failure" | attempt-2 | `MaudeInitError` is not a `MaudeWorkerError`; reachability unverified |
| B6 | `submit` `RuntimeError` after shutdown / spawn `OSError` bypass the mapping | attempt-2, attempt-3 | `_submit` catches only `BrokenProcessPool`; reachability unverified |
| B7 | Lost load output tail for a bounded search at end of file | previous PDD | already fixed; regression-check only |

## Probes

1. `probes/probe_cpython_pool.py` — stdlib semantics on CPython 3.14:
   - `future.cancel()` on queued vs running tasks;
   - `kill_workers()` outcome for pending vs running futures (repeat trials to
     measure the `CancelledError` / `BrokenProcessPool` split);
   - whether a timed-out future whose task is running can be cancelled.
2. `probes/probe_pool_cascade.py` — real `MaudeExecutor` + real workers:
   - attempt-4 recipe: 3 slow reductions + 1 non-terminating reduction with
     `timeout_secs=2` + 4 healthy searches;
   - per-call outcome, repeated to quantify the race;
   - whether a queued timeout's `future.cancel()` reports `True`.
3. `probes/probe_step_output.py` — `run_session` with real workers:
   - bounded `search` step output capture (B4);
   - bounded search as the last command in the loaded file (B7 regression).
4. `probes/probe_error_taxonomy.py` — exception hierarchy and reachability checks
   (B5, B6), plus which exceptions the tool maps to which message.
5. Source reading — CPython 3.14 `concurrent/futures/process.py`,
   `maude-bindings` search/print behavior, pebble crash/timeout semantics.
6. `research/architecture-options.md` — compare:
   - current single pool of N workers;
   - N pools of one worker (managed lifecycle, per-slot isolation);
   - pebble `ProcessPool` (restart/crash handling, timeout semantics);
   - per-call dedicated process.

## Deliverables

- `research/reproduction.md` — what reproduced, how often, exact messages.
- `research/cpython-pool-semantics.md` — verified stdlib behavior with source links.
- `research/step-output.md` — step capture findings.
- `research/error-taxonomy.md` — hierarchy/reachability for B5/B6.
- `research/architecture-options.md` — pool isolation options and trade-offs.

## Status (research complete)

All probes have run on `HEAD` = `9272529`, Python 3.14.2:

- B1/B2/B3 reproduced deterministically (`reproduction.md`).
- B4/B7 do not reproduce on this checkout (`step-output.md`).
- B5/B6 analyzed for reachability (`error-taxonomy.md`).
- Pool options evaluated with the stdlib source and a pebble 5.2.3 probe
  (`architecture-options.md`).

Open decision before design: accept pebble (LGPL-3.0) or implement N single-worker
pools (stdlib only).
