# Idea honing — more interpreter bugs

Status: requirements clarification in progress.

This document refines the rough idea into testable requirements. It is grounded in
the reproduction research: the shared `ProcessPoolExecutor` gives every concurrent
call a shared fate; a timed-out call kills the pool, unrelated calls fail with
"Maude worker crashed", and pending futures can surface as a bare `CancelledError`
in the "Unexpected failure" wrapper. The pool's call queue also makes a queued
timeout indistinguishable from a running one (`future.cancel()` is `False` for the
first `max_workers + 1` queued calls).

## 1. Decisions already taken

These are fixed inputs from the discussion and the research; they are not open
questions.

- **D1 — Architecture: one dedicated process per call (O3).** No pool. Each tool
  call spawns one process, sends one request, receives one response, and the
  process exits. This matches the existing fresh-interpreter-per-task guarantee and
  removes the shared-fate semantics entirely.
- **D2 — No third-party process-pool dependency.** Pebble is rejected on
  LGPL-3.0/GPL-2.0-only grounds; billiard is license-compatible but its pool
  threads can `os._exit`/SIGTERM the server, so it is not adopted.
- **D3 — Stdlib only.** `multiprocessing` with the `spawn` context and
  `multiprocessing.connection.Connection` (one-shot Pipe IPC).
- **D4 — Preserve the public tool contracts.** `maude_run` keeps per-step
  outcomes as data and whole-call failures as `MaudeRunError`;
  `maude_program_diagnostics` keeps its success/summary/diagnostics semantics and
  all-or-nothing aggregation. No breaking schema changes.
- **D5 — No retries.** A failed call is reported to the client, which decides
  whether to retry (current documented behavior).
- **D6 — B4/B7 need no code change.** Step stdout is empty by design (the
  bindings return values), and the load-phase flush fix already captures a bounded
  search at EOF. They get regression tests only.
- **D7 — The server process never imports `maude`.** The interpreter continues to
  live only in worker processes.

## 2. Proposed functional requirements

Each requirement is testable. "Call" means one `maude_run` or
`maude_program_diagnostics` tool invocation.

- **FR-1 — Per-call isolation.** A crash, timeout, or init failure in one call
  must not fail, cancel, or corrupt any other concurrent call. The failure is
  reported only to the call that owns the process.
- **FR-2 — Hermetic calls.** Every call runs in a fresh interpreter process; no
  loaded module, parser state, current term, or Maude global survives to another
  call. This includes the `q .` parser-residue case.
- **FR-3 — Whole-call timeout.** The call's timeout budget covers admission
  (waiting for a concurrency slot), process spawn, Maude initialization, file
  load, and every step. On expiry, the call's process is killed, the call gets a
  specific timeout error, and other calls are unaffected.
- **FR-4 — Bounded concurrency.** At most `maude_workers` interpreter processes
  exist at once. Waiting for a slot is bounded by the call's timeout; there is no
  unbounded queue and no eager pool.
- **FR-5 — Crash containment.** If a child dies abruptly (SIGSEGV, `os._exit`,
  OOM-kill), the parent detects it via the connection (EOF/`OSError` mid-message),
  maps it to a crash error, and the server continues serving other calls.
- **FR-6 — Distinct error categories.** The client must be able to distinguish at
  least: whole-call timeout, worker crash, Maude initialization failure, remote
  interpreter exception, shutdown/cancellation, invalid input (missing file, bad
  path, missing module, theory module), and an internal protocol failure. Per-step
  failures (`parse-error`, `too-large`) remain data in a successful result, not
  errors.
- **FR-7 — Rich, client-visible error details.** Whole-call failures must carry as
  much actionable detail as the MCP tool-error channel reliably supports. The
  error text is self-contained; it must not depend on `structuredContent` being
  preserved for error results. At minimum it includes:
  - the failure category and the exception type and message;
  - the full cause chain, outermost to root, including the remote (worker-side)
    type and message;
  - the call context: resolved absolute path, module name, phase (load / a step
    index and command / worker startup / shutdown), timeout seconds, and the
    worker pid when available;
  - a bounded, human-readable traceback (worker-side preferred, since that is
    where the failure originated), plus the server-side traceback when the
    failure originated in the server;
  - a truncation marker when a detail is capped.
  The full untruncated detail is always logged server-side. Requirements ER-1 to
  ER-6 below refine this.
