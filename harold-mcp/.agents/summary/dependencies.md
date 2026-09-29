# Dependencies

<!-- tags: dependencies, tooling -->

## Runtime

| Package | Constraint | Purpose |
| --- | --- | --- |
| `cyclopts` | `>=4.23.0` | CLI framework for both console scripts: `harold-mcp` (`main.py`) and `harold-update-prelude-sorts` (`heuristic/prelude_extract.py`) |
| `fastmcp` | `>=3.4.7` | Framework for building the MCP server (server instance, `@mcp.tool`, `@lifespan`, `Depends`, logging utilities) |
| `maude` | `==1.6.0` (pinned) | Python bindings for the Maude system — imported only inside the worker process |
| `mcp` | `>=1.29.0` | Official MCP SDK — typed primitives (`mcp.types.ToolAnnotations`, `Icon`) and transport support |
| `pydantic` | `>=2.13.4` | Data models and validation (`Field`) |
| `pydantic-settings` | `>=2.15.0` | `Settings` from `HAROLD_*` env vars |

The diagnostics seam and the heuristic linter added **no** runtime dependencies: they are
stdlib-only (`dataclasses`, `typing`, `re`, `unicodedata`, `hashlib`, `importlib`,
`datetime`, `collections`), which keeps the server process independent of the worker
stack.

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

- The `maude` bindings are **pinned exactly** (`==1.6.0`): the wheel bundles the Maude
  interpreter (built against Maude 3.5.1), so upgrading is a deliberate act. The bundled
  prelude sort snapshot (`harold_mcp.heuristic.prelude_sorts`) is generated from Maude
  3.5.1's `prelude.maude`; after an interpreter upgrade, regenerate it with
  `harold-update-prelude-sorts` and keep `--check` clean.
- The `maude` bindings provide no type stubs → mypy override `ignore_missing_imports`
  (see `data_models.md`); basedpyright runs with all diagnostics off except
  `reportUnusedCallResult`.
- Python is capped to the 3.14 series (`requires-python = ">=3.14,<3.15"`, normalized to
  `==3.14.*` in `uv.lock`): `maude==1.6.0` ships cp314-only wheels (no abi3), so a 3.15+
  interpreter would have no `maude` wheel and would fall back to a source build. Relax the cap
  when the bindings publish newer wheels. Lint/format target is `py314`.
- `ProcessPoolExecutor` uses an explicit `spawn` context (threaded parent; `forkserver`
  needs an AF_UNIX socket); Python 3.14 features in use: `ProcessPoolExecutor.kill_workers()`,
  `BrokenProcessPool` from `concurrent.futures.process`, PEP 758 `except A, B:` syntax.

## Related documents

- `codebase_info.md` — summary of the stack
- `workflows.md` — how the toolchain is invoked day to day
