# Review — detailed design: isolated interpreter workers with rich failures

Reviewed: `.agents/planning/more_interpreter_bugs/design/detailed-design.md`
Context read: `rough-idea.md`, `idea-honing.md`, `reproduction_attempt-2/3/4.md`,
`research/{reproduction,cpython-pool-semantics,error-taxonomy,architecture-options,billiard,ipc,step-output,plan}.md`,
and the current implementation (`maude/executor.py`, `maude/worker.py`, `maude/session.py`,
`maude/capture.py`, `maude/provider.py`, `server/server.py`, `server/tools/interpreter.py`,
`server/tools/diagnostics.py`, `diagnostics/aggregate.py`, `settings.py`) plus the
existing unit/integration tests for the executor.

**What this change does:** The design removes the shared `ProcessPoolExecutor` behind
`maude_run` and `maude_program_diagnostics` and gives every call one dedicated
`multiprocessing.Process`, admitted by a semaphore, exchanging one JSON
request/response over a `Pipe`. It adds a rich error formatter so whole-call
failures reach the MCP client with category, type, cause chain, call context and a
bounded traceback, and it maps each reproduced bug (B0–B7) to a remedy and a named
regression test.

## Requirements coverage

Checked against `idea-honing.md` (FR-1..16, ER-1..9, NFR-1..6, AC-1..7, P1..P10,
D1..D7, Q1 answer B) and `rough-idea.md`. Every requirement is carried into the
design, and the fixed decisions are honored: no pool (D1), stdlib only (D2/D3),
tool contracts preserved (D4), no retries (D5), B4/B7 get regression tests only
(D6), the server never imports `maude` (D7, §4.8). Three wording-level deviations,
none blocking:

- Design FR-11/NFR-4 says the parent "**may** pass `recv_bytes(maxlength=...)`"
  while idea-honing FR-11 makes it mandatory. The component spec (§4.2 step 6)
  does pass it mandatorily, so only the FR wording is weaker; align it.
- Design FR-6 adds a spawn-failure category absent from idea-honing's list — a
  superset, justified by B6.
- §7.4 uses a deterministic `os._exit` crash target instead of the "real
  SIGSEGV" idea-honing FR-15 mentions. Documented and reasonable; a real SIGSEGV
  is not reliably producible.

The design's external claims were verified against the installed environment
(FastMCP 3.4.7, mcp 1.29.0, CPython 3.14.2):

- FastMCP 3.4.7 wraps a raised exception as
  `ToolError(f"Error calling tool {name!r}: {e}")` with `mask_error_details=False`
  by default — no cause chain, no traceback. ER-9 is accurate: the text must be
  formatted into the exception message before raising.
- `recv_bytes(maxlength=N)` on an oversized message raises
  `OSError("bad message length")` and closes the connection; mid-message EOF
  raises `OSError("got end of file during message")`; clean EOF raises
  `EOFError`. The §4.2 step 6 / §5.5 mappings are correct.
- The pool-semantics claims (`EXTRA_QUEUED_CALLS`, `set_running_or_notify_cancel`
  at dispatch, `kill_workers()` = `shutdown(wait=False, cancel_futures=True)` +
  kill) match the CPython 3.14 source and the probes.

## Findings

### Must fix

