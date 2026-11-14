# harold-mcp

<img src="https://raw.githubusercontent.com/demiourgoi/Harold/refs/heads/main/harold-mcp/src/harold_mcp/assets/brand/Harold_logo.png" alt="Harold logo" width="100" />

`harold-mcp` is an MCP server that gives AI coding assistants tools for working with the Maude specification and verification language.

- **Github repository**: <https://github.com/demiourgoi/harold/>
- **Documentation** <https://demiourgoi.github.io>

## Tools

- **`maude_program_diagnostics(path)`** — diagnoses a Maude source file with two independent sources in one call: the **Maude interpreter** (loads the file, reports every problem including recovered warnings) and Harold's **heuristic linter** (text patterns for common mistakes: `when` guards, `--` comments, single `=` in `if … then … else … fi`, non-linear equation patterns, undeclared capitalized identifiers, non-ASCII punctuation, prelude-sort shadowing; findings are `warning`/`info`, as they may be false positives).

  Each diagnostic carries `source` and `code` provenance, a `severity` (`info`/`warning`/`error`), a `message`, an LSP-style 1-based `range` (`null` for whole-file problems), and — when a deterministic correction exists, e.g. ASCII punctuation — a report-only `fix` (the tool never modifies the file). Diagnostics are ordered by position, whole-file problems last; `success` is `true` only when no diagnostic is `warning` or `error`.

  Each call is hermetic: the file is loaded into a fresh interpreter, no state carries over. The interpreter checks the whole load — the file plus anything pulled in with `load`/`in`; problems in a dependency are reported as whole-file diagnostics naming that file. If a diagnostic provider fails, the call fails with one section per failing provider; full detail is logged server-side.

