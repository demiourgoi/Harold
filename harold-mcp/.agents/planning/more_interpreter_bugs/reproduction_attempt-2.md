I couldn't get a reproduction of the generic message — but I can now bound it to three code paths and rule out everything else. Along the way I found a **different deterministic bug** worth fixing.

## Where the message comes from

```python
except MaudeWorkerError as exc:
    raise MaudeRunError(f"Maude interpreter session failed: {exc.reason}") from exc
except Exception as exc:
    raise MaudeRunError("Unexpected failure running the Maude interpreter session") from exc
```

So bug 2 = any exception from `executor.run_session` that is not a `MaudeWorkerError`. Note the hierarchy trap: `MaudeInitError(MaudeError)` is **not** a `MaudeWorkerError`, so if it ever surfaced from `run_session` it would be mislabelled as "Unexpected failure".

## What I ruled out (all messages observed, not inferred)

| Probe | Result |
|---|---|
| Exact reported payload, 10× concurrent | 10/10 `ok`, 7-transition path each |
| All 5 `search_type`s (incl. `=>#` with a real branching solution, `=>!`, `=>+`) with `path` labels/full | `ok` |
| `depth` = `-1`, `0`, `10`, `2147483647`; `match` max depth | `ok` |
| `erewrite`, `bound`/`gas` set; `rewrite` bound 0 | `ok` |
| Non-terminating reduction (`eq f(X) = f(f(X))`), timeout 2 s | `Maude interpreter session failed: Maude worker timed out` |
| Same, timeout 5 s (worker dies) | `Maude interpreter session failed: Maude worker crashed` |
| Top-level `q .` in the loaded file | `ok` (load ignores it) |
| `CancelledError` hypothesis (`kill_workers` cancelling pending futures) | all pending calls reported **crashed**, not cancelled |

So the payload, the search engine, path reconstruction and the timeout/crash paths all produce *specific* messages.

## The deterministic bug I did find

A call that kills its worker takes down the **shared pool**, and every concurrent healthy call fails:

```
# 8 parallel calls, maude_workers = 3
LOOP   reduce f(a)           timeout_secs=2  →  "Maude worker timed out"
SHEPHERD search goal  ×3     timeout_secs=30 →  "Maude worker crashed"   (3/3)
SLOW   reduce count(2e6) ×4  timeout_secs=60 →  "Maude worker crashed"   (5/5), 2 ok
```

That matches `_reset_executor` → `kill_workers()` on a shared `ProcessPoolExecutor`. It's a real availability bug (a single bad call poisons unrelated calls), and it is the same *shape* as the report: bursts of failures in one call while the model is fine. It is **not** bug 2, because the message is the specific one.

## Why bug 2 looks like lifecycle/transport, not the model

- Identical payloads failed once and succeeded later in the same session; now they succeed 10/10 concurrently.
- During the failure window I got `No tool named maude_run exists` once, then `maude_program_diagnostics` worked, then `maude_run` worked again. That's server/registry churn, not a Maude failure.
- No timeout and no performance component: the dropped load command measured 0 ms / 2125 rewrites, and `timeout_secs=180` changed nothing.

## Remaining paths, ranked (all outside the caught set)

1. **`submit` raising `RuntimeError`** — `_submit` only catches `BrokenProcessPool`; a pool that is shut down raises `RuntimeError("cannot schedule new futures after shutdown")`. Reachable when the lifespan teardown (`executor.shutdown()`) overlaps a call — i.e. server restart/reconnect.
2. **`submit` raising `OSError`** from `Process.start()`. With `max_tasks_per_child=1` **every task spawns**, so this is the most load- and host-sensitive path — consistent with "less powerful host".
3. **A non-`MaudeWorkerError` inside `session.run_session`** (any SWIG-level raise; e.g. `getStateNr`/`getStateParent`/`getRule`, or `maude.load`). This would be deterministic per build — which fits `reproduction.md`'s conclusion that the report belongs to a different build with no `path` field.

## What will settle it

- At the catch site, log `type(exc).__name__`, `repr(exc)`, `exc.__cause__`, and a traceback (the client only ever sees the wrapper string).
- Log whether the failure came from `_submit` or from `future.result()`, plus a pool generation counter and `self._executor is None`.
- Two regression tests: (a) concurrent calls must not fail when one call crashes/times out — currently they do; (b) one test per exception class asserting distinct messages, including `MaudeInitError` (today it would be mislabelled as "Unexpected failure").

One extra data point for your bug-1 note: I confirmed the step-stdout half of it — a successful `search` step returned its structured `solutions` but `output.stdout` was `""`, and in one call the whole block surfaced inside a *different* step's `stdout`. Also, the mid-file bounded search only gets captured because later output flushes the buffer, so a regression test should cover both positions.

I cleaned up the scratch `probe.maude`; `shepherd.maude` is untouched. If you want, I can write the two regression tests or a small `maude_run`-level stress harness as a follow-up.