1. **A call can spawn its child after shutdown has already killed everything,
   and that child can run forever**
   (design §4.1 `_run_operation` step 3, §4.2 steps 2–3, §6.6;
   `src/harold_mcp/server/server.py:79`)
   - **What this is:** `_run_operation` checks the closed flag once, then calls
     the runner, which spawns the child and registers it in the active map.
     `shutdown()` sets the flag, then `kill_all()` snapshots the active map and
     kills what it sees.
   - **Problem:** A call that passes the closed-flag check just before shutdown,
     but registers its child just after the `kill_all()` snapshot, is never
     killed. The server then exits via `os._exit(0)`, which skips atexit, so
     multiprocessing's daemon-child cleanup never runs either. The child keeps
     running with no parent left to enforce its deadline: a non-terminating
     rewrite spins forever. This breaks FR-10 and acceptance criterion 7 ("no
     orphan processes remain after ... shutdown").
   - **Fix:** Give the runner its own closed flag, set by `kill_all()`. In
     `run()`, after registering the child, check it; if closed, kill and join the
     child and raise `MaudeWorkerCancelledError`. One check closes the window.
   - **If we skip it:** the "no orphans after shutdown" acceptance criterion is
     false as specified, and the escape is a permanent CPU spinner.

2. **The formatter's local-traceback rule produces "NoneType: None" in the
   diagnostics path**
   (design §4.5 step 4, §6.3 step 4, §6.5)
   - **What this is:** The formatter picks the originating traceback as
     `remote_traceback` if present, otherwise "`traceback.format_exc()` for a
     local one".
   - **Problem:** `format_exc()` only works inside an `except` block, for the
     exception currently being handled. The diagnostics aggregation renders each
     provider's failure inside `DiagnosticCollectionError` (as today's
     `aggregate.py` does), where the provider's exception is a stored object, not
     the one being handled. There `format_exc()` returns "NoneType: None" — the
     client sees a garbage traceback line for exactly the failures ER-7 covers
     (a heuristic-linter bug, or a worker crash/timeout, which carries no remote
     traceback).
   - **Fix:** Specify `"".join(traceback.format_exception(type(exc), exc,
     exc.__traceback__))` — it renders any exception object, in or out of a
     handler.
   - **If we skip it:** diagnostics provider failures ship a wrong traceback in
     the client-visible text.

### Should fix

