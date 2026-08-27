# Implementation Plan — `maude_program_diagnostics` (v1)

> Tracks the implementation of [`../design/detailed-design.md`](../design/detailed-design.md).
> All context documents (requirements in `../idea-honing.md`, research in `../research/`,
> design in `../design/`) are assumed available while working through this plan.

## Guiding principle

Convert the design into a series of implementation steps that will build each component in a
test-driven manner following agile best practices. Each step must result in a working,
demoable increment of functionality. Prioritize best practices, incremental progress, and
early testing, ensuring no big jumps in complexity at any stage. Make sure that each step
builds on the previous steps, and ends with wiring things together. There should be no
hanging or orphaned code that isn't integrated into a previous step.

Practical conventions: write the tests for a step's behavior **first** (red), then implement
(green). End every step with `make test` and `make check` green (use
`UV_CACHE_DIR=/tmp/uv-cache make ...` in sandboxes per AGENTS.md). All new code is mypy-strict
(annotate everything); `maude` values are `Any`. Run `uv run ruff check` + `uv run ruff format`
before committing (auto-fix fails CI).

## Checklist

- [x] Step 1: Reorganize into packages, add `Settings` + errors, remove `greet`
- [x] Step 2: Worker functions: capture + warning parsing (`maude/worker.py`)
- [x] Step 3: `MaudeExecutor` wrapper with recovery (`maude/executor.py`)
- [x] Step 4: Result models + the `maude_program_diagnostics` tool, registered on `mcp`
- [ ] Step 5: Lifespan warm-up/shutdown and fail-fast startup
- [ ] Step 6: End-to-end integration: fixtures, crash resilience, settings, MCP smoke test
- [ ] Step 7: README, docs, knowledge base, and the two final-testing reminders

> **Pending**: run `uv add pydantic` (pydantic is now a direct dependency — `pyproject.toml`
> is already edited) so `uv.lock` is in sync and `make check` passes end-to-end.

> **Step 2 findings (2026-08-24)**: (1) Maude colorizes stderr with ANSI CSI escapes when it
> detects a TTY at init time — the parser strips them (documented in
> `research/maude-bindings.md`); (2) `broken-non-recoverable.maude` yields **12** warnings
> through the Python bindings, not 14 (the `syntax error` lines are REPL-only); research
> notes corrected. Integration test file renamed to `test_maude_worker_integration.py`
> (pytest basename collision with the unit test).
>
> **Step 3 notes (2026-08-24)**: settings live in `harold_mcp/settings.py` (`get_settings()`);
> `get_maude_executor(settings: Settings = Depends(get_settings))` is a lazily-initialized,
> lock-guarded singleton (FastMCP nested dependency); `MaudeWorkerCrashedError` /
> `MaudeWorkerTimeoutError` subclasses; `_reset_executor` is a pure command (CQS) and the
> old pool is torn down with `ProcessPoolExecutor.kill_workers()` (3.14); the
> submit+await+recover loop is the generic `_run_task`; parallelism tests use slow
> `worker.sleep` tasks (the executor only spawns a worker when none is idle).

---

## Step 1: Reorganize into packages, add `Settings` + errors, remove `greet`

**Objective**: Establish the package layout from design §4.0 and the configuration surface,
keeping the application bootable. The placeholder `greet` tool and the old in-process
runtime go away here (they are the only users of `harold_mcp/maude.py`), so the server
briefly exposes zero tools — that is expected and still demoable.

Implementation guidance:

- Create `src/harold_mcp/maude/` with:
  - `__init__.py` re-exporting the public API per design §4.1.
  - `executor.py` containing the error hierarchy (`MaudeError`, `MaudeInitError`,
    `MaudeWorkerError`, `MaudeFileNotFoundError`) and `Settings(BaseSettings)` with
    `model_config = SettingsConfigDict(env_prefix="HAROLD_")`,
    `maude_workers: int = Field(default=1, gt=0)`, `maude_worker_timeout_secs: int =
    Field(default=60, gt=0)`, plus the module-level `settings = Settings()` singleton.
