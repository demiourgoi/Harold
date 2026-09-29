# Codebase Information

<!-- tags: overview, facts, stack -->

## Identity

- **Project**: `harold-mcp` v0.0.5.dev0 (WIP; `CHANGELOG.md` has an open `[0.0.5]` section documenting the heuristic-linter port)
- **Author**: Juan Rodriguez (`juanrh@pm.me`)
- **Repository**: <https://github.com/demiourgoi/harold>
- **Documentation site**: <https://demiourgoi.github.io/Harold/> (MkDocs, built from `docs/`)
- **License**: GNU General Public License v2 (see `LICENSE`)

## Language and runtime

- **Language**: Python
- **Supported versions**: 3.14 (`requires-python = ">=3.14"`)
- **Language floor for new code**: Python 3.14 (ruff `target-version = "py314"`)

## Package layout

- **Layout**: `src` layout; the importable package is `src/harold_mcp`
- **Build backend**: hatchling (`[build-system]` in `pyproject.toml`)
- **Package name on PyPI**: `harold-mcp`
- **Subpackages**:
  - `harold_mcp.server` — FastMCP instance, shared tag vocabulary, and the MCP tools;
  - `harold_mcp.diagnostics` — the provider-agnostic diagnostics seam: provider protocol, value types, error vocabulary, aggregation (stdlib-only, no interpreter);
  - `harold_mcp.heuristic` — the heuristic linter: lexical layer, rules, generated prelude-sort snapshot and its maintenance CLI (server process, never imports `maude`);
  - `harold_mcp.maude` — worker executor client, the interpreter diagnostics provider, and the worker-side code.
- Plus the flat modules `harold_mcp.main`, `harold_mcp.settings`, `harold_mcp.logging`, `harold_mcp.resources`.

## Dependency management

- **Manager**: `uv` — `uv.lock` is committed to the repository for reproducible installs
- All commands are expected to run through `uv run ...` / `uv sync` (see the `Makefile` and `README.md`)

## Runtime dependencies

- `cyclopts>=4.23.0` — CLI framework for both console scripts (`harold-mcp`, `harold-update-prelude-sorts`)
- `fastmcp>=3.4.7` — the framework used to build the MCP server
- `maude==1.6.0` — Python bindings for the Maude system, pinned exactly (built against Maude 3.5.1; loaded only in the worker process)
- `mcp>=1.29.0` — the official MCP Python SDK (types such as `ToolAnnotations` and `Icon`)
- `pydantic>=2.13.4` — data models and validation
- `pydantic-settings>=2.15.0` — configuration from `HAROLD_*` env vars

The heuristic linter and the diagnostics seam added **no** runtime dependencies: they are stdlib-only, which keeps the server process independent of the worker stack.

## Dev dependencies (dev group)

- `pytest`, `pytest-cov` — testing and coverage
- `ruff` — linter and formatter
- `mypy` — primary static type checker
- `basedpyright` — minimal companion check (unused call results only)
- `deptry` — dependency hygiene (unused/missing/misplaced dependencies)
- `tox-uv` — test matrix across Python versions
- `mkdocs`, `mkdocs-material`, `mkdocstrings[python]` — documentation

## Entry points

- Console script `harold-mcp` → `harold_mcp.main:app` (defined in `pyproject.toml` `[project.scripts]`). `main.py` builds a **cyclopts** CLI: the default command and the `serve` subcommand both run the MCP server over stdio (`--help`/`--version` come from cyclopts).
- Console script `harold-update-prelude-sorts` → `harold_mcp.heuristic.prelude_extract:app` — regenerates (or verifies with `--check`) the bundled Maude prelude sort snapshot.
- The Maude interpreter lives in a dedicated worker process; the heuristic linter runs in the server process.

## Related documents

- `architecture.md` — how the modules are organized
- `components.md` — per-module responsibilities
- `interfaces.md` — external and internal interfaces
- `dependencies.md` — dependency details and constraints
