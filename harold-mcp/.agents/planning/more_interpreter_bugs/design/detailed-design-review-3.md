# Review 3 — detailed design: isolated interpreter workers with rich failures (second revision)

Reviewed: `.agents/planning/more_interpreter_bugs/design/detailed-design.md` (revision
after review 2) and the updated `idea-honing.md`. Context re-checked against the
current implementation (`maude/executor.py`, `maude/worker.py`,
`server/server.py`, `server/tools/interpreter.py`) and the review-1/2 archives.

**What this change does:** The design replaces the shared `ProcessPoolExecutor`
with one dedicated `multiprocessing.Process` per call (semaphore admission,
one-shot JSON over a `Pipe`), adds a rich bounded error formatter for
client-visible failures, and maps every reproduced bug (B0–B7) to a remedy and
a named regression test. This revision incorporates review 2: `start()` builds
a fresh runner so a restart genuinely works, the crash→cancelled re-map covers
the send and join phases, `worker._crash` joins the removal list, the
category-less formatter fallback is specified, the old-architecture claim is
qualified to B1/B2/B3, and idea-honing FR-11 carries the design's qualified
send-bound wording.

## Previous findings: all 6 addressed

| # | Finding | Remedy in the revision | Verified |
| --- | --- | --- | --- |
| 1 | `start()` cleared `_closed` while shutdown was terminal; the runner's flag was never reset | `start()` builds a **fresh** runner from `runner_factory` (new closed flag) and clears the executor flag; §4.1 states restart works and that `start()` is lifecycle-only (§7.1 `test_start_after_shutdown_builds_fresh_runner`) | Yes — a fresh runner object makes the restart real; the "must not race with in-flight calls" clause covers the replacement hazard |
| 2 | crash→cancelled re-map enumerated only for `poll`/`recv_bytes` | §6.6: any runner crash while the executor is closed — EOF, send-phase `BrokenPipeError`, or a join failure — re-maps to `MaudeWorkerCancelledError`; unit test named in §7.1 | Yes |
| 3 | `worker._crash` fate unspecified | Added to the removal list with `sleep`/`rendezvous_pid` (§4.1, §7.2) | Yes — the lean point was adopted |
| 4 | `format_error_report`'s `category=None` fallback unspecified | §4.5/§6.3: explicit argument, else `exc.category`, else `Type: message` with the caller's prefix supplying context; §7.1 test | Yes |
| 5 | §7.3/AC-6 over-claimed which tests fail on the old architecture | Design AC-6 and §7.3 now say B1/B2/B3 only; new-machinery tests explicitly have no old-architecture counterpart | Yes — in the design (the idea-honing twin is finding 5 below) |
| 6 | idea-honing FR-11 absolute vs the design's qualified bound | FR-11 now states the bootstrap bound, the `BrokenPipeError` path and the watchdog fallback, matching design FR-11/Appendix D | Yes |

## Requirements coverage

The two documents now agree on FR-11/ER-4/P1/P4 and on the restart lifecycle.
The previously accepted deviations stand unchanged and remain acceptable:
§7.4's deterministic `os._exit` instead of a real SIGSEGV (idea-honing FR-15),
and design FR-6's extra spawn-failure category. One wording mismatch remains
(finding 5).

## Findings

### Must fix

None. The restart lifecycle fix is sound, the shutdown-window logic is
unchanged from the verified review-2 state, and every category mapping remains
consistent with the stdlib and FastMCP behavior verified in the earlier
reviews. This round re-verified the code-level claims against the current
sources: `WorkerInitError` exists and is raised by `worker.init_maude`
(`worker.py:29`, `:54`), `MaudeInitError(MaudeError)` is the current base
(`executor.py:25`), `start(timeout)` matches the current signature and the
lifespan call (`executor.py:137`, `server.py:36`), and the "replaces the worker
pool" sentence exists at `interpreter.py:626-627` (it spans a line break, so
the FR-16 docstring test should match on a substring that survives wrapping).

### Should fix

1. **The formatter's first-line shape is specified differently by the algorithm
   and by the examples** (design §4.5, §6.3 vs §6.1, §6.2, ER-6)
   - **What this is:** §4.5 and §6.3 define the first line as
     `<category>: <exception type>: <message>`. §6.1's client summaries and
     §6.2's example show `<category>: <message>`: "timeout: Maude worker timed
     out" (no `MaudeWorkerTimeoutError` token) and "remote-exception:
     ValueError: boom" (no `MaudeWorkerRemoteError` token; the remote type
     appears only because §5.4 defines that exception's message as
     `<Type>: <message>` of the remote). Under the algorithm, the example's
     first line would read "remote-exception: MaudeWorkerRemoteError:
     ValueError: boom".
   - **Problem:** An implementer codes §6.3 and writes the §7.1 formatter
     tests from §6.1/§6.2; the two disagree, so the shape gets pinned
     arbitrarily. ER-6 (both documents) also illustrates the category as
     "crashed" where the vocabulary (§5.4, §6.1) says "crash".
   - **Fix:** One editing pass. Pick one shape — the examples'
     `<category>: <message>` matches the current client text
     (`interpreter.py:648` raises with `exc.reason` only) with the category
     prepended, and the category already names the exception class one-to-one
     (§5.4); or keep the type token and rewrite §6.1/§6.2. Align ER-6's
     "crashed" with "crash".
   - **If we skip it:** the first client-visible line of every whole-call
     failure is decided by which section the implementer reads first, and the
     formatter/docstring tests freeze the accident.

