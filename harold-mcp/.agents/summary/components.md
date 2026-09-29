# Components

<!-- tags: components, modules, responsibilities -->

## `src/harold_mcp/` (the package)

### `harold_mcp.main`

- **Responsibility**: CLI/stdio entry point for the MCP server, built with **cyclopts**.
- `app = App(name="harold-mcp", help=...)` with a `serve` subcommand; both the app default
  and the `serve` default run `run()`, which delegates to `harold_mcp.server.run`. cyclopts
  provides `--help`/`--version`.
- Exposed as the `harold-mcp` console script (`harold_mcp.main:app`). The
  `if __name__ == "__main__"` guard is required: the `spawn`-context worker re-imports the
  main module.

### `harold_mcp.settings`

- **Responsibility**: application configuration, read once from `HAROLD_*` env vars.
- `Settings(BaseSettings)` — flat model: `maude_workers: int` (default 1, `gt=0`),
  `maude_worker_timeout_secs: int` (default 60, `gt=0`). Invalid values fail at import.
- `settings` — module-level singleton; `get_settings() -> Settings` returns it (FastMCP
  dependency factory). Env vars are documented in `README.md`.

### `harold_mcp.server` (package)

- **`__init__.py`** — re-exports `mcp` and `run` from `server.server`, and imports
  `harold_mcp.server.tools` (tool registration as a package side effect).
- **`server.py`** — the FastMCP instance and its lifecycle:
  - `mcp = FastMCP(name="Harold", instructions=..., website_url=..., icons=[HAROLD_ICON], lifespan=app_lifespan)`.
  - `app_lifespan` — `@lifespan`-decorated async generator: `get_maude_executor(
    get_settings()).start()` (warm-up, fail-fast), teardown in `finally`.
  - `run()` — registers a SIGTERM handler that raises `KeyboardInterrupt`, calls
    `mcp.run()`, and on `KeyboardInterrupt` logs and calls `os._exit(0)` (see
    `architecture.md` §5 for why).
  - `_handle_shutdown_signal` — the SIGTERM→`KeyboardInterrupt` bridge.
- **`tools/__init__.py`** — re-exports `maude_program_diagnostics`.
- **`tags.py`** — the shared tool-tag vocabulary (see `interfaces.md`): constants
  `MAUDE`/`PROGRAMMING` (domain), `DIAGNOSTICS`/`INTERPRETER`/`DOCS` (functional
  categories; the latter two reserved for planned tools), and `harold_tags(*tags)`,
  which always adds the domain tags. Effect/safety metadata is deliberately not a tag
  (it belongs in `ToolAnnotations`). With mcp SDK 1.29 tags are server-side only:
  they drive `mcp.enable`/`mcp.disable` and are not serialized to clients.
- **`tools/diagnostics.py`** — the MCP surface of `maude_program_diagnostics` and the
  adapter from the provider seam to the wire models:
  - Wire models (see `data_models.md`): `MaudePosition`, `MaudeRange`, `MaudeTextEdit`,
    `MaudeFix`, `MaudeDiagnostic` (with `source`, `code`, `fix`), `MaudeDiagnosticsSummary`
    (with `info`), `MaudeProgramDiagnosticsResult`.
  - Tool flow: `SourceFile.from_path(path)` (pre-check: rejects missing/non-regular
    files with `SourceFileNotFoundError`, reads the text once) →
    `collect_diagnostics((InterpreterDiagnosticProvider(maude_executor),
    HeuristicLinterProvider()), source)` → adapter to the wire models. `success` is
    `all(severity == "info")`; `summary` counts all three severities; `range` is `None`
    for whole-file problems; fix edits map to wire ranges with an exclusive `end`.
  - Registered with the full read-only annotation profile (`readOnlyHint=True`,
    `destructiveHint=False`, `idempotentHint=True`, `openWorldHint=False`) and
    `tags=harold_tags(DIAGNOSTICS)`. The models inherit the private `_ResultModel` base
    (`ConfigDict(use_attribute_docstrings=True)`), so their attribute docstrings reach
    clients as output-schema field descriptions (see `data_models.md`); a code comment next
    to the tool records that only the text above `Args:` becomes the MCP description.
  - The docstring describes both sources, the severity meanings, the `fix` payload, the
    ordering, and that loading mutates interpreter state ("last load wins").

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
    rejects anything that is not a regular file and reads with
    `utf-8`/`errors="replace"`), `FixEdit` (`line`, `start_column`, exclusive
    `end_column`, `new_text`), `FixSuggestion` (`description` + `edits` tuple),
    `ProviderDiagnostic` (`source`, `severity`, `code`, `message`, optional 1-based
    `line`/`column`/`end_column`, optional `fix`; `__post_init__` rejects columns without
    a line, an `end_column` without a column, and non-positive positions).
  - `DiagnosticProvider` — `Protocol` with a `name` property and
    `diagnose(source) -> list[ProviderDiagnostic]`; implementations wrap their failures
    in `DiagnosticProviderError`.
  - Error vocabulary: `DiagnosticsError(RuntimeError)` base, `SourceFileNotFoundError`
    (the tool's input error; `.path`), `DiagnosticProviderError` (`source`, `reason`).
- **`aggregate.py`** — running providers and merging findings:
  - `ProviderFailure` (`provider`, `error`) and `DiagnosticCollectionError` (`.failures`
    tuple; message names every failing provider and its reason — an unexpected provider
    bug keeps its exception type). The error chains the first failure as `__cause__`.
  - `collect_diagnostics(providers, source)`: runs every provider **in order**, never
    short-circuits after a failure (so all failures are named), discards successful
    providers' findings when any provider failed (no partial results, MCP cannot express
    "error + content"), then sorts the merged list by (whole-file last, line, provider
    registry order, column).

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
  `get_maude_executor`, `InterpreterDiagnosticProvider`. Importing the package never
  imports the SWIG `maude` bindings.
