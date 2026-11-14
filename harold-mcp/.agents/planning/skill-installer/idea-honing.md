# Requirements — skill installer

## Goal

A PyPI user can install the `maude-manual` agent skill with one command, and the
README's installation section is short and links to client docs instead of
embedding MCP config JSON.

## Requirements

1. **Packaging.** The built wheel (and sdist) of `harold-mcp` contains the
   `maude-manual` skill under the package (importable as package data at
   `harold_mcp/skills/maude-manual`). The skill's source of truth stays
   `skills/maude-manual` in the monorepo; the copy inside `src/harold_mcp/` is a
   build-time artifact that is git-ignored and never committed.
2. **Build integration.** A Makefile target copies the skill into the package tree;
   the local `build` target and the release workflow's build step both run it
   before building, so the published artifact always contains the skill.
3. **CLI.** `harold-mcp setup` copies the packaged skill to a skills directory:
   - default destination base: `./.agents/skills` (relative to the current working
     directory), so the skill lands at `./.agents/skills/maude-manual`;
   - `-g`/`--global`: destination base `~/.agents/skills`, so the skill lands at
     `~/.agents/skills/maude-manual`;
   - the destination base is overridable (a `--dir` option), defaulting to the
     project location above.
4. **Idempotence/update.** Running `setup` again overwrites a previously installed
   `maude-manual` (re-copy, removing stale files), so re-running `setup` after
   `uvx --refresh` updates the skill. It must not touch anything else inside the
   destination base.
5. **Feedback.** `setup` prints where the skill was installed and its version
   source (the `harold-mcp` package version), and exits non-zero with a clear
   message if the packaged skill is missing or the copy fails.
6. **README.** The installation section:
   - instructs the user to run the `setup` command;
   - explains updating as "run `setup` again" (after refreshing the package);
   - replaces the embedded Zed and opencode MCP config JSON with links to the
     clients' MCP-configuration docs (opencode v2 docs);
   - keeps every fact that is still true (Python 3.14 pin, bundled Maude
     interpreter, Zed "Write" profile note, reload note, `@latest`/`@VERSION`
     pinning), and the whole README becomes terser without losing information.
7. **Tests.** Unit tests cover the copy logic (fresh install, overwrite/update,
   `--global`, `--dir`, destination untouched siblings) and the CLI wiring.
8. **Quality gates.** `make check` and the unit test split pass unchanged.

## Constraints

- No new runtime dependencies (stdlib `shutil`, `pathlib`, `importlib.resources`
  and the existing `cyclopts` suffice).
- The release workflow (`on-release-main.yml`) builds with `uv build`; the skill
  copy must happen before that build in that same job.
- The `maude` interpreter is not needed for `setup`, so `setup` must work without
  spawning any worker.