- **FR-8 — Diagnostics failures are equally rich.** When
  `maude_program_diagnostics` aggregation fails, the client-visible error names
  every failing provider and carries each provider's cause chain and the same
  context fields as FR-7. The all-or-nothing semantics are unchanged.
- **FR-9 — Fail-fast initialization.** The lifespan still verifies that
  `maude_workers` fresh interpreters can initialize Maude within the diagnostics
  timeout; failure raises `MaudeInitError` and prevents the server from starting.
- **FR-10 — Clean shutdown.** The lifespan shutdown kills and reaps any in-flight
  child processes, is idempotent, leaves no orphans/zombies, and never hangs the
  server exit. In-flight calls receive a shutdown/cancellation error if a client is
  still waiting.
- **FR-11 — Wire robustness.** The parent always passes
  `recv_bytes(maxlength=...)`, distinguishes a malformed/oversized envelope from a
  crash, and bounds the response wait by the call deadline. The request send has no
  separate deadline but is bounded by child bootstrap (the child reads before
  importing Maude), and a dead child yields `BrokenPipeError`; a bootstrap-level
  hang is a residual risk with a watchdog fallback.
- **FR-12 — No behavioral regression.** Existing success results, per-step
  semantics, diagnostics ordering/severity/fix behavior, and tool schemas are
  unchanged. Only failure messages and worker internals change.
- **FR-13 — Performance.** Per-call cost is no worse than the current
  `max_tasks_per_child=1` behavior (spawn + prelude init); concurrency remains
  bounded by `maude_workers`. No global serialization beyond slot admission.
- **FR-14 — Observability.** Every failure logs the call context, exception type,
  cause chain, remote traceback, worker pid, phase and duration. Nothing logs
  while stdout/stderr are captured (the existing capture invariant).
- **FR-15 — Tests.** Unit tests cover the protocol envelope, exception mapping,
  truncation, admission and shutdown with fakes. Integration tests cover real
  SIGSEGV/abrupt exit, a non-terminating step with timeout, concurrent isolation
  (the attempt-4 recipe), a large response, parse errors and diagnostics. The
  reproduction scenarios become regression tests.
- **FR-16 — Documentation.** `README.md`, `CHANGELOG.md`, the tool descriptions and
  the `.agents/summary` knowledge base are updated for the new error behavior and
  architecture; `docs/modules.md` covers new modules if any.

## 3. Error reporting requirements (detail)

The MCP protocol's reliable error channel is the tool result text with
`isError: true` (FastMCP raises/converts the exception); protocol errors are
JSON-RPC errors. Structured content is defined for tool results, but clients are
not required to preserve it for error results, so **the text must stand alone**.

- **ER-1 — Self-contained text.** A reader with only the tool error text must be
  able to identify what failed, where, why, and what to try next.
- **ER-2 — No hidden cause.** When an exception has `__cause__`/`__context__`, the
  text includes the chain. A remote exception's type and message must survive the
  IPC boundary; its traceback is included as text.
- **ER-3 — Context.** Include the resolved path, module, step index and command
  (or "load"/"startup"), timeout, and pid where applicable.
- **ER-4 — Bounded.** The total error text is capped by
  `HAROLD_ERROR_DETAIL_MAX_CHARS` (default 4000, proposed; see P1). The first line
  is always present; if it alone exceeds the cap, its message part is truncated
  while the category and type are kept. The traceback is shortened first; a
  truncation marker states that details were logged server-side.
- **ER-5 — No secrets.** Do not include environment variables, unrelated process
  state, or file contents. Paths and module names are allowed.
- **ER-6 — Stable shape.** Use a consistent format, e.g.
  `Maude interpreter session failed: timeout: <details>` /
  `Maude interpreter session failed: crashed: <details>`, with a
  `Type: message <- Type: message` cause chain. Per-step data is not converted
  into an error.
