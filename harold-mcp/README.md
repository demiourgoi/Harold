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

  Each call is hermetic: the file is loaded into a fresh Maude interpreter, with no state
  carried over from previous calls. The interpreter checks the whole load — the file
  plus anything it pulls in with `load`/`in` — and problems found in a dependency are
  reported as whole-file diagnostics whose message names the dependency file and
  suggests diagnosing it on its own.

- **`maude_run(path, module, steps)`** — runs a bounded Maude interpreter session: loads
  one file into a fresh interpreter, selects a module, and executes an ordered list of
  `reduce`, `rewrite`, `frewrite`, `erewrite`, `match` and `search` steps, returning every
  intermediate result. Steps thread a current term REPL-style (omit a step's term or
  subject to use the previous result), and the optional `bound`, `gas` and `depth` inputs
  map to Maude's limits. Each call is hermetic: nothing survives between calls, so carry
  state by re-submitting a saved result term or writing a wrapper module. Load warnings
  are reported but evaluation proceeds; per-step failures (`parse-error`, `too-large`)
  stop the run and are returned as outcomes, and `match`/`search` cap their results with a
  `truncated` flag. Every phase reports the interpreter's captured stdout/stderr, and the
  path must be **absolute** (the server's working directory is not the client's).

Planned tools: a vector index of the Maude documentation for retrieval-augmented
generation (RAG).

## Installation

- Install [`uv`](https://docs.astral.sh/uv/getting-started/installation/)
- Run `uvx harold-mcp --version`

Harold requires **Python 3.14**: the `maude` dependency ships CPython 3.14 wheels only, so
Harold's metadata pins the 3.14 series. If you don't have 3.14 installed, `uvx` downloads it
automatically (or run `uv python install 3.14`); to select it explicitly — e.g. a specific
patch release — pass `uvx --python 3.14 harold-mcp`.

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

The server is configured through environment variables set in the MCP server configuration. `HAROLD_*` variables are Harold's own settings; `MAUDE_LIB` is inherited from the underlying Maude bindings:

| Env var | Meaning | Default |
| --- | --- | --- |
| `HAROLD_MAUDE_WORKERS` | Number of Maude worker processes. Workers are recycled after every call (each call gets a fresh interpreter), so this caps how many diagnostics/interpreter sessions can run concurrently, not how many interpreters stay warm. | half the logical CPUs, capped at 3 |
| `HAROLD_DIAGNOSTICS_TIMEOUT_SECS` | Seconds to wait for each `maude_program_diagnostics` worker call before failing it as timed out. Renamed from `HAROLD_MAUDE_WORKER_TIMEOUT_SECS`. | `60` |
| `HAROLD_INTERPRETER_TIMEOUT_SECS` | Default timeout for each `maude_run` call; its `timeout_secs` argument overrides it. | `60` |
| `HAROLD_INTERPRETER_MAX_STEPS` | Maximum steps per `maude_run` call. | `200` |
| `HAROLD_INTERPRETER_MAX_REWRITE_BOUND` | Maximum accepted `bound` per rewrite step. | `1000` |
| `HAROLD_INTERPRETER_MAX_SOLUTIONS` | Maximum `match` substitutions or `search` solutions returned per step. | `200` |
| `HAROLD_INTERPRETER_MAX_TERM_LENGTH` | Maximum characters of a term, pattern or subject input. | `100000` |
| `HAROLD_INTERPRETER_MAX_RESULT_LENGTH` | Maximum characters of a returned term; a longer result becomes a `too-large` step outcome. | `1000000` |
| `HAROLD_INTERPRETER_MAX_OUTPUT_LENGTH` | Maximum characters of each captured stream (stdout and stderr separately) returned per phase; longer captures are truncated and marked. | `1000000` |
| `MAUDE_LIB` | Inherited by the Maude bindings, not read by Harold itself: colon-separated directories where Maude searches for `prelude.maude` (and for library files loaded with `in`/`load`). Only needed to override the prelude bundled with the `maude` wheel. | unset (the bundled prelude is used) |

Invalid values (e.g. `HAROLD_MAUDE_WORKERS=0`) make the server fail fast at startup.

Both timeouts cover the whole worker call (interpreter startup included) and are best
effort: a call that exceeds its timeout fails, its worker is killed, and the worker pool
is replaced, so allow more time for long evaluations.

If you use `MAUDE_LIB` to override the bundled prelude, that prelude must match the Maude version Harold uses (currently Maude 3.5.1, the version the `maude` dependency is built against); a mismatched prelude can make the interpreter fail to load it or behave inconsistently. See [`.agents/summary/maude-lib.md`](.agents/summary/maude-lib.md) for how Maude locates the prelude.

## Development

Contributions are welcome! See
[`CONTRIBUTING.md`](https://github.com/demiourgoi/harold/blob/main/harold-mcp/CONTRIBUTING.md)
for the contribution workflow, and
[`DEVELOPER_GUIDE.md`](https://github.com/demiourgoi/harold/blob/main/harold-mcp/DEVELOPER_GUIDE.md)
for the development environment and release process.

---

Repository initiated with [osprey-oss/cookiecutter-uv](https://github.com/osprey-oss/cookiecutter-uv).
