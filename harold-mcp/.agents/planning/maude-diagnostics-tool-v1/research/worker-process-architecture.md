# Research: Dedicated Maude worker process (alternative architecture)

<!-- Research topic 5. Emerged from review of [`maude-bindings.md`](maude-bindings.md) and
     [`logging.md`](logging.md): the fd-2 capture is process-global, and the user proposed
     isolating Maude in a dedicated subprocess instead. Decision recorded in
     [`../idea-honing.md`](../idea-honing.md) (Q1). -->

## Problem recap

- `os.dup2(write_fd, 2)` redirects **fd 2 for the whole process**. The MCP server is
  multithreaded (FastMCP runs sync tools in a thread pool), so concurrent tool calls /
  FastMCP log records / library output on stderr can interleave into the capture pipe while
  `maude.load` runs — and our redirect also *steals* those threads' stderr for the window.
- File-logging (see [`logging.md`](logging.md)) reduces, but cannot eliminate, other fd-2
  writers; it is also based on reverse-engineered FastMCP internals.
- The `maude` bindings have a documented SIGSEGV history (see
  `.agents/planning/sigsegv-under-load/issue.md`): a segfault in the interpreter would kill
  the entire MCP server in-process. This tool is designed to feed arbitrary, LLM-generated,
  possibly broken Maude files to the interpreter in a long-running server.

## Proposed architecture

Run the Maude interpreter in a **dedicated long-lived worker process** owned by the MCP
server process. The worker is single-threaded, imports only `maude` + stdlib, and serves
RPC-style requests over `multiprocessing` queues. The MCP server's `MaudeRuntime` becomes a
thin **proxy** that forwards calls and returns serializable results.

```mermaid
sequenceDiagram
    participant T as MCP tool thread (FastMCP)
    participant P as MaudeRuntime proxy (main process)
    participant W as Maude worker process (queue loop)
    participant M as maude (SWIG/C++)
    T->>P: load_diagnostics(path)
    P->>W: cmd_queue.put({"op": "load_diagnostics", "path": ...})
    W->>M: dup2: fd2 -> tempfile; maude.load(path)
    M-->>M: Warning: ... -> fd 2 -> tempfile
    W->>M: restore fd2
    W-->>W: parse Warning: lines -> diagnostics list
    W->>P: result_queue.put({"ok": bool, "diagnostics": [...]})
    P-->>T: MaudeProgramDiagnosticsResult (pydantic)
```

### Worker command protocol (sketch)

- Request: `{"op": str, ...}` — v1 ops:
  - `load_diagnostics` `{path: str}` → `{ok: bool, warnings: [{line: int, message: str}, ...]}`
  - `reduce` `{module: str, term: str}` → `{result: str}` (keeps `greet` working)
- Response: JSON-able result or `{"error": str}`; sentinel `None` request = shutdown.
- All Maude access happens in the worker's single thread → no interpreter locking needed;
  the queue provides serialization naturally.

### Warning capture in the worker

Same fd-2 trick, but isolated to the worker process:

1. `saved = os.dup(2)`
2. `os.dup2(tmpfile.fileno(), 2)` (regular file — no 64 KB pipe-buffer blocking; the worker
   is single-threaded so no reader thread is needed)
3. `maude.load(path)`
4. restore fd 2; `tmpfile.seek(0)`; read text; parse `Warning:` lines (see
   [`maude-bindings.md`](maude-bindings.md) §4 for formats).

### Lifecycle

- Started in `server.run()` **before** `mcp.run()`; explicit shutdown sentinel + `join()` on
  server exit (or FastMCP lifespan).
- Crash detection: `result_queue.get(timeout=...)` raising / `proc.is_alive()` false → the
  current call returns an error ("Maude worker crashed"), and the proxy restarts the worker
  for subsequent calls.
- Start method: **not `fork`** (the parent is threaded — fork+threads is hazardous).
  Use explicit `multiprocessing.get_context("spawn")` (portable; macOS default) or
  `forkserver` (Python 3.14's Linux default).

### Critical invariants

- The worker inherits the parent's **stdout**, which is the MCP stdio transport: the worker
  must **never write to stdout**. stderr only, and only Maude's own output during capture
  windows.
- Worker-side Python code must not `print(...)`/log to stderr during `maude.load` (nothing to
  capture besides Maude); keep worker logging minimal or routed to a file.

## Benefits

1. **stderr isolation for free**: main process keeps FastMCP's default stderr logging (which
   is what the MCP spec recommends for stdio servers); [`logging.md`](logging.md)'s
   file-logging plan becomes unnecessary; no fd manipulation in the main process.
2. **Crash containment**: a Maude segfault kills only the worker; the server survives,
   reports the failure as a diagnostic, and restarts the worker. Strategically important
   given the SIGSEGV history and adversarial inputs.
3. **Simpler concurrency story**: single-threaded worker replaces the RLock serialization
   rationale (the lock itself becomes unnecessary; the proxy may still guard the queues).
4. **Controlled environment**: the worker imports only `maude` + stdlib, so nothing else can
   pollute the capture.

## Costs / risks

1. **API change**: SWIG wrapper objects cannot cross the process boundary. The current
   `MaudeRuntime` API (`get_module`/`load_module` returning live wrappers) must become a
   proxy returning serializable results. Affects `greet`, `tests/unit/test_maude.py`,
   integration tests, and the knowledge base (`components.md`, `interfaces.md`).
2. **Lifecycle complexity**: spawn/forkserver setup, queue EOF/crash detection, restart
   policy, shutdown hooks, timeouts. (Standard `multiprocessing` ground, but real code.)
3. **Slight per-call latency**: one queue round-trip — negligible vs. file loading + parsing.
4. **Two processes to debug**; ensure the worker never inherits/uses stdout.

## Comparison: in-process vs. worker

| Aspect | In-process + fd capture + file logging | Dedicated worker process |
| --- | --- | --- |
| stderr isolation | partial (defensive parsing needed; can lose other threads' stderr lines) | complete (capture scoped to worker) |
| Main-process logging | rework required (file logging, reversed-engineered FastMCP internals) | default stderr logging kept (spec-recommended) |
| Crash containment | none — segfault kills the MCP server | worker restarts; server survives |
| Concurrency | RLock serialization in-process | queue-serialized single-threaded worker |
| API surface | unchanged (live SWIG wrappers) | proxy with serializable results (breaks current API) |
| Scope for v1 | smaller diff | larger diff (protocol, lifecycle, `greet` migration) |
| Amount of throwaway work if architecture changes later | fd-capture + logging rework would be discarded | — |

## Sources

- User proposal (worker process + queue + fd-2 capture snippets), conversation 2026-08-22.
- `.agents/planning/sigsegv-under-load/issue.md` (SIGSEGV history in these bindings).
- [`maude-bindings.md`](maude-bindings.md), [`logging.md`](logging.md).
- Python docs: `multiprocessing` (start methods, queues), `os.dup2`.
