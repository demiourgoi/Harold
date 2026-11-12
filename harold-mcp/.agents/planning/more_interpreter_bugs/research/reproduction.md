# Reproduction record — pool cascade, CancelledError, and what did not reproduce

Environment: Python 3.14.2 (`uv`-managed venv), `HEAD` = `9272529`, `maude==1.6.0`,
`maude_workers = 3` for the cascade scenarios. All probes are Python-level and use the
real `MaudeExecutor` with real spawned Maude workers. Probe sources live in
`probes/`; every number below is observed output, not an estimate.

## 1. The cascade reproduces deterministically

### 1a. Attempt-4 recipe with finite slow reductions (`probes/probe_pool_cascade.py finite`)

Three `rewrite spin(0, 60M)` calls occupy the three workers (~9.5 s each on this
host), then a non-terminating `rewrite f(a)` with `timeout=2`, then four healthy
`search` calls with `timeout=60`:

| Call | Outcome | Cause | Elapsed |
| --- | --- | --- | --- |
| occupier-0 | `MaudeWorkerCrashedError: Maude worker crashed` | `BrokenProcessPool` | 4.0 s |
| occupier-1 | `MaudeWorkerCrashedError: Maude worker crashed` | `BrokenProcessPool` | 4.0 s |
| occupier-2 | `MaudeWorkerCrashedError: Maude worker crashed` | `BrokenProcessPool` | 4.0 s |
| trigger | `MaudeWorkerTimeoutError: Maude worker timed out` | `TimeoutError` | 2.0 s |
| search-0 | `MaudeWorkerCrashedError: Maude worker crashed` | `BrokenProcessPool` | 2.0 s |
| search-1 | `MaudeWorkerCrashedError: Maude worker crashed` | `BrokenProcessPool` | 2.0 s |
| search-2 | `MaudeWorkerCrashedError: Maude worker crashed` | `BrokenProcessPool` | 2.0 s |
| search-3 | **`CancelledError`** (escapes `_run_task`) | — | 2.0 s |

At the tool boundary, `search-3` becomes
`MaudeRunError("Unexpected failure running the Maude interpreter session: CancelledError")`
(the committed `_exception_detail` renders the type). This is **B1**, and the three
searches plus three occupiers are **B2**.

### 1b. Infinite occupiers (`... infinite`)

Same shape with three non-terminating `rewrite` calls instead of finite spinners:

| Call | Outcome |
| --- | --- |
| occupier-0..2 | `MaudeWorkerCrashedError` |
| trigger | `MaudeWorkerTimeoutError` |
| search-0 | `MaudeWorkerCrashedError` |
| search-1 | `MaudeWorkerCrashedError` |
| search-2 | **`CancelledError`** |
| search-3 | `MaudeWorkerCrashedError` |

Which search gets the `CancelledError` varies between runs (`search-3` in 1a,
`search-2` in 1b): it is a race, but at least one pending future always loses.

### 1c. The trigger never started

The trigger was submitted while all three workers were busy. Its work item was
dispatched to the pool's call queue and marked `RUNNING`, but no worker ever began
executing it. `probes/probe_pool_cascade.py cancel` submits six calls to the
saturated executor and reports:

```
future.cancel() -> [False, False, False, False, True, True]
result -> TimeoutError
result -> TimeoutError
result -> TimeoutError
result -> TimeoutError
result -> CancelledError
result -> CancelledError
```

So `future.cancel()` is `False` for the first four (three workers + one extra queued
call) and `True` only for the tail. This invalidates the proposed fix from
attempt 4 (`if future.cancel(): ...`): a timed-out call that is queued **inside the
call-queue buffer** never starts a worker yet cannot be cancelled, so the code would
still kill the pool. See `cpython-pool-semantics.md` for the source-level reason.

## 2. Exact mechanism

1. `maude_workers=3` → `ProcessPoolExecutor(max_workers=3, max_tasks_per_child=1)`.
2. Three occupiers run; the trigger and the searches are submitted. The pool's call
   queue holds `max_workers + EXTRA_QUEUED_CALLS = 4` work items; `add_call_item_to_queue`
   calls `future.set_running_or_notify_cancel()` when it puts an item on that queue,
   so those futures report `running() == True` even though no worker has started them.
3. The trigger's `future.result(timeout=2)` raises `TimeoutError`.
4. `MaudeExecutor._run_task` calls `_reset_executor(failed=executor)`, which swaps in a
   new pool and calls `old.kill_workers()`.
5. `kill_workers()` is `_force_shutdown(_KILL)`: it calls
   `shutdown(wait=False, cancel_futures=True)` and then `Process.kill()` on every
   worker. `cancel_futures=True` only cancels futures for which `future.cancel()`
   returns `True`; the work items in the call queue return `False`.
6. The manager's `_terminate_broken` then sets `BrokenProcessPool` on the remaining
   pending futures and ignores `InvalidStateError` for the ones it managed to cancel.
   The pool's `BrokenProcessPool` propagation is what kills the occupiers and the
   dispatched searches; the items that `shutdown` cancelled raise `CancelledError`.
7. `CancelledError` is a plain `Exception`, not a `BrokenProcessPool` or
   `TimeoutError`, so `_run_task` does not map it and `maude_run`'s generic handler
   reports the "Unexpected failure" text.

## 3. What did **not** reproduce

- **Lost load-output tail for a bounded search at EOF (B7).** The previous PDD's fix
  works: `probes/probe_step_output.py` shows the complete `Solution 1 ...` block in
  `load_output.stdout` when the file ends with `search [1] a =>* Z:S .`.
- **A successful search step's structured solutions with a lost output block (B4).**
  On this checkout every step's `stdout` is empty — because the SWIG bindings return
  values and do not print; `search` returns a `RewriteSequenceSearch` iterator. This
  is expected, not a bug. Step `stderr` still captures parse warnings. The earlier
  "block surfaced in a different step's stdout" is consistent with the pre-fix
  libmaude buffering leak and is not reproducible after the flush fix. Details in
  `step-output.md`.
- **A stale-server effect.** No MCP server is involved in these probes; the results
  are from the current checkout.

## 4. Secondary findings

- A non-terminating **equation** (`eq f(X) = f(f(X))` + `reduce f(a)`) crashed the
  worker with `BrokenProcessPool` (stack/term growth). A non-terminating **rule**
  (`rl f(X) => f(f(X))`) is the safe way to build a "never finishes" probe:
  `rewrite` loops iteratively without dying.
- `count(20M)` takes ~1.3 s on this host including spawn + prelude init; `rewrite
  spin(0, 60M)` takes ~9.5 s. The finite cascade needs an occupier that outlives the
  trigger's timeout.

## 5. Probe inventory

| Probe | Purpose |
| --- | --- |
| `probes/probe_cpython_pool.py` | stdlib `cancel()` / `kill_workers()` semantics |
| `probes/probe_pool_cascade.py` | real-executor cascade (`time`, `finite`, `infinite`, `cancel`) |
| `probes/probe_step_output.py` | step and load capture |
| `probes/probe_pebble.py` | pebble crash/timeout/queue/init/`max_tasks` semantics |
| `probes/fixtures/pool_bugs.maude` | `LOOP` (rewrite loop), `SLOW` (Peano counter), `SPIN` (finite spinner) |
| `probes/fixtures/step_output.maude` | bounded search at EOF |
| `probes/fixtures/shepherd.maude` | copy of the original search fixture |
