# Research: `ProcessPoolExecutor` as the Maude worker transport

> **Status: CHOSEN refinement of the worker architecture** (2026-08-24). The dedicated Maude
> worker process decision stands ([`worker-process-architecture.md`](worker-process-architecture.md),
> idea-honing Q1); only the *transport mechanism* changes: the hand-rolled `multiprocessing`
> queue pair is replaced by a `concurrent.futures.ProcessPoolExecutor` with `max_workers=1`,
> a spawn context, and a thin recovery wrapper.

<!-- Research topic 6. Emerged from review of the queue protocol in
     worker-process-architecture.md: a single shared result queue cannot demultiplex
     concurrent callers. Verified 2026-08-24 against Python 3.14.2 (the harold-mcp venv)
     and the installed fastmcp 3.4.7. -->

## Problem with the hand-rolled queue pair

- With **one shared result queue**, two threads in the FastMCP process submitting calls
  concurrently can each `get()` the *other* thread's result. Fixes exist (correlation IDs,
  per-call queues, an in-process lock around submit+get) but they re-implement what
  `ProcessPoolExecutor` already provides.
- `submit()` returns a **per-call `Future`**; the executor routes each result back to its
  own caller internally (`_pending_work_items`, work IDs, per-call `_result_queue` entries).
  No cross-talk by construction.

## Verified facts (2026-08-24, Python 3.14.2, harold-mcp venv)

1. **Start method**: Linux Python 3.14 defaults to `forkserver`
   (`multiprocessing.get_start_method()` → `forkserver`). Source inspection of
   `concurrent/futures/process.py` `__init__` shows that with `mp_context=None` and
   `max_tasks_per_child=None` the executor uses `mp.get_context()` — i.e. **3.14 no longer
   forces `fork` on POSIX**; it honors the default start method. A threaded parent is safe
   with either `forkserver` or `spawn`.
2. **Sandbox/container caveat**: `forkserver` needs to create an `AF_UNIX` listener socket;
   in the agent sandbox this failed with `PermissionError: [Errno 1] Operation not
   permitted`. `spawn` (pipe-based) worked. → **pass an explicit
   `mp_context=multiprocessing.get_context("spawn")`** for portability and determinism.
   (Also matches the spawn/forkserver recommendation already in
   [`worker-process-architecture.md`](worker-process-architecture.md).)
3. **`BrokenProcessPool` import path**: in 3.14 it is **not** re-exported from the top-level
   `concurrent.futures`; import it from `concurrent.futures.process`.
4. **FastMCP lifespan**: `FastMCP(lifespan=...)` accepts an `asynccontextmanager`
   (`LifespanCallable | Lifespan | None`; see `fastmcp/server/server.py:333`). The pool is
   created/warmed up in lifespan startup and shut down in lifespan exit. See
   <https://gofastmcp.com/servers/lifespan>.
5. **FastMCP error semantics**: an exception raised inside a tool is caught by the server
   and converted to a `ToolError` ("Error calling tool ..."), which becomes an MCP error
   result (`isError`) for the client — the "HTTP 500" analogue. Worker crashes therefore
   surface as ordinary tool errors; no special MCP plumbing needed.

## Empirical experiment (spawn context, real Maude interpreter)

Setup: `ProcessPoolExecutor(max_workers=1, initializer=init_maude, mp_context=spawn)`;
two threads submit `load_program` calls on the `hello.maude` / `hello2.maude` fixtures;
then a task calls `os._exit(1)` to simulate an abrupt worker death (the SIGSEGV analogue).

Results:

- `routing correct: True` — each thread received the result for **its own** path.
- `same worker pid: True` — both calls ran in the **same** worker process, i.e. they were
  serialized by the single worker. The `max_workers=1` pool is the implicit lock: **two
  concurrent tool calls run sequentially**, each with its own future.
- Crash → `BrokenProcessPool: A process in the process pool was terminated abruptly while
  the future was running or pending.` raised on `future.result()`.
- After the crash, `submit()` on the same executor raises `BrokenProcessPool` immediately
  (the pool stays broken — no automatic replacement).
- A **freshly created** executor works again (`recreated pool works: True`).

## Answers to the review questions

| Question | Answer |
| --- | --- |
| Do two threads + a queue pair risk cross-talk? | Yes — a shared result queue cannot demultiplex concurrent callers. The pool fixes it (per-call futures). |
| `max_workers=1`, `max_tasks_per_child=None`, `initializer=init_maude`? | Correct. `None` is the default for `max_tasks_per_child` (long-lived worker); the initializer runs `init_maude()` once per worker. |
| Initialize the pool via FastMCP lifespan? | Correct. Create + warm up in lifespan startup, `shutdown()` in lifespan exit. |
| Is `max_workers=1` an implicit lock with sequential execution? | Correct — verified (same worker pid, correct per-call routing). |
| Worker reuses one `MaudeRuntime` via `get_runtime()`? | Correct — the per-process singleton; `init_maude()` in the initializer, `get_runtime()` in tasks. |
| Is parallelism (`max_workers>1`) safe? | Yes (see below); keep the default at 1, make it configurable via env var. |
| Detect crashes via the future and report as tool failures? | Correct — `BrokenProcessPool` / `TimeoutError` from `future.result()`; FastMCP turns the exception into an `isError` tool result. |
| Is a recovery wrapper the easiest option? | Yes — the pool has no self-healing; a small wrapper that recreates the executor is the idiomatic fix (see below). |

## Parallelism assessment (`max_workers > 1`)