- **ER-7 — Diagnostics aggregation.** The `DiagnosticCollectionError` text lists
  every failing provider and its chain; the full traceback is logged.
- **ER-8 — Tests.** Assert the type, message, cause, context, traceback presence
  and truncation behavior, and assert that no secret-like values appear.
- **ER-9 — FastMCP channel.** FastMCP 3.4.7 converts a raised exception into
  `ToolError("Error calling tool '<name>': <str(exc)>")`; it does **not** include
  the cause chain or traceback automatically, and `mask_error_details` is off in
  this server. The tool must therefore format the full detail into the
  `MaudeRunError` / `DiagnosticCollectionError` message before raising.
  `ToolResult(is_error=True, structured_content=...)` exists and maps to
  `CallToolResult(isError=True)` (via `ToolResult.to_mcp_result`), but it is not a
  viable primary channel here: the tool has an inferred success output schema and
  MCP requires structured results to conform to it, and FastMCP's own client
  raises on `isError` and ignores `structuredContent` on error results. Text is the
  reliable channel; structured error content is optional at best.

## 4. Non-functional requirements

- **NFR-1 — Platform.** Python 3.14.x. The code must support **Linux and macOS**,
  and ideally **Windows**, using portable `multiprocessing` APIs only
  (`get_context("spawn")`, `Pipe`, `Connection.send_bytes`/`recv_bytes`,
  `Process.kill()`/`join()`/`daemon`); no POSIX-only calls in the new transport
  (`os.killpg`, `signal.SIGKILL`, `resource`, `fork`). Development and CI run on
  Linux only because of resource constraints; macOS/Windows are best-effort and
  must fail with a clear diagnostic when the `maude` bindings are unavailable.
  Actual platform availability is ultimately bounded by the `maude` wheel and the
  existing fd-capture code, which are out of scope for this change.
- **NFR-2 — Dependencies.** No new runtime dependencies; stdlib only.
- **NFR-3 — Safety.** Maude directory/file/process IO stays disabled in the
  worker; the IPC payload is parsed defensively; a malformed message cannot crash
  the server.
- **NFR-4 — Bounded memory.** Response caps remain enforced; the parent passes a
  `maxlength` to `recv_bytes`; no unbounded buffering.
- **NFR-5 — Logging hygiene.** No logging while fds 1/2 are captured; child
  stdout/stderr never contaminate the MCP stdio transport.
- **NFR-6 — Maintainability.** The process transport is isolated behind a small
  seam (a runner/connection abstraction) so unit tests do not spawn processes;
  error mapping lives in one place.

## 5. Acceptance criteria

1. The attempt-4 recipe (three occupiers + a queued 2 s non-terminating call +
   four healthy searches) produces: the occupiers and searches either complete or
   fail without `CancelledError`, and only the timed-out call reports a timeout;
   no client sees "Unexpected failure ...: CancelledError".
2. A worker that segfaults/`os._exit`s fails only its own call; concurrent calls
   succeed and the server stays up.
3. A non-terminating step times out and its process is killed; no other call is
   affected; a subsequent call succeeds.
4. Error text for a simulated worker exception contains its type, message, cause
   chain, path/module/step context and a bounded traceback; the full detail is in
   the server log.
5. The diagnostics tool reports all failing providers with their causes, and its
   success/summary behavior is unchanged.
6. `make check`, `make test`, and `make docs-test` pass; new regression tests
   fail on the old architecture and pass on the new one.
7. No orphan processes remain after normal use, timeouts, crashes, or shutdown
   (verified in integration tests by pid checks).

## 6. Out of scope

- Changing `maude_run`'s step vocabulary, result models, or per-step semantics.
- Changing the diagnostics severity/ordering/fix contract.
- Retries, persistent interpreter reuse, or a warm pool.
- Adding pebble/billiard or any new runtime dependency.
- The RAG/docs tool.
- Changing the default `maude_workers` value.

## 7. Proposed defaults (autonomous refinement)

These are decisions taken to keep the requirements actionable. They are design-level
defaults; correct any you disagree with without reopening the functional
requirements.

