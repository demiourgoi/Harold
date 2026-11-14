# Components

<!-- tags: components, modules, responsibilities -->

## `src/harold_mcp/` (the package)

### `harold_mcp.main`

- **Responsibility**: CLI/stdio entry point for the MCP server and the bundled-skill
  installer, built with **cyclopts**.
- `app = App(name="harold-mcp", help=...)` with a `serve` subcommand; both the app default
  and the `serve` default run `run()`, which delegates to `harold_mcp.server.run`. cyclopts
  provides `--help`/`--version`.
- `setup` subcommand — installs the bundled `maude-manual` skill via
  `skill_install.install_skill`: `--directory` defaults to `./.agents/skills`, `-g`/`--global`
  selects `~/.agents/skills` (the directory option is ignored), and it prints the installed
  path plus the `harold-mcp` package version from `importlib.metadata`. Errors propagate as
  normal CLI exceptions (cyclopts prints and exits non-zero).
- Exposed as the `harold-mcp` console script (`harold_mcp.main:app`). The
  `if __name__ == "__main__"` guard is required: the `spawn`-context worker re-imports the
  main module.

### `harold_mcp.skill_install`

- **Responsibility**: install the bundled `maude-manual` agent skill. Stdlib-only
  (`importlib.resources`, `pathlib`, `shutil`); never imports FastMCP or `maude`.
- `SKILL_NAME = "maude-manual"`; `skill_source() -> Path` locates
  `harold_mcp/skills/maude-manual` through `importlib.resources.files("harold_mcp")`.
- `install_skill(destination_base, source=None) -> Path` — copies the skill tree to
  `destination_base / SKILL_NAME` and returns it. It fails with a `FileNotFoundError`
  naming the expected path and `make skills` when the artifact was built without the
  copy; otherwise it creates the base directory, removes an existing destination first
  (`shutil.rmtree` for a directory, `Path.unlink` for a stray file), then `copytree`s.
  Removing first makes a re-run a full refresh (files dropped from a newer skill never
  survive) and leaves every sibling in the base directory untouched.
- The skill content is not committed: `make skills` copies the monorepo's
  `skills/maude-manual` into `src/harold_mcp/skills/` (git-ignored), and hatchling
  `artifacts` re-includes it in the wheel and sdist. `source=` exists for tests.

### `harold_mcp.settings`

- **Responsibility**: application configuration, read once from `HAROLD_*` env vars.
- `Settings(BaseSettings)` — flat model: `maude_workers` (default via
  `_default_maude_workers()` → `max(1, min(3, (os.cpu_count() or 0) // 2))` — half the
  logical CPUs, capped at 3; validated with `gt=0`), `diagnostics_timeout_secs` (default
  60; renamed from `maude_worker_timeout_secs`), `interpreter_timeout_secs` (default 60),
  the interpreter caps `interpreter_max_steps` (200), `interpreter_max_rewrite_bound`
  (1000), `interpreter_max_solutions` (200), `interpreter_max_term_length` (100000),
  `interpreter_max_result_length` (1000000), `interpreter_max_path_steps` (100) and
  `interpreter_max_output_length` (1000000), `error_detail_max_chars` (4000; capped
  client error text) and `ipc_max_response_bytes` (2 GiB; worker-response read cap).
  All are `gt=0`. Workers are transient (one fresh process per call), so `maude_workers`
  caps concurrent per-call interpreters (≈100 MB each), not warm workers. Invalid values
  fail at import.
- `settings` — module-level singleton; `get_settings() -> Settings` returns it (FastMCP
  dependency factory). Env vars are documented in `README.md`.

### `harold_mcp.errors`

- **Responsibility**: the stdlib-only, shared error formatter. It never reads env vars,
  files or unrelated process state.
