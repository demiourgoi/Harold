# harold-mcp

<img src="https://raw.githubusercontent.com/demiourgoi/Harold/refs/heads/main/harold-mcp/src/harold_mcp/assets/brand/Harold_logo.png" alt="Harold logo" width="100" />

Harold MCP tools:

- **Github repository**: <https://github.com/demiourgoi/harold/>
- **Documentation** <https://demiourgoi.github.io>

## What is this?

`harold-mcp` is an MCP server that gives AI coding assistants tools for working with the Maude specification and verification language. 

### Harold MCP Tools

- **`maude_program_diagnostics(path)`** — diagnoses a Maude source file by loading it
  into the Maude interpreter and reporting every problem it finds, including warnings
  Maude can recover from. Returns a structured, LSP-style result: a `success` flag (true
  only when the file loads with no warnings and no errors), per-severity counts, and one
  diagnostic per problem with a 1-based line range (`range` is `null` for whole-file
  problems). Use it to check whether a Maude program is well formed, and to get a list of
  issues to fix.

Planned tools: running Maude programs, and a vector index of the Maude documentation for
retrieval-augmented generation (RAG).

## Installation

- Install [`uv`](https://docs.astral.sh/uv/getting-started/installation/)
- Run `uvx harold-mcp --version`

To update run `uvx harold-mcp@latest --version`.   
If you want to run a specific version, check the release [history in pypi](https://pypi.org/project/harold-mcp/#history) use `uvx harold-mcp@VERSION`, e.g. `uvx harold-mcp@0.0.2`.  

Then setup the `harold-mcp` command defined on `pyproject.toml` as an MCP server for your IDE, using the command full path. 
For example, for Zed add the following to `~/.config/zed/settings.json`:

```json
  "context_servers": {
    "harold": {
      "enabled": true,
      "remote": false,
      "command": "uvx harold-mcp",
      "args": [],
      "env": {}
    }
  },
  ...
```

for opencode (useful for automated testing) add the following to `~/.config/opencode/opencode.jsonc`:


```json
  "mcp" : {
    "harold": {
      "type": "local",
      "command": ["uvx harold-mcp"],
      "enabled": true,
      "environment": {}
    }
  }
```

for Cline (useful for manual testing and Maude programming) add the following to `~/.cline/data/settings/cline_mcp_settings.json`:


```json
  "mcpServers" : {
    "harold": {
      "command": "uvx harold-mcp",
      "args": [],
      "disabled": false,
      "autoApprove": [],
      "env": {}
    }
  }
```

For production, harold-mcp will be distributed as a Python package and run with `uvx`. 

### Configuration

The server is configured through environment variables (`HAROLD_*` prefix) set in the MCP server configuration:

| Env var | Meaning | Default |
| --- | --- | --- |
| `HAROLD_MAUDE_WORKERS` | Number of Maude worker processes. Diagnostics run in parallel across workers; more workers use more memory (each creates its own Maude interpreter). | `1` |
| `HAROLD_MAUDE_WORKER_TIMEOUT_SECS` | Seconds to wait for each worker call before failing it as timed out. | `60` |

Invalid values (e.g. `HAROLD_MAUDE_WORKERS=0`) make the server fail fast at startup.

## Developer guide

### Development environment setup

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
# uv run harold-mcp
```

This will also generate your `uv.lock` file.   
Use the full path to `harold-mcp/.venv/bin/harold-mcp` on opencode or whatever agent harness you want to use, to run it locally. 

#### Recommendations

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

### Releasing a new version

One time setup:
- Create an API Token on [PyPI](https://pypi.org/).
- Add the API Token to your projects secrets with the name `PYPI_TOKEN` by visiting [this page](https://github.com/demiourgoi/harold/settings/secrets/actions/new).
- On https://github.com/demiourgoi/Harold/settings/pages enable GitHub pages with source "GitHub Actions". On https://github.com/demiourgoi/Harold/settings/environments the environment github-pages, on "Deployment branches and tags" use "Selected branches and tags" and add a rule for the tag patttern "*.*.*".

__New release__ process:

1. Create a [new release](https://github.com/demiourgoi/harold/releases/new) on Github.
    1. Make sure `make release` passes and CI checks are passing. 
    2. Set tag to a new tag in the form `*.*.*` for the current version on `pyproject.toml`, removing the ".dev0" suffix. Use "Create new tag on publish".
    3. Set target to `main`. Note the [release GH workflow](https://github.com/demiourgoi/Harold/blob/main/.github/workflows/on-release-main.yml) will patch `pyproject.toml` to use the version specified in the previous step, irrespective of the versión that appears in the main branch
    4. Use the `CHANGELOG.md` entry for that version for the release notes
    5. Add the pre-release label as required, and any suitable binaries
    6. Click "Publish release"
    7. Watch it run under the **Actions** tab → `release-main`. Success means the package is on PyPI and docs are live. Confirm all went well on https://pypi.org/project/harold-mcp/
2. New the version on `pyproject.toml` so the tip of main is the code for the next release, still WIP. Also add a new entry on CHANGELOG.md for the new version (without the  the ".dev0" suffix).

Note:

- PyPI versions are immutable — you can never re-upload or fix a released version. If a release fails after a partial publish, you must bump to `0.0.4` (or use a dev suffix).

### References

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

---

Repository initiated with [osprey-oss/cookiecutter-uv](https://github.com/osprey-oss/cookiecutter-uv).
