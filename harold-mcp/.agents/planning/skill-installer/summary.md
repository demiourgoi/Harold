# Summary — skill installer

## What was built

- **Packaging**: `make skills` copies the monorepo's `skills/maude-manual` into
  the git-ignored `src/harold_mcp/skills/maude-manual`, which hatchling
  re-includes via `artifacts` in both the wheel and the sdist. `make build`
  depends on it, and the release workflow's build step now runs
  `make skills && uv build`, so the published artifact always contains the
  skill. Key discovery: hatchling's sdist respects `.gitignore` (and
  `uv build` builds the wheel from the sdist), so the ignored copy must be
  re-included explicitly.
- **CLI**: `harold-mcp setup` (`src/harold_mcp/skill_install.py` +
  `main.py`) installs the packaged skill at `./.agents/skills/maude-manual`
  (default), `~/.agents/skills/maude-manual` (`-g`/`--global`), or any
  `--directory`, removing an existing copy first so re-running it after
  `uvx --refresh` is a full refresh that never touches siblings.
- **README**: installation revolves around `setup`; update is "refresh and run
  `setup` again"; the Zed and opencode v2 MCP config JSON is replaced by links
  to their MCP docs; the whole README was condensed (≈17.2 KB → ≈8.6 KB)
  keeping every fact (tools, all env vars and defaults, notes).
- `CHANGELOG.md` `[0.0.6]` documents the feature.

## Verification

- `make skills && uv build`: wheel and sdist both contain the 27 skill files.
- `make check`, `make test-unit` (397 passed), `make docs-test`, and the
  integration `test_lifespan.py` pass.
- Live smoke: `uv run harold-mcp setup --directory …` installs and
  re-installs correctly.

## Reviews (ponytail-review SOP)

- Design review (round 1): 3 findings (stray-file destination, packaged-skill
  test, release-path note) — all incorporated.
- Code review (round 2): 1 finding (changelog entry) — fixed.
- Round 3: "Looks good. Ship."

## Follow-ups (not in scope)

- `.agents/summary/` knowledge base refresh (interfaces, workflows, packaging
  sections now mention `setup` and the skill copy) at the next docs cycle.