- `format_error_report(exc, *, context, max_chars, category=None, message=None)` — renders
  `<category>: <message>` (or `<Type>: <message>`), a merged `context:` line (the
  exception's own context first, caller keys winning, `None` values skipped), a
  cycle-guarded `cause: Type: message <- ...` chain (plus the remote cause for a remote
  error), the originating traceback (the first remote one in the chain, else the local
  one) and, when the cap shortens the text, `TRUNCATION_MARKER`. Truncation order:
  traceback, then the cause line, then the first line's message (its prefix kept).
  `max_chars <= 0` is unbounded (server-log rendering).
- `format_context`, `format_exception_text` — helpers reused by the tools and the
  diagnostics aggregation; `DEFAULT_ERROR_DETAIL_MAX_CHARS` (4000) is shared with
  `Settings.error_detail_max_chars`.

### `harold_mcp.server` (package)

- **`__init__.py`** — re-exports `mcp` and `run` from `server.server`, and imports
  `harold_mcp.server.tools` (tool registration as a package side effect).
- **`server.py`** — the FastMCP instance and its lifecycle:
  - `mcp = FastMCP(name="Harold", instructions=..., website_url=..., icons=[HAROLD_ICON], lifespan=app_lifespan)`.
  - `app_lifespan` — `@lifespan`-decorated async generator: `get_maude_executor(
    get_settings()).start()` (fail-fast init check), teardown in `finally`.
  - `run()` — registers a SIGTERM handler that raises `KeyboardInterrupt`, calls
    `mcp.run()`, and on `KeyboardInterrupt` logs and calls `os._exit(0)` (see
    `architecture.md` §5 for why).
  - `_handle_shutdown_signal` — the SIGTERM→`KeyboardInterrupt` bridge.
- **`tools/__init__.py`** — re-exports both tools (`maude_program_diagnostics`,
  `maude_run`) so importing the package registers them.
- **`tags.py`** — the shared tool-tag vocabulary (see `interfaces.md`): constants
  `MAUDE`/`PROGRAMMING` (domain), `DIAGNOSTICS`/`INTERPRETER`/`DOCS` (functional
  categories; `DOCS` reserved for the planned RAG tool), and `harold_tags(*tags)`,
  which always adds the domain tags. Effect/safety metadata is deliberately not a tag
  (it belongs in `ToolAnnotations`). With mcp SDK 1.29 tags are server-side only:
  they drive `mcp.enable`/`mcp.disable` and are not serialized to clients.
- **`tools/diagnostics.py`** — the MCP surface of `maude_program_diagnostics` and the
  adapter from the provider seam to the wire models:
  - Wire models (see `data_models.md`): `MaudePosition`, `MaudeRange`, `MaudeTextEdit`,
    `MaudeFix`, `MaudeDiagnostic` (with `source`, `code`, `fix`), `MaudeDiagnosticsSummary`
    (with `info`), `MaudeProgramDiagnosticsResult`.
  - `get_diagnostic_providers(maude_executor=Depends(get_maude_executor))` — the
    module-level FastMCP dependency returning the provider registry
    `(InterpreterDiagnosticProvider(executor), HeuristicLinterProvider())`; the tool
    receives it via `Depends` (dependency parameters are excluded from the MCP schema).
    Direct callers (tests) pass an executor explicitly; the registry order is the
    merge/tie-break order.
  - Tool flow: `SourceFile.from_path(path)` (pre-check: rejects missing/non-regular
    files with `SourceFileNotFoundError`, resolves the path to absolute, reads the text
    once) → `collect_diagnostics(providers, source)` → adapter to the wire models.
    `success` is `all(severity == "info")`; `summary` counts all three severities; `range`
    is `None` for whole-file problems; fix edits map to wire ranges with an exclusive
    `end`. The result reports `str(source.path)` — the resolved absolute path — not the
    raw input.
  - Registered with the full read-only annotation profile (`readOnlyHint=True`,
    `destructiveHint=False`, `idempotentHint=True`, `openWorldHint=False`) and
    `tags=harold_tags(DIAGNOSTICS)`. The models inherit the private `_ResultModel` base
    (`ConfigDict(use_attribute_docstrings=True)`), so their attribute docstrings reach
    clients as output-schema field descriptions (see `data_models.md`); a code comment next
    to the tool records that only the text above `Args:` becomes the MCP description.
  - The docstring describes both sources, their severity meanings, the `fix` payload, the
    ordering, the hermetic per-call semantics (fresh interpreter; no state carries over)
    and the whole-load/dependency behavior (dependency problems are whole-file diagnostics
    naming the dependency and pointing at this tool).
- **`tools/interpreter.py`** — the MCP surface of `maude_run` and the adapter from the
  worker session protocol to the wire models:
  - Input models: a discriminated union (`MaudeStep`) over `ReduceStep`, `RewriteStep`,
    `FrewriteStep`, `ErewriteStep`, `MatchStep`, `SearchStep`, sharing `_StepBase`
    (`term`), `_BoundedStep` (`bound`), `_GassedStep` (`gas`) and `_PatternStep`
    (`pattern`, `subject`, `depth`). `bound`/`gas` are `>= 0`; `depth` is constrained to
    Maude's int32 range (`-1` … `2147483647`). `SearchStep` adds the required
    `search_type` and `path: Literal["none", "labels", "full"] = "labels"`.
  - Result models: `MaudeRunResult`, `MaudeLoadInfo`, `MaudeLoadWarning`,
    `MaudeCapturedOutput`, `MaudeStepOutcome`, `MaudeMatch`, `MaudeSearchSolution`,
    `MaudeSearchPath`, `MaudePathTransition`, `MaudeRuleRef`, `MaudeBinding` (all under
    `_ResultModel`, with field docstrings). A search solution's `path` is `None` only
    when the step requested `path="none"`; otherwise it carries the initial state and
    the ordered transitions.
  - `MaudeRunError` — whole-call failure (missing/unreadable path, load failure,
    undefined module, theory module, worker crash/timeout), chaining the worker cause.
  - Tool flow: `_resolve_path` (expanduser + `resolve`, require a regular file) →
    `_validate_steps` (non-empty, step count, term/pattern/subject length, rewrite-bound
    cap, current-term threading) → `_to_request` (flat `SessionRequest` carrying the caps,
    including `max_path_steps`, and every step's `path_mode`) →
    `executor.run_session(request, timeout)` → `_to_wire_result` (rejects `load_ok=False`,
    `module_found=False` and theory module types; adapts load warnings/output and the
    executed step outcomes, including `PathDict` → `MaudeSearchPath`). `timeout_secs`
    overrides the interpreter setting.
  - Whole-call failures: a `MaudeWorkerError` or an unexpected non-worker exception
    becomes a `MaudeRunError` whose text comes from
    `harold_mcp.errors.format_error_report` (a stable category, the merged context, the
    cause chain and the originating traceback), capped at `error_detail_max_chars`; the
    tool logs the uncapped report via its module logger. Input-validation failures keep
    their specific message plus the same context line (`format_context`). The resolved
    path and module are in the context because MCP clients see only the error text;
    this makes non-deterministic worker failures diagnosable.
  - Registered with the same read-only annotation profile and
    `tags=harold_tags(INTERPRETER)`. The description documents commands, threading, search
    paths, load warnings, per-step failure semantics, output limits and the timeout
    behavior.

### `harold_mcp.diagnostics` (package)

The provider-agnostic seam. Stdlib-only; imports no interpreter, no FastMCP, no wire
models, so every capability package can depend on it independently.

- **`__init__.py`** — re-exports the whole public surface (protocol, value types, errors,
  aggregator).
- **`provider.py`** — the contract and value types:
  - `Severity = Literal["info", "warning", "error"]` and
    `DiagnosticSource = Literal["interpreter", "heuristic-linter"]` (the closed set of
    provider names; tool code and the wire model share these aliases).
  - Frozen slotted dataclasses: `SourceFile` (`path` + `text`; `from_path` classmethod
    rejects anything that is not a regular file, then stores `Path.resolve()` — `path` is
    always absolute, so the worker can load it from any cwd — and reads with
    `utf-8`/`errors="replace"`), `FixEdit` (`line`, `start_column`, exclusive
    `end_column`, `new_text`), `FixSuggestion` (`description` + `edits` tuple),
    `ProviderDiagnostic` (`source`, `severity`, `code`, `message`, optional 1-based
    `line`/`column`/`end_column`, optional `fix`; `__post_init__` rejects columns without
    a line, an `end_column` without a column, and non-positive positions).
  - `DiagnosticProvider` — `Protocol` with a `name` property and
    `diagnose(source) -> list[ProviderDiagnostic]`; implementations wrap their failures
    in `DiagnosticProviderError`.
  - Error vocabulary: `DiagnosticsError(RuntimeError)` base, `SourceFileNotFoundError`
    (the diagnostics tool's input error; `.path`), `DiagnosticProviderError` (`source`,
    `reason`).
- **`aggregate.py`** — running providers and merging findings:
  - `ProviderFailure` (`provider`, `error`) and `DiagnosticCollectionError` (`.failures`
    tuple; message names every failing provider and its reason — an unexpected provider
    bug keeps its exception type). The error chains the first failure as `__cause__`.
  - `collect_diagnostics(providers, source)`: runs every provider **in order**, never
    short-circuits after a failure (so all failures are named), discards successful
    providers' findings when any provider failed (no partial results, MCP cannot express
    "error + content"), then sorts the merged list with the module-level `_order` key
    (bound per call via `functools.partial`) by (whole-file last, line, provider registry
    order, column).

### `harold_mcp.heuristic` (package)

Harold's heuristic linter for Maude programs: report-only pattern checks that run in the
MCP server process, pure text in and diagnostics out. It never imports the `maude`
bindings and never depends on the worker; it complements the interpreter rather than
replacing it (findings are heuristics and may be false positives).

- **`__init__.py`** — re-exports `HeuristicLinterProvider`.
- **`provider.py`** — `HeuristicLinterProvider` (`name = "heuristic-linter"`):
  `diagnose` builds a `SourceView` from `source.text`, runs the rule registry (default
  `RULES`, overridable for tests/future tools) and stamps each finding with the rule's
  `code`/`severity`. Unlike the interpreter provider it does **not** wrap failures: a
  rule bug is already a diagnostics-subsystem failure, reported by the aggregator's
  safety net.
- **`lexical.py`** — the shared lexical layer of the rules:
  - `is_identifier_char` — Maude identifier material (alphanumerics, `_ ' - ? $`, bytes
    ≥ 0x80), used for token-boundary tests.
  - `CodeLine` (`number`, `code`) and `code_view(text)`: one masked line per physical
    line, **length-preserving**, so a character's index equals its 1-based column.
    Masked to spaces: `***`/`---` comments, string literals (cannot span lines; an
    unterminated literal blanks the rest of the line), quoted identifiers (run to the
    next whitespace; a `'` after identifier material belongs to the identifier, e.g.
    `A'`), and `[label]` slots right after `eq`/`ceq`/`rl`/`crl`.
  - `Declarations` + `declaration_index(lines)`: file-wide `var`/`vars` names, inline
    `X:Sort` annotations, `op`/`ops` identifiers, and base names used after `:` (sort
    references) — what rules 5–6 need.
  - `SourceView` (`lines`, `sort_declarations`, `declarations`; `from_text`, `sort_bases`
    — declared sort names without parameters).
- **`declarations.py`** — the single implementation of "what is a sort declaration",
  shared by the `prelude-sort-redeclared` rule, rule 6's allow-list and the snapshot
  extractor (so they can never disagree):
  - `SortDeclaration` (`name` as written incl. parameters, `line`, `column`, `module`).
  - `iter_sort_declarations(lines, excluded=None)`: tracks module context
    (`fmod`/`fth`/`mod`/`smod`/`th`/`view`; a module opened and closed on one line opens
    nothing), handles `sorts A B .` statements spanning continuation lines, and excludes
    declarations outside a module, view bodies, theory bodies (`fth`/`th` — user modules
    are expected to redeclare theory interface sorts), renaming mappings (statements
    containing `to`), the `none` placeholder, and tokens that are not sort-shaped.
    `excluded` accumulates per-reason drop counts for the CLI's report.
- **`rules.py`** — the check registry:
  - `RuleFinding` (message + span + optional fix), `Rule` (`code`, `severity`, `detect`),
    and `RULES` — the ordered registry (order = evaluation order and the position
    tie-break).
  - Seven rules: `non-ascii-character` (`info`; one finding per non-ASCII character in
    code, with a 1-character fix for the ported typographic-punctuation table, skipping
    U+FFFD from lossy decoding), `when-guard` (`warning`), `dash-comment` (`warning`),
    `eq-in-term` (`warning`), `non-linear-pattern` (`warning`), `undeclared-identifier`
    (`warning`), `prelude-sort-redeclared` (`info`).
  - Hardening: rules 2–3 skip declaration lines (`op when : Bool -> Bool .` is legal);
    rule 4 only inspects `if … then` spans and its lone-`=` regex excludes `==`, `=/=`,
    `<=`, `>=`, `/\`, `\/`; rule 5 counts only declared variables in an `eq`/`ceq`
    left-hand side; rule 6 allow-lists declared variables/operators/sort references,
    declared sort bases, the prelude sort bases, and the ported lowercased
    `MAUDE_KEYWORDS` list (so `True`/`False` stay silenced); rule 7 matches both plain
    and parameterized declarations against the snapshot.
  - Messages are model-facing English explanations that say how to write the construct in
    Maude; rule 1's fixes come from `UNICODE_FIXES` (ported verbatim).
- **`prelude_sorts.py`** — the **generated** snapshot module (do not hand-edit):
  `PRELUDE_SORTS` maps the 164 sort names the Maude 3.5.1 prelude declares to their
  declaring module (theory sorts excluded), and `PRELUDE_SORT_BASES` is the same set
  without parameters (`List{X}` → `List`). The header records the generator, Maude
  version, source path, SHA-256 and extraction date.
- **`prelude_extract.py`** — extractor, renderer and the `harold-update-prelude-sorts`
  CLI (the only module importing cyclopts for the linter; neither the provider nor the
  rules depend on the CLI):
  - `extract_prelude_sorts` / `extract_prelude_sort_bases` reuse
    `iter_sort_declarations` (first declaring module wins).
  - `render_snapshot_module` renders byte-stable sorted output (ASCII, trailing commas);
    `SNAPSHOT_PATH` defaults the CLI's `--output`; `MINIMUM_SORT_NAMES = 50` refuses a
    snapshot from a non-prelude file.
  - CLI: `harold-update-prelude-sorts <prelude.maude> [--output PATH] [--check]
    [--maude-version V]`; prints extraction/exclusion counts; `--check` compares the
    **data** (not the header) against a fresh extraction and exits non-zero when stale.

### `harold_mcp.maude` (package)

- **`__init__.py`** — re-exports the public API: error hierarchy, `MaudeExecutor`,
  `get_maude_executor`, `InterpreterDiagnosticProvider`, and the capture/session protocol
  types (`CapturedOutput`, `WarningDict`, `BindingDict`, `CommandName`, `SessionRequest`,
  `SessionResult`, `SolutionDict`, `StepOutcomeDict`, `StepRequest`, `StepStatus`,
  `PathRuleDict`, `PathTransitionDict`, `PathDict`).
  Importing the package never imports the SWIG `maude` bindings.
- **`capture.py`** — the shared worker-side stream capture (stdlib only):
  - `capture_streams(fn)` redirects fd 1 and fd 2 to temp files (not pipes: no
    pipe-buffer blocking, worker is single-threaded), restores them in `finally`, and
    returns `(result, {"stdout", "stderr"})` with ANSI CSI sequences stripped and lossy
    UTF-8 decoding. Nothing may log/print while both fds are redirected.
  - `_flush_stdio()` flushes Python's `sys.stdout`/`sys.stderr` and the C/C++ stdio buffer
    (`ctypes.CDLL(None).fflush(NULL)`), suppressing every failure. `capture_streams` calls
    it before the redirect (so pre-existing buffered bytes do not enter the capture) and
    in the `finally` before restoring the fds, while the capture files are still fd 1/2.
    This recovers output libmaude buffers independently — a bounded `search` ending a load
    does not print its terminator or flush itself — so the tail stays in the result and
    cannot leak to a later phase or the MCP stdio transport.
  - `parse_warnings(text)` parses `Warning:` lines (quoted or `<standard input>` file,
    line, optional `(fmod X)` context, both colon spellings) into `WarningDict`s;
    `strip_ansi` and `truncate_output` (appends `TRUNCATION_MARKER`) complete the helper.
- **`worker_errors.py`** — the stdlib-only error vocabulary: `MaudeError(RuntimeError)`
  base; `MaudeWorkerError(reason, *, context, remote_traceback)` with the `category`
  class attribute and `MaudeInitError` / `MaudeWorkerCrashedError` /
  `MaudeWorkerTimeoutError` / `MaudeWorkerSpawnError` / `MaudeWorkerRemoteError` /
  `MaudeWorkerCancelledError` / `MaudeWorkerProtocolError` subclasses. The hierarchy is
  re-exported by `harold_mcp.maude`; the old `MaudeFileNotFoundError` was removed.
- **`executor.py`** — the client-side access layer:
  - `MaudeExecutor(Logging)` — owns a `ProcessRunner` factory, a
    `BoundedSemaphore(maude_workers)` and a closed event. `_run_operation` computes a
    deadline, acquires a slot with the remaining budget (no slot → a timeout naming the
    interpreter slot), checks the closed flag, creates the runner lazily, calls
    `runner.run`, and releases in `finally`; a crash observed while closed (and a stray
    `CancelledError`) becomes `MaudeWorkerCancelledError`. `start(timeout)` builds a
    fresh runner, clears the closed flag, runs `maude_workers` `ping`s in parallel under
    one deadline and raises `MaudeInitError` (chaining the first failure) after killing
    and discarding the runner; `shutdown()` sets the flag and calls `runner.kill_all()`
    (idempotent). `diagnostics(path)` and `run_session(request, timeout)` are the typed
    operations. There is no `submit()` and no pool.
  - `get_maude_executor(settings: Settings = Depends(get_settings)) -> MaudeExecutor` —
    process-wide singleton, created lazily under a lock (nested FastMCP dependency).
- **`runner.py`** — the parent-side process runner: the `ProcessRunner` protocol and
  `PipeProcessRunner(settings, *, target=serve_one, context=None)`. One `spawn` process
  per call with a one-shot `multiprocessing.Pipe`; registration and the closed check
  share a lock, `send_bytes` failures / EOF / mid-message errors map to crash, the
  deadline to timeout, `recv_bytes(maxlength=ipc_max_response_bytes)` oversize to a
  protocol error naming the setting, and envelopes map by `error.category` to the typed
  exceptions. `_reap` closes the pipe and kills/joins the child under a termination lock;
  `kill_all()` sets the closed flag and reaps every active child; `active_count()` exists
  for tests.
- **`transport.py`** — the child entry point `serve_one(conn)`: redirects fds 0/1/2 to
  `/dev/null` (exit 1 without output on failure), reads and validates one JSON request
  (`ping`/`diagnostics`/`session`), always calls `worker.init_maude()` first, dispatches
  with lazy imports, and sends one ok/error envelope. Error categories are `protocol`,
  `init` and `remote`; `_worker_context` carries the session phase annotation. No
  protocol version field (the child is one-shot and from the same package).
- **`session.py`** — the worker-side bounded interpreter session engine (the server
  imports its request/result types and the transport calls it in the child; `maude` is
  lazily imported inside `run_session`). Unexpected exceptions carry a `worker_context`
  annotation (load phase, or step index/command) for the error envelope.
  - Protocol TypedDicts: `StepRequest` (every command field present, `None` when not
    applicable, including `path_mode`), `SessionRequest` (path, module, steps, caps
    including `max_path_steps`), `BindingDict`, `PathRuleDict`, `PathTransitionDict`,
    `PathDict`, `SolutionDict` (now with `path`), `StepOutcomeDict` (per-step failures are
    data), `SessionResult` (load outcome, module lookup/type, defined modules, warnings,
    load output, outcomes). Aliases `CommandName`, `RewritingCommand`, `MatchingCommand`
    and `StepStatus`.
  - `run_session` captures the load (both fds), diffs `maude.getModules()` to report the
    modules the load defined, parses warnings from the full stderr before truncation,
    looks up the module, and runs steps until the first non-`ok` outcome.
  - Rewriting commands parse the term and run `reduce`/`rewrite(bound)`/
    `frewrite(bound, gas)`/`erewrite(bound, gas)` (omitted bounds become the bindings'
    `-1`), report the interpreter rewrite counter and `str(term)`, and mark
    `parse-error`/`too-large` with a message naming the exceeded setting. `match`/`search`
    parse subject and pattern, use the search-type constants (spelled out to avoid
    importing `maude`), iterate lazily (at most `max_solutions`, plus one item only to set
    `truncated`), and enforce `max_result_length` on every serialized term/binding.
  - Search paths: when `path_mode` is `"labels"` or `"full"`, `_collect_solutions` reads
    the solution's state number from `iterator.getStateNr()` while the iterator is
    positioned, then `_reconstruct_path` walks `getStateParent()` iteratively (never the
    recursive `pathTo`), stops at `max_path_steps`, and calls `getRule()` only for states
    with a parent (`getRule(0)` crashes the interpreter). `"full"` also serializes rule
    text and intermediate states; every string is checked against `max_result_length`.
    Over-cap paths/elements produce a named `too-large` outcome.
  - Current-term threading happens here: rewriting outcomes carry the new term;
    match/search outcomes leave it unchanged (`term=None`).
- **`provider.py`** — `InterpreterDiagnosticProvider` (v1 behavior behind the seam):
  runs `executor.diagnostics(str(source.path))`, maps each `Warning:` to a `warning`
  diagnostic and appends one synthesized whole-file `error` when the load failed
  (`ok=False`); every diagnostic carries `source="interpreter"` and `code="compiler"`.
  Attribution rule (`_to_diagnostic`): warnings Maude attributed to the diagnosed file or
  to `<standard input>` (some first-line warnings) keep their line; warnings for another
  file (a `load`/`in` dependency) become **whole-file** diagnostics (`line=None`) whose
  message names the dependency and suggests running `maude_program_diagnostics` on it
  (`_dependency_message`; a missing final punctuation is completed). A `MaudeWorkerError`
  (any category: timeout, crash, spawn, init, remote, cancelled or protocol) becomes a
  `DiagnosticProviderError` with the original error as `__cause__`, the resolved path and
  `phase="load"` in the context, and the worker error's own context merged in.
- **`worker.py`** — the interpreter side, imported by the spawned child (safe to import in
  the server: `maude` is imported **lazily inside functions**; the absolute `import maude`
  is the third-party package, not this one):
  - `init_maude()` — idempotent; `maude.init(loadPrelude=True, advise=False)` then
    disables Maude IO (`setAllowDir/File/Processes(False)`); raises `WorkerInitError`.
  - `load_diagnostics(path) -> LoadDiagnosticsResult` — `capture_streams` around
    `maude.load`; parses warnings from stderr only (stdout is discarded, keeping embedded
    `red` output away from the MCP transport). `WarningDict` lives in `maude/capture.py`.

### `harold_mcp.resources`

- **Responsibility**: packaging of static brand assets. `HAROLD_ICON` — an `mcp.types.Icon`
  built from `assets/brand/Harold_logo.png`, passed to the `FastMCP` constructor.

### `harold_mcp.logging`

- **Responsibility**: logging utilities. Re-exports `get_logger` from
  `fastmcp.utilities.logging` and defines `Logging`, a base class exposing a `_log`
  property (logger named after the concrete class). `MaudeExecutor` uses the mixin.

## Tests

- `tests/unit/` (hermetic, mocked):
  - `test_settings.py` — the default formula (`max(1, min(3, cpu_count // 2))`,
    monkeypatched `cpu_count` matrix incl. `None`), env overrides (including
    `interpreter_max_path_steps`, `error_detail_max_chars` and `ipc_max_response_bytes`),
    case-insensitivity, invalid values, singleton.
  - `test_errors.py` — the shared formatter: first-line category/type shapes, context
    merge precedence, the cycle-guarded cause chain (including the remote cause), stored
    exceptions (no `NoneType: None`), traceback selection, truncation order/marker, the
    huge-first-line last resort, `max_chars <= 0`, no secrets, and the worker-error
    hierarchy/categories.
  - `test_tags.py` — the shared vocabulary: `harold_tags` always adds the domain tags,
    and the tag strings are pinned (they are part of the client-visible interface).
  - `test_maude_worker.py` — `init_maude` sequence (success/failure, IO lockdown,
    idempotency) and `load_diagnostics` (stderr-only parsing, stdout discarded, load
    result forwarded) with the `maude` bindings faked via `sys.modules`.
  - `test_maude_capture.py` — the shared capture helper: fd 1/2 separation, return value,
    restoration on success and exception, ANSI stripping, lossy decoding, truncation
    marker, the C-buffer flush (buffered output captured, not leaked to the restored
    stdout, and failing Python/libc flushes suppressed), and the warning parser
    (quoted/`<standard input>`/`(fmod X) :` formats, order, unmatched/advisory lines).
  - `test_maude_executor.py` — a fake `ProcessRunner`: delegation/context, lazy runner
    creation, admission timeout and serialization, the post-admission budget check, every
    runner error category, stray `CancelledError`, crash-while-closed → cancelled,
    shutdown cancellation, `start()` pings/failure/discard/restart, shutdown idempotence,
    singleton.
  - `test_maude_runner.py` — the process runner with a fake context: success and request
    envelope, response cap, EOF/mid-message/other `OSError` → crash, deadline → timeout,
    oversized response naming the setting, send/spawn/pipe failures, the shutdown
    registration race, the terminate-lock pipe-close serialization, envelope mapping
    (init/remote/protocol/unknown/invalid), and active-map cleanup on every error path.
  - `test_maude_transport.py` — the child transport: ok/error envelopes (no version
    field), protocol validation (non-object JSON, operation/payload/path), dispatch
    (init first, unknown operation), remote/init categorization, phase-context forwarding,
    first-recv EOF/OSError as a closed peer, redirect-failure exit without output, and
    the stored-exception traceback helper.
  - `test_maude_provider.py` — `InterpreterDiagnosticProvider`: warning/error mapping,
    `source`/`code` stamping, own-file and `<standard input>` attribution, foreign-file
    warnings becoming whole-file dependency diagnostics, and worker errors becoming
    `DiagnosticProviderError` with the cause chained.
  - `test_diagnostics_seam.py` — seam contracts: errors are not `MaudeError`s, message
    formatting, position invariants, frozen fix values, and `SourceFile.from_path`
    (regular file, string paths, relative-path resolution to absolute, missing/directory/
    non-regular/unreadable rejection, lossy decoding, newline normalization).
  - `test_diagnostics_aggregate.py` — merge provenance and ordering (file order, provider
    tie-break, whole-file last), every provider receives the source, no-diagnostics
    success, one failing provider → `DiagnosticCollectionError` without partial results
    (the successful provider's findings never leak into the error), remaining providers
    still attempted with both cause chains present, unexpected bugs reported with their
    type, and the capped/uncapped report rendering.
  - `test_interpreter_tool.py` — `maude_run` validation and adaptation: description (no
    worker-pool wording), path pre-check, empty/too-many steps, term/pattern/subject
    length caps, rewrite-bound cap, first-step threading, omitted terms later,
    `bound`/`gas`/`depth`/`search_type`/`path` forwarding, timeout override, request caps
    (including `max_path_steps`), every outcome shape (rewriting, match, search
    with/without a path, parse-error, too-large with a named limit), whole-call errors
    (load failure, missing module with defined-module list, theory module, all seven
    worker categories with rich capped text, input-error context lines, worker/unexpected
    exception chaining, the unexpected case asserting the full log vs capped client
    text).
  - `test_maude_session.py` — the session engine's path reconstruction with fake search
    iterators: path assembly in labels/full modes, state-number capture while the
    iterator is positioned, zero-transition paths, unlabeled rules, per-solution
    laziness, path and element cap overflow, and the named `too-large` reasons; invalid
    `path_mode` contract handling; and the load/step `worker_context` phase annotations.
  - `test_diagnostics.py` — the tool with the real provider registry wired to a fake
    executor (`_providers` helper): warning/error mapping and the
    synthesized whole-file error, `info`-only success, summary counts, whole-file ranges,
    adapter mapping of columns and fixes, pre-check before any provider,
    `DiagnosticCollectionError` propagation, the capped client text vs the full log, and
    interpreter-before-heuristic ordering on a line.
  - `test_heuristic_lexical.py` — masking per region (comments, string literals incl.
    `***`/`--` inside them, quoted identifiers, labels), length/column fidelity,
    `declaration_index`, `SourceView`.
  - `test_heuristic_declarations.py` — `iter_sort_declarations`: multi-line statements,
    parameterized module headers, one-line views, view/renaming/theory/meta-term
    exclusions, `?`-suffixed names, comments.
  - `test_heuristic_rules.py` — one positive test per rule (code, severity, span,
    message, fix) plus the hardening negatives (strings, quoted identifiers,
    declarations, labels, inline annotations, `True`, `Elt`) and the registry metadata
    invariants.
  - `test_heuristic_provider.py` — stamping from the registry, custom rule subset, full
    registry by default, idempotence, clean text.
  - `test_heuristic_prelude.py` — `extract_prelude_sorts` against an inline sample prelude
    (every exclusion rule) and snapshot invariants (`Qid`→`QID`, `Nat`, parameterized
    names; `Elt` absent; no junk names; bases; > 20 modules).
  - `test_prelude_extract_cli.py` — the cyclopts app in-process: writes a loadable
    snapshot, explicit `--maude-version`, byte-stable regeneration, `--check` pass/fail,
    junk-extraction refusal, missing prelude.
  - `test_skill_install.py` — `install_skill` with an explicit source: fresh copy,
    re-install drops stale files, a stray file at the destination is replaced, siblings
    are untouched, a missing source raises with a `make skills` hint; the packaged-source
    contract (`skill_source()` contains `SKILL.md`, skipped when `make skills` was not
    run), and the CLI wiring for `setup --directory` and `setup -g` (monkeypatched
    `Path.home` and installer).
- `tests/integration/` (real interpreter; distinct basenames to avoid pytest module-name
  collisions):
  - `test_maude_worker_integration.py` — `load_diagnostics` shapes through
    `MaudeExecutor.diagnostics` on the interpreter fixtures (including the `file` values,
    `<standard input>` attribution), the fresh-interpreter guarantee, and the parent-stdout
    leak regression with a per-call child.
  - `test_maude_executor_integration.py` — real `diagnostics` and `run_session` through
    the executor, plus two concurrent calls proven to use distinct processes via an
    injected rendezvous target (no sleeps as synchronization).
  - `test_maude_transport_integration.py` — real `spawn` processes: ping +
    `load_diagnostics`, crash isolation, timeout + follow-up, a 100 kB request, large
    responses and the lowered `HAROLD_IPC_MAX_RESPONSE_BYTES` protocol error.
  - `test_process_isolation_integration.py` — the B1/B2/B3 historical cascade (occupiers
    hold the slots, the queued trigger times out on admission, healthy searches complete,
    no `CancelledError`), a running timeout beside a healthy peer + follow-up, and
    shutdown with an in-flight call (cancellation + pid orphan check).
  - `test_maude_session_integration.py` — the worker session engine against the real
    interpreter: reduce and current-term threading, parse errors as outcomes, missing
    module reporting, load warnings and embedded `red` output, a bounded search ending
    the load (its complete result block must be captured), too-large results and
    output truncation without hiding warnings, hermetic sessions, the rewriting family
    (`rewrite`/`frewrite`/`erewrite`, bounds and gas), match hit/miss and depth modes,
    match leaving the current term unchanged, every search type, solution caps and
    result-length caps, parse errors in match/search, and search paths (labels/full/none,
    zero-transition paths for reflexive and branching searches, unlabeled rules, lazy
    per-solution paths, `max_solutions=1`, deep 1500-step searches, exact-cap and
    over-cap behavior).
  - `test_maude_run_integration.py` — the `maude_run` tool end to end: reduce, missing
    module listing defined modules, a broken file as a whole-call failure, reduce-then-
    rewrite threading, failing middle step stopping the run, match/search threading, and
    search paths (`labels`/`full`/`none`, normal-form paths, and cap overflow as a
    `too-large` step).
  - `test_lifespan.py` — lifespan start/teardown, fail-fast, real-executor drive.
  - `test_diagnostics_integration.py` — the acceptance suite, per source: interpreter
    fixtures; the relative-path regression test; the isolation regressions (`quit_command`,
    `q_with_trailing_text`, and a `q .` inside a loaded dependency) each followed by a
    clean diagnosis; the dependency tests (`loads_dependency`, `loads_missing_dependency`,
    `loads_bad_dependency` with honest attribution); linter fixtures for every rule
    (`when_guard`, `dash_comment`, `eq_in_if`, `non_linear_pattern`,
    `undeclared_identifier`, `nonascii_apostrophe`, `redeclare_prelude`,
    `elt_sort_declaration`); negative fixtures (`string_with_specials`,
    `quoted_id_when_dash`, `declarations_when_dash`, `capitalized_identifiers_ok`);
    binary-file regression; the parallel race test
    (`test_parallel_diagnostics_do_not_share_interpreter_state`, 4 workers, every
    interpreter-clean fixture swept); the crash and timeout cases producing a rich
    provider section (path/phase/pid context and the chained worker cause) with a healthy
    executor still working; and the MCP smoke test (real stdio server), which asserts the
    client-visible annotation profile, the new schema (e.g. `redeclare_prelude` returns
    `success=true` with one `heuristic-linter`/`prelude-sort-redeclared`/`info`
    diagnostic) and the hermetic + dependency sentences of the served description. Tags
    are intentionally not asserted on the wire: mcp SDK 1.29 does not serialize them.
- `tests/integration/fixtures/`:
  - interpreter baseline: `hello.maude`, `hello2.maude`, `broken-recoverable.maude`
    (1 warning, loads), `broken-non-recoverable.maude` (12 warnings, loads — Maude
    recovers from everything parseable), `no_new_module.maude`;
  - interpreter sessions: `counter.maude` (unbounded `inc` rule, used for threading and
    rewrite bounds), `assoc_match.maude` (associative `_;` for match-depth modes),
    `warns_and_prints.maude` (load warning plus a top-level `red`), `search_path.maude`
    (`SHEPHERD` river-crossing path, `UNLABELED`, the unbounded `CHAIN`, and the
    one-state branching `BRANCH` system), `bounded_search_last.maude` (a bounded search
    as the last load command, for the capture-flush regression);
  - isolation/`q .` regressions: `quit_command.maude`, `q_with_trailing_text.maude`,
    `dep_q.maude` + `loads_dependency_q.maude`;
  - dependency handling: `dep_clean.maude` + `loads_dependency.maude`, `dep_bad.maude` +
    `loads_bad_dependency.maude`, `loads_missing_dependency.maude`;
  - linter positives: `when_guard.maude`, `dash_comment.maude`, `eq_in_if.maude`,
    `non_linear_pattern.maude`, `undeclared_identifier.maude`, `nonascii_apostrophe.maude`,
    `redeclare_prelude.maude`;
  - linter negatives: `string_with_specials.maude`, `quoted_id_when_dash.maude`,
    `declarations_when_dash.maude`, `capitalized_identifiers_ok.maude`,
    `elt_sort_declaration.maude`;
  - theory handling: `theories.maude` (a theory plus a module).

## Planning docs (`.agents/planning/`)

- `maude-diagnostics-tool-v1/` — complete PDD cycle for the first tool:
  `rough-idea.md`, `idea-honing.md` (Q&A + amendments + verified final-testing reminders),
  `research/` (six notes; `logging.md` superseded), `design/detailed-design.md`,
  `implementation/plan.md` (7 steps, checklist ticked), `summary.md`.
- `port-linter.py/` — complete PDD cycle for the heuristic-linter port (implemented):
  `rough-idea.md`; `idea-honing.md` (Q&A Q1–Q11 + design-review decisions D1–D7);
  `research/` (linter.py analysis, the diagnostics pipeline, integration options, Maude
  lexical probes, prelude sorts, plus re-runnable `probes/` scripts);
  `design/detailed-design.md` (requirements LP1–LP14, seam, components, models, testing,
  appendices incl. the known limitations); `implementation/plan.md` (six test-driven
  steps); `summary.md` (closing record and follow-ups).
- `port-maude_eval.py/` — complete PDD cycle for the `maude_run` interpreter-session tool
  (implemented): `rough-idea.md` (2026-10-17 update), `idea-honing.md` (Q1–Q11),
  `research/` (contribution, placement, consumers, term API, worker behavior, probes),
  `design/detailed-design.md` (requirements R1–R16, session engine, caps, outcomes),
  `implementation/plan.md` (six TDD steps) plus step reviews, and `summary.md` (closing
  record; the code is in `maude/session.py`, `server/tools/interpreter.py` and the
  integration tests).
- `maude_eval_search_path/` — PDD cycle for search paths in `maude_run` (implemented):
  `rough-idea.md`, `idea-honing.md` (eight settled decisions), `research/` (bindings
  path API, current implementation, design options, related commands, executable probes
  and transcripts for `SHEPHERD`/`UNLABELED`/`CHAIN`/`BRANCH`), `design/detailed-design.md`
  (revision 4), three design-review rounds, and `implementation/plan.md` (five TDD steps).
  Its `summary.md` predates the implementation and still says "implementation has not
  started" — the code, fixture and tests exist; treat the design and plan as the record.
- `Unexpected_failure_during_search/` — complete PDD cycle for the missing captured
  output and the generic unexpected-failure message (both fixes implemented):
  `rough-idea.md`; `research/reproduction.md`, `load-output-truncation.md` (verified
  libmaude buffering mechanism), `error-surfacing.md` and executable probes;
  `design/detailed-design.md`; `implementation/plan.md`; `pdd_review-1.md`; `summary.md`.
  The original whole-call failure was not reproduced on this checkout and remains open;
  the new error detail and server traceback make the next occurrence diagnosable.
- `port-repair.py/` — early planning record for a future repair/fix-application tool:
  `rough-idea.md`, `idea-honing.md`, `research/`, `summary.md`. No production code yet.
- `no_new_module_quirk/` — complete PDD cycle for the deferred `q .` parser-residue bug
  (implemented): `rough-idea.md`, `idea-honing.md`, `research/` (quirk inventory, race
  reproduction, dependencies, misattribution, isolation cost), `design/detailed-design.md`
  (option A: per-call isolated interpreters), `implementation/plan.md` (8 steps, checklist
  ticked, deviations recorded), `summary.md`, and the `maude-bindings-issue.md` bug
  report (filed upstream) with its standalone `repro_minimal.py` + `repro/` `.maude`
  inputs.
- `more_interpreter_bugs/` — complete PDD cycle for per-call isolated workers: the
  reproduction record, the design and its reviews, and the implementation plan with
  per-step implementation notes and review records.
- `skill-installer/` — complete PDD cycle for the bundled-skill `setup` command and its
  packaging (implemented): `rough-idea.md`, `idea-honing.md`, `research/release-packaging.md`
  (the hatchling `artifacts` finding), `design/detailed-design.md` plus design-review and
  two code-review rounds, `implementation/plan.md`, and `summary.md` (its only follow-up,
  this knowledge-base refresh, is done).
- `sigsegv-under-load/` — SIGSEGV history that motivated the worker architecture:
  `issue.md` (the `maude` Python bindings) and `scala-issue.md` (root-cause analysis of
  SIGSEGV and throughput degradation in the Scala/Java Maude bindings — background
  material from a related codebase).

## Docs

- `docs/` — MkDocs sources; `docs/modules.md` renders `harold_mcp.server.server`,
  `harold_mcp.server.tags`, `harold_mcp.server.tools.diagnostics`,
  `harold_mcp.server.tools.interpreter`, `harold_mcp.errors`,
  `harold_mcp.diagnostics.provider`, `harold_mcp.diagnostics.aggregate`,
  `harold_mcp.heuristic.provider`, `harold_mcp.heuristic.rules`,
  `harold_mcp.heuristic.lexical`, `harold_mcp.heuristic.declarations`,
  `harold_mcp.heuristic.prelude_extract`, `harold_mcp.heuristic.prelude_sorts`,
  `harold_mcp.maude.capture`, `harold_mcp.maude.executor`, `harold_mcp.maude.provider`,
  `harold_mcp.maude.runner`, `harold_mcp.maude.session`, `harold_mcp.maude.transport`,
  `harold_mcp.maude.worker`, `harold_mcp.maude.worker_errors`, `harold_mcp.settings` via
  mkdocstrings. The thin CLI/packaging modules (`main`, `skill_install`, `resources`,
  `logging`) are not on that page; see `review_notes.md` completeness gap 6.
- Root-level docs: `README.md` (installation with `setup`, update, MCP client config and
  the env-var table), `CONTRIBUTING.md` (contribution workflow), `DEVELOPER_GUIDE.md`
  (dev environment, agent skills, prelude snapshot maintenance, release process),
  `CHANGELOG.md` (release notes).

## Related documents

- `architecture.md` — module dependency graph and architectural decisions
- `interfaces.md` — public surface of these components
