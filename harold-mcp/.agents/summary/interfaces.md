# Interfaces

<!-- tags: interfaces, api, entry-points, mcp -->

## External interfaces

### MCP server (stdio)

- **Transport**: stdio (FastMCP default via `mcp.run()`).
- **Server name**: `Harold`, with the packaged logo as icon,
  `website_url="https://demiourgoi.github.io"`, and `instructions` describing the tool
  areas (diagnose, run, RAG over Maude docs).
- **Tools**:
  - `maude_program_diagnostics(path: str) -> MaudeProgramDiagnosticsResult` — diagnoses
    one Maude source file with two providers in a single call: the **Maude interpreter**
    load (worker process) and Harold's **heuristic linter** (server process, pure text).
    Input schema is exactly `{path: str}` (the provider registry is injected via
    `Depends` — `get_diagnostic_providers`, which itself depends on
    `get_maude_executor` — and excluded from the schema).
    - Every diagnostic carries `source` (`"interpreter"` | `"heuristic-linter"`), `code`
      (`"compiler"` for the interpreter; the rule name for linter findings), `severity`
      (`"info"` | `"warning"` | `"error"`), `message`, an LSP-style 1-based `range`
      (`null` for whole-file problems; interpreter findings have `column=null`; heuristic
      findings carry exact exclusive-end columns), and an optional report-only `fix`
      (`description` + applyable `edits`; the tool never writes to the file).
    - Each call is hermetic (a fresh interpreter loads the file; no state carries over),
      and the interpreter checks the whole load: the file plus its `load`/`in`
      dependencies. Problems attributed to a dependency are whole-file diagnostics whose
      message names the dependency and points at this tool; the result `path` is the
      input path **made absolute** (`Path.resolve()`).
    - `success` is `true` only when no diagnostic has severity `warning` or `error`;
      `"info"`-only results (a shadowed prelude sort, non-ASCII punctuation Maude
      accepts) still succeed. `summary` counts all three severities. Diagnostics are
      ordered by file position, with interpreter findings first on a line and whole-file
      problems last.
    - Errors: missing/unreadable input raises `SourceFileNotFoundError`; any provider
      failure raises `DiagnosticCollectionError` (names every failing provider; a worker
      crash/timeout is chained from the interpreter provider) — no partial results are
      returned. Both surface to the client as tool errors (`isError`); the MCP client
      retries, the pool is replaced.
    - Annotated with the full read-only profile — `readOnlyHint=True`,
      `destructiveHint=False`, `idempotentHint=True`, `openWorldHint=False` (the spec
      defaults `destructiveHint` to true, so it must be negated explicitly) — and tagged
      `tags=harold_tags(DIAGNOSTICS)` (`{maude, programming, diagnostics}`; see the tags
      module below). With mcp SDK 1.29 the tags are not serialized to clients — only the
      annotations reach the wire.
    - Only the free-form text above `Args:` becomes the MCP tool description (FastMCP
      excludes `Returns`/`Raises`/`Example` sections — noted in a comment in the code),
      and the result models' attribute docstrings become output-schema field descriptions
      (see `data_models.md`). The hermetic per-call and whole-load/dependency semantics are
      documented in that prose.
  - `maude_run(path: str, module: str, steps: list[MaudeStep], timeout_secs: int | None
    = None) -> MaudeRunResult` — runs a bounded Maude interpreter session. It loads one
    file into a fresh worker (dependencies resolve as usual), selects an explicit
    **module** (case-sensitive; a theory is rejected) and executes an ordered list of
    steps:
    - `reduce` (`term`), `rewrite` (`term`, optional `bound`), `frewrite` (`term`,
      optional `bound`, `gas`), `erewrite` (same; the original term is kept).
    - `match` (`pattern`, optional `subject`, `depth`) and `search` (`pattern`, optional
      `subject`, `depth`, required `search_type` = `one-step` | `at-least-one-step` |
      `any-steps` | `normal-form` | `branch`).
    - The input is a discriminated union on `command`; all fields are optional except
      where required. A step may omit its `term`/`subject` to use the current term: the
      session starts with none (so the first step must provide one), rewriting commands
      replace it, and `match`/`search` leave it unchanged. `bound`/`gas` are `>= 0`;
      `depth` is `-1` (on top without extension, the default), `0` (on top with
      extension) or `2147483647` (anywhere).
    - The result reports the absolute `path`, the requested `module`, load `warnings` and
      captured `load.output`, `completed` (all steps `ok`), and one outcome per executed
      step (`index`, `command`, `status`, `term`, `rewrites`, `matches`/`solutions`,
      `truncated`, `message`, `limit`, `output`). `status` is `ok`, `parse-error` or
      `too-large`; the run stops at the first failure and later steps are not executed.
    - Load warnings do not stop evaluation (use `maude_program_diagnostics` for a full
      diagnosis). Whole-call failures raise `MaudeRunError`: missing/unreadable path, load
      failure, module not defined (the message lists the modules the load defined), a
      theory module, or a worker crash/timeout (the `MaudeWorkerError` is chained).
    - All caps come from settings (step count, rewrite bound, solutions, term/result/
      output length); `timeout_secs` overrides `HAROLD_INTERPRETER_TIMEOUT_SECS`. The
      timeout covers interpreter startup and is best effort (a hung reduction fails the
      call and replaces the pool). Each phase reports captured stdout/stderr with ANSI
      codes stripped; over-long streams are truncated and marked.
    - Annotated with the same full read-only profile and tagged
      `tags=harold_tags(INTERPRETER)` (`{maude, programming, interpreter}`). Only the
      prose above `Args:` becomes the description; field docstrings describe the output
      schema.

