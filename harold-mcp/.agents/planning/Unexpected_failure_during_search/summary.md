# Summary — Unexpected failure during search

## Status

Implementation complete and validated. The bug report contained two distinct problems;
both are now addressed:

1. **Confirmed defect (fixed):** captured Maude output lost its tail because
   `capture_streams` restored fds 1/2 without flushing libmaude's C/C++ stdio buffers.
   The unflushed bytes surfaced later — in a later phase or on the worker's inherited
   stdout, which is the MCP stdio transport.
2. **Diagnostic gap (fixed):** a non-`MaudeWorkerError` from `maude_run` returned only
   the generic "Unexpected failure running the Maude interpreter session" text. The
   exception type and message now reach the client, and the traceback is logged.

The **original whole-call error is still not reproduced** on `main` (`6b7a19f`,
`0.0.5.dev0`). It remains tied to the original, less powerful host. The new error detail
is what will make the next occurrence diagnosable there.

## Root cause of the confirmed defect

- A bounded `search` that reaches its bound does not print `No more solutions.` and does
  not flush libmaude's output buffer. If it is the last command in a loaded file, its
  result block is still buffered when `maude.load` returns.
- `capture_streams` restored fds 1/2 immediately, so the block was not in the capture.
  It was flushed later to whatever fd 1 pointed at (another capture or the real stdout).
- Adding `fflush(NULL)` inside the capture window recovers the complete block; this was
  verified directly. The other host's "missing terminator / desynchronized session"
  explanation was a plausible but incorrect mechanism: Harold does not frame or parse
  load output.

## Changes

- `src/harold_mcp/maude/capture.py`: new `_flush_stdio()` (Python streams + libc
  `fflush(NULL)`, failures suppressed); called before the redirect and in the `finally`
  before restoring the descriptors.
- `src/harold_mcp/server/tools/interpreter.py`: `_exception_detail()` appends the
  exception type and message to the generic `MaudeRunError`; the traceback is logged
  with the module logger together with the resolved path and module; the cause stays
  chained.
- Tests:
  - unit: buffered C output is captured and does not leak to a stdout sink;
  - unit: failing Python and libc flushes are suppressed, leaving the phase result and
    captured output unchanged;
  - unit: unexpected exception text includes `ValueError: boom`, the empty-message case
    surfaces its type, and the recording logger sees the traceback call with the
    path/module arguments;
  - integration: a fixture ending in a bounded search reports the solution in
    `load_output`.
- `CHANGELOG.md`: two Fixed entries under `[0.0.5]` (the release is still unreleased, so
  no version bump).
- `.agents/summary/review_notes.md`: remaining issue 12 updated to reflect the fixed
  side issues and the still-open original failure.

## Validation

- `make check`: lockfile, ruff, format, mypy, basedpyright and deptry all pass.
- `make test`: **360 passed**.
- Research probes (outside the suite): 7 passed after the fix; complete load output,
  empty inherited stdout.
- Review feedback `pdd_review-1` applied for findings 2-4; finding 1 (knowledge base
  refresh) was deferred at the user's request.

## Artifacts

- `rough-idea.md` — original report and the other host's analysis.
- `research/reproduction.md` — what could and could not be reproduced.
- `research/load-output-truncation.md` — verified mechanism and impact.
- `research/error-surfacing.md` — diagnostic gap and remaining hypotheses.
- `research/probes/` — executable evidence (load truncation; flush recovery).
- `design/detailed-design.md` — standalone design.
- `implementation/plan.md` — steps, tests and implementation notes with deviations.
- `pdd_review-1.md` — review of the PDD and implementation; findings 2-4 applied,
  finding 1 deferred to the knowledge-base refresh.

## Next steps

1. Restart or repoint the MCP server on the original host at this checkout and retry the
   failing call. With the new error text and server traceback, the cause should be
   identifiable if it recurs.
2. Refresh the committed knowledge base with the codebase-summary skill (the session
   engine, capture helper, error behavior and planning records changed).
3. Commit the working tree after review. No commit was made by the agent.