2. **The §6.2 example's cause chain contains an element the specified algorithm
   cannot produce** (design §6.2 vs §6.3 step 3, §5.4, §5.5)
   - **What this is:** The example renders
     `cause: MaudeWorkerRemoteError: ValueError: boom <- ValueError: boom`.
     The formatter is called on the `MaudeWorkerRemoteError` (§4.6), which the
     runner constructs from the error envelope (§5.5) — it has no local
     `__cause__`/`__context__`, and the remote exception exists only as
     `remote_type`/`remote_message` attributes (§5.4). The §6.3 walk of
     `__cause__` then `__context__` therefore yields nothing for it.
   - **Problem:** Same class as finding 1: the normative example and the
     normative algorithm disagree, so a test written from the example cannot
     pass against the algorithm — and the remote-exception chain is the one
     category where a cause chain actually matters to a client.
   - **Fix:** State the mechanism. Either the formatter appends
     `remote_type: remote_message` as the final chain element when those
     attributes are present, or the runner attaches a synthetic cause, or the
     element is dropped from the example (the first line and the traceback
     section already carry the remote type and message).
   - **If we skip it:** the remote-failure cause line is unspecified and the
     §7.1 chain tests pin whichever behavior emerges.

3. **§4.6's adapter pseudocode logs the truncated report, contradicting the
   "full untruncated report is logged" requirement** (design §4.6 vs §4.5,
   §6.4, FR-14, ER-4)
   - **What this is:** The snippet computes
     `detail = format_error_report(..., max_chars=settings.error_detail_max_chars)`
     — the capped client text — and then logs that same `detail` in both the
     `MaudeWorkerError` and the generic branch. §6.4 says the tool logs "the
     full (untruncated) report", §4.5 says "the full untruncated report is
     logged by the caller", and ER-4's truncation marker tells the client to
     "see the server log".
   - **Problem:** Followed literally, the log record holds exactly what the
     client already has, so the marker points at nothing and FR-14's "full
     untruncated detail is always logged server-side" is violated. The
     normative text is right; only the snippet contradicts it — but the
     snippet is what gets copied.
   - **Fix:** One line: log an uncapped rendering (call the formatter without
     the cap for the log record, or have it return the full text alongside
     the capped one), in both branches.
   - **If we skip it:** the person debugging a non-deterministic failure from
     the logs has less information than the design promises, and the
     client-visible marker is misleading.

### Nice to have

4. **The child's stdio-redirect failure path can print to the MCP transport
   fds** (design §3.3, §4.3 vs NFR-5)
   - **What this is:** `_redirect_stdio_to_devnull()` is the first statement of
     `serve_one`, outside any handler, and the first `recv_bytes()` catches
     only `EOFError`. An exception from the redirect (e.g. `EMFILE` opening
     devnull) or an `OSError` from that recv escapes to multiprocessing's
     bootstrap, which prints the traceback to the inherited fd 2 — the MCP
     stdio transport.
   - **Problem:** NFR-5 claims child output never contaminates the transport.
     The probability is low (the redirect is one `open` plus three `dup2`s,
     and `maude_workers` caps concurrent children), but the contamination is
     protocol-level when it happens.
   - **Fix:** Wrap the redirect (on failure, `os._exit(1)` without printing —
     the parent maps EOF to crash) and catch `OSError` alongside `EOFError` on
     the first recv.
   - **If we skip it:** an fd-exhaustion edge case surfaces as MCP protocol
     corruption instead of a clean per-call crash.

5. **idea-honing AC-6 keeps the blanket old-architecture claim the design just
   qualified** (idea-honing §5 item 6 vs design §2.4 AC-6, §7.3)
   - **What this is:** Review 2's finding 5 was fixed in the design (B1/B2/B3
     only), but the requirements document still says "new regression tests
     fail on the old architecture and pass on the new one" without the
     qualification.
   - **Problem:** Running the new-machinery tests against the old code fails
     at import (the modules do not exist), so the claim is technically true
     but vacuous — the same over-claim, now only on the requirements side.
   - **Fix:** Mirror the design's wording in idea-honing §5 item 6.
   - **If we skip it:** requirement and design disagree on paper while
     agreeing in substance — the same class as review-2 finding 6, which was
     fixed.

## Verdict

**Verdict: fix 1–3 before implementation (one editing pass over
§4.5/§6.1/§6.2/§6.3/ER-6 and one line in §4.6); 4–5 are optional polish.** No
must-fix issues. The review-2 remedies are all correct: the fresh-runner
restart is sound, the shutdown-window logic holds under all interleavings, and
the test plan covers both the original bugs and the prior findings. The
remaining issues are internal consistency defects in the error-text
specification — the part of the design every failure path renders, so they
are cheap to settle now and annoying to discover mid-implementation.

**Lean:** resolving finding 1 toward the examples' shape removes the
exception-type token from the first line — the category already names the
class one-to-one, and the current client text (`exc.reason` only) reads the
same way. The previous lean point (`worker._crash`) was adopted.

**Not checked:** the research probes were still not re-executed (recorded
outputs taken at face value), and macOS/Windows transport behavior remains
untested (NFR-1 is best-effort; CI is Linux-only). FastMCP 3.4.7 and CPython
3.14 `recv_bytes` behaviors are carried forward from the reviews that verified
them; this round re-verified the code-level claims listed under "Must fix"
against the current sources.