```mermaid
sequenceDiagram
    participant C as MCP client
    participant F as FastMCP server
    participant T as diagnostics tool
    participant P as providers
    participant W as Maude worker
    C->>F: tools/call maude_program_diagnostics path
    F->>T: run tool, inject providers via Depends
    T->>T: SourceFile.from_path pre-check and read
    T->>P: collect_diagnostics interpreter + heuristic, in order
    P->>W: interpreter provider: load_diagnostics task
    W->>W: redirect both fds, maude.load, parse stderr warnings
    W-->>P: ok and warnings dict
    P->>P: heuristic provider: mask text, run rule registry
    P-->>T: merged diagnostics, ordered
    T-->>F: MaudeProgramDiagnosticsResult
    F-->>C: structuredContent plus JSON text
```

```mermaid
sequenceDiagram
    participant C as MCP client
    participant F as FastMCP server
    participant T as maude_run tool
    participant E as MaudeExecutor
    participant W as Maude worker session
    C->>F: tools/call maude_run path, module, steps
    F->>T: run tool, inject executor and settings
    T->>T: resolve path, validate caps and current-term threading
    T->>E: run_session SessionRequest, timeout
    E->>W: fresh process, init_maude, load file
    W->>W: capture streams, diff getModules, parse warnings
    W->>W: getModule, run steps until first failure
    W-->>E: SessionResult (load info + outcomes)
    E-->>T: SessionResult
    T->>T: adapt outcomes to MaudeRunResult
    T-->>F: MaudeRunResult
    F-->>C: structuredContent plus JSON text
```

### Console scripts

- **`harold-mcp`** → `harold_mcp.main:app` (declared in `pyproject.toml`
  `[project.scripts]`) — a **cyclopts** CLI. The default command and the `serve`
  subcommand both run the MCP server over stdio; `--help`/`--version` come from cyclopts.
- **`harold-update-prelude-sorts`** → `harold_mcp.heuristic.prelude_extract:app` — the
  maintenance CLI for the bundled prelude sort snapshot:
  `harold-update-prelude-sorts <prelude.maude> [--output PATH] [--check]
  [--maude-version V]`. It prints extraction/exclusion counts, writes the generated
  module (byte-stable), refuses extractions with fewer than 50 sort names, and with
  `--check` compares the **data** against a fresh extraction (exit 1 when stale; the
  provenance header may differ). See `DEVELOPER_GUIDE.md`.
- On startup the lifespan performs a fail-fast worker initialization check (one
  `init_maude` ping per worker; the pinged processes are recycled — no warm pool stays
  around); on SIGTERM the server tears the pool down and exits 0.
- Intended for installation via `uvx harold-mcp` and configuration as an MCP server
  command for clients (the Zed and opencode configurations we test live in `README.md`;
  any other MCP-compatible client works too).

### Configuration (env vars)

