# Detailed design — the `maude-manual` skill installer

## Overview

Two coordinated changes:

1. **Packaging**: a `skills` Makefile target copies the monorepo's
   `skills/maude-manual` into `src/harold_mcp/skills/maude-manual` (git-ignored),
   so hatchling ships it inside the wheel/sdist. The local `build` target and the
   release workflow's build step run the copy first.
2. **CLI**: a `harold-mcp setup` command copies the packaged skill into the
   agent skills directory (project `./.agents/skills` by default, `~/.agents/skills`
   with `-g`), overwriting any previous `maude-manual` so re-running it updates
   the skill.

## Packaging

### Makefile

New target (placed next to `build`):

```make
.PHONY: skills
skills: ## Copy the maude-manual skill from the monorepo into the package tree
	@echo "🚀 Copying skills/maude-manual into src/harold_mcp/skills"
	@uv run python -c "import shutil; shutil.rmtree('src/harold_mcp/skills', ignore_errors=True); shutil.copytree('../skills/maude-manual', 'src/harold_mcp/skills/maude-manual')"
```

- The destination root `src/harold_mcp/skills` is removed first, so a stale
  copy (e.g. after the skill is renamed or files are deleted upstream) never
  leaks into a build.
- `build` gains `skills` as a prerequisite: `build: clean-build skills`.

### `.gitignore`

Add `src/harold_mcp/skills/` to the first block (next to `.agents/skills`), so
the copy is never committed and the single source of truth stays
`skills/maude-manual`.

### Release workflow (`.github/workflows/on-release-main.yml`)

In the `publish` job, the "Build package" step becomes:

```yaml
      - name: Build package
        run: make skills && uv build
```

The checkout in that job is the full monorepo, so `../skills/maude-manual`
exists relative to the default `harold-mcp` working directory.

## CLI

### Module layout

- `src/harold_mcp/skill_install.py` (new): the install logic, unit-testable
  without the CLI.
- `src/harold_mcp/main.py`: the `setup` command, wired to the logic.

### `skill_install.py`

```python
SKILL_NAME = "maude-manual"

def skill_source() -> Path:
    """Path of the packaged skill inside the harold_mcp package."""

def install_skill(destination_base: Path, source: Path | None = None) -> Path:
    """Copy the skill to destination_base / SKILL_NAME and return that path."""
```

- `skill_source()` resolves `importlib.resources.files("harold_mcp") / "skills" /
  SKILL_NAME` with `as_file`-free `Path` conversion (hatchling ships the files
  as real directories in both wheel and sdist installs, so
  `importlib.resources.files(...)` joined and coerced to `Path` is enough;
  `uvx`/`pip` installs are never zip-imported).
- `install_skill`:
  - `source` defaults to `skill_source()`; the parameter exists for tests.
  - Fails fast with a clear `FileNotFoundError`-style message if the source is
    missing (an artifact built without the `skills` target).
  - `destination = destination_base / SKILL_NAME`; if it exists, remove it
    first — `shutil.rmtree` when it is a directory, `Path.unlink` when it is a
    plain file (a stray file named `maude-manual` must not brick `setup`) —
    then `shutil.copytree`. Removing the destination (not
    `dirs_exist_ok=True`) is what makes re-running `setup` a true update:
    files deleted from a newer skill never survive.
  - Creates `destination_base` (and parents) as needed.
  - Returns the installed path so the CLI can report it.

### `main.py` — the `setup` command

```python
@app.command
def setup(
    directory: Annotated[Path, Parameter(help="...")] = Path(".agents") / "skills",
    global_: Annotated[bool, Parameter("--global", "-g", help="...")] = False,
) -> None:
    """Install the bundled maude-manual skill for coding agents."""
```

- Default base: `./.agents/skills` (project-level, per the Mistral skills
  location convention). With `-g`: `Path.home() / ".agents" / "skills"` (the
  `directory` option is ignored in that case, matching the convention that the
  global location is fixed).
- Prints the installed path and the package version
  (`importlib.metadata.version("harold-mcp")`), so users can tell which
  release's skill they have.
- Errors (missing packaged skill, unwritable destination) propagate as normal
  CLI exceptions: cyclopts prints the message and exits non-zero.

## README

The Installation section is rewritten to:

1. prerequisites: `uv`, `uvx harold-mcp --version`, the Python 3.14 pin
   (kept, condensed), bundled Maude interpreter note;
2. `uvx harold-mcp setup` to install the skill, with the `-g` variant and the
   locations convention link;
3. update: refresh the package (`uvx --refresh harold-mcp --version` or
   `@latest` / `@VERSION` pinning) and run `setup` again;
4. MCP client configuration: one sentence pointing at the client's MCP docs —
   Zed (`https://zed.dev/docs/ai/mcp-servers`) and opencode v2
   (`https://opencode.ai/docs/mcp-servers/`) — replacing both embedded JSON
   blocks; the Zed "Write" profile and reload notes are kept, condensed into one
   sentence each. The ACP/TUI note is kept in one short sentence.

The rest of the README (tool descriptions, configuration table, development
pointers) is condensed without dropping facts: every setting, default, note and
link survives, in fewer words.

## Tests

`tests/unit/test_skill_install.py`:

- `install_skill` with an explicit `source` tmp dir:
  - fresh install creates `base/maude-manual` mirroring the source;
  - re-install over an existing copy with extra stale files removes them
    (update semantics);
  - sibling entries in `base` are untouched;
  - missing source raises with a clear message.
- `setup` CLI wiring: invoke `main.app` (cyclopts) with `["setup", "--dir", …]`
  and with `-g` (monkeypatching `Path.home` and the source), asserting the copy
  lands at the expected path.

A full-pipeline test that builds a wheel is not added (slow in CI for little
value); instead one cheap unit test asserts the packaging contract: when
`src/harold_mcp/skills/maude-manual` exists in the checkout (i.e. after
`make skills`), `skill_source()` points at a directory containing `SKILL.md`
(`pytest.mark.skipif` when the copy is absent, so a plain dev checkout still
passes). The wheel contents themselves are verified manually during
implementation (`make skills` + `uv build` + `unzip -l`) and by the workflow
change, which keeps the release build on the same path (`make skills &&
uv build`; locally, `make build` is the equivalent pre-release artifact check).

## Failure modes

- **Artifact built without the copy** (e.g. someone runs `uv build` by hand
  before `make skills`): `setup` fails fast with a message naming the missing
  packaged path and pointing at `make skills`. The release workflow cannot hit
  this because the copy is now part of the build step.
- **Destination exists and is read-only / unwritable**: the `shutil` call
  raises; cyclopts surfaces the message, exit code non-zero. No partial-state
  protection beyond remove-then-copy is attempted; the skill is data-only and
  re-running `setup` repairs any partial copy.
