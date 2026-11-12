# Implementation Plan — Complete Maude output capture and diagnosable `maude_run` failures

## Checklist

- [x] Step 1: Flush captured stdio (unit tests first)
- [x] Step 2: Integration regression for a bounded search at the end of a load
- [x] Step 3: Surface unexpected exception details in `maude_run`
- [x] Step 4: Full validation, changelog and planning records

## Working agreements

Proceed step by step:

- After each step, ask me for confirmation before completing it
- When completing a step, add an "Implementation notes" subsection to its section in the plan, summarizing what we did, focusing on deviations from the plan, why we made them, and implications for subsequent steps

Additional agreements for this plan:

- Run `make check` and `make test` from the package directory before declaring the plan
  complete.
- Do not commit; leave the working tree for the user to review and commit.
- The probes under the research record stay outside `tests/` so the normal suite does
  not collect them.

## Step 1: Flush captured stdio

**Objective.** Make `capture_streams` flush Python and C/C++ stdio buffers while the
capture descriptors are installed, so the tail of a phase is never left for a later
flush.

**Guidance.** Add a private `_flush_stdio()` helper using `sys.stdout.flush()`,
`sys.stderr.flush()` and libc `fflush(NULL)` through `ctypes`, with every failure
suppressed. Call it before redirecting fds (pre-existing output must not enter the
capture) and in the `finally`, before restoring the descriptors. Keep the public
signature and return shape unchanged.

**Tests.** Write the failing unit test first: call C `printf` for text without a newline
inside `capture_streams` and assert it is captured. Add the companion test that the same
bytes do not reach a stdout sink after the capture. Add suppression tests for a failing
Python flush and a failing libc flush: the phase result and captured output must still
come back unchanged.

**Integration.** No other module changes are needed; `maude.load` and the session engine
call the helper through the existing interface.

**Demo.** `uv run python -m pytest tests/unit/test_maude_capture.py -q` passes,
including the C-buffer and no-leak cases.

**Implementation notes.** Added `_flush_stdio()` as designed: Python stream flushes,
then `ctypes.CDLL(None).fflush(None)` with explicit `argtypes`/`restype`; failures are
suppressed. The helper is called before the redirect and again in the `finally` before
restoring fds. basedpyright's unused-call-result rule required `_ =` on the Python
flushes. The new unit tests pass, including the C-buffer, no-leak and both flush-failure
suppression cases, and the existing capture tests are unchanged.

## Step 2: Integration regression for a bounded search at the end of a load

**Objective.** Prove with the real interpreter that a load whose last command is a
bounded search reaching its bound now reports the search result in `load_output`.

**Guidance.** Add a fixture with a tiny module and `search [1] a =>* Z:S .` as the last
line. Add an integration test that runs a session with no steps and asserts the header,
`Solution 1 (state 0)` and the binding in `load_output["stdout"]`.

**Tests.** The test fails before the flush (only the header is captured) and passes
after it.

**Integration.** Uses the existing module-scoped `MaudeExecutor` fixture; no new
dependencies or protocol fields.

**Demo.**
`uv run python -m pytest tests/integration/test_maude_session_integration.py -q` passes.

**Implementation notes.** Added `tests/integration/fixtures/bounded_search_last.maude`
and `test_bounded_search_at_the_end_of_the_load_is_captured`. Deviation: the first draft
also asserted that a `search` **step** captures Maude's textual block. That test failed
with an empty step stdout; investigation showed the bindings' search API returns results
programmatically and prints nothing, so step stdout is empty by design. The test was
removed and the research note corrected: the observable loss is in the load phase (the
only phase that executes embedded commands). This also confirmed the original host's
statement that `maude_run` steps are unaffected, for textual output. The integration file
ends at 37 passing tests.

## Step 3: Surface unexpected exception details in `maude_run`

**Objective.** Make a non-`MaudeWorkerError` failure diagnosable from the MCP client and
the server log.

**Guidance.** Render the exception as `TypeName: message` (or `TypeName` when the
message is empty), include it in the existing `Unexpected failure ...` message, keep the
original exception chained, and log the traceback with the module logger before raising,
including the resolved request path and module. Leave the `MaudeWorkerError` branch
untouched.

**Tests.** Extend the existing chaining test to assert `ValueError: boom` appears in the
message; add a test for an empty-message exception that asserts only the type appears.
Use a recording logger to assert the ERROR log call and its path/module arguments.

**Integration.** The tool boundary is unchanged for expected failures; the new text is
the only wire-visible difference.

**Demo.** `uv run python -m pytest tests/unit/test_interpreter_tool.py -q` passes.

**Implementation notes.** Added `_exception_detail`, the module-level logger, and
`_log.exception(...)` in the generic branch with the resolved path and module. The
client message appends the detail and the cause remains chained. The chaining test now
uses a recording logger and asserts both the wire text and the log call; the
empty-message test passes. Logging runs in the server process on stderr; it does not
interact with the worker capture.

## Step 4: Full validation, changelog and planning records

**Objective.** Validate the whole repository and record the change.

**Guidance.** Run `make check` and `make test`. Update the changelog's Fixed section.
Update the research record with the post-fix probe behavior and the error-surfacing
notes. Do not bump the version: the changes belong to the unreleased `0.0.5` section.

**Tests.** The full suite and static checks must pass.

**Integration.** No further code changes expected after this step.

**Demo.** `make check` and `make test` both succeed.

**Implementation notes.** `make check` passes (lockfile, ruff, format, mypy,
basedpyright, deptry). `make test` passes: 360 tests. The changelog has two Fixed
entries. The research probes were updated to assert post-fix behavior and pass when run
explicitly (7 passed; complete load output, empty inherited stdout). No version bump was
made because `0.0.5` is not released yet. Remaining follow-up: reproduce the original
generic failure on the slower host now that the error text and traceback are available,
and refresh the committed knowledge base.

## Review feedback applied (`pdd_review-1`)

- **Finding 2 (flush-failure suppression had no test).** Added
  `test_capture_streams_suppresses_python_flush_failures` and
  `test_capture_streams_suppresses_c_flush_failures`; both assert the phase result and
  captured output are unchanged.
- **Finding 3 (traceback logging was not asserted).** The existing chaining test now
  replaces the module logger with a recording logger and asserts one ERROR record for
  the unexpected failure.
- **Finding 4 (no request context in the log line).** The log call now includes the
  resolved path and module, and the recording logger test asserts both arguments.
- **Finding 1 (knowledge base refresh)** was deferred at the user's request; the user
  will run the codebase-summary refresh.
