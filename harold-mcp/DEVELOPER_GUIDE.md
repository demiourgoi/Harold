# Developer guide

This guide is for contributors and maintainers of `harold-mcp`. For
user-facing documentation (installation, MCP client configuration, and the
`HAROLD_*` environment variables), see [`README.md`](README.md); the
contribution workflow lives in [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Development environment setup

Install the environment with

```bash
make install

# code validations
make check test

# run all CI checks before pushing a code change
make release

# run the MCP server over stdio transport
make run
# or directly:
uv run harold-mcp

# list the available entry points
uv run harold-mcp --help
```

Use the full path to `harold-mcp/.venv/bin/harold-mcp` on opencode or whatever agent harness you want to use, to run it locally. 

### Recommendations

- In case you are using the Zed IDE, it is also recommended to clone https://github.com/fadoss/maude-bindings, and add it to the Zed project together with the root folder of this file, so it is available to coding agents.
- Cline is great for debugging tool behaviour, because it displays the full JSON response from each tool call.
- Setup the following agent skills:
  - `codebase-summary`: copy the corresponding [agent SOP](https://github.com/strands-agents/agent-sop/blob/main/agent-sops/codebase-summary.sop.md) to  ~/.agents/skills/codebase-summary/SKILL.md, and add the following frontmatter

```md
---
name: codebase-summary
description: Generates structured codebase documentation — architecture, components, interfaces, data models, workflows — into `.agents/summary/`, and produces consolidated files like `AGENTS.md`, `README.md`, or `CONTRIBUTING.md`. Use when the user asks to document, summarize, understand, or onboard to a codebase.
---
```

  - `pdd`: copy the corresponding [agent SOP](https://github.com/strands-agents/agent-sop/blob/main/agent-sops/pdd.sop.md) to  ~/.agents/skills/pdd/SKILL.md, and add the following frontmatter

```md
---
name: pdd
description: Transforms a rough idea into a detailed design document, implementation plan, and actionable todo list using the Prompt-Driven Development (PDD) methodology. Use when a user describes a project concept or feature idea they want to develop, when they need to flesh out requirements and research before coding, or when they ask to plan, design, or create a structured specification for a new project.
---
```

## Releasing a new version

One time setup:
- Create an API Token on [PyPI](https://pypi.org/).
- Add the API Token to your projects secrets with the name `PYPI_TOKEN` by visiting [this page](https://github.com/demiourgoi/harold/settings/secrets/actions/new).
- On https://github.com/demiourgoi/Harold/settings/pages enable GitHub pages with source "GitHub Actions". On https://github.com/demiourgoi/Harold/settings/environments the environment github-pages, on "Deployment branches and tags" use "Selected branches and tags" and add a rule for the tag pattern "*.*.*".

__New release__ process:

1. Create a [new release](https://github.com/demiourgoi/harold/releases/new) on GitHub.
    1. Make sure `make release` passes and CI checks are passing. 
    2. Set tag to a new tag in the form `*.*.*` for the current version on `pyproject.toml`, removing the ".dev0" suffix. Use "Create new tag on publish".
    3. Set target to `main`. Note the [release GH workflow](https://github.com/demiourgoi/Harold/blob/main/.github/workflows/on-release-main.yml) will patch `pyproject.toml` to use the version specified in the previous step, irrespective of the version that appears in the main branch.
    4. Use the `CHANGELOG.md` entry for that version for the release notes
    5. Add the pre-release label as required, and any suitable binaries
    6. Click "Publish release"
    7. Watch it run under the **Actions** tab → `release-main`. Success means the package is on PyPI and docs are live. Confirm all went well on https://pypi.org/project/harold-mcp/
2. Bump the version on `pyproject.toml` so the tip of `main` is the code for the next release, still WIP. Also add a new entry to `CHANGELOG.md` for the new version (without the ".dev0" suffix).

Note:

- PyPI versions are immutable — you can never re-upload or fix a released version. If a release fails after a partial publish, you must bump to the next version (e.g. `0.0.4`).

## References

- Maude
  - [Maude manual](https://maude.lcc.uma.es/maude-manual/)
  - [Bindings docs](https://fadoss.github.io/maude-bindings/)
  - [vscode-maude](https://github.com/Sirquini/vscode-maude) for syntax highlighting. To install on VsCodium use [VSIX Downloader](https://cypherpunksamurai.github.io/vsix-downloader-webui/) to download the VSIX file from the [marketplace](https://marketplace.visualstudio.com/items?itemName=sirquini.maude), and install it with Extensions view → ... → "Install from VSIX...".
- [FastMCP](https://gofastmcp.com)
  - Agent docs
    - [Incremental](https://gofastmcp.com/llms.txt).
    - [Full](https://gofastmcp.com/llms-full.txt): probably uses too much context.
- [OpenCode Python SDK](https://github.com/anomalyco/opencode-sdk-python)
  - [API docs](https://github.com/anomalyco/opencode-sdk-python/blob/main/api.md)
