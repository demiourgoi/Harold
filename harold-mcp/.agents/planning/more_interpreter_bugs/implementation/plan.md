# Implementation plan — isolated interpreter workers with rich failures

## Checklist

- [x] Step 1 — Error model, formatter, and rich tool errors
- [ ] Step 2 — One-shot IPC transport and process runner
- [ ] Step 3 — Replace the pool executor with per-call processes
- [ ] Step 4 — Real-process isolation, regression, and pool-remnant cleanup
- [ ] Step 5 — Diagnostics end-to-end and error parity
- [ ] Step 6 — Documentation and final validation

## Working agreements

Proceed step by step:

- After each step, ask me for confirmation before completing it
- When completing a step, add an "Implementation notes" subsection to its section in the plan, summarizing what we did, focusing on deviations from the plan, why we made them, and implications for subsequent steps

Additional agreements for this project:

- Use `UV_CACHE_DIR=/tmp/uv-cache` for `make`/`uv` commands when the default cache is read-only.
- After every step run `make check` and `make test-unit`; run the focused integration tests for the step. Before declaring the plan complete run `make test`, `make check`, and `make docs-test`.
- Never commit or stage; use only read-only `git` commands.
- Keep the server process free of `maude` imports; add no runtime dependencies.
- Update the tests in the same step as the production code; do not accumulate untested code.
- Follow the detailed design; record any deviation and its implications in the step's Implementation notes.
- Do not edit `.md.html` files that sit next to a `.md` source.

## Scope and references

Implement the approved design: one dedicated `spawn` process per interpreter call, a
one-shot JSON request/response over a `multiprocessing` Pipe, semaphore admission,
a process runner with a shutdown-safe active map, and rich bounded error text in
the MCP tool responses.

Context documents: the detailed design and the requirements/idea-honing record
live in this project directory. The design is the normative source for behavior;
this plan is the implementation order.

Baseline: Python 3.14.x, `maude==1.6.0`, stdlib only, `spawn` start method. The
project splits tests into `tests/unit/` (hermetic, no interpreter) and
`tests/integration/` (real interpreter); `make test` is the authoritative full run.

---

## Step 1: Error model, formatter, and rich tool errors

**Objective.** Introduce the shared error formatter and the final error taxonomy,
and make `maude_run` and `maude_program_diagnostics` return rich, bounded error
text while the current pool executor is still in place. This is a user-visible
increment and the foundation for the worker rewrite.

**Implementation guidance.**

- Add a stdlib-only `harold_mcp.errors` module with
  `format_error_report(exc, *, context, max_chars, category=None)`:
  - first line `<category>: <message>` (or `<Type>: <message>` when no category);
  - merged context (`{**getattr(exc, "context", {}), **context}`, caller wins);
  - cause chain starting with the exception itself, then `__cause__`/`__context__`
    with a cycle guard, then `remote_type: remote_message` when present;
  - originating traceback via
    `traceback.format_exception(type(exc), exc, exc.__traceback__)` for local
    failures, or `remote_traceback`;
  - truncation: traceback first, then long causes, then the first-line message;
    `max_chars <= 0` disables truncation (server-log rendering).
- Add `Settings.error_detail_max_chars` (`HAROLD_ERROR_DETAIL_MAX_CHARS`, default
  4000, `gt=0`).
- Extend the executor error hierarchy in `maude/executor.py`:
  - `MaudeWorkerError` gains `category`, `context`, `remote_traceback` while
    keeping `reason`;
  - add `MaudeWorkerSpawnError`, `MaudeWorkerRemoteError`,
    `MaudeWorkerCancelledError`, `MaudeWorkerProtocolError`;
  - change `MaudeInitError` to subclass `MaudeWorkerError` with reason
    `"Failed to initialize the Maude interpreter in the worker process"`;
  - keep `MaudeWorkerCrashedError` and `MaudeWorkerTimeoutError` behavior.
- Replace `_exception_detail` in `server/tools/interpreter.py` with the formatter:
  build the context (resolved path, module, step count, timeout), log the uncapped
  report (`max_chars=0`), raise `MaudeRunError` with the capped report; do the same
  in the generic branch. Keep per-step `parse-error`/`too-large` data untouched.
- Make the input-error raise sites (path/steps validation, missing file, missing
  module, theory module) include the same context line while keeping their specific
  messages; the context line applies to every whole-call failure, not only the two
  except branches.
