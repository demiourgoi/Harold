# Dependencies

<!-- tags: dependencies, tooling -->

## Runtime

| Package | Constraint | Purpose |
| --- | --- | --- |
| `fastmcp` | `>=3.4.7` | Framework for building the MCP server (server instance, `@mcp.tool`, logging utilities) |
| `maude` | `>=1.6.0` | Python bindings for the Maude system (runtime init, module lookup, term parsing/reduction) |
| `mcp` | `>=1.29.0` | Official MCP SDK — typed primitives (`mcp.types.Icon`) and transport support |

## Dev group

| Package | Purpose |
| --- | --- |
| `pytest` / `pytest-cov` | Tests and coverage |
| `ruff` | Lint and format (configuration in `pyproject.toml`) |
| `mypy` | Strict static typing (configuration in `pyproject.toml`) |
| `deptry` | Detect unused/missing/misplaced dependencies (`make check` runs `deptry src`) |
| `tox-uv` | Multi-Python test matrix (see `tox.ini`) |
| `mkdocs` / `mkdocs-material` / `mkdocstrings[python]` | Documentation build (see `mkdocs.yml`) |

## Build

- **Backend**: hatchling; wheel packages `src/harold_mcp`.

## Lockfile

- `uv.lock` is committed; `make check` verifies it is in sync with `pyproject.toml` (`uv lock --locked`). After changing dependencies, regenerate it (`uv lock`) and commit the result.

## Notable constraints

- The `maude` bindings provide no type stubs → mypy override `ignore_missing_imports` (see `data_models.md`).
- Minimum Python is 3.10; lint/format target is `py310` (`pyproject.toml`).

## Related documents

- `codebase_info.md` — summary of the stack
- `workflows.md` — how the toolchain is invoked day to day
