# Components

<!-- tags: components, modules, responsibilities -->

## `src/harold_mcp/` (the package)

### `harold_mcp.main`

- **Responsibility**: CLI/stdio entry point for the MCP server.
- `run() -> None` delegates to `server.run()`, which initializes Maude and runs the MCP server.
- Executable directly (`if __name__ == "__main__"`) and exposed as the `harold-mcp` console script.

### `harold_mcp.server`

- **Responsibility**: owns the MCP server and its tools. This is where new MCP tools should be added.
- `run()` — initializes Maude (cached `init()` from `harold_mcp.maude`) then calls `mcp.run()`; fails fast at startup if Maude cannot initialize.
- Defines `mcp = FastMCP(name="Harold", icons=[HAROLD_ICON])` — the single shared server instance.
- Registers the hello-world tool `greet(name: str) -> str` with `@mcp.tool`. `greet` loads Maude's built-in `NAT` module, parses the term `2 * 3`, reduces it, and returns the result as a string. (Note: the `name` parameter is currently accepted but unused.)
- Cross-reference: `interfaces.md`.

### `harold_mcp.resources`

- **Responsibility**: packaging of static brand assets.
- `HAROLD_RESOURCES` — the `importlib.resources` anchor for the package.
- `HAROLD_LOGO_PATH` — path to `assets/brand/Harold_logo.png`.
- `HAROLD_ICON` — an `mcp.types.Icon` built from the logo as a data URI, passed to the `FastMCP` constructor.

### `harold_mcp.logging`

- **Responsibility**: logging utilities for the package.
- Re-exports `get_logger` from `fastmcp.utilities.logging` and defines `Logging`, a base class exposing a `_log` property that returns a logger named after the concrete class.
- Cross-reference: `data_models.md`.

### `harold_mcp.assets.brand`

- Static asset directory containing `Harold_logo.png` (the server icon).

## Tests

- `tests/unit/test_maude.py` — mocked unit tests for `harold_mcp.maude`: `init_maude` runs `maude.init()` only once, retries after failure, and `MaudeRuntime.get_module` initializes and delegates to `maude.getModule`.
- `tests/integration/test_maude_runtime.py` — real-interpreter test: `get_module("NAT")` → `parseTerm("2 * 3")` → `reduce()` → `"Result = 6"`.

## Docs

- `docs/` — MkDocs sources (see `workflows.md` and `dependencies.md` for the toolchain).
- `docs/modules.md` — mkdocstrings entry point; currently renders only `harold_mcp.server`. New modules must be added here to appear in the rendered docs.

## Related documents

- `architecture.md` — module dependency graph
- `interfaces.md` — public surface of these components
