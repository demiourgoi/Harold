# Error taxonomy and reachability (B5/B6)

## Hierarchy

```
MaudeError(RuntimeError)
├── MaudeInitError
└── MaudeWorkerError
    ├── MaudeWorkerCrashedError   reason: "Maude worker crashed"
    └── MaudeWorkerTimeoutError   reason: "Maude worker timed out"
```

Verified with `issubclass(MaudeInitError, MaudeWorkerError) == False`.
`concurrent.futures.CancelledError` is `CancelledError -> Error -> Exception`
(not a `BrokenProcessPool`, not a `TimeoutError`).

## Tool mapping

`harold_mcp/server/tools/interpreter.py`:

```python
try:
    result = executor.run_session(request, timeout=timeout)
except MaudeWorkerError as exc:
    raise MaudeRunError(f"Maude interpreter session failed: {exc.reason}") from exc
except Exception as exc:
    _log.exception(...)
    raise MaudeRunError(
        f"Unexpected failure running the Maude interpreter session: {_exception_detail(exc)}"
    ) from exc
```

So:

| Exception from `run_session` | Client message |
| --- | --- |
| `MaudeWorkerCrashedError` | `Maude interpreter session failed: Maude worker crashed` |
| `MaudeWorkerTimeoutError` | `Maude interpreter session failed: Maude worker timed out` |
| `CancelledError` | `Unexpected failure ...: CancelledError` |
| `MaudeInitError` | **would be** `Unexpected failure ...: MaudeInitError: ...` |
| `RuntimeError` / `OSError` / any other | `Unexpected failure ...: <Type>: <message>` |

The type/message suffix comes from the previous PDD's `_exception_detail`; the
server log carries the traceback. This is why attempt 4 could see
`Unexpected failure ...: CancelledError`.

## B5 — `MaudeInitError` mislabelling

`MaudeInitError` is raised only by `MaudeExecutor.start()` (the lifespan fail-fast
ping). A worker initializer failure inside a normal call is reported by
`ProcessPoolExecutor` as `BrokenProcessPool`, which `_run_task` maps to
`MaudeWorkerCrashedError`; the initializer's `WorkerInitError` never crosses the
process boundary as `MaudeInitError`.

Therefore **B5 is not reachable through `run_session` today**. It remains a latent
trap: if any future code raises `MaudeInitError` from a worker task (or maps it
there), the generic wrapper will mislabel it. A design-level safeguard is to make the
tool catch `MaudeError` and keep `MaudeInitError` in the specific branch, or to make
`MaudeInitError` a `MaudeWorkerError` if the semantics allow it.

## B6 — submit/shutdown and spawn failures

- **`RuntimeError` after `shutdown()`**: unreachable through `MaudeExecutor`.
  `shutdown()` sets `_executor = None` under `_executor_lock`; `_submit()` checks and
  creates the pool under the same lock, so it always submits to a live pool. A
  `RuntimeError` would require a caller holding a stale pool reference.
- **`OSError` from `Process.start()`**: reachable. `submit()` calls
  `_adjust_process_count()` → `_spawn_process()` → `p.start()` without catching
  exceptions, so resource exhaustion propagates out of `submit()` and reaches the
  generic wrapper. The cause is now visible in the message (`OSError: ...`) and the
  traceback is logged, so this is diagnosable, but it is not mapped to a Maude error.
- The attempt-3 instrumentation added logging for both paths. Its value is
  diagnostic, not behavioral; the current `_exception_detail` already surfaces the
  type/message, and `_log.exception` in the tool records the traceback. Whether to
  keep the additional executor-level generation logging is a design decision (the
  research recommendation is to keep enough logging to identify the failing pool
  generation, but not to rely on logs for client-visible behavior).

## What the executor must map after a redesign

At minimum:

1. worker death (crash/SIGSEGV) → `MaudeWorkerCrashedError`
2. whole-call timeout → `MaudeWorkerTimeoutError`
3. `CancelledError` (whether self-inflicted by a timeout or caused by another
   failure) → `MaudeWorkerTimeoutError` or a dedicated `MaudeWorkerCancelledError`,
   never the generic wrapper
4. initializer failure → `MaudeInitError` (start) or `MaudeWorkerCrashedError`
   (mid-call), never "Unexpected failure"
5. unexpected exceptions → propagate with type/message and a logged traceback
