# Review 2 — detailed design: isolated interpreter workers with rich failures (revised)

Reviewed: `.agents/planning/more_interpreter_bugs/design/detailed-design.md` (revision
marked "revised after the first design review") and the updated `idea-honing.md`.
Context re-checked against the current implementation and tests
(`maude/executor.py`, `maude/worker.py`, `server/server.py`,
`server/tools/interpreter.py`, `tests/unit/test_maude_executor.py`,
`tests/integration/test_maude_executor_integration.py`,
`tests/integration/test_diagnostics_integration.py`) and the installed stdlib /
FastMCP behavior.

**What this change does:** The design replaces the shared `ProcessPoolExecutor`
with one dedicated `multiprocessing.Process` per call (semaphore admission,
one-shot JSON over a `Pipe`), adds a rich bounded error formatter for
client-visible failures, and maps every reproduced bug (B0–B7) to a remedy and a
named regression test. This revision incorporates the first review: a
runner-level closed flag closes the shutdown race, the formatter renders stored
exceptions, the runner takes an injectable test target, the IPC cap is 2 GiB
with a setting-naming error, and the first line has a last-resort truncation.

## Previous findings: all 11 addressed

| # | Finding | Remedy in the revision | Verified |
| --- | --- | --- | --- |
| 1 | Shutdown registration race → permanent orphan | Runner owns `_closed`; registration + closed check under one lock; `kill_all()` sets the flag before snapshotting (§4.2 step 4, §6.6, Appendix D) | Yes — all interleavings close: register before the snapshot → killed by `kill_all`; register after → sees the flag and kills its own child; the lock serializes the two |
| 2 | `format_exc()` renders "NoneType: None" for stored exceptions | `_format_exc` = `traceback.format_exception(type(exc), exc, exc.__traceback__)` everywhere (§4.3, §4.5, §6.3, §6.5) | Yes |
| 3 | No seam for crash/concurrency tests | `PipeProcessRunner(settings, *, target=...)`; `submit`, `worker.sleep`, `rendezvous_pid` removed; §7.2 names the injection path | Yes — grep confirms those helpers are used only by the executor and the four test files named for rewrite |
| 4 | 256 MiB cap below legitimate maximum | Default 2 GiB; rationale (label-path results approach ~1 GiB; full paths bounded by child memory); oversize error names `HAROLD_IPC_MAX_RESPONSE_BYTES` (§4.7, §6.1, Appendix D) | Yes — the ~1 GiB figure is defensible (200 solutions × 1 MB terms plus unbounded-count bindings) |
| 5 | Huge first line defeats the cap | Last-resort rule: truncate the first line's message, keep category and type (ER-4, §6.3 step 6) | Yes |
| 6 | Send-side block unaddressed | FR-11, §4.2 step 5 and Appendix D state the bootstrap bound and the `BrokenPipeError` path; large-request integration test | Yes |
| 7 | Child protocol error mislabeled | Error envelope carries `category` (`protocol`/`init`/`remote`); §5.5 maps by category | Yes |
| 8 | Non-object request outside try | `isinstance` checks inside the try (§4.3) | Yes |
| 9 | No load-phase context | `worker_context` = `{"phase": "load"}` / `{"phase": "step", ...}` (§4.4) | Yes |
| 10 | Stale "replaces the worker pool" sentence | FR-16 names the sentence, README table, `docs/modules.md`, CHANGELOG; docstring test | Yes |
| 11 | Context merge unspecified | `{**exc.context, **context}`, caller wins (§4.5, §6.3 step 2) | Yes |

The lean point was adopted (no `v` envelope field; Appendix A documents why), and
the FR-11 wording was aligned ("always passes" `maxlength`). The §7.5 "Review
finding coverage" table maps every finding to a test; each mapping is real.

## Requirements coverage

The revision keeps the design aligned with `idea-honing.md`: ER-4/P1 (first-line
rule) and P4 (mandatory `maxlength`, 2 GiB default) now read the same in both
documents. The previously accepted deviations stand unchanged and remain
acceptable: §7.4's deterministic `os._exit` instead of a real SIGSEGV
(idea-honing FR-15), and design FR-6's extra spawn-failure category. One new
wording mismatch is finding 6 below.

## Findings

### Must fix

