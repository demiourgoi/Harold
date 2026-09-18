# harold-mcp

<img src="https://raw.githubusercontent.com/demiourgoi/Harold/refs/heads/main/harold-mcp/src/harold_mcp/assets/brand/Harold_logo.png" alt="Harold logo" width="100" />

Harold MCP tools:

- **Github repository**: <https://github.com/demiourgoi/harold/>
- **Documentation** <https://demiourgoi.github.io>

## What is this?

`harold-mcp` is an MCP server that gives AI coding assistants tools for working with the Maude specification and verification language.

### Harold MCP Tools

- **`maude_program_diagnostics(path)`** — diagnoses a Maude source file with two
  independent sources, run in a single call:
  - the **Maude interpreter**, which loads the file and reports every problem Maude
    finds, including the warnings it recovers from; and
  - Harold's **heuristic linter**, which checks the file's text for common mistakes:
    a `when` guard borrowed from Haskell/SML, `--` used as a comment, a single `=` in an
    `if … then … else … fi` term, non-linear equation patterns, capitalized identifiers
    that nothing declares, non-ASCII typographic punctuation, and sorts that shadow a
    prelude sort. Heuristic findings are pattern-based and may be false positives, so
    they are reported as `warning` (suspicious code) or `info` (observations that do not
    affect the load).

  Every diagnostic carries `source` and `code` provenance, a `severity` (`info`,
  `warning` or `error`), a `message`, an LSP-style 1-based `range` (`null` for whole-file
  problems; heuristic findings include exact, exclusive-end columns), and — when a
  deterministic correction exists, such as replacing typographic punctuation with ASCII
  — a report-only `fix` (a description plus applyable edits; the tool never modifies the
  file). Diagnostics are ordered by position, whole-file problems last. `success` is
  `true` only when no diagnostic has severity `warning` or `error`, so `info`-only
  results still count as success. Use it to check whether a Maude program is well formed,
  and to get a list of issues to fix.

Planned tools: running Maude programs, and a vector index of the Maude documentation for
retrieval-augmented generation (RAG).

## Installation

- Install [`uv`](https://docs.astral.sh/uv/getting-started/installation/)
- Run `uvx harold-mcp --version`

The `maude` dependency bundles the Maude interpreter (built against Maude 3.5.1),
so there is nothing else to install.

Then setup the `harold-mcp` command defined on `pyproject.toml` as an MCP server for your IDE.  
Any MCP-compatible client works (including Cline); the Zed and opencode configurations below are the ones we test.  
For example, for [_Zed IDE_](https://zed.dev/docs/getting-started) add the following to `~/.config/zed/settings.json`:

```json
  "context_servers": {
    "harold": {
      "enabled": true,
      "remote": false,
      "command": "uvx",
      "args": [
        "harold-mcp"
      ],
      "env": {}
    }
  },
  ...
```

_Note_: with the Zed agent (at least as of Zed 1.20.2) you must use the "Write" profile, as Zed ignores MCP tools in other profiles, even those marked with `readOnlyHint`.  
Also note Zed requires a reload after changing the MCP config, both for the Zed agent and for ACP agents.

For [_opencode_](https://opencode.ai) add the following to `~/.config/opencode/opencode.jsonc`:

```jsonc
  "mcp" : {
    "harold": {
      "type": "local",
      "command": ["uvx", "harold-mcp"],
      "enabled": true,
      "environment": {}
    }
  }
```

This works both for the [opencode TUI](https://opencode.ai/docs/tui/), and the [ACP agent for opencode in Zed](https://opencode.ai/docs/acp/#zed).

### Update

To manually update run `uvx --refresh harold-mcp --version`.  
Alternatively, use `uvx harold-mcp@latest` in your MCP client configuration, to perform an update check on each boot (instead of the manual command above). That implies a longer boot time, but for most IDEs this is negligible, since they spawn MCP servers in the background and don't block the UI on startup. CLI clients may behave differently.  
If you want to run a specific version, check the release [history in PyPI](https://pypi.org/project/harold-mcp/#history). Use `uvx harold-mcp@VERSION`, e.g. `uvx harold-mcp@0.0.2`.  

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