- Create `src/harold_mcp/server/` with:
  - `server.py` — the current `src/harold_mcp/server.py` **minus** `greet`, its imports
    (`get_runtime`, `init_maude`), and the `init_maude()` call in `run()`.
  - `__init__.py` — `from harold_mcp.server.server import mcp, run`, `__all__ = ["mcp", "run"]`.
- Delete `src/harold_mcp/server.py` and `src/harold_mcp/maude.py`.
- Add the dependency: `uv add pydantic-settings` (declare it in `pyproject.toml`; `uv lock`
  and commit `uv.lock`). In a sandbox use `UV_CACHE_DIR=/tmp/uv-cache`; if `uv` needs the
  registry to resolve, request network access for the command.
- `src/harold_mcp/main.py` is unchanged (`from harold_mcp.server import run` now hits the
  package).

Tests (write first):

- `tests/unit/test_settings.py`: defaults are 1 and 60; env overrides
  (`HAROLD_MAUDE_WORKERS`, `HAROLD_MAUDE_WORKER_TIMEOUT_SECS`, case-insensitivity);
  `HAROLD_MAUDE_WORKERS=0` / non-integer values raise `ValidationError`. Note: `Settings`
  reads env at instantiation — use `monkeypatch.setenv` and construct fresh instances.
- Delete `tests/unit/test_maude.py` and `tests/integration/test_maude_runtime.py` (their
  subject — the old `MaudeRuntime` API — is removed).

Integration with previous work: none (first step). Sets up everything later steps import.

**Demo**: `UV_CACHE_DIR=/tmp/uv-cache uv run harold-mcp` starts and answers `tools/list`
with an empty list; `HAROLD_MAUDE_WORKERS=3 uv run python -c "from harold_mcp.maude import
settings; print(settings.maude_workers)"` prints `3`.

---

## Step 2: Worker functions — stderr capture + warning parsing (`maude/worker.py`)

**Objective**: Implement the interpreter-side module (design §4.2): the lazy-`maude`
`init_maude()`, the `ping()` no-op, `load_diagnostics(path) -> LoadDiagnosticsResult` with
the fd-2 capture, and the `_crash()` test hook, plus the warning parser. Nothing in the app
calls these yet; they are exercised directly by tests.

Implementation guidance:

- `src/harold_mcp/maude/worker.py` exactly per design §4.2: `TypedDict`s (`WarningDict`,
  `LoadDiagnosticsResult`), `init_maude()` (idempotent via a module flag, `maude.init(
  advise=False)`, raises `RuntimeError("Failed to initialize the Maude interpreter")`),
  `ping()`, `load_diagnostics(path)`, `_crash()` (`os._exit(1)`).
- **`import maude` only inside functions** (keeps importing this module in the server
  process free of the SWIG bindings — design §4.2 gotcha: this is the third-party package,
  keep it an absolute import).
- Capture: `saved = os.dup(2)` → `os.dup2(tmp.fileno(), 2)` (a regular `TemporaryFile`, not
  a pipe) → `ok = maude.load(path)` → restore fd 2 and close `saved` in a `finally` → read
  the tempfile → parse. **No logging between the `dup2` and the restore.**
- Parser: `_WARNING_RE` from design §4.2; matched lines →
  `{"line": int, "message": str}`; unmatched lines ignored for now (hardened in Step 7).

Tests (write first):

- `tests/unit/test_maude_worker.py` (pure, no `maude` import needed): `_parse_warnings`
  against synthetic stderr text — the three formats from design §4.2 (`"file"`, `(context)`,
  `<standard input>`), multiple warnings, unmatched lines ignored, empty text → `[]`.
