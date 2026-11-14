# Research — packaging the skill and the release pipeline

## The release pipeline (how the PyPI artifact is built)

Release process (from `DEVELOPER_GUIDE.md`, "Releasing a new version"):

1. `CHANGELOG.md` is updated and the version on `pyproject.toml` is bumped on
   `main` (with a `.dev0` suffix while WIP).
2. A GitHub release is published with a `*.*.*` tag targeting `main`.
3. The [`on-release-main.yml`](../../../../../.github/workflows/on-release-main.yml)
   workflow then runs two jobs:
   - `set-version`: patches `version = "…"` in `harold-mcp/pyproject.toml` to the
     release tag and uploads the patched file as an artifact.
   - `publish`: checks out the repository (the **full monorepo**, so
     `skills/maude-manual` is present at `../skills/maude-manual` relative to the
     default `harold-mcp` working directory), restores the patched
     `pyproject.toml`, then builds with **`uv build`** and publishes with
     `uv publish` (`UV_PUBLISH_TOKEN` secret).

Key consequence: the release build does **not** go through `make build`; it calls
`uv build` directly inside the `publish` job. Any skill-copy step must therefore
run in that job before `uv build` (the workflow must be updated), and the local
`make build` target must run the same copy so local and CI artifacts match.

## How the wheel/sdist include files

- Build backend is **hatchling** with
  `[tool.hatch.build.targets.wheel] packages = ["src/harold_mcp"]`
  (`pyproject.toml`). Hatchling includes **every file** (not only `.py`) that
  lives under the configured package directory, recursively, in both the wheel
  and the sdist. No `package-data` configuration is needed: dropping the skill
  at `src/harold_mcp/skills/maude-manual/` before the build is enough for it to
  be shipped, and to be importable as package data via
  `importlib.resources.files("harold_mcp") / "skills" / "maude-manual"`.
- Hatchling's `force-include` could map `../skills/maude-manual` into the wheel
  without a copy, but referencing paths outside the project root is fragile and
  the requirement explicitly prefers the Makefile-copy approach (which also
  keeps `uv build` from silently depending on monorepo layout).

## Skill source and size

`skills/maude-manual/` is ~320 KiB of Markdown (`SKILL.md`, `cheatsheet.md`,
`glossary.md`, `patterns.md`, `chapters/*.md`). Copying it into the package tree
has a negligible effect on wheel size. It carries no license restriction issue
for redistribution inside the same project's artifact (the skill is authored in
this monorepo).

## Skills location convention

Per the Mistral skills documentation (`https://docs.mistral.ai/vibe/code/cli/skills#locations`),
agents discover skills at:

- project level: `./.agents/skills/<skill-name>/` (relative to the project root,
  i.e. the current working directory of the command);
- user level: `~/.agents/skills/<skill-name>/`.

So `setup` must place the skill at `<base>/maude-manual/` with
`<base> = ./.agents/skills` by default and `~/.agents/skills` when a global flag
is passed.

## CLI framework

`main.py` uses **cyclopts** (`App`). Existing pattern: a default command
(`run`) plus a `serve` subcommand. Adding `app.command def setup(...)` follows
the same pattern. Boolean flags are declared with
`Annotated[bool, Parameter("--global", "-g")]`; `Path`-typed parameters become
positional/options automatically. `harold-update-prelude-sorts` shows a
`cyclopts` CLI with options is already an established pattern in this codebase.

## Client docs to link from the README

- Zed MCP servers: `https://zed.dev/docs/ai/mcp-servers`
- opencode (v2) MCP servers: `https://opencode.ai/docs/mcp-servers/`

## Alternatives considered

- **`hatch force-include` of `../skills/maude-manual`**: no copy needed, but
  depends on a path outside the package root, and the release workflow would
  still need no change — yet local `uv build` from `harold-mcp/` alone (e.g. an
  sdist-only checkout) would break. Rejected in favor of the explicit copy.
- **Downloading the skill from GitHub at `setup` time**: adds a network
  dependency and a version-skew problem (skill vs. server version). Rejected;
  shipping it in the wheel pins them together.
- **Separate `harold-skill` PyPI package**: doubles the release work and can
  drift from the server version. Rejected.
