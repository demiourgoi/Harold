Reproduced — and the root cause is now pinned

**Minimal recipe** (all calls in one batch, `maude_workers` defaults to ≤ 3):

1. Three slow reductions (`count(10000000)`) — occupy every worker.
2. One non-terminating reduction (`eq f(X) = f(f(X))`, `reduce f(a)`) with `timeout_secs: 2` — queued, so it times out *while queued*.
3. Four healthy `search` calls with `timeout_secs: 60` — queued behind the others.

Observed:

```
slow  → Maude interpreter session failed: Maude worker crashed
slow  → Unexpected failure running the Maude interpreter session: CancelledError
slow  → Unexpected failure running the Maude interpreter session: CancelledError
loop  → Maude interpreter session failed: Maude worker timed out
shep  → Unexpected failure running the Maude interpreter session: CancelledError
shep  → Unexpected failure running the Maude interpreter session: CancelledError
shep  → Maude interpreter session failed: Maude worker crashed
shep  → Maude interpreter session failed: Maude worker crashed
```

A simpler cascade (9 identical 2 s calls) produced 2 `CancelledError`s. Subsequent calls recover cleanly.

## Mechanism (verified against CPython 3.14)

1. The queued call's `future.result(timeout=2)` raises `TimeoutError`.
2. `executor._run_task` → `_reset_executor(failed=executor)` → `old.kill_workers()`.
3. `ProcessPoolExecutor.kill_workers()` is `_force_shutdown(operation=_KILL)`, whose first act is **`self.shutdown(wait=False, cancel_futures=True)`** — this *cancels* every pending work item.
4. The manager thread's `_terminate_broken` also marks pending futures with `BrokenProcessPool`, but with exactly this comment:
   > `set_exception() fails if the future is cancelled: ignore it.`
5. So each pending future ends up either **cancelled** (`CancelledError`) or **broken** (`BrokenProcessPool`), depending on who wins.
6. `_run_task` catches only `BrokenProcessPool` and `TimeoutError`; `concurrent.futures.CancelledError` has MRO `CancelledError → Error → Exception`, so it escapes `run_session`, hits `maude_run`'s `except Exception`, and becomes the generic message.

This is a **race**, which explains the non-determinism: on the slower host, `max_tasks_per_child=1` means every task pays spawn + prelude init, so many calls sit pending for long — the cancellation wins far more often. It also means bug 2 **is** downstream of the pool kill after all: same trigger as the collateral-damage bug, different race outcome. (The earlier `No tool named maude_run exists` remains unrelated — that was the server restart.)

## Fix

Minimal, two parts (both in `MaudeExecutor`):

1. **Map the cancellation.** Catch `concurrent.futures.CancelledError` in `_run_task` and raise a worker error — best a new `MaudeWorkerCancelledError(MaudeWorkerError)` with reason `"Maude worker call was cancelled"`, so the client gets `Maude interpreter session failed: …` instead of "Unexpected failure". Required regardless, because another call can always cancel this call's pending future.
2. **Don't kill the pool for a timeout that never started a worker.**
   ```python
   except TimeoutError as exc:
       if future.cancel():          # still pending: no stuck worker to kill
           raise MaudeWorkerTimeoutError() from exc
       self._reset_executor(failed=executor)
       raise MaudeWorkerTimeoutError() from exc
   ```
   This removes the most common trigger of the cascade (queueing timeouts) and the collateral damage it causes.

Optional third part: retry once a call whose future was cancelled by *another* call's pool replacement (it provably never ran) — but the tool's documented contract says "the failed call is never retried", so that's a design decision for you.

Want me to implement 1 + 2 with regression tests (a cancelled-future test and a "queued timeout does not replace the pool" test)? I'd also keep the instrumentation as is — it's what made this diagnosable.

```maude
fmod LOOP is
  sort S .
  op a : -> S [ctor] .
  op f : S -> S .
  var X : S .
  eq f(X) = f(f(X)) .
endfm

fmod SLOW is
  protecting NAT .
  op count : Nat -> Nat .
  var N : Nat .
  eq count(0) = 0 .
  eq count(s(N)) = count(N) .
endfm
```