- Make `diagnostics.aggregate.DiagnosticCollectionError` carry the failing
  `(provider_name, exception)` pairs and render provider sections with the same
  formatter; keep all-or-nothing aggregation.
- Update `server/tools/diagnostics.py` to log the full collection report with the
  path/provider context and re-raise it; keep the success/summary/diagnostics
  behavior unchanged.
- If `maude/provider.py` drops cause/context while wrapping a worker error,
  preserve the chain and add the path/phase context.

**Test requirements.**

- New `tests/unit/test_errors.py`: first-line shapes, category resolution,
  context-merge precedence, cause chain including the exception itself and the
  remote cause, **cycle guard**, stored exception outside a handler (no
  `NoneType: None`), traceback selection, truncation order and **marker**,
  huge-first-line last resort, `max_chars <= 0` unbounded, no secrets.
- Update `tests/unit/test_interpreter_tool.py`: timeout, crash, init, remote,
  spawn, cancelled and protocol errors produce the rich capped text; the log
  record holds the uncapped report; per-step data is unchanged; input errors
  (missing file, missing module, theory module) keep their specific message and
  include the context line.
- `tests/unit/test_settings.py`: `error_detail_max_chars` default.
- Add/update diagnostics unit tests: a provider failure renders its chain and a
  real traceback (not `NoneType: None`), the collection lists every provider, and
  the all-or-nothing contract is unchanged.
- Hierarchy tests: `MaudeInitError` is a `MaudeWorkerError`; categories are exposed
  as class attributes.

**Integration with previous work.** No architecture change yet. The current
executor still uses the pool; its existing `MaudeWorkerCrashedError`/
`MaudeWorkerTimeoutError` now reach clients with the richer text. Both tools keep
their schemas and success behavior.

**Demo.** A focused unit test with a fake executor shows a timeout and a remote
exception as `Maude interpreter session failed: timeout: ...` with context, cause
chain and traceback; a diagnostics provider failure shows its own section. Run
`make test-unit`.

### Implementation notes (Step 1)

Implemented as planned. Deviations and additions, with their rationale:

- `format_error_report` gained an additive `message=` keyword (defaults to
  `str(exc)`). The diagnostics aggregation needs its section first line to read
  `- interpreter: Maude worker timed out`; without the override the wrapping
  `DiagnosticProviderError`'s `str()` already starts with `interpreter:`, which
  would render `interpreter: interpreter: ...`. The design signature is otherwise
  unchanged.
