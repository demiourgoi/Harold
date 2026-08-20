# Review Notes

<!-- tags: review, consistency, completeness, gaps -->

Findings from the consistency and completeness review. Issues marked **Resolved** have been fixed since the initial generation.

## Resolved issues

1. **`pyproject.toml` description** — now reads "An MCP server for AI-assisted Maude programming." ✅
2. **CI location clarified** — GitHub Actions workflows (`main.yml`, `on-release-main.yml`) live at the Git repository root (`.github/workflows/`, the parent directory of this package). Consistent with the `[gh-actions]` mapping in `tox.ini`. Not missing. ✅
3. **`pre-commit` removed** — the dev dependency was dropped, so no `.pre-commit-config.yaml` is needed. ✅
4. **`CONTRIBUTING.md` pre-commit step** — the `uv run pre-commit install` step was removed and the setup list renumbered. ✅
5. **`Makefile` `release` target** — now a single definition with prerequisites and a success-message recipe. ✅
6. **`logging.py` cleanup** — the inert `# pylint: disable=too-few-public-methods` comment was removed and the `Logging` docstring now describes the class accurately (a base class exposing `_log`, not a `Protocol`). ✅
7. **`keywords` in `pyproject.toml`** — extended to `['maude', 'mcp', 'python']`. ✅

## Remaining issues

1. **`greet` tool ignores its parameter** — `greet(name: str)` never uses `name`; it always reduces `2 * 3` in `NAT`. Expected for a hello-world skeleton, but worth remembering when the first real tool is designed.
2. **No real tests** — `tests/test_foo.py` is a placeholder (`assert True`). The coverage configuration (`branch = true`, source = `src`) is ready, but nothing meaningful is covered yet.
3. **Docs render only one module** — `docs/modules.md` contains only `::: harold_mcp.server`; `main.py`, `resources.py`, and `logging.py` are not rendered in the generated site.

## Completeness gaps

1. **No domain models yet** — expected at this stage; see `data_models.md`.
2. **No real test suite** — see remaining issue 2.

## Language-support limitations

- Single language (Python) — no cross-language gaps.
- The `maude` bindings ship no type stubs, so mypy cannot check Maude-related code (`ignore_missing_imports` override). This is a tooling limitation, not a documentation gap.

## Recommendations

1. Add real tests as tools are implemented, and document new modules in `docs/modules.md`.
2. Re-run the codebase-summary process after significant architecture changes so this knowledge base does not drift from the code.
