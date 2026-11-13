# Review — Step 2: one-shot IPC transport and process runner (uncommitted)

Reviewed: the uncommitted working-tree changes, which implement Step 2 of
`.agents/planning/more_interpreter_bugs/implementation/plan.md` (the checklist
marks Steps 1 and 2 done). CI is assumed green per the request; I did not run
`make check`/`make test`. I did run two small Python 3.14 probes to verify
`multiprocessing` connection behavior (results quoted below).

## What this change does

It adds the one-shot child-side transport (`maude/transport.py`: devnull stdio
redirect, one JSON request, one JSON response, error envelopes with
`protocol`/`init`/`remote` categories) and the parent-side runner
(`maude/runner.py`: one `spawn` process per call, a pipe exchange bounded by a
deadline, an active-process registry with a shutdown-safe `kill_all`). The
worker error hierarchy moves from `executor.py` to a new stdlib-only
`maude/errors.py`, `session.run_session` annotates unexpected exceptions with
the failing phase/step, and `Settings.ipc_max_response_bytes` (2 GiB default)
caps response reads. The runner is not yet wired into `MaudeExecutor` — that is
Step 3 — so today it is exercised by 47 new unit and integration tests, as the
plan prescribes.

## Must fix

1. **A raw `OSError` escapes `run()` when `kill_all()` closes the pipe before
   `poll()` is entered** (`src/harold_mcp/maude/runner.py:167`)
   - **What this is:** `run()` maps every pipe failure to a typed error:
     `send_bytes` OSError → crash (lines 162-165), `recv_bytes` EOF/OSError →
     crash/protocol (`_receive`, lines 177-194). The `parent.poll(remaining)`
     call on line 167 is the only pipe operation with no such mapping.
   - **Problem:** `Connection.poll()` raises `OSError("handle is closed")` when
     the connection was closed — I verified this on Python 3.14.2
     (`poll raised OSError handle is closed`). `kill_all()` closes the parent
     connection of every active call (line 247), so when shutdown races a call
     that is between `send_bytes` and `poll`, the raw `OSError` propagates out
     of `run()` unmapped. The Step 3 executor re-maps typed worker errors to
     `MaudeWorkerCancelledError` when closed (design §6.6), but a bare
     `OSError` bypasses that and reaches the tool's generic branch: the client
     sees `Unexpected failure ... OSError: handle is closed` — exactly the
     undiagnosable B0 failure this project exists to eliminate, in a scenario
     the design explicitly covers (FR-10, shutdown with in-flight calls). The
     window is narrow (the common case is a call blocked inside the `poll`
     syscall, which wakes on the child's death and lands in the mapped
     `recv_bytes` path), but it is a designed-for race that will eventually
     fire.
   - **Fix:** wrap the poll like its siblings:
     ```python
     if remaining <= 0:
         raise MaudeWorkerTimeoutError(context={**context, "pid": proc.pid})
     try:
         ready = parent.poll(remaining)
     except OSError as exc:
         raise MaudeWorkerCrashedError(context={**context, "pid": proc.pid}) from exc
     if not ready:
         raise MaudeWorkerTimeoutError(context={**context, "pid": proc.pid})
     ```
     Add a unit test: a fake connection whose `poll` raises
     `OSError("handle is closed")` → `MaudeWorkerCrashedError`. The Step 3
     executor then re-maps it to `cancelled` when closed, as designed.
   - **If we skip it:** a shutdown race produces an "Unexpected failure" with
     no pid or category instead of `cancelled during shutdown`, and Step 4's
     shutdown tests become intermittently wrong.

## Should fix

2. **`_terminate` can raise a raw `ProcessLookupError` that replaces the typed
   error** (`src/harold_mcp/maude/runner.py:57-63`)
   - **What this is:** `_terminate` guards the kill with
     `contextlib.suppress(ValueError)` around `if proc.is_alive(): proc.kill()`.
   - **Problem:** `proc.kill()` can also raise `ProcessLookupError` (an
     `OSError`, not suppressed): when `kill_all()` and the call's own `finally`
     both terminate the same process, one thread's `is_alive()` can return
     True, the other thread's `join()` reaps the child, and the first thread's
     `os.kill(pid)` then finds no process. An exception raised in a `finally`
     replaces the in-flight exception, so the client would lose the typed
     `MaudeWorkerCancelledError`/`MaudeWorkerTimeoutError` and get the raw
     `OSError` instead — the same escape as finding 1, in a narrower window.
   - **Fix:** `with contextlib.suppress(ValueError, ProcessLookupError):` —
     a child that vanished between the check and the kill needs no killing;
     the following `join()` handles the rest.
   - **If we skip it:** a double-terminate race during shutdown turns a clean
     typed error into an "Unexpected failure".