None. The locking remedy for the shutdown race is correct, the formatter
algorithm is now handler-independent, and every category mapping is consistent
with the stdlib and FastMCP behavior verified in the first review.

### Should fix

1. **`start()` clears `_closed` while shutdown is terminal, and the runner's
   closed flag is never reset** (design §4.1)
   - **What this is:** §4.1 says `start(timeout)` "clears `_closed`", and also
     says `shutdown()` "is terminal for the instance; the lifespan starts one
     executor. A test that needs a fresh start constructs a new `MaudeExecutor`."
     The runner's own `_closed` flag (§4.2) is set by `kill_all()` and nothing
     in the design ever clears it.
   - **Problem:** The two adjacent sentences disagree. An implementer following
     the first literally gets: `shutdown()` → runner closed; `start()` on the
     same instance → executor flag cleared, runner still closed → every
     subsequent call spawns a child, kills it at the post-registration check and
     raises `MaudeWorkerCancelledError` forever. A restart looks supported but
     produces a silently broken executor.
   - **Fix:** One sentence. Either `start()` also builds a fresh runner via
     `runner_factory` (making restart genuinely work), or drop "clears
     `_closed`" and state that `start()` is once per instance.
   - **If we skip it:** the spec invites a restart path that cannot work; the
     failure mode is a confusing permanent "cancelled" error.

### Nice to have

2. **The crash→cancelled re-map is enumerated only for `poll`/`recv_bytes`**
   (design §6.6). A child killed between the runner's post-registration check
   and the send makes `send_bytes` raise `BrokenPipeError`, which the runner
   maps to crash; §6.6's wording ("a call blocked in `poll`/`recv_bytes` wakes
   with EOF") does not name that phase. Fix: state the re-map generally — any
   runner crash while the executor is closed becomes
   `MaudeWorkerCancelledError`. If skipped: a shutdown-window call can be
   labelled "crash" instead of "cancelled"; same acceptable class as the
   imprecision Appendix D already documents, but the spec should say so.

3. **`worker._crash`'s fate is unspecified** (design §4.1). `sleep` and
   `rendezvous_pid` are named as removed; `_crash` is the third test-only
   helper and no operation dispatches to it after the rewrite, so keeping it
   is dead code. Fix: add it to the removal list. If skipped: an unused
   function lingers in `worker.py`.

4. **`format_error_report`'s `category=None` fallback is unspecified**
   (design §4.5, §4.6). The generic branch passes no category, and §6.1's
   "unexpected" row implies a first-line shape, but the formatter's first line
   for a category-less exception is not defined. Fix: one sentence (omit the
   category prefix, or derive it from `exc.category` when present). If
   skipped: the implementer invents the shape and the docstring test in §7.1
   may pin an accidental one.

5. **§7.3 over-claims which tests "fail on the old architecture"** (design
   §7.3, AC-6). The claim is meaningful for B1/B2/B3 — §7.5 states this
   precisely — but vacuous for the new-machinery tests (formatter,
   shutdown-race, target seam), which cannot run against the old architecture
   at all. Fix: align §7.3/AC-6 with §7.5's wording. If skipped: a future
   reader tries to run new-machinery tests against the old code and concludes
   the criterion is unmeetable.

6. **idea-honing FR-11 still reads as an absolute; the design now qualifies
   it** (idea-honing §2 FR-11 vs design FR-11/Appendix D). The requirement
   says "never blocks forever on a child that stops responding"; the design
   documents the send-side bound with a residual (a bootstrap-level hang, with
   a watchdog as the fallback). Fix: align the requirement text with the
   design's qualified statement. If skipped: requirement and design disagree
   on paper while agreeing in substance.

## Verdict

**Verdict: fix 1 before implementation; 2–6 are optional polish.**

The revision is a clean incorporation of the first review: every finding has a
correct remedy, the shutdown-race locking argument holds under all
interleavings, and the test plan now covers both the original bugs and the
review findings. No must-fix issues remain.

**Lean: -1 function possible** (`worker._crash`, finding 3). The previous lean
point (the `v` envelope field) was adopted.

**Not checked:** the probes were still not re-executed (recorded outputs taken
at face value), and macOS/Windows transport behavior remains untested (NFR-1
is best-effort; CI is Linux-only).
