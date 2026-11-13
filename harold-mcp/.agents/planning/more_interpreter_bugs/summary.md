# Summary — more interpreter bugs

## Status

Requirements, research, design (three review rounds) and the implementation plan
are complete. No production code has been changed yet.

## Artifacts

- `rough-idea.md` — original report and the reproduction attempts (2–4, diff).
- `idea-honing.md` — refined requirements: FR-1..16, ER-1..9, NFR-1..6,
  acceptance criteria, proposed defaults P1–P10, Q1 answer (bounded traceback).
- `research/plan.md` — research plan and status.
- `research/reproduction.md` — reproduced cascade, exact messages and
  non-determinism.
- `research/cpython-pool-semantics.md` — CPython 3.14 call-queue, `cancel()` and
  `kill_workers()` semantics.
- `research/step-output.md` — B4/B7 findings (step stdout by design; load capture
  fixed).
- `research/error-taxonomy.md` — hierarchy/reachability (B5/B6).
- `research/architecture-options.md` — O0–O3 comparison and recommendation.
- `research/billiard.md` — billiard license and verified semantics.
- `research/ipc.md` — one-shot Pipe IPC probe and protocol implications.
- `research/probes/` — executable probes and fixtures (CPython pool, executor
  cascade, step output, pebble, billiard, IPC).
- `design/detailed-design.md` — standalone design incorporating all reviews.
- `design/detailed-design-review-1/2/3.md` — review records (all findings
  addressed).
- `implementation/plan.md` — six test-driven, demoable steps with checklist and
  working agreements.
- `summary.md` — this document.

## Design in brief

The shared `ProcessPoolExecutor` is replaced with one dedicated `spawn` process per
call. A `BoundedSemaphore(maude_workers)` admits calls; each call sends one JSON
request and receives one JSON response over a `multiprocessing` Pipe, then the child
exits. A crash or timeout kills only that child. The child redirects fds 0/1/2 to
devnull at startup, initializes Maude, dispatches `ping`/`diagnostics`/`session`,
and sends a success or category-tagged error envelope.

The error model has distinct categories (timeout, crash, spawn, init, remote,
cancelled, protocol, input, unexpected). `MaudeInitError` becomes a
`MaudeWorkerError`; the new `MaudeWorkerSpawnError`/`RemoteError`/`CancelledError`/
`ProtocolError` complete the taxonomy. A stdlib-only formatter renders a stable
first line, context, cause chain (including the remote cause), and a bounded
originating traceback. The client gets `HAROLD_ERROR_DETAIL_MAX_CHARS` (4000) of
detail; the server logs the uncapped report. FastMCP forwards the exception text;
structured error content is deliberately not used because it conflicts with the
success output schema and is dropped by clients on `isError`.

The test plan covers the original bugs B0–B7, the three review rounds' findings,
the historical cascade, real crash/timeout isolation, large request/response,
shutdown/orphan checks, capture behavior and diagnostics parity. Unit tests use
fake runners/connections; integration tests use real `spawn` processes and the real
interpreter with deterministic crash/timeout targets.

## Implementation plan in brief

1. Error model, formatter, and rich tool errors (works on the current pool).
2. One-shot IPC transport and process runner (unit + real-process tests).
3. Replace the pool executor with per-call processes (executor rewrite and tests).
4. Real-process isolation, regression, and pool-remnant cleanup.
5. Diagnostics end-to-end and error parity.
6. Documentation and final validation.

Each step has an objective, implementation guidance, test requirements,
integration notes and a demo. The plan uses the required step-by-step working
agreement: confirm after each step and record Implementation notes.

## Next steps

1. Start implementation at Step 1; after each step, confirm before proceeding.
2. Run `make check` and `make test-unit` per step; the full `make test`,
   `make check` and `make docs-test` before completion.
3. After the behavior changes, refresh the committed codebase-summary knowledge
   base and add the CHANGELOG entry; suggest a version bump to the user (no commit
   is made by the agent).

## Areas to watch

- The research probes were not re-executed during the design reviews; their
  recorded outputs are the evidence. The implementation's integration tests will
  re-validate the important ones.
- macOS/Windows remain best-effort: the transport uses portable APIs, but CI is
  Linux-only and the Maude wheel/capture code remain the platform limit.
- The `path="full"` result can approach the 2 GiB IPC cap in theory; the child's
  memory is the practical bound, and the oversize error names the setting.
- The shutdown-window fix relies on the runner's registration and closed check
  sharing one lock; the synchronized unit test and the in-flight integration test
  are required to keep it.