3. **The crash and concurrency integration tests have no way to reach a crash
   target**
   (design §4.1, §4.2 step 2, §4.3 `_dispatch`, §7.2, §7.5)
   - **What this is:** `_dispatch` admits only `ping`, `diagnostics`, `session`;
     anything else is a protocol error. `PipeProcessRunner` hardcodes
     `transport.serve_one` as the process target. The public surface drops
     `submit()`.
   - **Problem:** Today's tests trigger a crash and force concurrency through
     `executor.submit(worker._crash)`
     (`tests/integration/test_diagnostics_integration.py:444`) and
     `executor.submit(worker.rendezvous_pid, ...)`
     (`tests/integration/test_maude_executor_integration.py:26`). The design
     requires "a test-only transport target that calls `os._exit(1)`" (§7.2)
     but never says how a test installs it. As written, the B2/B6 integration
     tests cannot be built through the real runner, and "the public surface
     stays the same" (§4.1) is inaccurate — `submit` is gone.
   - **Fix:** Name the seam: either a test-only `crash` operation in `_dispatch`
     (the analogue of today's `worker._crash`), or a constructor-injectable
     process target on `PipeProcessRunner`. State explicitly that `submit`,
     `worker.sleep` and `rendezvous_pid` are removed or repurposed, since
     existing tests depend on them.
   - **If we skip it:** the implementer improvises the seam mid-flight and the
     §7.5 test matrix is not implementable as specified.

4. **The 256 MiB response cap is below the result size the existing caps allow,
   so a legitimate call can fail as a protocol error**
   (design §4.7, §5.5, Appendix D; idea-honing P4)
   - **What this is:** `recv_bytes(maxlength=ipc_max_response_bytes)` with a
     256 MiB default; an oversized response is a protocol error.
   - **Problem:** The existing caps allow more than 256 MiB in one response.
     One search step can return 200 solutions of up to 1,000,000 characters
     each — 200 MB of terms alone — plus bindings, and with `path="full"` up to
     100 transitions per solution each carrying a 1 MB rule text and a 1 MB
     state. A client that legitimately approaches the caps gets
     `protocol-error: invalid worker response`: a wrong category that names no
     setting. P4 requires the cap to be "above the legitimate maximum result
     size"; the design calls the default "generous" without computing that
     maximum.
   - **Fix:** Document what the cap is for (hardening against a buggy child;
     the pathological worst case dies of MemoryError in the child first, since
     the child builds the JSON string in memory), raise the default above the
     realistic maximum (200 solutions with label paths fits in ~1 GiB), and make
     the oversize error name `HAROLD_IPC_MAX_RESPONSE_BYTES` the way `too-large`
     outcomes name their setting.
   - **If we skip it:** a legal large session fails with a message that sends
     the client debugging a protocol bug that does not exist.

5. **One huge exception message defeats the 4000-character cap, because the
   first line is never truncated**
   (design ER-4, §6.3 step 6)
   - **What this is:** The error-text cap shortens the traceback first, then
     long cause messages, but the first line (category, type, message) is
     exempt.
   - **Problem:** The first line embeds the exception message, and nothing
     bounds a remote message — the child sends `str(exc)` of whatever Maude
     raised, which can embed a huge term. A 10 MB message produces a 10 MB
     client-visible error; the cap fails on exactly the failures it was
     written for.
   - **Fix:** Add a last-resort rule: if the first line alone exceeds the cap,
     truncate its message part (keep category and type) and append the
     truncation marker.
   - **If we skip it:** one pathological failure floods the client's context
     window.

6. **"Never blocks forever on a child that stops responding" is not enforced
   while sending the request**
   (design FR-11, §4.2 step 4, Appendix D)
   - **What this is:** The deadline is enforced by `poll(remaining)` for the
     response. The request `send_bytes` has no deadline.
   - **Problem:** A request bigger than the 64 KiB pipe buffer (up to ~20 MB:
     200 steps × 100,000-character terms) blocks in `send_bytes` until the
     child reads. The child does read before importing Maude (`serve_one`'s
     first acts are the stdio redirect and `recv_bytes`), so a hang needs a
     spawn-bootstrap hang — thin, but FR-11 is stated as absolute and the
     design discusses only the receive side.
   - **Fix:** Either state the bound explicitly in Appendix D (the child reads
     before any Maude import, so the send is bounded by bootstrap time, and a
     dead child yields `BrokenPipeError`), or enforce the deadline on the send
     too.
   - **If we skip it:** an absolute requirement stays unenforced on one path;
     a bootstrap-level hang wedges a server thread forever.

### Nice to have

7. **The child's own protocol-error envelope is mislabeled by the parent's
   mapping table** (design §4.3, §5.5). The child answers invalid JSON with
   `type="ProtocolError"`; §5.5 maps "any other class name" to
   `MaudeWorkerRemoteError`, so it would surface as
   `remote-exception: ProtocolError: ...` instead of `protocol-error`.
   Unreachable in practice (the parent is trusted), but the table is
   self-inconsistent. Fix: special-case the name or add a category field to
   the error envelope.

8. **`serve_one` reads `request.get(...)` outside both try blocks**
   (design §4.3). Valid JSON that is not an object (for example `"123"`)
   raises `AttributeError` outside the handlers; the child dies and the parent
   reports a crash instead of a protocol error. NFR-3 says IPC payloads are
   validated. Fix: check `isinstance(request, dict)` inside the existing try.

9. **Load-phase exceptions carry no phase context** (design §4.4). Only step
   exceptions get the `worker_context` annotation, so an unexpected exception
   during the load reaches the envelope with no phase, and FR-7's "phase
   (load / a step ...)" is half-implemented. Fix: wrap the load section the
   same way.

10. **The documentation plan is generic; one client-visible sentence goes
    stale** (design FR-16). The `maude_run` description shipped to MCP clients
    says a non-terminating reduction "fails the call and replaces the worker
    pool" (`src/harold_mcp/server/tools/interpreter.py`, docstring) — false
    under the new design. Fix: name the concrete edits: that sentence, the
    README env-var table for the two new settings, and `docs/modules.md`
    entries for `harold_mcp.errors` and the transport module.

11. **The context merge is unspecified** (design §4.6, §5.4).
    `MaudeWorkerError` carries its own `context`, and the tool builds another;
    who merges the two maps and who wins on a key collision is not stated.
    One sentence fixes it.

## Verdict

**Verdict: fix 1 and 2 first; settle 3 before implementation starts.**

The architecture is sound: one process per call is the right fix for the
reproduced shared-fate bugs, the research supports every load-bearing claim,
and the bug-to-test matrix is complete. The two must-fix items are spec bugs
that would ship wrong behavior (an orphaned child on shutdown; a garbage
traceback in diagnostics errors), and both are one-line design changes.

**Lean: about -10 lines possible.** The `v` envelope field is dead hardening:
parent and child are always the same package, and a one-shot child never
outlives its pipe into a new server generation, so a version mismatch cannot
occur. Dropping it removes a field, a check and a wrong-version test. Optional;
if kept, it is cheap.

**Not checked:** the probes were not re-executed (their recorded outputs were
taken at face value), and macOS/Windows behavior of the portable-`multiprocessing`
transport was not tested (NFR-1 claims best-effort; CI is Linux-only).