- **`maude_run(path, module, steps)`** — runs a bounded Maude session: loads one file into a fresh interpreter, selects a module, and executes ordered `reduce`, `rewrite`, `frewrite`, `erewrite`, `match` and `search` steps, returning every intermediate result. Steps thread the current term REPL-style (omit a step's term/subject to reuse the previous result); `bound`, `gas` and `depth` map to Maude's limits. Load warnings are reported but evaluation proceeds; per-step failures (`parse-error`, `too-large`) stop the run as outcomes; `match`/`search` cap results with a `truncated` flag. Each `search` solution carries its rewrite path: `path: "labels"` (default), `path: "full"` (adds rule text and intermediate states), or `path: "none"`. Every phase reports captured stdout/stderr, and `path` must be **absolute** (the server's working directory is not the client's). Whole-call failures (missing path, load failure, missing/theory module, worker crash or timeout) fail with a category (`timeout`, `crash`, `spawn-failure`, `init-failure`, `remote-exception`, `cancelled`, `protocol-error`); the full detail is logged server-side.

Planned tools: a vector index of the Maude documentation for retrieval-augmented generation (RAG).

## Installation

- Install [`uv`](https://docs.astral.sh/uv/getting-started/installation/), then:

```bash
uvx harold-mcp --version   # check the install
uvx harold-mcp setup       # install the Harold skills (currently just maude-manual) into ./.agents/skills of the current directory — see "The `setup` command"
```

Harold requires **Python 3.14** (the `maude` dependency ships CPython 3.14 wheels only, so the metadata pins the 3.14 series); `uvx` downloads it automatically if missing, or run `uv python install 3.14` / pass `uvx --python 3.14`. The `maude` dependency bundles the Maude interpreter (built against Maude 3.5.1), so there is nothing else to install.

### The `setup` command

`setup` copies the bundled `maude-manual` skill (the Maude 3.5.1 manual as an agent skill) into your agent's skills directory, following the [standard skills locations](https://docs.mistral.ai/vibe/code/cli/skills#locations):

- default: `./.agents/skills/maude-manual` (project-level);
- `-g`/`--global`: `~/.agents/skills/maude-manual` (user-level);
- `--directory PATH`: any other skills directory.

Re-running `setup` refreshes the installed skill (a full re-copy), and never touches anything else in the directory.

### Update

Refresh the package and run `setup` again:

```bash
uvx --refresh harold-mcp setup
```

This refreshes the package and installs the Harold skills (currently just `maude-manual`) into `./.agents/skills` of the current directory — see [The `setup` command`](#the-setup-command) for the destinations.

Alternatively, configure your MCP client with `uvx harold-mcp@latest` to update-check on each boot (slightly longer boot; negligible for IDEs, which spawn MCP servers in the background — CLI clients may differ). To pin a version, check the [PyPI release history](https://pypi.org/project/harold-mcp/#history) and use `uvx harold-mcp@VERSION`, e.g. `uvx harold-mcp@0.0.2`.

### MCP client configuration

Register `uvx harold-mcp` as a local MCP server in your client; any MCP-compatible client works (including Cline). See the MCP configuration docs of the clients we test: [Zed](https://zed.dev/docs/ai/mcp-servers) and [opencode (v2)](https://opencode.ai/docs/mcp-servers/) (works for both the [opencode TUI](https://opencode.ai/docs/tui/) and the [ACP agent for opencode in Zed](https://opencode.ai/docs/acp/#zed)). Zed gotchas: use the "Write" profile for the Zed agent (as of Zed 1.20.2 it ignores MCP tools in other profiles, even those marked `readOnlyHint`), and reload Zed after changing the MCP config (also for ACP agents).

### Configuration

Environment variables set in the MCP server configuration. `HAROLD_*` are Harold's settings; `MAUDE_LIB` is inherited from the Maude bindings:

| Env var | Meaning | Default |
| --- | --- | --- |
| `HAROLD_MAUDE_WORKERS` | Maximum concurrent Maude interpreter processes (each call runs in a fresh process; this caps concurrency, not warm workers). | half the logical CPUs, capped at 3 |
| `HAROLD_DIAGNOSTICS_TIMEOUT_SECS` | Seconds to wait per `maude_program_diagnostics` worker call. Renamed from `HAROLD_MAUDE_WORKER_TIMEOUT_SECS`. | `60` |
| `HAROLD_INTERPRETER_TIMEOUT_SECS` | Default timeout per `maude_run` call; the call's `timeout_secs` argument overrides it. | `60` |
| `HAROLD_INTERPRETER_MAX_STEPS` | Maximum steps per `maude_run` call. | `200` |
| `HAROLD_INTERPRETER_MAX_REWRITE_BOUND` | Maximum accepted `bound` per rewrite step. | `1000` |
| `HAROLD_INTERPRETER_MAX_SOLUTIONS` | Maximum `match` substitutions or `search` solutions per step. | `200` |
| `HAROLD_INTERPRETER_MAX_TERM_LENGTH` | Maximum characters of a term, pattern or subject input. | `100000` |
| `HAROLD_INTERPRETER_MAX_RESULT_LENGTH` | Maximum characters of a returned term (or path string); longer becomes a `too-large` outcome. | `1000000` |
| `HAROLD_INTERPRETER_MAX_PATH_STEPS` | Maximum transitions per `search` solution path; longer becomes a `too-large` outcome. | `100` |
| `HAROLD_INTERPRETER_MAX_OUTPUT_LENGTH` | Maximum characters per captured stream (stdout and stderr separately) per phase; longer captures are truncated and marked. | `1000000` |
| `HAROLD_ERROR_DETAIL_MAX_CHARS` | Maximum error-detail characters returned to the client; the full report is always logged, and a truncated report ends with a marker pointing at the log. | `4000` |
| `HAROLD_IPC_MAX_RESPONSE_BYTES` | Maximum bytes of one worker response (hardening against a buggy child, not a QoS limit); an oversized response is a protocol error naming this setting. | `2147483648` (2 GiB) |
| `MAUDE_LIB` | Inherited by the Maude bindings, not read by Harold: colon-separated directories where Maude searches for `prelude.maude` (and library files loaded with `in`/`load`). Only needed to override the bundled prelude. | unset (bundled prelude used) |

Invalid values (e.g. `HAROLD_MAUDE_WORKERS=0`) make the server fail fast at startup. Both timeouts cover the whole worker call (admission, process startup, Maude initialization, the load and every step) and are best effort: a timed-out call fails, its process is killed, and other concurrent calls are unaffected; allow more time for long evaluations. A `MAUDE_LIB` prelude override must match Harold's Maude version (currently 3.5.1), or the interpreter may fail to load it or behave inconsistently; see [`.agents/summary/maude-lib.md`](.agents/summary/maude-lib.md) for how Maude locates the prelude.

## Development

Contributions are welcome! See [`CONTRIBUTING.md`](https://github.com/demiourgoi/harold/blob/main/harold-mcp/CONTRIBUTING.md) for the contribution workflow, and [`DEVELOPER_GUIDE.md`](https://github.com/demiourgoi/harold/blob/main/harold-mcp/DEVELOPER_GUIDE.md) for the development environment and release process.

---

Repository initiated with [osprey-oss/cookiecutter-uv](https://github.com/osprey-oss/cookiecutter-uv).