- **Safe**: each worker process owns an independent Maude interpreter (own prelude, own
  module table, own RNG seed from `init_maude()`). No shared mutable state across workers;
  consistent with the "no module wrapper caching / last load wins" semantics — each load is
  independent. Concurrent diagnostics on different (or the same) files cannot interfere.
- **Costs**: memory × N (each interpreter loads the prelude), init cost × N under `spawn`
  (re-import `maude` + `init_maude()` per worker — one-time per worker at pool warm-up),
  and a worker crash breaks the **whole** executor (all pending futures fail; the wrapper
  recreates the pool). With `max_workers=1` the last point is moot.
- **Recommendation**: default `max_workers=1` (build-tool etiquette on a dev machine);
  expose an env var (e.g. `HAROLD_MAUDE_WORKERS`) for opt-in parallelism. Warm up **all**
  workers in lifespan startup if `>1`, to preserve fail-fast init.

## Recovery wrapper (design input)

A thin class owning the executor, replacing the queue protocol:

- `submit(...)` catches `BrokenProcessPool` (pool already broken) → **recreate** the
  executor → resubmit once.
- On `future.result(timeout=...)` raising:
  - `BrokenProcessPool` → worker died mid-task: recreate the pool (so the *next* call
    works) and raise a typed error (e.g. `MaudeWorkerError`) for *this* call.
  - `TimeoutError` → the task is still running (a timeout does **not** cancel it; the only
    way to interrupt a stuck interpreter is to kill the pool): `shutdown(wait=False,
    cancel_futures=True)`, recreate, raise. Without this, one hung load would poison the
    single worker for every subsequent call.
  - Task's own exception (e.g. `MaudeLoadError`) → propagate as-is (recoverable, pool is
    healthy).
- Recreate path: `shutdown(wait=False, cancel_futures=True)` on the old executor (reaps the
  dead worker), then build a fresh one with the same settings. Guarded by a lock — two
  threads may detect the crash simultaneously.
- **Retry policy**: do *not* auto-retry the failed call itself; a file that crashed the
  worker will likely crash it again. Diagnostics is load-only (idempotent), so the MCP
  client can retry the tool call safely. (Design-phase decision.)
- **Fail-fast startup**: `server.run()`'s current `init_maude()` call is replaced by a
  lifespan warm-up that submits a ping through the pool and waits (with a timeout). Note:
  if the *initializer* raises, the worker dies before completing any task, so the ping
  surfaces as `BrokenProcessPool` — the wrapper should map warm-up failures to
  `MaudeInitError` so the startup error message stays meaningful.

## Remaining invariants and caveats

- **stdout**: the worker inherits the MCP server's stdout (the stdio transport). Worker
  code must never write to stdout.
- **Worker logging**: the worker imports `fastmcp` transitively (`harold_mcp.logging`), so
  its stderr gets FastMCP's RichHandler. Harmless (stderr is not the transport), but keep
  the existing invariant: **no worker logging during the fd-2 capture window** around
  `maude.load`.
- **Picklability**: under `spawn`, the initializer and task functions must be importable
  top-level functions (no lambdas/closures). Put them in a dedicated module, e.g.
  `src/harold_mcp/maude_worker.py`. `main.py` already has a `__main__` guard (needed).
- **Two `get_runtime()` singletons, one per process**: in the MCP server process,
  `get_runtime()` returns the pool wrapper (the client); in the worker, `get_runtime()`
  returns the in-worker `MaudeRuntime` interpreter facade. Clean separation — the SWIG
  wrappers never cross the process boundary.
- **Orphaned workers**: a SIGKILL of the server can orphan workers (no PDEATHSIG); normal
  exit is handled by the executor's atexit shutdown. Accepted for v1.
- **Warm-up cost**: with `spawn`, the ping also forces the first worker to spawn, import
  `maude`, and load the prelude — i.e. the init cost moves from server start to lifespan
  startup. Fine (still fail-fast), just slightly slower startup.

## Updated flow

```mermaid
sequenceDiagram
    participant T as MCP tool thread (FastMCP)
    participant P as Pool wrapper (main process, get_runtime)
    participant E as ProcessPoolExecutor (spawn, max_workers=1)
    participant W as Maude worker process
    T->>P: diagnostics(path)
    P->>E: submit(load_diagnostics, path)
    E->>W: run task (serialized)
    W->>W: init_maude once (initializer); fd-2 capture around maude.load
    W-->>E: result dict
    E-->>P: future.result(timeout)
    P-->>T: MaudeProgramDiagnosticsResult (or MaudeError on crash/timeout)
```

## Sources

- Experiment: `/tmp/pool_experiment.py`, run 2026-08-24 in the harold-mcp venv
  (Python 3.14.2, `spawn` context, real `maude` loads + `os._exit(1)` crash).
- CPython 3.14.2 source: `concurrent/futures/process.py` (`ProcessPoolExecutor.__init__`,
  `submit`, `_process_worker`), `multiprocessing/forkserver.py` (AF_UNIX listener).
- Python docs: <https://docs.python.org/3/library/concurrent.futures.html#concurrent.futures.ProcessPoolExecutor>
  (incl. the 3.3 `BrokenProcessPool` change quoted in the review).
- Installed fastmcp 3.4.7 source: `fastmcp/server/server.py` (lifespan param, `ToolError`
  conversion of tool exceptions).
- FastMCP lifespan docs: <https://gofastmcp.com/servers/lifespan>
- [`worker-process-architecture.md`](worker-process-architecture.md) (architecture decision,
  transport refined here).