| Env var | Default | Meaning |
| --- | --- | --- |
| `HAROLD_MAUDE_WORKERS` | `max(1, min(3, cpu_count // 2))` | bound on concurrently running Maude interpreters (workers are recycled after every call) |
| `HAROLD_DIAGNOSTICS_TIMEOUT_SECS` | `60` | per-call timeout for `maude_program_diagnostics` (renamed from `HAROLD_MAUDE_WORKER_TIMEOUT_SECS`; the startup ping uses it too) |
| `HAROLD_INTERPRETER_TIMEOUT_SECS` | `60` | default per-call timeout for `maude_run` (`timeout_secs` overrides it) |
| `HAROLD_INTERPRETER_MAX_STEPS` | `200` | maximum steps per `maude_run` call |
| `HAROLD_INTERPRETER_MAX_REWRITE_BOUND` | `1000` | maximum accepted `bound` per rewrite step |
| `HAROLD_INTERPRETER_MAX_SOLUTIONS` | `200` | maximum match substitutions / search solutions per step |
| `HAROLD_INTERPRETER_MAX_TERM_LENGTH` | `100000` | maximum characters of a term, pattern or subject |
| `HAROLD_INTERPRETER_MAX_RESULT_LENGTH` | `1000000` | maximum characters of a returned term; longer results become `too-large` outcomes |
| `HAROLD_INTERPRETER_MAX_OUTPUT_LENGTH` | `1000000` | maximum characters per captured stream per phase (longer captures are truncated and marked) |

Invalid values fail fast at import (pydantic validation).

## Internal Python interfaces

- `harold_mcp.server.mcp` / `harold_mcp.server.run` — the shared FastMCP instance and the
  server entry point. Tools register via `@mcp.tool` on the instance imported from
  `harold_mcp.server.server` (never the package `__init__` — cycle-proof).
- `harold_mcp.server.tags` — the shared tool-tag vocabulary:
  - Constants: `MAUDE`/`PROGRAMMING` (domain tags), `DIAGNOSTICS`/`INTERPRETER`/`DOCS`
    (functional categories; `DOCS` awaits its planned tool).
  - `harold_tags(*tags) -> set[str]` — builds a tool's tag set with the domain tags
    automatically added; pass it to `@mcp.tool(tags=...)`.
  - Effect/safety metadata stays in `ToolAnnotations`, not tags.
- `harold_mcp.server.tools.diagnostics.get_diagnostic_providers(
  maude_executor=Depends(get_maude_executor))` — the provider registry in merge/tie-break
  order, injected into the tool via `Depends`; direct callers (tests) pass an executor
  explicitly.
- `harold_mcp.diagnostics` — the provider seam (stdlib-only):
  - `DiagnosticProvider` — the protocol (`name`, `diagnose(source)`); implement it to
    add a new diagnostics source. Providers live with their capability package and raise
    `DiagnosticProviderError` (chaining the cause).
  - Value types: `SourceFile` (`from_path` — the tool's pre-check, path resolution to
    absolute and read; raises `SourceFileNotFoundError`), `ProviderDiagnostic` (source,
    severity, code, message, 1-based `line`/`column`/`end_column`, optional fix),
    `FixEdit`, `FixSuggestion`, `Severity`, `DiagnosticSource`.
  - `collect_diagnostics(providers, source) -> list[ProviderDiagnostic]` — runs every
    provider in order, merges and orders the result, and raises
    `DiagnosticCollectionError` (with `.failures`) when any provider failed.
- `harold_mcp.heuristic` — the linter:
  - `HeuristicLinterProvider(rules=RULES)` — a `DiagnosticProvider` over the rule
    registry.
  - `RULES` — the ordered `Rule` registry (`code`, `severity`, `detect`); add a rule here
    to extend the linter. `RuleFinding` / `Rule` are the rule-authoring types.
  - `SourceView.from_text(text)` — the masked code view rules run over; `CodeLine`,
    `Declarations`, `declaration_index`, `is_identifier_char` (lexical layer).
  - `iter_sort_declarations(lines)` + `SortDeclaration` — the shared sort-declaration
    reader (rule 7 and the snapshot extractor).
  - `PRELUDE_SORTS` / `PRELUDE_SORT_BASES` — the generated snapshot data.
  - `extract_prelude_sorts` / `render_snapshot_module` — the snapshot maintenance API
    behind the CLI.