- **`executor.py`** — the client-side access layer:
  - Error hierarchy: `MaudeError(RuntimeError)` base; `MaudeInitError` (worker init
    failure, surfaced at warm-up); `MaudeWorkerError(reason)` with
    `MaudeWorkerCrashedError` / `MaudeWorkerTimeoutError` subclasses. The old
    `MaudeFileNotFoundError` was removed — the tool's input error is
    `harold_mcp.diagnostics.SourceFileNotFoundError`.
  - `MaudeExecutor(Logging)` — wraps a `ProcessPoolExecutor` (spawn,
    `initializer=worker.init_maude`): `start()` (warm-up pings, `MaudeInitError` on
    failure), `shutdown()` (idempotent), `submit()` (raises `MaudeWorkerCrashedError` on a
    broken pool, replaces it), `diagnostics(path)` (thin wrapper over `_run_task`), and
    the generic `_run_task(fn, *args) -> T` runner (submit + await + crash/timeout
    mapping). `_reset_executor(replace=True, failed=None)` is a pure command (CQS) that
    swaps the pool under `_executor_lock` (an RLock) and kills the old pool with
    `kill_workers()` outside the lock; the `failed` identity check makes concurrent
    failure reports replace exactly once.
  - `get_maude_executor(settings: Settings = Depends(get_settings)) -> MaudeExecutor` —
    process-wide singleton, created lazily under a lock (nested FastMCP dependency).
- **`provider.py`** — `InterpreterDiagnosticProvider` (v1 behavior behind the seam):
  runs `executor.diagnostics(str(source.path))`, maps each `Warning:` to a line-only
  `warning` diagnostic and appends one synthesized whole-file `error` when the load
  failed (`ok=False`); every diagnostic carries `source="interpreter"` and
  `code="compiler"`. A `MaudeWorkerError` (crash/timeout) becomes a
  `DiagnosticProviderError` with the original error as `__cause__`.
- **`worker.py`** — the interpreter side, pickled/spawn-imported by the worker process;
  imports `maude` **lazily inside functions** so the server process never touches the
  bindings (the absolute `import maude` is the third-party package, not this one):
  - `init_maude()` — idempotent; `maude.init(loadPrelude=True, advise=False)` then
    disables Maude IO (`setAllowDir/File/Processes(False)`); raises `WorkerInitError`.
  - `ping()` — warm-up no-op. `sleep(seconds) -> int` — test/timeout support.
  - `load_diagnostics(path) -> LoadDiagnosticsResult` — fd-2 capture around `maude.load`
    (binary tempfile, lossy UTF-8 decode, ANSI CSI stripping, `Warning:` regex parsing).
  - `_crash()` — test-only `os._exit(1)` (SIGSEGV analogue).

### `harold_mcp.resources`

- **Responsibility**: packaging of static brand assets. `HAROLD_ICON` — an `mcp.types.Icon`
  built from `assets/brand/Harold_logo.png`, passed to the `FastMCP` constructor.

### `harold_mcp.logging`

- **Responsibility**: logging utilities. Re-exports `get_logger` from
  `fastmcp.utilities.logging` and defines `Logging`, a base class exposing a `_log`
  property (logger named after the concrete class). `MaudeExecutor` uses the mixin.

## Tests