- **P1 — Error detail cap.** New setting `error_detail_max_chars`
  (`HAROLD_ERROR_DETAIL_MAX_CHARS`, default 4000, `gt=0`). The first line is always
  present; if it alone exceeds the cap, its message is truncated while the category
  and type are kept. The traceback is shortened first; a marker points to the
  server log.
- **P2 — Remote exceptions.** A remote Python exception is a distinct category
  (`MaudeWorkerRemoteError(MaudeWorkerError)`) whose reason names the remote type
  and message; the full remote traceback is appended per P1. This is distinct from
  a crash (EOF) and a timeout.
- **P3 — Shutdown cancellation.** Calls killed by server shutdown raise
  `MaudeWorkerCancelledError(MaudeWorkerError)` with a "cancelled during shutdown"
  reason. A bare `concurrent.futures.CancelledError` must never reach the tool.
- **P4 — Wire format.** JSON over `Connection.send_bytes` with
  `ensure_ascii=False`; the request/response envelope is explicit. The parent
  always passes `recv_bytes(maxlength=...)`; the cap must be above the legitimate
  maximum result size (design default 2 GiB). An oversized/malformed envelope is a
  distinct protocol error naming the setting, not a crash.
- **P5 — Admission.** `threading.BoundedSemaphore(maude_workers)`;
  `acquire(timeout=remaining_budget)`. Failure raises the timeout error with a
  "no interpreter slot available" context.
- **P6 — Startup.** `start()` spawns `maude_workers` short-lived init processes in
  parallel, waits with the diagnostics timeout, and raises `MaudeInitError` on the
  first failure; no pool is created.
- **P7 — Portable transport.** Only portable `multiprocessing` APIs; Linux is the
  tested platform, macOS/Windows best-effort (NFR-1).
- **P8 — Child lifecycle.** One-shot process, `daemon=True`; the parent owns
  `kill()`/`join()` on timeout and shutdown; in-flight children are tracked in a
  lock-protected set.
- **P9 — Error text shape.** A stable first line naming the category, followed by
  the cause chain (`Type: message <- Type: message`), the call context
  (path/module/step/timeout/pid), and the bounded worker traceback. The exact
  punctuation is a design detail; the fields are not.
- **P10 — Diagnostics.** `DiagnosticCollectionError` keeps its all-or-nothing
  behavior and lists every failing provider with its chain; no aggregation change.

## 8. Questions and answers

### Q1 — How rich should the client-visible error text be?

The MCP tool-error text is the reliable channel. The FastMCP 3.4.7 check narrows the
options:

- FastMCP has `ToolResult(is_error=True, structured_content=...)` and maps it to
  `CallToolResult(isError=True)`, so a structured payload is technically possible.
- However, the tools have inferred success output schemas; MCP requires structured
  results to conform to the declared schema, so an error-shaped payload would force
  a schema change (e.g. a union) for an uncertain client benefit. FastMCP's own
  client raises on `isError` and drops `structuredContent` on errors.
- FastMCP wraps a raised exception as `Error calling tool '<name>': <str(exc)>`;
  it does not append the cause chain or traceback. The text must therefore be
  formatted in full before raising.

Options:

- **A. Compact.** Category + `Type: message` + cause chain + context, no
  traceback. Smallest context cost; the traceback stays in the server log.
- **B. Bounded traceback (recommended).** A + the worker-side traceback (the
  originating one) truncated to a total cap (proposal: 4000 characters), with a
  truncation marker; the server logs the untruncated detail.
- **C. Maximum text.** A + both worker and server tracebacks, capped at a larger
  limit (e.g. 16000 characters). Most detail, highest context cost and noise.
- **D. Structured error payload.** Not recommended: it conflicts with the current
  success output schema and FastMCP clients drop structured content on `isError`;
  the text must still carry everything. Only revisit if the success schema is
  deliberately redesigned as a union.

**Answer: B — bounded traceback.** The client-visible text includes the
worker-side traceback, capped by `HAROLD_ERROR_DETAIL_MAX_CHARS` (default 4000,
proposed in P1) with a truncation marker; the full detail is logged server-side.
