# Review Notes

<!-- tags: review, consistency, completeness, gaps -->

Findings from the consistency and completeness review of the generated documentation.

## Consistency issues found

1. **`pyproject.toml` description is a template leftover** — it reads "This is a template repository for Python projects that use uv for their dependency management." It does not describe harold-mcp. Recommend updating it to describe the MCP server for Maude.
2. **CI referenced but absent** — `README.md` shows a GitHub Actions status badge (`main.yml`) and `tox.ini` has a `[gh-actions]` section, but no `.github/workflows/` directory exists in the working tree. Either the workflow is missing from this checkout or it was never added.
3. **`pre-commit` configured but not configured** — `pre-commit` is a dev dependency and `CONTRIBUTING.md` instructs `uv run pre-commit install`, but there is no `.pre-commit-config.yaml` in the tree, so the install would have nothing to run.
4. **`logging.py` references pylint** — it carries a `# pylint: disable=too-few-public-methods` comment, but pylint is not a dependency; the project lints with ruff. The comment is inert.
5. **`Logging` docstring inconsistency** — the docstring says classes "extend this Protocol", but `Logging` is a plain class with a `_log` property, not a `Protocol`.
6. **`Makefile` `release` target defined twice** — the target appears twice (once with prerequisites `install check test docs-test`, once with an echo recipe). GNU make merges the prerequisites and lets the later recipe win, so `make release` currently runs the checks as prerequisites and then just echoes a success message. It works by accident; recommend merging into a single definition.
7. **`greet` tool ignores its parameter** — `greet(name: str)` never uses `name`; it always reduces `2 * 3` in `NAT`. Expected for a hello-world skeleton, but worth remembering when the first real tool is designed.

## Completeness gaps

1. **No real tests** — `tests/test_foo.py` is a placeholder (`assert True`). The coverage configuration (`branch = true`, source = `src`) is ready but nothing meaningful is covered yet.
2. **No domain models** — expected at this stage; see `data_models.md`.
3. **Docs render only one module** — `docs/modules.md` contains only `::: harold_mcp.server`; `main.py`, `resources.py`, and `logging.py` are undocumented in the generated site.
4. **No CI workflow files** in the working tree (see consistency issue 2).
5. **No `.pre-commit-config.yaml`** (see consistency issue 3).

## Language-support limitations

- Single language (Python) — no cross-language gaps.
- The `maude` bindings ship no type stubs, so mypy cannot check Maude-related code (`ignore_missing_imports` override). This is a tooling limitation, not a documentation gap.

## Recommendations

1. Update `pyproject.toml` `description` and `keywords` to reflect the project's actual purpose.
2. Add `.github/workflows/main.yml` (or drop the badge and `[gh-actions]` mapping).
3. Add a `.pre-commit-config.yaml` mirroring the `make check` steps (ruff, mypy) or remove the `pre-commit` dependency and the `CONTRIBUTING.md` instruction.
4. Remove the inert pylint comment from `logging.py` and fix the `Logging` docstring.
5. Merge the duplicate `release` target in the `Makefile`.
6. Add real tests as tools are implemented; document new modules in `docs/modules.md`.
