# Implementation plan — skill installer

## Checklist

- [x] Step 1: Package the skill (Makefile `skills` target, `.gitignore`, release
      workflow build step, hatchling `artifacts`)
- [x] Step 2: The `setup` command (`skill_install.py`, `main.py`, unit tests)
- [x] Step 3: README rewrite (installation, setup/update, client-doc links,
      terser whole-README)

## Working agreements

- The design at `../design/detailed-design.md` is the source of truth. If the
  code contradicts it, update the design (and this plan) first.
- Test-driven: write/update the tests together with each step's code; run the
  targeted tests first, then `make check` and `make test-unit`.
- In sandboxed environments prefix commands with `UV_CACHE_DIR=/tmp/uv-cache`.
- One commit per step, plus one commit per PDD phase document.
- After each step: tick the checklist and append an "Implementation notes"
  subsection to that step.

---

## Step 1: Package the skill

**Objective.** Make `make build` (local) and the release workflow's `uv build`
produce an artifact containing `harold_mcp/skills/maude-manual`.

**Guidance.**

- `Makefile`: add the `skills` target from the design (remove
  `src/harold_mcp/skills`, copy `../skills/maude-manual` to
  `src/harold_mcp/skills/maude-manual`); make it a prerequisite of `build`.
- `.gitignore`: ignore `src/harold_mcp/skills/`.
- `.github/workflows/on-release-main.yml`: change the `publish` job's
  "Build package" step to `make skills && uv build`.
- Verify: `make skills`, then `uv build` (sandboxed cache) and inspect the
  wheel (`unzip -l`) for `harold_mcp/skills/maude-manual/SKILL.md`; then
  remove the copy so it is never committed.

**Tests.** None (build plumbing); verified by wheel inspection.

### Implementation notes

Implemented as planned, with one necessary addition: hatchling's sdist (and
`uv build`, which builds the wheel **from the sdist**) respects `.gitignore`,
so the git-ignored copy was silently excluded from the artifacts. Adding
`artifacts = ["src/harold_mcp/skills"]` to both hatchling targets re-includes
it; the design was updated with this finding. Verified: `make skills &&
uv build` produces a wheel and an sdist that both contain the 27 skill files
(`harold_mcp/skills/maude-manual/SKILL.md` present).

---

## Step 2: The `setup` command

**Objective.** `harold-mcp setup` installs the packaged skill at
`<base>/maude-manual`, overwriting a previous copy.

**Guidance.**

- Add `src/harold_mcp/skill_install.py` with `SKILL_NAME`, `skill_source()` and
  `install_skill(destination_base, source=None)` per the design.
- Add the `setup` command to `src/harold_mcp/main.py` (cyclopts `App`
  command; `--dir` option defaulting to `.agents/skills`, `-g/--global` for
  `~/.agents/skills`); print the installed path and the package version.
- Add `tests/unit/test_skill_install.py` per the design: copy semantics
  (fresh, update-over-stale, siblings untouched, missing source) and CLI
  wiring (default, `--dir`, `-g` with monkeypatched home and source).

**Tests.** `uv run python -m pytest tests/unit/test_skill_install.py`, then
`make check` and `make test-unit`.

### Implementation notes

Implemented as planned (including the stray-file handling from design review
round 1). Deviations: cyclopts 4 takes the flag names as a single list
(`Parameter(["--global", "-g"], ...)`), and the CLI tests invoke
`main.app([...], result_action="return_value")` instead of an `exit=` kwarg
(removed in cyclopts 4). `_ = copytree(...)` matches the repo's basedpyright
`reportUnusedCallResult` convention. `make check` and `make test-unit` pass
(397 unit tests); a live `uv run harold-mcp setup --directory …` smoke test
installs and re-installs correctly.

---

## Step 3: README rewrite

**Objective.** A terse README whose installation section runs `setup`,
explains update as "run setup again", and links the Zed and opencode v2 MCP
docs instead of embedding JSON.

**Guidance.**

- Rewrite the Installation section per the design (setup command, locations
  convention link, update via re-running setup, client-doc links, Zed "Write"
  profile and reload notes condensed).
- Condense the rest of the README without losing facts: the two tool
  descriptions, the configuration table (all env vars and defaults), the
  `MAUDE_LIB` note, and the development pointers.

**Tests.** `make docs-test` (README is included in the docs build) plus a
manual read-through for lost facts.

### Implementation notes

Implemented as planned: the installation section now runs `setup`, documents
its destinations and the locations convention, explains update as
"refresh + run `setup` again", and links the Zed and opencode v2 MCP docs
instead of embedding JSON. The Zed "Write" profile, reload, and opencode
TUI/ACP notes survive as single sentences. The tool descriptions and the
configuration section were condensed while keeping every env var, default and
note (Python 3.14 pin, bundled interpreter, `@latest`/`@VERSION` pinning,
timeout semantics, `MAUDE_LIB` caveat). README went from ~17.2 KB to ~8.6 KB.
`make docs-test` passes.

---
