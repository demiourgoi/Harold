# Idea Honing

Requirements clarification Q&A for the Maude diagnostics tool v1.

## Q1. Architecture: in-process fd-2 capture vs. dedicated Maude worker process

**Question**: Should the Maude interpreter run in the MCP server process (with os-level stderr
capture + file logging), or in a dedicated long-lived worker subprocess that owns the
interpreter and is reached via `multiprocessing` queues?

Context:

- `os.dup2`-based warning capture redirects fd 2 process-wide; concurrent tool calls and
  FastMCP's stderr logging can interleave into the capture window (see
  `research/logging.md`, `research/worker-process-architecture.md`).
- The worker option isolates capture to a single process, contains Maude SIGSEGVs (see
  `.agents/planning/sigsegv-under-load/issue.md`), and keeps the MCP server's default stderr
  logging. Cost: `MaudeRuntime` becomes a proxy returning serializable results (SWIG
  wrappers can't cross processes), which changes `greet` and the current API.
- Recommendation: worker process for v1 (full isolation, crash containment; avoids
  throwaway fd-capture/logging work). Alternative: in-process for v1, defer worker to v2.

**Answer**: Confirmed — the dedicated Maude **worker process** is the v1 architecture
(decided 2026-08-22). See `research/worker-process-architecture.md`. The in-process fd-2
capture + file-logging plan (`research/logging.md`) is superseded.

> **Transport refinement (2026-08-24)**: the hand-rolled `multiprocessing` queue pair is
> replaced by a `concurrent.futures.ProcessPoolExecutor` (`max_workers=1`, explicit
> `spawn` context, `initializer=init_maude`), with a thin recovery wrapper for
> `BrokenProcessPool`/timeout. `max_workers` configurable via env var (default 1).
> Rationale and verification: `research/process-pool-executor.md`. The worker-process
> architecture itself is unchanged.

## Q2. Remove the placeholder `greet` tool

**Question**: The `greet` tool was a placeholder to validate the FastMCP setup. Now that a
real tool (`maude_program_diagnostics`) is coming, do we remove `greet`?

**Answer**: Confirmed — remove `greet` in v1 (decided 2026-08-22). `maude_program_diagnostics`
becomes the first real tool; the v1 worker protocol then only needs a `load_diagnostics` op
(no term-reduction op to migrate `greet`).

## Q3. Confirm the requirements decisions made during research feedback

**Question**: The research notes record several requirements-level decisions that were made
in conversation during the research phase (2026-08-22 / 2026-08-24) but never written down
here. Before I record them as official requirements, please confirm they are accurate, and
flag anything to change:

1. **`success` semantics** (`research/tool-schema.md`): `success=True` only when there are
   NO warnings and NO errors. A recoverable warning (Maude still loads the file) makes
   `success=False`, because the tool's purpose is to point out anything the agent should fix.
2. **LSP-style range** (`research/tool-schema.md`): diagnostics carry a `range` with
   `start`/`end` positions (1-based line, `column=None`) instead of a bare line number —
   familiar to LLMs trained on LSP diagnostics, future-proofed for richer sources.
3. **No module list in the result** (`research/tool-schema.md`): detection relies solely on
   the `maude.load` return value + captured warnings; module-set heuristics are rejected.
4. **Dependency injection** (`research/existing-code.md`): the tool receives the runtime via
   `Depends(get_runtime)`, keeping the MCP schema at `{path: str}`.
5. **Worker crash/timeout → tool error** (`research/process-pool-executor.md`): failures
   raise, so FastMCP reports them as `isError` tool results (the "HTTP 500" analogue),
   rather than encoding failure in the result model.
6. **`readOnlyHint=True`** (`research/tool-schema.md`, currently only a "consider"): the
   tool declares a read-only safety profile even though it loads the program into the
   server-side interpreter. Needs explicit confirmation.

**Answer**: All six items confirmed as-is (2026-08-24). Additionally, the worker-pool
configuration is settled via **`pydantic-settings`** (new direct dependency; already
present in the venv as a transitive dependency of fastmcp — see `research/logging.md`):

- `HAROLD_MAUDE_WORKERS` — number of Maude worker processes; default `1`.
- `HAROLD_MAUDE_WORKER_TIMEOUT_SECS` — timeout in seconds waiting for each future result;
  default `60`.

Note: the file-logging rework stays **out of v1** (superseded by the worker process);
pydantic-settings enters v1 for this worker configuration instead.

## Q4. Result convenience: per-severity summary counts

**Question**: Should the result model include a convenience summary of the diagnostics
(e.g. counts per severity) alongside the `diagnostics` list, or is the list enough?

Context:

- The current sketch is `MaudeProgramDiagnosticsResult {path, success, diagnostics[]}`.
- `success` already gives the LLM a one-bit verdict, and severities are a fixed set
  (`warning` | `error`), so counts are derivable from the list — but computing them costs
  the LLM tokens/effort on every call.
- Options: (a) list only; (b) add a small `summary` field (e.g. `{"warning": n, "error": n}`);
  (c) also include a short human-readable summary line.

**Answer**: Option (b) — add a small `summary` field with per-severity counts, e.g.
`{"warning": n, "error": n}` (2026-08-24). Exact field name/shape to be fixed in the design
phase.

## Q5. Advisory channel

**Question**: Maude's `Advisory:` messages (e.g. `Advisory: redefining module X.`) are
currently suppressed by `maude.init(advise=False)` in `init_maude()`. Should the diagnostics
tool keep them suppressed, or surface them as diagnostics too?

Context:

- Advisories are informational, not errors (e.g. module redefinitions). Research
  (`research/maude-bindings.md` §1) shows `advise` gates advisories only — warnings always
  print.
- Surfacing them would require a third severity (e.g. `info`/`advisory`) in the model, a
  bigger schema change (`severity` is currently `Literal["warning", "error"]`).
- The v1 purpose is to point out things the agent should fix; advisories mostly aren't
  fix-worthy.

**Answer**: Keep advisories suppressed (2026-08-24). Advisories notify things like a module
being redefined — definitively not errors. No `info`/`advisory` severity in v1;
`maude.init(advise=False)` stays as-is.

## Q6. Missing/unreadable file: tool error or error diagnostic?

**Question**: If the file at `path` does not exist or cannot be read, how should the tool
respond?

Context:

- `maude.load(path)` returns `False` both for a missing/unreadable file and for an
  unrecoverable parse failure — the return value alone cannot distinguish them
  (`research/maude-bindings.md` §2).
- A missing file is arguably not a "diagnosis of a Maude program" — the agent likely
  passed a wrong path; an unrecoverable parse failure IS a diagnosis of the file's contents.
- Options:
  - (a) pre-check existence/readability in the tool; missing/unreadable → raise → tool error
    (`isError`); unrecoverable parse failure → error-severity diagnostic in the result
    (`success=False`).
  - (b) treat both alike: synthesize one error diagnostic ("failed to load"), `success=False`,
    no raise.
- (Reference: `result.path` echoes the input path as given.)

**Answer**: Option (a) (2026-08-24). The tool pre-checks that the path exists and is a
readable regular file (e.g. `Path.is_file()`); missing/unreadable → raise → tool error
(`isError`). Unrecoverable parse failures from `maude.load` → synthesized error-severity
diagnostic, `success=False`. `result.path` echoes the input path as given.

## Q7. Position model: nullable line for the synthesized error

**Question**: The synthesized error diagnostic for an unrecoverable load failure has no line
number (Maude's hard-failure return carries none). How should the position model represent
that?

Context:

- Sketch: `MaudePosition {line: int, column: int | None}` and
  `MaudeRange {start: MaudePosition, end: MaudePosition | None}`.
- Warnings always carry a line (parsed from `Warning: ..., line N:`), but the synthesized
  error has none.
- Options:
  - (a) make `line` nullable (`int | None`) — null only for the synthesized error;
  - (b) keep `line: int` required and drop the synthesized diagnostic — the failure would be
    visible only via `success=False` (and a summary count), which reads inconsistently;
  - (c) something else.

**Answer**: Yes — `MaudeDiagnostic.range: MaudeRange | None` (2026-08-24). `None` means the
problem affects the whole file (e.g. completely unparseable/binary input). This keeps
`MaudePosition.line: int` a strict invariant — every positioned diagnostic has a real
1-based line — and pushes the "no location" case up to the range level, cleaner than a
nullable line. In practice only the synthesized load-failure error uses `range=None`;
parsed warnings always carry a line. Missing files raise per Q6, so they never reach the
model.

## Q8. Success criteria for v1

**Question**: What counts as "done" for v1? Proposed acceptance criteria (confirm or
amend):

1. `maude_program_diagnostics` is callable over MCP with schema `{path: str}` and returns
   the structured result model.
2. The four fixture outcomes are correct end-to-end: clean → `success=True`, no diagnostics;
   recoverable → `success=False` + warning(s); non-recoverable → `success=False` + warnings
   + synthesized error; no-new-module → `success=True`.
3. Missing/unreadable file → tool error (`isError`).
4. Worker crash (simulated) → the current call errors, the next call succeeds on a
   recreated worker.
5. Settings honored: `HAROLD_MAUDE_WORKERS`, `HAROLD_MAUDE_WORKER_TIMEOUT_SECS`.
6. CI green (`make release`), docs updated (`docs/modules.md`), unit + integration tests.

**Answer**: Confirmed — that is the definition of done for v1 (2026-08-24).

## Design review amendments (2026-08-24)

Recorded during the design review; they refine earlier answers without reopening the Q&A.

1. **Worker rationale completed**: besides SIGSEGV containment, the worker process exists so
   the `maude` package's fd-2 (stderr) warning output can be redirected to a temp file for
   capture, while the parent FastMCP process keeps its own stderr for logging — as
   recommended for stdio MCP servers. See `design/detailed-design.md` §1.
2. **Code organization (supersedes the path in `rough-idea.md`)**: packages replace flat
   modules — `src/harold_mcp/server/` (FastMCP instance, lifespan, tools) and
   `src/harold_mcp/maude/` (executor client + worker code). The tool lives at
   `src/harold_mcp/server/tools/diagnostics.py`; tool registration happens in
   `server/__init__.py` (a side effect of importing the package). Public APIs are
   re-exported from the package `__init__`s.
3. **Naming**: `MaudePool` → `MaudeExecutor`; `get_runtime()` → `get_maude_executor()`.
   Eager executor replacement after a crash confirmed.
4. **New task**: document `HAROLD_MAUDE_WORKERS` and `HAROLD_MAUDE_WORKER_TIMEOUT_SECS`
   (purpose + defaults) in a README subsection under "How to run harold-mcp".

### Design review amendments, round 2 (2026-08-24)

1. **`Settings` moved to `src/harold_mcp/settings.py`** (application-wide config, flat
   class, `maude_`-prefixed fields) with a `get_settings()` singleton. `get_maude_executor`
   now takes a `Settings` argument, initializes the singleton lazily under a lock (like
   `init_maude`), and is wired through FastMCP nested dependencies
   (`get_maude_executor(settings: Settings = Depends(get_settings))`).
2. **Lock semantics**: the executor lock is renamed `_executor_lock` and is an **RLock**
   (`_submit` holds it while calling `_reset_executor`). It only guards the executor
   reference against replacement-vs-submit races; task execution is NOT serialized — with
   `max_workers > 1`, futures run in parallel in the pool.
3. **Error hierarchy**: `MaudeWorkerCrashedError` and `MaudeWorkerTimeoutError` subclass
   `MaudeWorkerError`, each calling `super().__init__` with its own message.
4. **Pool teardown**: replaced `shutdown`/hand-rolled termination with
   `ProcessPoolExecutor.kill_workers()` (new in Python 3.14; SIGKILL + internal
   `shutdown()`). `_terminate_workers` helper deleted as redundant.
5. **Executor swap**: `_new_executor`/`_replace_locked`/`_replace_after_failure` collapsed
   into `_reset_executor(replace=True, failed=None)` (identity-checked exactly-once swap,
   kill outside the lock, `Logging` mixin for pool lifecycle logs).
6. **No resubmit**: a submit-time `BrokenProcessPool` replaces the pool and raises
   `MaudeWorkerCrashedError` — no reason to assume a retry would succeed; the idempotent
   tool call is retried by the MCP client. Result-time failures are still mapped (and the
   stuck worker killed on timeout) in `diagnostics`, because submit-time recovery cannot
   see a crash that happens mid-task or a hung worker.

## Reminders for final testing (from the research phase)

Two quick verification items deferred from research, to be folded into the final test plan
(added 2026-08-24):

1. **Warning-format catalog**: feed additional adversarial fixtures through the worker
   capture (module redefinitions → advisories, multi-line messages, `<standard input>`
   attribution) to harden the warning parser. Formats observed so far are in
   `research/maude-bindings.md` §4.
2. **FastMCP lifespan + `mcp.run()` interaction**: verify that lifespan startup/shutdown
   actually fires on the stdio transport before relying on it for pool warm-up/teardown.
