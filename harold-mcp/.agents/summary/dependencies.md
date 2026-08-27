# Dependencies

<!-- tags: dependencies, tooling -->

## Runtime

| Package | Constraint | Purpose |
| --- | --- | --- |
| `fastmcp` | `>=3.4.7` | Framework for building the MCP server (server instance, `@mcp.tool`, `@lifespan`, `Depends`, logging utilities) |
| `maude` | `>=1.6.0` | Python bindings for the Maude system — imported only inside the worker process |
| `mcp` | `>=1.29.0` | Official MCP SDK — typed primitives (`mcp.types.ToolAnnotations`, `Icon`) and transport support |
| `pydantic` | `>=2.13.4` | Data models and validation (`Field`) |
| `pydantic-settings` | `>=2.15.0` | `Settings` from `HAROLD_*` env vars |

## Dev group

| Package | Purpose |
| --- | --- |
| `pytest` / `pytest-cov` | Tests and coverage |
| `ruff` | Lint and format (configuration in `pyproject.toml`) |
| `mypy` | Primary strict type checker (configuration in `pyproject.toml`) |
| `basedpyright` | Minimal companion check: `reportUnusedCallResult` only (`typeCheckingMode = "off"`), matching Zed's LSP |
| `deptry` | Detect unused/missing/misplaced dependencies (`make check` runs `deptry src`) |
| `tox-uv` | Multi-Python test matrix (see `tox.ini`) |
| `mkdocs` / `mkdocs-material` / `mkdocstrings[python]` | Documentation build (see `mkdocs.yml`) |

## Build

- **Backend**: hatchling; wheel packages `src/harold_mcp`.

## Lockfile

- `uv.lock` is committed; `make check` verifies it is in sync with `pyproject.toml`
  (`uv lock --locked`). After changing dependencies, regenerate it (`uv lock`) and commit
  the result.

## Notable constraints

- The `maude` bindings provide no type stubs → mypy override `ignore_missing_imports`
  (see `data_models.md`); basedpyright runs with all diagnostics off except
  `reportUnusedCallResult`.
- Minimum Python is 3.14; lint/format target is `py314` (`pyproject.toml`).
- `ProcessPoolExecutor` uses an explicit `spawn` context (threaded parent; `forkserver`
  needs an AF_UNIX socket); Python 3.14 features in use: `ProcessPoolExecutor.kill_workers()`,
  `BrokenProcessPool` from `concurrent.futures.process`, PEP 758 `except A, B:` syntax.

## Related documents

- `codebase_info.md` — summary of the stack
- `workflows.md` — how the toolchain is invoked day to day
