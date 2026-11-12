# Error surfacing for unexpected `maude_run` failures

Status: **implemented** — the tool now includes the exception type and message in the
wire error and logs the traceback server-side.

## The gap

`maude_run` maps the expected failures to specific `MaudeRunError` messages:

- a load failure names the file (and includes stderr detail);
- a missing module lists the modules the load defined;
- a theory module explains that terms cannot be parsed in a theory;
- worker crashes and timeouts use `MaudeWorkerError.reason` ("worker crashed" /
  "worker timed out").

Everything else is caught by a generic branch:

```python
except Exception as exc:
    raise MaudeRunError("Unexpected failure running the Maude interpreter session") from exc
```

The original exception stays chained server-side, but MCP clients only see
`str(MaudeRunError)`, so the type, message and traceback were lost on the wire. The
reported failure was exactly this generic text, which is why the cause could not be
identified from the client side. The committed knowledge base already flagged this as
the recommendation for the open investigation.

## Hypotheses for the original non-deterministic error

The output-truncation/leak bug found on the same file is a **different** defect: it
cannot raise inside `executor.run_session`. The generic text still requires a non-
`MaudeWorkerError` exception. Candidate sources:

1. **A worker-side exception** that is not one of the per-step outcomes — for example a
   SWIG binding error, `MemoryError` under memory pressure, or an `OverflowError` from a
   binding typemap. Worker exceptions propagate through `future.result()` unchanged.
2. **A pool-management exception** not covered by `_run_task`'s
   `BrokenProcessPool`/`TimeoutError` mapping — for example a `RuntimeError` from a
   shut-down executor or a `CancelledError`.
3. **Resource exhaustion** on the less powerful host (spawn failure, OOM) surfacing as
   an `OSError` rather than a broken pool. A worker killed by the OS normally becomes
   `BrokenProcessPool` ("worker crashed"), but an exception raised before/around the
   pool call would not.
4. **A different call/file than the report** (the reporting agent mentioned a "trace"
   search, while the JSON shows `SHEPHERD`; the attached server's schema also differed).
   The next occurrence should include the request context in its report.

## Change

- `_exception_detail(exc)` renders `TypeName: message`, or just `TypeName` when the
  message is empty.
- The generic branch raises
  `MaudeRunError("Unexpected failure running the Maude interpreter session: <detail>")`
  and keeps `from exc`.
- `get_logger(__name__).exception(...)` logs the traceback (including the remote worker
  traceback that `concurrent.futures` attaches) to the server log before raising,
  together with the request path and module so the log line can be correlated with the
  client call. This runs in the server process on stderr, separate from the worker
  capture.
- Tests extend the existing chaining test with a recording logger that asserts the
  ERROR log call and its path/module arguments. The capture fix's flush-failure
  suppression is covered by unit tests that make the Python and libc flushes raise and
  check that the phase result and captured output are unchanged.

## What this does and does not solve

It does not identify or fix the original non-deterministic failure. It makes the next
occurrence actionable: the client-visible message names the exception type and text, and
the server log has the traceback. Combined with the capture fix (no more stray output in
the MCP stdio stream), the next reproduction on the slower host can be classified as a
genuine session exception, a pool problem, or a transport issue instead of a generic
"unexpected failure".