- `harold_mcp.settings.Settings` / `get_settings()` — configuration model and singleton
  (workers, both timeouts, and the interpreter caps).
- `harold_mcp.maude.MaudeExecutor` — the client wrapper (one task per process:
  `max_tasks_per_child=1`, so every call gets a fresh interpreter):
  - `start()` / `shutdown()` — pool lifecycle (start runs the fail-fast init pings).
  - `submit(fn, *args) -> Future` — raw submit (test/crash support); raises
    `MaudeWorkerCrashedError` on a broken pool.
  - `diagnostics(path) -> LoadDiagnosticsResult` — typed worker op; crash/timeout mapped
    to `MaudeWorkerCrashedError` / `MaudeWorkerTimeoutError`, pool replaced.
  - `run_session(request, timeout) -> SessionResult` — typed worker op for `maude_run`;
    same crash/timeout mapping.
  - `_run_task(fn, *args, timeout) -> T` — generic submit-and-await runner for worker ops.
- `harold_mcp.maude.capture` — worker-side capture helpers: `capture_streams`,
  `parse_warnings`, `strip_ansi`, `truncate_output`, `WarningDict`, `CapturedOutput`.
- `harold_mcp.maude.session` — the bounded session engine and protocol: `run_session`,
  `CommandName`, `StepStatus`, `StepRequest`, `SessionRequest`, `BindingDict`,
  `SolutionDict`, `StepOutcomeDict`, `SessionResult`.
- `harold_mcp.server.tools.interpreter` — `maude_run`, `MaudeRunError`, the step input
  models (`ReduceStep`, `RewriteStep`, `FrewriteStep`, `ErewriteStep`, `MatchStep`,
  `SearchStep`) and the result models (`MaudeRunResult`, `MaudeLoadInfo`,
  `MaudeLoadWarning`, `MaudeCapturedOutput`, `MaudeStepOutcome`, `MaudeMatch`,
  `MaudeSearchSolution`, `MaudeBinding`).
- `harold_mcp.maude.InterpreterDiagnosticProvider(executor)` — the interpreter provider
  (warning mapping + synthesized whole-file error; own-file/`<standard input>` warnings
  keep their line, foreign-file warnings become whole-file dependency diagnostics naming
  the file and suggesting this tool; worker errors become `DiagnosticProviderError` with
  the cause chained).
- `harold_mcp.maude.get_maude_executor(settings=Depends(get_settings))` — lazy,
  lock-guarded singleton; FastMCP resolves the nested `get_settings` dependency. Direct
  callers pass settings explicitly.
- `harold_mcp.maude.worker` — worker-side module (imported by the worker process only in
  practice; safe to import anywhere): `init_maude`, `ping`, `sleep`, `rendezvous_pid`,
  `load_diagnostics`, `_crash`, and the `WarningDict` / `LoadDiagnosticsResult` TypedDicts
  (`WarningDict` lives in `maude/capture.py` and carries the `file` Maude attributed the
  warning to).
- `harold_mcp.maude` error hierarchy — `MaudeError`, `MaudeInitError`,
  `MaudeWorkerError` (`MaudeWorkerCrashedError`, `MaudeWorkerTimeoutError`).
- `harold_mcp.resources.HAROLD_ICON` — `mcp.types.Icon` used for server branding.
- `harold_mcp.logging.get_logger` / `harold_mcp.logging.Logging` — logging helpers.

## Import-time side effects

Importing `harold_mcp.server`:

1. Builds the global `mcp` server instance (in `harold_mcp.server.server`).
2. Registers both tools (via `server/__init__.py` → `tools/__init__.py` → `diagnostics.py`
   and `interpreter.py`; the former also imports the heuristic registry and the prelude
   snapshot data).
3. Reads the `HAROLD_*` env vars once (pydantic-settings `Settings`).

The Maude interpreter is **not** touched at import time: no `maude` import in the server
process (worker.py imports it lazily), and the worker pool is created in the lifespan
(startup), not at import — and each task then runs in its own fresh process
(`max_tasks_per_child=1`). The heuristic linter and the prelude snapshot are pure data and
text processing — importing them never touches the interpreter.

## Related documents

- `components.md` — module responsibilities
- `workflows.md` — end-to-end flows
- `data_models.md` — the types these interfaces use
