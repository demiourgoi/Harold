Instrumentation added

| File | Change |
|---|---|
| `src/harold_mcp/logging.py` | `describe_exception_chain(exc, max_length=2000)` — renders `Type: message <- cause: message <- context: ...` with a cycle guard |
| `src/harold_mcp/maude/executor.py` | pool **generation** counter; `_create_executor()` logs a creation/spawn failure; `_submit` logs any non-`BrokenProcessPool` submit failure; `_run_task` logs crash, timeout, and — the bug-2 path — any unexpected result-phase exception with type, chain and traceback (includes the worker's remote traceback); `kill_workers` failures logged too. Every line names the generation and the task |
| `src/harold_mcp/server/tools/interpreter.py` | `_LOG.exception(...)` with `path/module/steps/timeout`, plus the chain in the **client-visible** message: `Unexpected failure running the Maude interpreter session: <Type>: <msg> <- <cause>: <msg>` |
| tests | `test_unexpected_exception_is_chained` now asserts the cause is in the message; 3 new executor tests cover worker-exception logging (chain + `exc_info`), non-`BrokenProcessPool` submit failure (`RuntimeError` after shutdown), and pool-creation failure (`OSError`) |

The wire change matters because server logs aren't reachable from a tool call: if the generic error fires again, **I will see the cause directly** in the tool result. Its absence (bare old text) also tells us the running server hasn't been restarted from this checkout yet.

Validation: `make check` clean, `make test-unit` 269 passed, `make test` **357 passed**.

## Reproduction campaign (all with the instrumented semantics in mind)

| Probe | Result |
|---|---|
| Reported payload ×10 concurrent | 10/10 ok |
| All search types incl. `=>#`/`=>!`/`=>+`; depths `-1/0/10/maxint`; `path` none/labels/full | ok |
| `erewrite`, `bound=0`, non-terminating reduce | ok / timeout / crash — all **specific** messages |
| Missing file, missing module, theory module | specific `MaudeRunError`s |
| `too-large` result cap (1M) and path cap (100) | `too-large` data, correct `limit`/`message` |
| 6 concurrent depth-300 searches (~45k states each, no output) | 6/6 ok |
| One call kills the pool, concurrent calls in flight | 5/5 `Maude worker crashed` — deterministic, but **not** the generic message |

So every path reachable from the tool surface now produces either a step status or a specific error. The only unattempted triggers are the two lifecycle ones I flagged: `submit` raising `RuntimeError` after `executor.shutdown()` (server restart/reconnect) and `OSError` from a worker spawn (`max_tasks_per_child=1` means every task spawns). Forcing those needs process/memory exhaustion or a server shutdown, neither of which I can do safely from a tool call.

Circumstantial evidence still points at lifecycle: identical payloads failed only in one window, the tool briefly vanished (`No tool named maude_run exists`), and everything has been clean before and after — i.e. the server was restarting while calls were in flight.

## Two things you may want next

1. **Restart the MCP server from this checkout** (`harold-mcp/`), then I'll retry the campaign. A failing call will now report the actual cause, and the server log will have `Unexpected failure in maude_run (...)` plus the pool generation and remote traceback.
2. The deterministic **pool-coupling bug** is worth fixing independently: one timing-out/crashing call kills the shared pool and takes down unrelated concurrent calls ("Maude worker crashed"). Options: track generations and only reset the pool if the failing call's pool is still current (already done), but also **retry once** a call whose future belonged to a pool that was killed by *another* call, or use one pool per in-flight call. Also note `MaudeInitError` is not a `MaudeWorkerError`, so if it ever surfaces from `run_session` it gets mislabelled as "Unexpected failure" — now at least visible in the message.
