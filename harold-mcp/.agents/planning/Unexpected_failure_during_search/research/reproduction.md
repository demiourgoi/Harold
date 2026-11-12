# Reproduction — `maude_run` search failure

Status: **the reported `Unexpected failure running the Maude interpreter session` is not
reproducible on the current worktree (`main`, `6b7a19f`, `0.0.5.dev0`), but the
bounded-search output-loss/leak reported by the original host is reproducible
deterministically.** These are two different symptoms: the whole-call error is still tied
to the build/environment that produced the report (which the attached MCP server does not
represent); the output bug is a separate, confirmed defect. The follow-up reproduction
and mechanism are in `load-output-truncation.md`.

## Reported call

```json
{
  "module": "SHEPHERD",
  "path": "/home/juanrh/systems/harold-testing/shepherd.maude",
  "steps": [
    {
      "command": "search",
      "pattern": "< right | right | right | right >",
      "search_type": "any-steps",
      "subject": "initial"
    }
  ]
}
```

Observed client-side error:

```
Error calling tool 'maude_run': Unexpected failure running the Maude interpreter session
```

That string is the catch-all at `maude_run` (`src/harold_mcp/server/tools/interpreter.py`),
which wraps any non-`MaudeWorkerError` exception raised by `executor.run_session`. The
cause is chained server-side but is not sent to the MCP client, so the wire message
carries no exception type or context.

## Method

The attached MCP server does not read this worktree (see "Server anomaly" below), so the
reproduction was run against the same code path the tool uses:

```mermaid
flowchart LR
    T[SessionRequest<br>exact tool payload] --> E[MaudeExecutor.run_session]
    E --> W[spawned Maude worker<br>init_maude + session.run_session]
    W --> R[SessionResult / exception]
```

A temporary integration test built the `SessionRequest` exactly as `_to_request` /
`_to_step_request` do (flat step dict, `path_mode="labels"`, default caps: 200 solutions,
100 path steps, 1,000,000 chars), pointed at
`.agents/planning/Unexpected_failure_during_search/shepherd.maude`, and called
`MaudeExecutor.run_session(..., timeout=60)`.

## Results on current HEAD

All variants completed in ~1.4 s total; no exception. The calls succeed, but their
**captured output is incomplete** — the load and search-step captures lose the tail of
the last Maude command when it does not flush (see the confirmed defect below and
`load-output-truncation.md`).

| Variant | Result |
| --- | --- |
| Reported call: `SHEPHERD`, `< right \| right \| right \| right >`, `any-steps`, `path="labels"` | `ok`; 1 solution; 7-transition path: `carry-sheep, solo, carry-cabbage, carry-sheep, carry-dog, solo, carry-sheep`; not truncated |
| Same call with `path_mode=None` (payload shape of a pre-search-path build) | `ok`; 1 solution; no path; not truncated |
| `SHEPHERD-TRACE`, `< right \| right \| right \| right \| H >`, `any-steps`, `path="labels"` (the "trace search" the reporting agent suspected of hanging) | `ok`; 200 solutions (cap); `truncated=true`; first solution has the same 7-step path; no hang |

Load phase: `load_ok=true`, no warnings/diagnostics, and the file's embedded top-level
`search` commands execute as part of the load.

## Server anomaly (why the tool could not be used directly)

The MCP server attached to this session does not see the live worktree:

- `maude_run` and `maude_program_diagnostics` both reject
  `.agents/planning/Unexpected_failure_during_search/shepherd.maude` as
  "file not found or unreadable", although `read_file` and `find_path` see it.
- A brand-new file written under `tests/integration/fixtures/` is also rejected.
- Staging the shepherd content over an existing readable fixture
  (`tests/integration/fixtures/counter.maude`) produced
  `modules defined by the load: none`, i.e. the server did not see that content either.
  The fixture was restored afterwards; `git status` is clean.
- The server's `SearchStep` input schema has no `path` field, while the current tool
  defines it (and the description visible to this agent mentions search paths). This
  suggests the server runs an older/inconsistent build.

Consequence: to reproduce through the tool, the server must be restarted or repointed at
this checkout. Until then, the reported error can only be attributed to a build this
session cannot exercise.

## Load-output truncation (confirmed)

Captured load stdout contains the results of the file's first two embedded searches and
only the header line of the third (`search [1, 10] initial =>* < right | right | right |
right | H > .` in `SHEPHERD-TRACE`). The same trace search run as a session step returns
200 solutions structurally, but its textual block appears after the capture ends (on the
inherited stdout in our run).

This is not a failure of the session: it is the unflushed libmaude C/C++ stdio buffer in
`capture_streams`. `load-output-truncation.md` proves it (`fflush(NULL)` inside the
capture window recovers the complete block) and documents the leak to the worker's
inherited stdout. It is a real defect, separate from the whole-call error.

## Open questions for the next research decision

1. Which harold-mcp version/commit and Maude build produced the report, and how is that
   agent's server launched?
2. Does the failure still occur after restarting that server against the current code?
3. If it does, what is the chained cause? The tool currently loses it on the wire
   (noted in `.agents/summary/review_notes.md`, remaining issue 12).

Follow-up: `load-output-truncation.md` verifies the analysis from the original host and
identifies the unflushed-stdio bug behind the missing load output.
