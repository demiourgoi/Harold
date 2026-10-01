# Idea honing — `no_new_module_quirk` PDD

Status: the user declared the requirements **clear** and directed the process to skip
interactive clarification and proceed to research ("let's do a quick PDD project ... The
requirements are clear, so go ahead with the research"). This file therefore consolidates
the requirements as stated by the user, verbatim from their message (see
[`rough-idea.md`](./rough-idea.md)); no interactive Q&A was conducted.

## Consolidated requirements

### R1. Isolation via `max_tasks_per_child=1` (option A)

- Set `max_tasks_per_child=1` on the `ProcessPoolExecutor` in
  `src/harold_mcp/maude/executor.py`, so every worker task gets a fresh interpreter
  process and parse residue (the deferred `q .` warning, leaked file context) cannot
  reach another call.
- Accept the performance cost (~0.34 s per call, spawn + prelude init) as a deliberate
  trade-off: diagnostics is not expected to run many concurrent files, and
  `HAROLD_MAUDE_WORKERS` remains the user's knob.
- Document the semantics change correctly in the tool description: the interpreter is
  **fresh per call** — the "loading the file updates the interpreter's loaded modules
  (last load wins), like the Maude CLI" sentence must go/change.

### R2. `HAROLD_MAUDE_WORKERS` default change

- Default should become `os.cpu_count() / 2` (user's proposal; open question in their
  message: "what do you think? maybe 2 or 3 is a better option?").
- Research must answer: given `max_tasks_per_child=1` (transient workers, per-call
  spawn+init), what is the sensible default? Measure memory and parallel-call behavior
  to decide; any minimum/cap must keep `gt=0`.

### R3. Fix the integration tests (they "are designed to allow a bug")

- Remove the `heuristic_executor` workaround fixture
  (`tests/integration/test_diagnostics_integration.py` L40–53) and its comment; all
  diagnostics tests share one executor.
- `no_new_module.maude` stays a **correct** program: it must diagnose clean
  (`success=true`, no diagnostics). No new diagnostic may be emitted just because the
  file contains `q .` (option D — a REPL-only-command lint rule — is rejected: it would
  discourage a perfectly fine language construct).

### R4. New failing tests for isolation bugs (red-green-refactor)

- Write tests that fail on the current code and pass after R1, covering at least:
  - a `q .` file followed by a clean file on the same worker: the clean file must stay clean;
  - the relative-path variant (leaked file context) if reachable through the tool;
  - other state-leak examples ("we do not have true isolation this way: try to construct
    other failing examples due to that" — e.g. `quit .`, text after `q .`).
- Red-green-refactor style: write the tests first, observe them fail (red), apply R1,
  observe them pass (green).

### R5. Reproduce the opencode race claim

- opencode claimed: "parallel calls race on the shared Maude interpreter — load
  diagnostics are only reliable when checks are serialized" (spurious interpreter error
  when diagnosing the 17 fixtures in parallel).
- Reproduce this in a test (pytest-repeat or a repeated/concurrent harness if needed).
- Verify that R1 fixes it: with a fresh interpreter per call there is no shared state to
  race on.

### R6. Maude file dependencies (`load`/`in` inside a file)

- Answer "what happens when a Maude file depends on another maude file, have we tested
  that?" — currently untested.
- Write a test that reproduces the dependency scenario and decide the expected behavior
  (red-green-refactor). Known open design space from the user: accepting several files
  as input to diagnostics vs. an explicit list of dependency files vs. one file at a
  time (IDE-style, like IntelliJ/Java). Research must first establish *current* behavior
  (path resolution of `load`/`in` inside a file; does the loaded module exist for the
  diagnosed file's parse?).

### R7. Bug report proposal for maude-bindings

- Write a bug report proposal with a **minimal Python reproduction** to send as a GitHub
  issue to the maude-bindings repository (`maude.load` leaves the parser half-parsed
  after a top-level `q .`; the pending command contaminates the next `maude.load`).
- The proposal must be standalone (copy-paste-able into an issue) and reference the
  pinned `maude==1.6.0` / Maude 3.5.1.

## Non-goals (explicitly rejected options)

- **B** (dummy-load flush in the worker): unnecessary if we do A.
- **C** (filename-aware warning filtering): too complex and brittle for this bug.
- **D** (linter rule for REPL-only commands): discourages a perfectly fine language
  construct; `q .` must stay clean.
- **E** (status quo + test workaround): the whole point of R3 is to remove it.
- Fixing the bug inside maude-bindings: desirable upstream (R7), but does not provide
  the diagnostics isolation that A gives.

## Success criteria

1. Two consecutive `maude_program_diagnostics` calls on one server — first
   `no_new_module.maude`, then `hello.maude` — both report `success=true`, no
   interpreter diagnostics (deterministic; fails today).
2. The integration suite has no `heuristic_executor` workaround and is green.
3. Concurrent diagnostics calls (≥ 2 workers) are deterministic: each result is
   attributable to its own file only.
4. A fixture with a `load` dependency on a sibling file has a defined, tested behavior.
5. `.agents/planning/no_new_module_quirk/` contains a ready-to-send GitHub issue
   proposal for maude-bindings with a minimal reproduction.