## Nice to have

3. **An `ok` envelope without a `result` key returns `None` instead of a
   protocol error** (`src/harold_mcp/maude/runner.py:196-201`)
   - **What this is:** `_decode_response` validates `status` and the error
     object, but for `status == "ok"` it returns `envelope.get("result")`.
   - **Problem:** a buggy child sending `{"status": "ok"}` yields `None`, and
     the failure surfaces later as `TypeError: 'NoneType' object is not
     subscriptable` in the tool — an "unexpected" error instead of the
     protocol error the design's envelope validation (§4.2 step 8) calls for.
     Today the child is our own code, so this is hardening, not a live bug.
   - **Fix:** require `"result" in envelope` for `ok`, else
     `_fail_protocol("invalid worker response: missing result", ...)`.
   - **If we skip it:** a future child-side regression is reported as an
     untyped crash far from its cause.

4. **The Step 2 implementation notes overstate the re-export**
   (`.agents/planning/more_interpreter_bugs/implementation/plan.md`, Step 2
   notes)
   - **What this is:** the notes say "`maude/executor.py` and
     `maude/__init__.py` re-export it, so the public import paths are
     unchanged."
   - **Problem:** `executor.py` imports only the three classes it uses
     (`MaudeInitError`, `MaudeWorkerCrashedError`, `MaudeWorkerTimeoutError`);
     `from harold_mcp.maude.executor import MaudeWorkerRemoteError` no longer
     works. I grepped: nothing in the repo imports the hierarchy from
     `executor`, and `harold_mcp.maude` re-exports everything, so no code
     breaks — but the notes are the record Steps 3-6 rely on.
   - **Fix:** correct the note (only `harold_mcp.maude` preserves the public
     path), or make `executor.py` re-export explicitly.
   - **If we skip it:** a later step may "restore" an import path that was
     deliberately dropped.

5. **Two modules named `errors`** (`src/harold_mcp/maude/errors.py` vs
   `src/harold_mcp/errors.py`)
   - **What this is:** Step 1 added the formatter at `harold_mcp.errors`; this
     step adds the worker error classes at `harold_mcp.maude.errors`.
   - **Problem:** the names differ only by the package segment; an import
     written for one resolves against the other only at the IDE/mypy level.
     The move itself is right (it breaks the executor↔runner import cycle).
   - **Fix:** rename the new module (e.g. `maude/worker_errors.py`) before
     Step 3 builds on it — three import sites today, more after Step 3.
   - **If we skip it:** a recurring, if minor, source of import confusion.

## What I checked and found solid

- The `kill_all` registration race is closed exactly as designed §4.2 step 4
  describes: registration and the closed check share one lock; a child
  registered after the snapshot is killed by its own call. The unit test makes
  the window deterministic via the `on_start` hook.
- Double-close and double-terminate are safe: `Connection.close()` is
  idempotent (verified), and `_terminate` tolerates an already-reaped process.
- The pid-keyed active map cannot collide: a pid is reusable only after the
  previous child is reaped, and the entry is popped before the reap.
- The child never imports `maude` at module level; the transport imports
  worker/session lazily, and the spawn bootstrap imports the package (and
  fastmcp) regardless, so the request-send bound argument (Appendix D) holds.
- The oversized-response mapping matches CPython's
  `OSError("bad message length")` from `recv_bytes(maxlength=...)`, and the
  integration test exercises it against a real pipe with a lowered cap.
- The session phase annotation covers the load and each step, keeps
  per-step `parse-error`/`too-large` as data, and the two new unit tests pin
  the annotation through a fake `maude` module.
- Test coverage matches the plan's Step 2 requirements line by line (22
  transport, 25 runner unit tests, the settings additions, and the real-spawn
  integration suite: ping + `load_diagnostics`, crash isolation via barrier,
  timeout + follow-up, 100 kB request, 10 kB response, lowered cap). No sleeps
  are used as synchronization.

## Verdict

Verdict: fix 1 and 2 first.

Not checked: `make check`/`make test` (assumed green per the request); the
committed Step 1 formatter was only consulted, not re-reviewed; the
`maude_run` description and README table are stale by design until Step 6.