- `tests/integration/test_maude_worker_integration.py` (real interpreter; distinct
  basename to avoid pytest's module-name collision with the unit test): drive
  `load_diagnostics` through a bare `ProcessPoolExecutor(max_workers=1, mp_context=spawn,
  initializer=init_maude)` — this also validates the spawn/pickling story early. Assert:
  `hello.maude` → `ok=True`, no warnings; `broken-recoverable.maude` → `ok=True`, one
  warning with `line=2` and message `missing is keyword.`; `broken-non-recoverable.maude` →
  `ok=True` (empirical result — see `research/maude-bindings.md`) with exactly 12
  warnings (the two `syntax error` lines in the REPL transcript are interactive-parser-only
  and do not appear through the Python bindings); `no_new_module.maude` → `ok=True`, no
  warnings. Use paths relative to the test file.

Integration with previous work: lives in the `maude/` package from Step 1; uses the repo
fixtures that already exist.

**Demo**: one-liner submitting `load_diagnostics` on
`tests/integration/fixtures/broken-recoverable.maude` via a spawn pool and printing the
parsed warning dict.

---

## Step 3: `MaudeExecutor` — wrapper with crash/timeout recovery (`maude/executor.py`)

**Objective**: Implement the client-side wrapper (design §4.1): executor creation (spawn,
`initializer=worker.init_maude`), warm-up pings, `submit` with one-shot recovery, and
`diagnostics` with timeout/crash mapping; plus `get_maude_executor()` and the package
re-exports.

Implementation guidance:

- Extend `src/harold_mcp/maude/executor.py` with `ExecutorFactory` and `MaudeExecutor`
  exactly per design §4.1: `__init__(settings=None, *, executor_factory=None)` (the factory
  is the unit-test seam), `start()`, `shutdown()`, `submit(fn, *args)`, `diagnostics(path)`,
  `_new_executor()`, `_replace_after_failure()` (eager + lock-guarded), `_warm_up()`.
- `submit` recovers from `BrokenProcessPool` raised by `executor.submit` (pool already
  broken) by replacing the executor and resubmitting once; lazy-start when the executor is
  `None`.
- `diagnostics`: `submit(worker.load_diagnostics, path)` +
  `future.result(timeout=settings.maude_worker_timeout_secs)`; map `BrokenProcessPool` →
  replace + `MaudeWorkerError("Maude worker crashed")`; `concurrent.futures.TimeoutError` →
  replace (kill) + `MaudeWorkerError("Maude worker timed out")`; other exceptions propagate.
- `start()` warm-up: one `worker.ping` per `maude_workers`, awaited with the timeout;
  `BrokenProcessPool`/`TimeoutError` → `MaudeInitError`.
- `shutdown()`: idempotent, `executor.shutdown(wait=False, cancel_futures=True)`.
- Update `maude/__init__.py` to also export `MaudeExecutor`, `get_maude_executor`.

Tests (write first):

- `tests/unit/test_maude_executor.py` (inject `executor_factory` returning a fake executor
  and fake futures): warm-up success and failure mapping; `submit` recovery (broken submit →
  new executor → resubmit once); `diagnostics` delegation on success; result
  `BrokenProcessPool` → `MaudeWorkerError` + executor replaced; `TimeoutError` →
  `MaudeWorkerError` + executor replaced; `shutdown` idempotence; two threads replacing
  concurrently produce exactly one new executor (lock).
- `tests/integration/test_maude_executor_integration.py` (real interpreter): `start()` +
  `diagnostics` on the four fixtures; crash resilience — `submit(worker._crash)` raises
  `BrokenProcessPool` on `result()`, then the next `diagnostics(...)` succeeds on the
  recreated worker; a fresh executor with `Settings(maude_workers=2)` runs tasks on two
  distinct pids.

Integration with previous work: first consumer of `worker.py` (Step 2); timeout mapping
uses the Step 1 `Settings` singleton by default.

**Demo**: script that starts the executor, diagnoses `broken-recoverable.maude`, crashes the
worker via `_crash` (observe `MaudeWorkerError`), then diagnoses again successfully.

---

## Step 4: Result models + the tool, registered on `mcp`

**Objective**: Add the pydantic output models and `maude_program_diagnostics` (design §4.3,
§5), wired into the server package so it is reachable over MCP. End-to-end functionality is
available from here: the tool calls the real `MaudeExecutor`, which starts its worker
lazily (the lifespan warm-up arrives in Step 5).

Implementation guidance:

- `src/harold_mcp/server/tools/__init__.py` — re-export `maude_program_diagnostics`.
- `src/harold_mcp/server/tools/diagnostics.py`:
  - models per design §5: `MaudePosition`, `MaudeRange`, `MaudeDiagnostic`,
    `MaudeDiagnosticsSummary`, `MaudeProgramDiagnosticsResult` (`severity:
    Literal["warning", "error"]`, `range: MaudeRange | None`, …).
  - imports: `from fastmcp.dependencies import Depends`, `from mcp.types import
    ToolAnnotations`, `from harold_mcp.server.server import mcp` (**concrete module**),
    `from harold_mcp.maude import MaudeExecutor, MaudeFileNotFoundError,
    get_maude_executor`.
  - the tool exactly per design §4.3: decorator with
    `annotations=ToolAnnotations(readOnlyHint=True)`, parameters
    `(path: str, maude_executor: MaudeExecutor = Depends(get_maude_executor))`, the
    docstring from the design (it becomes the MCP description), the file pre-check
    (`Path(path).is_file()` + `os.access(path, os.R_OK)` → `MaudeFileNotFoundError`), and
    the tri-state mapping incl. the synthesized `error` with `range=None` and the
    `success = ok and not warnings` rule.
- Update `src/harold_mcp/server/__init__.py` to `from harold_mcp.server import tools  # noqa: F401` after the `server.server` import (per design §4.3 — registration as a package
  side effect; `main.py` needs no change).

Tests (write first):

- `tests/unit/test_diagnostics.py` (fake `MaudeExecutor` passed explicitly — `Depends` does
  not block direct calls): clean / warnings-only / hard-failure dicts map to the right
  models; `success` semantics; `summary` counts; `path` echo; synthesized error has
  `range=None` and `severity="error"`; warning ranges carry the parsed line;
  missing file (`tmp_path` non-existent) and unreadable file (`chmod 0o000`, skipped when
  running as root) → `MaudeFileNotFoundError`.

Integration with previous work: consumes `MaudeExecutor` (Step 3) and the `server` package
(Step 1).

**Demo**: `uv run python -c` that calls
`maude_program_diagnostics("tests/integration/fixtures/broken-recoverable.maude",
maude_executor=get_maude_executor())` and prints the pydantic result (the executor starts
lazily on this first call).

---

## Step 5: Lifespan warm-up/shutdown and fail-fast startup

**Objective**: Wire pool lifecycle into the server (design §4.4): warm-up pings at startup
(fail fast on `MaudeInitError`) and executor shutdown at exit, via the FastMCP lifespan.

Implementation guidance:

- In `src/harold_mcp/server/server.py`: add the `lifespan` `asynccontextmanager` per design
  §4.4 (`get_maude_executor().start()` / `try: yield / finally: shutdown()`), pass it to
  `FastMCP(..., lifespan=lifespan)`, and simplify `run()` to just `mcp.run()`.
- Keep heavy work out of import time: the pool is created inside `lifespan`, not at import.

Tests (write first):

- `tests/integration/test_lifespan.py`: wrap `asyncio.run` around the `lifespan`
  context manager and assert it calls `start`/`shutdown` on the singleton executor (or use
  a spy executor injected via `monkeypatch`). A `start()` failure must propagate out of the
  lifespan (fail-fast path).
- **Final-testing reminder #2** (from `../idea-honing.md`): verify manually that the
  lifespan actually fires on the stdio transport — `make run`, confirm the worker warm-up
  output appears on stderr at startup and that the pool shuts down cleanly on exit. Record
  the result in `../idea-honing.md`.

Integration with previous work: completes the Step 4 tool with proper lifecycle; replaces
the old eager `init_maude()` startup pattern (removed in Step 1).

**Demo**: `make run` starts with the warm-up ping visible on stderr (fail-fast if Maude is
broken); a tool call over a real MCP client succeeds; exiting the server shuts the worker
down.

---

## Step 6: End-to-end integration — fixtures, crash resilience, settings, MCP smoke test

**Objective**: Lock in the acceptance criteria (R18 / Q8) end-to-end: the full tool over the
real worker on all four fixtures, crash resilience through the tool, settings honored, and
one real MCP-level call.

Implementation guidance:

- Extend/add `tests/integration/test_diagnostics_integration.py` to call
  `maude_program_diagnostics(path, maude_executor=get_maude_executor())` (with a started
  executor fixture) and assert the **result models** per design §5 for all four fixtures
  (including the 14-warning + synthesized-error case for `broken-non-recoverable.maude` and
  `success=True` for `no_new_module.maude`).
- Crash resilience at the tool level: submit `worker._crash` through the executor, then
  assert the next tool call succeeds (the current call that hit the crash is already
  covered by Step 3's executor-level test).
- Settings honored end-to-end: run diagnostics through an executor built with
  `Settings(maude_workers=2)` and assert both workers are used (or that calls succeed under
  parallelism).
- MCP smoke test (R18.1): use the fastmcp `Client` against a subprocess-started
  `harold-mcp` server (or a raw stdio JSON-RPC `initialize` + `tools/list` +
  `tools/call`) to assert the tool is listed with schema `{path: str}` and returns the
  structured result. Keep it small; if subprocess-based MCP testing proves flaky in CI,
  document that and rely on the direct-call tests plus the Step 5 manual verification.

Integration with previous work: assembles Steps 2–5 into the full acceptance suite.

**Demo**: `make release` green; a scripted MCP client session that lists tools and calls
`maude_program_diagnostics` on a broken fixture, showing the structured result.

---

## Step 7: README, docs, knowledge base, and final-testing hardening

**Objective**: Finish the non-code obligations (R19, design §4.5) and execute the two
final-testing reminders.

Implementation guidance:

- `README.md`: add the env-var subsection under "How to run harold-mcp" with the table from
  design §4.5 (`HAROLD_MAUDE_WORKERS` → default `1`; `HAROLD_MAUDE_WORKER_TIMEOUT_SECS` →
  default `60`; what each does).
- `docs/modules.md`: replace the old entries with
  `::: harold_mcp.server.server`, `::: harold_mcp.server.tools.diagnostics`,
  `::: harold_mcp.maude.executor`, `::: harold_mcp.maude.worker`; keep `make docs-test`
  green (strict).
- **Final-testing reminder #1** (warning-format catalog): add adversarial fixtures under
  `tests/integration/fixtures/` (module redefinition → advisory suppressed; any construct
  that yields `<standard input>` attribution or unusual messages) and extend
  `test_maude_worker.py`/integration tests so the parser's behavior on them is pinned. If a
  gap is found, harden the parser and document the new format in
  `../research/maude-bindings.md`.
- Knowledge base: re-run the **codebase-summary** skill so `.agents/summary/` and
  `AGENTS.md` describe the new package layout (server/tools, maude/executor+worker), the
  new tool, and the env vars. Update this plan's checklist as steps complete.

Tests (write first / alongside): the new fixture-driven parser tests; everything else from
previous steps stays green (`make release`).

Integration with previous work: final wiring; no orphan code remains (every module is
imported, documented, and tested).

**Demo**: `make release` fully green (install, check, test, docs-test); the README shows the
configuration table; the knowledge base at `.agents/summary/` is up to date.
