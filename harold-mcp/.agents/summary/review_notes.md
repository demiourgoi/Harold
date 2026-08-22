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
8. **`harold_mcp.maude` is now documented and tested** — the module was reworked into `init_maude()` + `MaudeRuntime` + error hierarchy (lock-guarded init, RLock-serialized access, no wrapper caching), covered by unit tests (`tests/unit/test_maude.py`) and integration tests (`tests/integration/test_maude_runtime.py`); `docs/modules.md` renders it. ✅

## Remaining issues

1. **`greet` tool ignores its parameter** — `greet(name: str)` never uses `name`; it always reduces `2 * 3` in `NAT`. Expected for a hello-world skeleton, but worth remembering when the first real tool is designed.
2. **`server.py` itself is untested** — tests cover `harold_mcp.maude` thoroughly, but nothing exercises tool registration, the `mcp` instance config, or `run()`.
3. **Docs render only two modules** — `docs/modules.md` contains `harold_mcp.server` and `harold_mcp.maude`; `main.py`, `resources.py`, and `logging.py` are not rendered in the generated site.
4. **`harold_mcp.tools/` is empty** — the placeholder subpackage exists, but no tools are implemented yet. First planned tool: `maude_program_diagnostics` (see `.agents/planning/maude-diagnostics-tool-v1/`).
5. **`broken-*.maude` fixtures are unused by tests** — `broken-recoverable.maude` and `broken-non-recoverable.maude` are studied in the diagnostics-tool planning doc but are not referenced by any test; they may be picked up when the diagnostics tool is implemented.

## Completeness gaps

1. **No real MCP tools yet** — only the hello-world `greet`; the planned tools (diagnose, run, RAG over docs) are not implemented.
2. **Domain model is limited to the error hierarchy** — see `data_models.md`; more types are expected as tools are built.

## Language-support limitations

- Single language (Python) — no cross-language gaps.
- The `maude` bindings ship no type stubs, so mypy cannot check Maude-related code (`ignore_missing_imports` override). This is a tooling limitation, not a documentation gap.

## Recommendations

1. Add real tests as tools are implemented (including tests for `server.py` tool registration), and document new modules in `docs/modules.md`.
2. Keep `.agents/planning/` notes in sync with implementations — `harold_mcp.maude` was built from `sigsegv-under-load/issue.md`; the diagnostics tool should follow `maude-diagnostics-tool-v1/`.
3. Re-run the codebase-summary process after significant architecture changes so this knowledge base does not drift from the code.
