# Components

<!-- tags: components, modules, responsibilities -->

## `src/harold_mcp/` (the package)

### `harold_mcp.main`

- **Responsibility**: CLI/stdio entry point for the MCP server.
- `run() -> None` delegates to `harold_mcp.server.run`. The `if __name__ == "__main__"`
  guard is required: the `spawn`-context worker re-imports the main module.
- Exposed as the `harold-mcp` console script.

### `harold_mcp.settings`

- **Responsibility**: application configuration, read once from `HAROLD_*` env vars.
- `Settings(BaseSettings)` — flat model: `maude_workers: int` (default 1, `gt=0`),
  `maude_worker_timeout_secs: int` (default 60, `gt=0`). Invalid values fail at import.
- `settings` — module-level singleton; `get_settings() -> Settings` returns it (FastMCP
  dependency factory). Env vars are documented in `README.md`.

### `harold_mcp.server` (package)

- **`__init__.py`** — re-exports `mcp` and `run` from `server.server`, and imports
  `harold_mcp.server.tools` (tool registration as a package side effect).
- **`server.py`** — the FastMCP instance and its lifecycle:
  - `mcp = FastMCP(name="Harold", instructions=..., website_url=..., icons=[HAROLD_ICON], lifespan=app_lifespan)`.
  - `app_lifespan` — `@lifespan`-decorated async generator: `get_maude_executor(
    get_settings()).start()` (warm-up, fail-fast), teardown in `finally`.
  - `run()` — registers a SIGTERM handler that raises `KeyboardInterrupt`, calls
    `mcp.run()`, and on `KeyboardInterrupt` logs and calls `os._exit(0)` (see
    `architecture.md` §5 for why).
  - `_handle_shutdown_signal` — the SIGTERM→`KeyboardInterrupt` bridge.
- **`tools/__init__.py`** — re-exports `maude_program_diagnostics`.
- **`tools/diagnostics.py`** — the pydantic result models (see `data_models.md`) and the
  `maude_program_diagnostics` tool (see `interfaces.md`): file pre-check → executor
  `diagnostics` → tri-state mapping (warnings → LSP ranges; `ok=False` → synthesized
  whole-file `error`; `success = ok and no warnings`; per-severity counts).

### `harold_mcp.maude` (package)

- **`__init__.py`** — re-exports the public API: error hierarchy, `MaudeExecutor`,
  `get_maude_executor`. Importing the package never imports the SWIG `maude` bindings.
- **`executor.py`** — the client-side access layer:
  - Error hierarchy: `MaudeError(RuntimeError)` base; `MaudeInitError` (worker init
    failure, surfaced at warm-up); `MaudeWorkerError(reason)` with
    `MaudeWorkerCrashedError` / `MaudeWorkerTimeoutError` subclasses (messages defined in
    the classes); `MaudeFileNotFoundError(path)` (input path missing/unreadable).
  - `MaudeExecutor(Logging)` — wraps a `ProcessPoolExecutor` (spawn,
    `initializer=worker.init_maude`): `start()` (warm-up pings, `MaudeInitError` on
    failure), `shutdown()` (idempotent), `submit()` (raises `MaudeWorkerCrashedError` on a
    broken pool, replaces it), `diagnostics(path)` (thin wrapper over `_run_task`), and
    the generic `_run_task(fn, *args) -> T` runner (submit + await + crash/timeout
    mapping). `_reset_executor(replace=True, failed=None)` is a pure command (CQS) that
    swaps the pool under `_executor_lock` (an RLock) and kills the old pool with
    `kill_workers()` outside the lock; the `failed` identity check makes concurrent
    failure reports replace exactly once.
  - `get_maude_executor(settings: Settings = Depends(get_settings)) -> MaudeExecutor` —
    process-wide singleton, created lazily under a lock (nested FastMCP dependency).
- **`worker.py`** — the interpreter side, pickled/spawn-imported by the worker process;
  imports `maude` **lazily inside functions** so the server process never touches the
  bindings (the absolute `import maude` is the third-party package, not this one):
  - `init_maude()` — idempotent, `maude.init(advise=False)`, raises `WorkerInitError`.
  - `ping()` — warm-up no-op. `sleep(seconds) -> int` — test/timeout support.
  - `load_diagnostics(path) -> LoadDiagnosticsResult` — fd-2 capture around `maude.load`
    (binary tempfile, lossy UTF-8 decode, ANSI CSI stripping, `Warning:` regex parsing).
  - `_crash()` — test-only `os._exit(1)` (SIGSEGV analogue).

### `harold_mcp.resources`

- **Responsibility**: packaging of static brand assets. `HAROLD_ICON` — an `mcp.types.Icon`
  built from `assets/brand/Harold_logo.png`, passed to the `FastMCP` constructor.

### `harold_mcp.logging`

- **Responsibility**: logging utilities. Re-exports `get_logger` from
  `fastmcp.utilities.logging` and defines `Logging`, a base class exposing a `_log`
  property (logger named after the concrete class). `MaudeExecutor` uses the mixin.

## Tests

- `tests/unit/` (hermetic, mocked):
  - `test_settings.py` — defaults, env overrides, case-insensitivity, invalid values.
  - `test_maude_worker.py` — `_parse_warnings`: observed formats, ANSI stripping,
    unmatched/advisory lines ignored.
  - `test_maude_executor.py` — fake executors/futures: warm-up (success/fail), broken
    submit, crash/timeout mapping + kill, exception propagation, exactly-once concurrent
    replacement, singleton.
  - `test_diagnostics.py` — fake executor: tri-state mapping, summary counts, `range=None`,
    path echo, missing/unreadable file errors.
- `tests/integration/` (real interpreter; distinct basenames to avoid pytest module-name
  collisions):
  - `test_maude_worker_integration.py` — `load_diagnostics` on the four fixtures +
    advisory suppression on redefinition.
  - `test_maude_executor_integration.py` — warm-up, fixtures, real `_crash` containment +
    retry, two-worker parallelism via slow `sleep` tasks.
  - `test_lifespan.py` — lifespan start/teardown, fail-fast, real-pool drive.
  - `test_diagnostics_integration.py` — the acceptance suite: tool-level fixtures, binary
    file regression, crash recovery, and the MCP smoke test (real stdio server).
- `tests/integration/fixtures/` — `hello.maude`, `hello2.maude`, `broken-recoverable.maude`
  (1 warning, loads), `broken-non-recoverable.maude` (12 warnings, loads — Maude recovers
  from everything parseable), `no_new_module.maude`.

## Planning docs (`.agents/planning/`)

- `maude-diagnostics-tool-v1/` — complete PDD cycle for the first tool:
  `rough-idea.md`, `idea-honing.md` (Q&A + amendments + verified final-testing reminders),
  `research/` (six notes; `logging.md` superseded), `design/detailed-design.md`,
  `implementation/plan.md` (7 steps, checklist ticked), `summary.md`.
- `sigsegv-under-load/issue.md` — analysis of SIGSEGV issues in the `maude` Python
  bindings, which motivated the worker-process architecture.

## Docs

- `docs/` — MkDocs sources; `docs/modules.md` renders `harold_mcp.server.server`,
  `harold_mcp.server.tools.diagnostics`, `harold_mcp.maude.executor`,
  `harold_mcp.maude.worker`, `harold_mcp.settings` via mkdocstrings.

## Related documents

- `architecture.md` — module dependency graph and architectural decisions
- `interfaces.md` — public surface of these components
