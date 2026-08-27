# harold-mcp

<img src="src/harold_mcp/assets/brand/Harold_logo.png" alt="Harold logo" width="100" />

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

An installer is still to be developed. For now you need to download the code and run `make install`. 

Then setup the `harold-mcp` command defined on `pyproject.toml` as an MCP server for your IDE, using the command full path. 
For example, for Zed add the following to `~/.config/zed/settings.json`:

```json
  "context_servers": {
    "harold": {
      "enabled": true,
      "remote": false,
      "command": "/home/juanrh/git/demiourgoi/Harold/harold-mcp/.venv/bin/harold-mcp",
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
      "command": ["/home/juanrh/git/demiourgoi/Harold/harold-mcp/.venv/bin/harold-mcp"],
      "enabled": true,
      "environment": {}
    }
  }
```

for Cline (useful for manual testing and Maude programming) add the following to `~/.cline/data/settings/cline_mcp_settings.json`:


```json
  "mcpServers" : {
    "harold": {
      "command": "/home/juanrh/git/demiourgoi/Harold/harold-mcp/.venv/bin/harold-mcp",
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

- Create an API Token on [PyPI](https://pypi.org/).
- Add the API Token to your projects secrets with the name `PYPI_TOKEN` by visiting [this page](https://github.com/demiourgoi/harold/settings/secrets/actions/new).
- Create a [new release](https://github.com/demiourgoi/harold/releases/new) on Github.
- Create a new tag in the form `*.*.*`.


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
