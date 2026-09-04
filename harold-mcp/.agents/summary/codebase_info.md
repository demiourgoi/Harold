# Codebase Information

<!-- tags: overview, facts, stack -->

## Identity

- **Project**: `harold-mcp` v0.0.3.dev0 (WIP; `CHANGELOG.md` has an open `[0.0.3]` section)
- **Author**: Juan Rodriguez (`juanrh@pm.me`)
- **Repository**: <https://github.com/demiourgoi/harold>
- **Documentation site**: <https://demiourgoi.github.io/Harold/> (MkDocs, built from `docs/`)
- **License**: see `LICENSE`

## Language and runtime

- **Language**: Python
- **Supported versions**: 3.14 (`requires-python = ">=3.14"`)
- **Language floor for new code**: Python 3.14 (ruff `target-version = "py314"`)

## Package layout

- **Layout**: `src` layout; the importable package is `src/harold_mcp`
- **Build backend**: hatchling (`[build-system]` in `pyproject.toml`)
- **Package name on PyPI**: `harold-mcp` (planned distribution via `uvx`)
- **Subpackages**: `harold_mcp.server` (FastMCP instance + tools) and `harold_mcp.maude` (worker executor + worker-side code), plus the `harold_mcp.settings` module.

## Dependency management

- **Manager**: `uv` — `uv.lock` is committed to the repository for reproducible installs
- All commands are expected to run through `uv run ...` / `uv sync` (see the `Makefile` and `README.md`)

## Runtime dependencies

- `cyclopts>=4.23.0` — CLI framework for the `harold-mcp` console command
- `fastmcp>=3.4.7` — the framework used to build the MCP server
- `maude==1.6.0` — Python bindings for the Maude system, pinned exactly (built against Maude 3.5.1; loaded only in the worker process)
- `mcp>=1.29.0` — the official MCP Python SDK (types such as `ToolAnnotations`)
- `pydantic>=2.13.4` — data models and validation
- `pydantic-settings>=2.15.0` — configuration from `HAROLD_*` env vars

## Dev dependencies (dev group)

- `pytest`, `pytest-cov` — testing and coverage
- `ruff` — linter and formatter
- `mypy` — primary static type checker
- `basedpyright` — minimal companion check (unused call results only)
- `deptry` — dependency hygiene (unused/missing/misplaced dependencies)
- `tox-uv` — test matrix across Python versions
- `mkdocs`, `mkdocs-material`, `mkdocstrings[python]` — documentation

## Entry point

- Console script `harold-mcp` → `harold_mcp.main:app` (defined in `pyproject.toml` `[project.scripts]`)
- `main.py` builds a **cyclopts** CLI: the default command and the `serve` subcommand both run the MCP server over stdio (`--help`/`--version` come from cyclopts).
- The Maude interpreter lives in a dedicated worker process.

## Related documents

- `architecture.md` — how the modules are organized
- `components.md` — per-module responsibilities
- `interfaces.md` — external and internal interfaces
- `dependencies.md` — dependency details and constraints
