# One-shot Pipe IPC for a dedicated process per call (O3)

Probe: `probes/probe_ipc.py` (Python 3.14.2, `spawn` context, real processes).
This validates the mechanism the user sketched; it does not yet exercise Maude.

## Results

| Scenario | Result |
| --- | --- |
| 1 MB JSON payload + non-ASCII text echoed back | `ok` in 0.03 s, payload identical |
| Child exits `os._exit(7)` | parent sees EOF (`recv_bytes` raises `EOFError`) in 0.03 s |
| Child hangs; parent deadline 0.5 s | `poll` returns false at 0.50 s; `kill()` + `join()` |
| 4 concurrent calls from threads | 4 × `ok` in 0.03 s total |

`Pipe` + `send_bytes`/`recv_bytes` handles the maximum response sizes the worker
can produce (each stream/result is capped at 1,000,000 characters). JSON with
`ensure_ascii=False` keeps non-ASCII Maude output intact (the current lossy
decode produces valid Unicode).

## Framing and serialization (CPython 3.14 source)

`multiprocessing.connection.Connection` is a thin fd/socket wrapper that adds two
things:

1. **Framing** (`send_bytes`/`recv_bytes`): `_send_bytes` writes a 4-byte
   `!i` length header (or a `-1` marker plus an 8-byte `!Q` length for messages
   over 2 GiB), then the payload. `_send` loops until every byte is written, and
   `_recv` reads the header and then loops until the full payload arrives. This is
   exactly what makes the 64 KiB pipe buffer a non-issue: partial writes are
   continued, and a large message is one logical read.
2. **Pickling** (`send`/`recv`): `send` pickles with `_ForkingPickler` and delegates
   to `send_bytes`; `recv` unpickles. `send_bytes`/`recv_bytes` bypass pickling.

Edge cases the client must handle:

| Situation | Exception |
| --- | --- |
| Peer closed before any response | `EOFError` |
| Peer closed mid-message | `OSError("got end of file during message")` |
| Message exceeds `recv_bytes(maxlength=...)` | `OSError("bad message length")` (connection is closed) |

Both EOF cases are the crash signal. The `maxlength` case is a protocol error and
should be treated separately. Passing a `maxlength` derived from the settings caps
(e.g. a few MB above the largest expected envelope) is cheap hardening against a
buggy child.

**Serialization choice:** JSON for the request/envelope, sent as
`conn.send_bytes(json.dumps(payload, ensure_ascii=False).encode())`, is explicit,
testable and safe; the result is plain JSON-safe data. Pickle via `send`/`recv` is
a valid alternative (it is what the pool does today and avoids manual encoding),
but the wire format becomes opaque and a remote exception still has to be reduced
to strings. The design can choose either; JSON is the default recommendation.

## Recommended protocol

One-shot, not a loop: one process receives **one** request, executes **one**
operation, sends **one** response, and exits. This matches the isolation and
fresh-interpreter requirements and avoids the parser-residue class of bugs that
motivated `max_tasks_per_child=1`.

Response envelope:

```json
{"status": "ok", "result": {...}}
{"status": "error", "type": "ValueError", "message": "...", "traceback": "..."}
```

The server maps:

| Event | Mapping |
| --- | --- |
| `status == "ok"` | return `result` |
| `status == "error"` | remote exception: log the traceback; surface type/message as a `MaudeWorkerError` (or the current generic wrapper with the cause chained) |
| `EOFError` before any response | `MaudeWorkerCrashedError` (SIGSEGV, `os._exit`, OOM kill) |
| `poll` deadline exceeded | `MaudeWorkerTimeoutError`; `kill()` the child and `join()` |
| `init_maude` fails at startup ping | `MaudeInitError` |

## Lifecycle details

- Parent creates `ctx.Pipe()`, `proc = ctx.Process(target=worker.serve_one, args=(child,), daemon=True)`,
  starts it, then **closes `child`** in the parent so EOF is observable when the
  child dies. The child closes `parent` and its own `conn` in `finally`.
- Deadline: `parent.poll(remaining)`, then `recv_bytes()`. On timeout call
  `proc.kill()` (SIGTERM may not stop libmaude; use SIGKILL for a stuck
  interpreter), `proc.join()`, and map to a timeout. `join` after a response is
  also bounded and followed by `kill()` if the child does not exit.
- `daemon=True` prevents orphans if the server exits; the per-call `finally`
  still kills and joins every child.
- Admission: `threading.BoundedSemaphore(maude_workers)`; acquire with a timeout
  counted inside the whole-call budget so a queued call cannot wait forever.
- `start()`: spawn `maude_workers` short-lived init pings in parallel, bounded by
  the diagnostics timeout; failure raises `MaudeInitError`. `shutdown()` kills and
  joins any tracked in-flight children.
- The child entry point lives in `harold_mcp/maude/worker.py` (or a sibling
  `ipc.py` imported by it), dispatches on a method tag (`load_diagnostics` /
  `run_session`), calls `init_maude`, invokes the existing worker function, and
  sends the envelope. The `maude` import stays lazy.

## Why this fits Harold better than a pool

- A crash or timeout kills exactly one process; there is no shared pool, call
  queue, broken-pool state or cross-call cancellation.
- The per-call cost is the same as today: the executor already uses
  `max_tasks_per_child=1`, so every current task pays spawn + prelude init
  (~0.3 s on this host).
- The public `MaudeExecutor` surface (`diagnostics`, `run_session`, `start`,
  `shutdown`) can stay identical; only the transport changes.
- A `ProcessRunner`/`call_in_process` seam keeps unit tests hermetic (fake
  process/connection), while integration tests cover real SIGSEGV, timeout and
  large-response cases.

## Residual risks

- `recv_bytes` is unbounded once the header has arrived: a child that sends a
  header and then stalls mid-payload blocks the parent. The child constructs the
  complete JSON/pickled bytes before calling `send_bytes`, and the 1 MB caps make
  this negligible; a reader thread or watchdog is the fallback if a strict hard
  deadline is ever required. Partial writes and the 64 KiB pipe buffer are already
  handled by `_send`/`_recv`.
- Tracking in-flight children for shutdown needs a lock-protected set; a child
  that ignores SIGKILL is a kernel-level problem, not solvable in-process.
- JSON adds a transient copy of each result; ~1 MB results are fine. Pickle is a
  possible optimization, not a requirement.
