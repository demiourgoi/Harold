# Components

<!-- tags: components, modules, responsibilities -->

## `src/harold_mcp/` (the package)

### `harold_mcp.main`

- **Responsibility**: CLI/stdio entry point for the MCP server.
- `run() -> None` delegates to `server.run()`, which initializes Maude and runs the MCP server.
- Executable directly (`if __name__ == "__main__"`) and exposed as the `harold-mcp` console script.

### `harold_mcp.server`

- **Responsibility**: owns the MCP server and its tools. This is where new MCP tools should be registered (`@mcp.tool`), though their implementations are expected to live in `harold_mcp.tools` (see below).
- Defines `mcp = FastMCP(name="Harold", ...)` — the single shared server instance, configured with:
  - `instructions=` describing the three tool areas: diagnosing Maude programs, running Maude programs, and RAG over the Maude documentation.
  - `website_url="https://demiourgoi.github.io"` and `icons=[HAROLD_ICON]`.
- `run()` — logs startup, calls `init_maude()` (fail-fast at startup), then `mcp.run()`.
- Registers the hello-world tool `greet(name: str) -> str` with `@mcp.tool`. `greet` gets the `MaudeRuntime` singleton via `get_runtime()`, loads Maude's built-in `NAT` module, parses the term `2 * 3`, reduces it, and returns the result as a string. (Note: the `name` parameter is currently accepted but unused.)
- Cross-reference: `interfaces.md`.

### `harold_mcp.maude`

- **Responsibility**: safe access layer over the SWIG-generated `maude` Python bindings. The Maude interpreter is not thread-safe, so all access is serialized. See `.agents/planning/sigsegv-under-load/issue.md` for the design rationale (including why module wrappers are never cached).
- **Error hierarchy** (all subclass `MaudeError(RuntimeError)`):
  - `MaudeError` — base error for failures in the Maude runtime wrapper.
  - `MaudeInitError` — raised when the interpreter fails to initialize.
  - `MaudeLoadError` — raised when a program file fails to load; carries `program_path`.
  - `MaudeModuleNotFoundError` — raised when a requested module is not loaded; carries `module_name`.
- `init_maude() -> None` — initializes the interpreter exactly once per process. Double-checked locking on the module-level `_INIT_LOCK` and `_maude_initialized` flag; the flag is set only on success, so a failed init is retried on the next call. Calls `maude.init(advise=False)` to suppress advisories (e.g. `Advisory: redefining module X.`) on stderr.
- `MaudeRuntime` — thread-safe facade over the interpreter:
  - `_lock` — a `threading.RLock`; `_maude_locked()` context manager acquires it and ensures `init_maude()` ran.
  - `get_module(module_name) -> Any` — returns a fresh wrapper for a loaded module; raises `MaudeModuleNotFoundError` if absent.
  - `load_program(program_path) -> None` — loads (or reloads) a Maude program file, resolving the path to absolute; raises `MaudeLoadError` on failure. "Last load wins", so edits to a `.maude` file are picked up by the next call.
  - `load_module(program_path, module_name) -> Any` — (re)loads the program, then returns a fresh wrapper for the module.
- `get_runtime() -> MaudeRuntime` — returns the process-wide `_RUNTIME` singleton (no state cached; exists to share the interpreter lock across tool calls).
- Cross-reference: `data_models.md` (types), `interfaces.md` (API).

### `harold_mcp.resources`

- **Responsibility**: packaging of static brand assets.
- `HAROLD_RESOURCES` — the `importlib.resources` anchor for the package.
- `HAROLD_LOGO_PATH` — path to `assets/brand/Harold_logo.png`.
- `HAROLD_ICON` — an `mcp.types.Icon` built from the logo: `fastmcp.utilities.types.Image(path=...).to_data_uri()`, passed to the `FastMCP` constructor.

### `harold_mcp.logging`

- **Responsibility**: logging utilities for the package.
- Re-exports `get_logger` from `fastmcp.utilities.logging` and defines `Logging`, a base class exposing a `_log` property that returns a logger named after the concrete class.
- Cross-reference: `data_models.md`.

### `harold_mcp.tools`

- **Responsibility**: planned home of the MCP tool implementations. Currently an **empty placeholder**.
- The first planned tool is `maude_program_diagnostics` (diagnose a Maude source file by loading it), defined in `tools/diagnostics.py` and annotated with `@mcp.tool` on the `mcp` instance from `harold_mcp.server` — see `.agents/planning/maude-diagnostics-tool-v1/rough-idea.md`.

### `harold_mcp.assets.brand`

- Static asset directory containing `Harold_logo.png` (the server icon).

## Tests

- `tests/unit/test_maude.py` — mocked unit tests for `harold_mcp.maude` (9 tests): `init_maude` calls `maude.init(advise=False)` exactly once, retries after an exception or a `False` return; `MaudeRuntime.get_module` initializes and delegates to `maude.getModule`, raises `MaudeModuleNotFoundError` for missing modules; `load_program` passes the resolved absolute path, raises `MaudeLoadError` on failure; `load_module` chains load + get; `get_runtime()` returns a singleton. An autouse fixture resets `_maude_initialized` between tests.
- `tests/integration/test_maude_runtime.py` — real-interpreter tests (2):
  - `get_module("NAT")` → `parseTerm("2 * 3")` → `reduce()` → `"Result = 6"`.
  - `load_module` picks up a redefined module: `hello.maude` and `hello2.maude` both define `HELLO-WORLD` with `f = 1 * 2` and `f = 1 + 2` respectively (simulating an edit), and the fresh wrapper reduces `f` to `2` then `3`.
- `tests/integration/fixtures/` — `hello.maude`, `hello2.maude` (used by the integration tests) and `broken-recoverable.maude`, `broken-non-recoverable.maude` (recoverable/non-recoverable parse errors; not referenced by tests yet, studied in `.agents/planning/maude-diagnostics-tool-v1/rough-idea.md` for the diagnostics tool).

## Planning docs (`.agents/planning/`)

- `maude-diagnostics-tool-v1/` — PDD work for the first real MCP tool: `rough-idea.md` (goal, tool schema questions, experiments on detecting load failures), `idea-honing.md` (requirements Q&A), plus empty `design/`, `implementation/`, `research/` subdirectories.
- `sigsegv-under-load/issue.md` — analysis of SIGSEGV issues in the `maude` Python bindings and the proposed `MaudeRuntime` design that `harold_mcp.maude` implements (also `scala-issue.md`, `issue.md.html`).

## Docs

- `docs/` — MkDocs sources (see `workflows.md` and `dependencies.md` for the toolchain).
- `docs/modules.md` — mkdocstrings entry point; currently renders `harold_mcp.server` and `harold_mcp.maude`. New modules must be added here to appear in the rendered docs.

## Related documents

- `architecture.md` — module dependency graph
- `interfaces.md` — public surface of these components
