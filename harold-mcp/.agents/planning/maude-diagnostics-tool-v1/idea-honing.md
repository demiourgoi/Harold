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