- `harold_mcp.errors` also exposes `format_context` (used by the interpreter tool
  to append the context line to input errors) and `format_exception_text` (the
  `traceback.format_exception(type(exc), exc, exc.__traceback__)` helper, which
  Step 2's transport will reuse for `_format_exc`).
- `DiagnosticCollectionError` renders at construction from a new `max_chars`
  argument passed through `collect_diagnostics(..., max_chars=...)`, and exposes
  `format_report(max_chars)` for the uncapped log rendering. Its default cap is
  the new `DEFAULT_ERROR_DETAIL_MAX_CHARS` constant, which is also the default of
  `Settings.error_detail_max_chars`, so the seam keeps a single source of truth
  without importing settings. It also carries a `context` (the diagnosed path) so
  every provider section is self-contained.
- `DiagnosticProviderError` gained an optional `context`; the interpreter provider
  passes the resolved path, `phase="load"` and the worker error's own context, so
  the wrap no longer drops the chain's context.
- `_traceback_text` walks the cause chain for the first non-empty
  `remote_traceback`. A wrapper (`DiagnosticProviderError`) does not own the remote
  traceback, and without this walk a diagnostics failure would show only its local
  raise site.
- `maude_program_diagnostics` gained a `settings` FastMCP dependency (for the cap),
  matching `maude_run`. Direct callers (unit and integration tests) now pass
  `settings=Settings(maude_workers=1)`. The success/summary/diagnostics behavior is
  unchanged.
- The `maude_run` description still has the stale “replaces the worker pool”
  sentence: Step 6 owns that edit per the plan.
- The pool-era integration assertion in `test_tool_reports_crash_and_recovers` was
  updated to the new multi-line collection shape; that test is rewritten around the
  target seam in Step 4.
- The tool context keys are `path`, `module`, `steps` and `timeout`; worker-provided
  context (`phase`, `step`, `command`, `pid`) merges in with caller keys winning,
  which is what Steps 2/3 need.

Validation: `make check`, `make test-unit` (317 passed) and the focused integration
runs (`test_diagnostics_integration.py`, `test_maude_run_integration.py`; 41 passed)
are green.

---

## Step 2: One-shot IPC transport and process runner

**Objective.** Implement the one-shot Pipe protocol and the process runner, fully
unit-tested and exercised with real `spawn` processes, ready to replace the pool in
Step 3.

**Implementation guidance.**

- Add `harold_mcp.maude.transport`:
  - request/response envelopes (no version field):
    `{"operation", "payload"}` and
    `{"status", "result"}` / `{"status", "error", "error": {category, type,
    message, traceback, context}}`;
  - `serve_one(conn)`: try/except around the stdio redirect (`os._exit(1)` without
    printing on failure), first `recv_bytes` catching `(EOFError, OSError)`, JSON
    and payload validation inside the try, protocol errors with category
    `protocol`, dispatch `ping`/`diagnostics`/`session` with lazy
    `worker`/`session` imports and a close in `finally`; `_dispatch` always calls
    `worker.init_maude()` first, so `ping` is a real initialization check;
  - `ChildProtocolError`, `_format_exc`, `_worker_context`.
- Add a small annotation to `maude/session.py`: `run_session` wraps the load and
  each step, setting `exc.worker_context = {"phase": "load"}` or
  `{"phase": "step", "step": index, "command": command}` on unexpected
  exceptions; `_worker_context` reads it into the envelope.
- Add a stdlib-only `harold_mcp.maude.runner`:
  - `ProcessRunner` protocol and `PipeProcessRunner(settings, *, target=...)`;
  - spawn + `Pipe`, parent closes the child end, register under a lock, check the
    runner's `_closed` under the same lock, kill/join and raise
    `MaudeWorkerCancelledError` if closed;
  - send the request (`BrokenPipeError`/`OSError` → crash), `poll(remaining)` for
    the deadline, `recv_bytes(maxlength=settings.ipc_max_response_bytes)` with the
    EOF/mid-message/oversized mappings, decode and map by `error.category`;
  - `kill_all()` sets `_closed` then snapshots under the lock and kills/joins
    outside it; `active_count()` for tests; close/kill/join in `finally`;
  - constructed runner errors carry `pid=proc.pid` in their `context` (None when
    spawn failed), so ER-3's pid is present in the client text.
- Add `Settings.ipc_max_response_bytes` (`HAROLD_IPC_MAX_RESPONSE_BYTES`, default
  2147483648 / 2 GiB, `gt=0`); the oversize error names the setting.
- The transport/runner must not import `maude` at module level.

**Test requirements.**

- Unit transport tests: valid envelopes, non-object JSON, invalid operation/payload,
  unknown operation, protocol-category error, first-recv `OSError` treated as
  closed, redirect failure exits without output, stored-exception traceback helper,
  no version field.
- Envelope-mapping tests: a fake connection returns an `init`, `remote` and
  `protocol` error envelope and the parent raises `MaudeInitError`,
  `MaudeWorkerRemoteError` and `MaudeWorkerProtocolError` respectively; a
  fake-dispatch test asserts `init_maude` is called first and `serve_one` can
  dispatch without importing Maude.
- Session phase annotation tests: load and step exceptions carry `phase`/`step`/
  `command`; `test_load_failure_has_phase_load` and the step variant.
- Unit runner tests with fake process/connection: success, EOF, mid-message
  `OSError`, timeout, oversized response naming the setting, `BrokenPipeError` on
  send, spawn failure, shutdown registration race, active-map cleanup after every
  exit path; constructed errors carry the child pid in `context`.
- `tests/unit/test_settings.py`: `ipc_max_response_bytes` default and the combined
  new-settings assertions.
- Integration tests with the real `spawn` context: an injected crash target
  (`os._exit`), a timeout target, a large request (> 64 KiB), a large response with
  a lowered `ipc_max_response_bytes`, and a real `ping`/`load_diagnostics` through
  the runner. Assert one failure does not affect a peer call.

**Integration with previous work.** Uses the settings and error classes added in
Step 1. The runner is not yet wired into `MaudeExecutor`; Step 3 does that. The
component is exercised by unit and integration tests, not left dead.

**Demo.** A focused integration test runs `load_diagnostics` through
`PipeProcessRunner`; a crash target fails only its own call while a healthy target
returns a result. Run the transport/runner tests.

---

## Step 3: Replace the pool executor with per-call processes

**Objective.** Rewrite `MaudeExecutor` to own the runner and semaphore admission,
preserving `start`/`shutdown`/`diagnostics`/`run_session`, and remove the
`ProcessPoolExecutor` from the production path.

**Implementation guidance.**

- Rewrite `maude/executor.py`:
  - `__init__(settings=None, *, runner_factory=None)`: `_runner_factory`,
    `_runner=None`, `_semaphore = BoundedSemaphore(settings.maude_workers)`,
    `_closed = threading.Event()`.
  - `_run_operation(operation, payload, timeout, context)`: deadline, semaphore
    acquire with the remaining budget (false → timeout with "no interpreter slot
    available"), closed check, lazy runner creation, `runner.run`, release in
    `finally`.
  - `diagnostics(path)` and `run_session(request, timeout)` delegate.
  - `start(timeout)`: build a fresh runner, clear `_closed`, run `maude_workers`
    pings in parallel with a shared deadline, kill the runner and raise
    `MaudeInitError` on failure; restart after shutdown works.
  - `shutdown()`: set `_closed`, call `runner.kill_all()`, idempotent.
  - Remove `ProcessPoolExecutor`, `_reset_executor`, `_submit`, `submit`; the
    server lifespan API is unchanged.
- Remove the pool-only helper functions from `maude/worker.py` (`sleep`,
  `rendezvous_pid`, `_crash`) or leave them until Step 4 if needed to migrate the
  existing integration tests; prefer removing them here once the executor no
  longer uses them.
- Keep `get_maude_executor` and the singleton semantics.

**Test requirements.**

- Rewrite `tests/unit/test_maude_executor.py` around a fake `ProcessRunner`:
  success, timeout, crash, spawn failure, init failure, remote error, protocol
  error, stray `CancelledError` → cancelled, shutdown cancellation, crash while
  closed → cancelled, admission (a second call waits), `start()` pings
  `maude_workers` times and fails fast, `start()` after `shutdown()` uses a fresh
  runner, shutdown idempotence, lazy runner creation.
- Update the existing integration tests that used `executor.submit`/`sleep`/
  `rendezvous_pid` to the target seam or real sessions. Add a basic real
  `diagnostics` and `run_session` through `MaudeExecutor` (normal results
  semantically equal to the old behavior).
- Keep the current tool/diagnostics adapter tests green; no tool changes are
  expected beyond Step 1.

**Integration with previous work.** This is the point where Steps 1 and 2 are
wired into the application: the tools, the diagnostics provider and the lifespan
all call the new executor. The old pool tests are replaced, not kept alongside.

**Demo.** `maude_run` and `maude_program_diagnostics` run end-to-end through the
new executor on real fixtures; `start`/`shutdown` are clean; `make test-unit` and
the focused integration tests pass.

---

## Step 4: Real-process isolation, regression, and pool-remnant cleanup

**Objective.** Prove the reproduced bugs stay fixed under real processes, complete
the migration of the pool-era test helpers, and remove any remaining pool
abstractions.

**Implementation guidance.**

- Add the design's integration suite (or extend the existing files):
  - historical cascade: three slow occupiers, a queued non-terminating call with a
    2 s timeout, four healthy searches; no `CancelledError`, only the trigger
    times out, the others complete;
  - peer crash survival via the injected crash target; real timeout kills only its
    own process; a follow-up call succeeds;
  - large request (> 64 KiB) and large response (lowered
    `HAROLD_IPC_MAX_RESPONSE_BYTES`) round-trip;
  - step stdout empty/stderr warnings and bounded-search-at-EOF load capture
    (B4/B7);
  - parse error, `too-large`, missing module and theory module unchanged;
  - shutdown with an in-flight call; no orphan processes (pid checks).
- Remove the remaining pool helpers (`worker.sleep`, `worker.rendezvous_pid`,
  `worker._crash`) and any pool-specific test code; use test targets and real
  sessions instead.
- Update the integration fixtures (non-terminating rewrite module, bounded-search
  EOF module, large-result module, cascade modules, crash target) under the
  existing `tests/integration/fixtures/` layout.
- If a regression test exposes a gap (for example a missed cancellation mapping),
  fix it in the executor/runner and add the focused unit test.

**Test requirements.** The integration/bug matrix from the design: B0–B7 and the
review findings (including the session phase annotation and envelope-mapping tests
added in Step 2); B1/B2/B3 tests must fail on the old pool architecture and pass
here. No sleeps as synchronization; use markers, explicit deadlines or
`active_count`. Add the test names from the design (the names are illustrative).

**Integration with previous work.** Validates Step 3 and removes the last
pool-era code and tests; `maude/executor.py` and `maude/worker.py` no longer
contain pool abstractions or helpers.

**Demo.** The historical cascade and crash/timeout tests pass with per-call
isolation; no orphan processes remain after the shutdown tests; the full
integration suite is green.

---

## Step 5: Diagnostics end-to-end and error parity

**Objective.** Verify `maude_program_diagnostics` through the new executor and
ensure provider failures are rich, attributed and still all-or-nothing.

**Implementation guidance.**

- Update `maude/provider.py` so a `MaudeWorkerError` (including the new spawn,
  init, remote, cancelled and protocol errors) is wrapped in
  `DiagnosticProviderError` with its cause and the resolved path/context preserved.
- Ensure the diagnostics tool logs the full `DiagnosticCollectionError` report
  (uncapped) and returns the capped report, consistent with `maude_run`.
- Keep the diagnostics success result, ordering, severities, fixes and
  all-or-nothing behavior unchanged; do not let a provider failure leak partial
  diagnostics.

**Test requirements.**

- Unit provider tests: timeout, crash, init, remote, spawn and protocol errors map
  to a `DiagnosticProviderError` (or the documented specific error) with the cause
  chain and path context.
- Unit aggregation/tool tests: multiple providers fail → all names and chains are
  present; one provider succeeds and one fails → no partial result; the log holds
  the full report.
- Integration: diagnostics success on a clean fixture; a worker timeout/crash
  produces a rich provider section; warnings/severity/fix behavior are unchanged.

**Integration with previous work.** Uses the formatter from Step 1 and the executor
from Step 3; validates the diagnostics half of the design's error contract.

**Demo.** `maude_program_diagnostics` returns its normal result on a clean file and
a rich, provider-attributed error when the interpreter provider fails; the success
schema and ordering are unchanged.

---

## Step 6: Documentation and final validation

**Objective.** Update all user-facing and agent-facing documentation, add the
release notes, and run the full validation gate.

**Implementation guidance.**

- Update the `maude_run` tool description: remove the stale "replaces the worker
  pool" sentence; describe per-call isolation, the timeout covering
  admission/spawn/init, and the rich error categories.
- Update `README.md`'s `HAROLD_*` table with `HAROLD_ERROR_DETAIL_MAX_CHARS` and
  `HAROLD_IPC_MAX_RESPONSE_BYTES`; check the tool list/description is accurate.
- Update `docs/modules.md` with `harold_mcp.errors`, `harold_mcp.maude.transport`
  and `harold_mcp.maude.runner` (or the final module names).
- Update `CHANGELOG.md` under the current unreleased section; suggest the version
  bump to the user (do not commit or tag).
- Refresh the committed agent knowledge base per the project's
  codebase-summary workflow (or record the specific sections that need refreshing).
- Run the full gate: `make check`, `make test`, `make docs-test`.

**Test requirements.** `make check`, `make test` and `make docs-test` pass; the
docstring assertion for the stale sentence passes; the README/settings table and
`docs/modules.md` entries are present; no orphan process or changed success schema
is observed in the final suite.

**Integration with previous work.** Documents the completed architecture and error
behavior; no behavior change.

**Demo.** The full CI-equivalent gate is green, the strict docs build succeeds, and
the tool description/README describe the new behavior.

---

## Completion criteria

- All checklist items are checked and each step has its Implementation notes.
- The B0–B7 regression matrix and the review-finding coverage tests pass.
- `make check`, `make test` and `make docs-test` pass.
- No pool abstraction, `submit`, `sleep`, `rendezvous_pid` or `_crash` remains.
- The server process has no `maude` import and no new runtime dependency.
- Documentation and the knowledge base describe the final architecture.