- `tests/unit/` (hermetic, mocked):
  - `test_settings.py` — defaults, env overrides, case-insensitivity, invalid values,
    singleton.
  - `test_tags.py` — the shared vocabulary: `harold_tags` always adds the domain tags,
    and the tag strings are pinned (they are part of the client-visible interface).
  - `test_maude_worker.py` — `_parse_warnings` (observed formats, ANSI stripping,
    unmatched/advisory lines ignored) and the `init_maude` sequence (success/failure, IO
    lockdown, idempotency) with the `maude` bindings faked via `sys.modules`.
  - `test_maude_executor.py` — fake executors/futures: warm-up (success/fail), broken
    submit, crash/timeout mapping + kill, exception propagation, exactly-once concurrent
    replacement, singleton.
  - `test_maude_provider.py` — `InterpreterDiagnosticProvider`: warning/error mapping,
    `source`/`code` stamping, and worker errors becoming `DiagnosticProviderError` with
    the cause chained.
  - `test_diagnostics_seam.py` — seam contracts: errors are not `MaudeError`s, message
    formatting, position invariants, frozen fix values, and `SourceFile.from_path`
    (regular file, string paths, missing/directory/non-regular/unreadable rejection,
    lossy decoding, newline normalization).
  - `test_diagnostics_aggregate.py` — merge provenance and ordering (file order, provider
    tie-break, whole-file last), every provider receives the source, no-diagnostics
    success, one failing provider → `DiagnosticCollectionError` without partial results,
    remaining providers still attempted, unexpected bugs reported with their type.
  - `test_diagnostics.py` — the tool with a fake executor: warning/error mapping and the
    synthesized whole-file error, `info`-only success, summary counts, whole-file ranges,
    adapter mapping of columns and fixes, pre-check before any provider,
    `DiagnosticCollectionError` propagation, and
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
- `tests/integration/` (real interpreter; distinct basenames to avoid pytest module-name
  collisions):
  - `test_maude_worker_integration.py` — `load_diagnostics` on the four interpreter
    fixtures + advisory suppression on redefinition.
  - `test_maude_executor_integration.py` — warm-up, interpreter fixtures, real `_crash`
    containment + retry, two-worker parallelism via slow `sleep` tasks.
  - `test_lifespan.py` — lifespan start/teardown, fail-fast, real-pool drive.
  - `test_diagnostics_integration.py` — the acceptance suite, per source: interpreter
    fixtures; linter fixtures for every rule (`when_guard`, `dash_comment`, `eq_in_if`,
    `non_linear_pattern`, `undeclared_identifier`, `nonascii_apostrophe`,
    `redeclare_prelude`, `elt_sort_declaration`); negative fixtures
    (`string_with_specials`, `quoted_id_when_dash`, `declarations_when_dash`,
    `capitalized_identifiers_ok`); binary-file regression; parallel workers; crash
    recovery (the tool now raises `DiagnosticCollectionError` naming `interpreter` and
    recovers on the next call); and the MCP smoke test (real stdio server), which asserts
    the client-visible annotation profile and the new schema (e.g. `redeclare_prelude`
    returns `success=true` with one `heuristic-linter`/`prelude-sort-redeclared`/`info`
    diagnostic). Tags are intentionally not asserted on the wire: mcp SDK 1.29 does not
    serialize them.
- `tests/integration/fixtures/` — 17 files:
  - interpreter baseline: `hello.maude`, `hello2.maude`, `broken-recoverable.maude`
    (1 warning, loads), `broken-non-recoverable.maude` (12 warnings, loads — Maude
    recovers from everything parseable), `no_new_module.maude`;
  - linter positives: `when_guard.maude`, `dash_comment.maude`, `eq_in_if.maude`,
    `non_linear_pattern.maude`, `undeclared_identifier.maude`, `nonascii_apostrophe.maude`,
    `redeclare_prelude.maude`;
  - linter negatives: `string_with_specials.maude`, `quoted_id_when_dash.maude`,
    `declarations_when_dash.maude`, `capitalized_identifiers_ok.maude`,
    `elt_sort_declaration.maude`.

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
- `port-maude_eval.py/` — research record for a future term-evaluation tool (`maude_eval.py`
  port). **Paused at the decision point**: the capability is wanted (term parse → reduce →
  value, the seed of "run Maude programs") but deliberately not implemented; `design/` and
  `implementation/` are intentionally empty and `summary.md` lists the five Phase-2 probes
  to resume with. No code changed for it.
- `sigsegv-under-load/` — SIGSEGV history that motivated the worker architecture:
  `issue.md` (the `maude` Python bindings) and `scala-issue.md` (root-cause analysis of
  SIGSEGV and throughput degradation in the Scala/Java Maude bindings — background
  material from a related codebase).

## Docs

- `docs/` — MkDocs sources; `docs/modules.md` renders `harold_mcp.server.server`,
  `harold_mcp.server.tags`, `harold_mcp.server.tools.diagnostics`,
  `harold_mcp.diagnostics.provider`, `harold_mcp.diagnostics.aggregate`,
  `harold_mcp.heuristic.provider`, `harold_mcp.heuristic.rules`,
  `harold_mcp.heuristic.lexical`, `harold_mcp.heuristic.declarations`,
  `harold_mcp.heuristic.prelude_extract`, `harold_mcp.heuristic.prelude_sorts`,
  `harold_mcp.maude.executor`, `harold_mcp.maude.provider`, `harold_mcp.maude.worker`,
  `harold_mcp.settings` via mkdocstrings.
- Root-level docs: `README.md` (installation + MCP client config), `CONTRIBUTING.md`
  (contribution workflow), `DEVELOPER_GUIDE.md` (dev environment, agent skills, prelude
  snapshot maintenance, release process), `CHANGELOG.md` (release notes).

## Related documents

- `architecture.md` — module dependency graph and architectural decisions
- `interfaces.md` — public surface of these components
