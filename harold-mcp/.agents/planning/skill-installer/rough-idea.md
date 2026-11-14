# Ship the `maude-manual` skill with `harold-mcp` and install it with a `setup` command

## Context

The Harold monorepo contains two relevant parts:

- `harold-mcp/`: the MCP server package published to PyPI as `harold-mcp`.
- `skills/maude-manual/`: an agent skill (SKILL.md, cheatsheet, glossary, patterns,
  and a `chapters/` split of the Maude 3.5.1 manual) that teaches coding agents the
  Maude language.

Today the skill is only usable by cloning the monorepo. Users who install
`harold-mcp` from PyPI get the MCP tools but not the skill, so their agent lacks the
Maude manual reference the tools are meant to be paired with.

## Idea

1. Distribute the skill inside the PyPI artifacts, without duplicating its source:
   a Makefile target copies `skills/maude-manual` from the monorepo into the package
   tree (`src/harold_mcp/skills/maude-manual`) before building, and `.gitignore`
   excludes the copy so it is never committed.
2. Add a `setup` command to the `harold-mcp` CLI (`src/harold_mcp/main.py`) that
   copies the packaged skill into a skills directory:
   - default: `./.agents/skills/maude-manual` (project-level, relative to the
     current working directory);
   - `-g`: `~/.agents/skills/maude-manual` (user-level).
   These follow the common agent-skills location convention (project skills under
     `./.agents/skills`, user skills under `~/.agents/skills`, as documented by the
     Mistral skills locations reference).
3. Re-running `setup` after an upgrade refreshes the installed skill, so "update"
   in the README becomes "run setup again".

## Non-goals

- Installing other skills from the monorepo (only `maude-manual` ships).
- Managing or uninstalling previously installed skills beyond overwriting
  `maude-manual` itself.
- Renaming or restructuring `skills/maude-manual`.
