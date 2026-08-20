# Codebase Information

<!-- tags: overview, facts, stack -->

## Identity

- **Project**: `harold-mcp` v0.0.1
- **Author**: Juan Rodriguez (`juanrh@pm.me`)
- **Repository**: <https://github.com/demiourgoi/harold>
- **Documentation site**: <https://demiourgoi.github.io> (MkDocs, built from `docs/`)
- **License**: see `LICENSE`

## Language and runtime

- **Language**: Python
- **Supported versions**: 3.14 (`requires-python = ">=3.14"`)
- **Language floor for new code**: Python 3.14 (ruff `target-version = "py314"`)

## Package layout

- **Layout**: `src` layout; the importable package is `src/harold_mcp`
- **Build backend**: hatchling (`[build-system]` in `pyproject.toml`)
- **Package name on PyPI**: `harold-mcp` (planned distribution via `uvx`)

## Dependency management

- **Manager**: `uv` — `uv.lock` is committed to the repository for reproducible installs
- All commands are expected to run through `uv run ...` / `uv sync` (see the `Makefile` and `README.md`)

## Runtime dependencies

- `fastmcp>=3.4.7` — the framework used to build the MCP server
- `maude>=1.6.0` — Python bindings for the Maude system
- `mcp>=1.29.0` — the official MCP Python SDK (types, transports)

## Dev dependencies (dev group)

- `pytest`, `pytest-cov` — testing and coverage
- `ruff` — linter and formatter
- `mypy` — static type checking
- `deptry` — dependency hygiene (unused/missing/misplaced dependencies)
- `tox-uv` — test matrix across Python versions
- `mkdocs`, `mkdocs-material`, `mkdocstrings[python]` — documentation

## Entry point

- Console script `harold-mcp` → `harold_mcp.main:run` (defined in `pyproject.toml` `[project.scripts]`)
- Runs an MCP server over stdio.

## Related documents

- `architecture.md` — how the modules are organized
- `components.md` — per-module responsibilities
- `interfaces.md` — external and internal interfaces
- `dependencies.md` — dependency details and constraints
