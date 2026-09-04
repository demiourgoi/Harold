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
If you want to run a specific version, check the release [history in PyPI](https://pypi.org/project/harold-mcp/#history) use `uvx harold-mcp@VERSION`, e.g. `uvx harold-mcp@0.0.2`.  

The `maude` dependency bundles the Maude interpreter (built against Maude 3.5.1),
so there is nothing else to install.

Then setup the `harold-mcp` command defined on `pyproject.toml` as an MCP server for your IDE.  
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

### Configuration

The server is configured through environment variables (`HAROLD_*` prefix) set in the MCP server configuration:

| Env var | Meaning | Default |
| --- | --- | --- |
| `HAROLD_MAUDE_WORKERS` | Number of Maude worker processes. Diagnostics run in parallel across workers; more workers use more memory (each creates its own Maude interpreter). | `1` |
| `HAROLD_MAUDE_WORKER_TIMEOUT_SECS` | Seconds to wait for each worker call before failing it as timed out. | `60` |

Invalid values (e.g. `HAROLD_MAUDE_WORKERS=0`) make the server fail fast at startup.

## Development

Contributions are welcome! See
[`CONTRIBUTING.md`](https://github.com/demiourgoi/harold/blob/main/harold-mcp/CONTRIBUTING.md)
for the contribution workflow, and
[`DEVELOPER_GUIDE.md`](https://github.com/demiourgoi/harold/blob/main/harold-mcp/DEVELOPER_GUIDE.md)
for the development environment and release process.

---

Repository initiated with [osprey-oss/cookiecutter-uv](https://github.com/osprey-oss/cookiecutter-uv).
