# Implementation plan — `maude_run`

> PDD phase 7 for the `port-maude_eval.py` project. Design:
> [`../design/detailed-design.md`](../design/detailed-design.md). Requirements:
> [`../idea-honing.md`](../idea-honing.md) Q1–Q11. Research:
> [`../research/term-api.md`](../research/term-api.md),
> [`../research/worker-behavior.md`](../research/worker-behavior.md).

## Checklist

- [x] **Step 1** — Settings and stream-capture foundation
- [x] **Step 2** — Worker session engine and executor (reduce only)
- [x] **Step 3** — `maude_run` tool end to end (reduce only)
- [ ] **Step 4** — Rewriting family and current-term threading
- [ ] **Step 5** — `match` and `search`, final tool description
- [ ] **Step 6** — Documentation, release bookkeeping, full validation

## Working agreements

- **TDD:** each step starts with the failing tests for its slice, then the implementation. Tests are
  part of the step, never a later "testing step".
- **Every step is demoable** and leaves `make check` clean; run
  `UV_CACHE_DIR=/tmp/uv-cache make test-unit` while iterating and the full
  `UV_CACHE_DIR=/tmp/uv-cache make test` before closing a step that touches the interpreter.
- **Conventions:** ruff + `ruff format` with `--exit-non-zero-on-fix`, mypy strict, basedpyright
  unused-call-result (`_ = ...` for intentional discards), `Depends(...)` needs `# noqa: B008`
  except for immutable generics, test basenames must be distinct between `tests/unit/` and
  `tests/integration/`, and the server process must never import the `maude` bindings.
- **Fixtures:** reuse `tests/integration/fixtures/`; new fixtures are added by the step that first
  needs them.

Proceed step by step:

- After each step ask me for confirmation before completing the step
- When completing a step, add a new subsection "Implementation notes" to the step section in the plan, with a summary of what we did, focusing on the deviations from the plan, explaining why we did them and the implications for subsequent steps

---

## Step 1: Settings and stream-capture foundation

**Objective.** Introduce every setting the tool needs and extract the shared stream-capture helper,
so `load_diagnostics` captures both stdout and stderr without changing its observable result.

**General implementation guidance.**

- `src/harold_mcp/settings.py`:
  - rename `maude_worker_timeout_secs` → `diagnostics_timeout_secs` (env
    `HAROLD_DIAGNOSTICS_TIMEOUT_SECS`), and update `MaudeExecutor` defaults;
  - add `interpreter_timeout_secs` (`HAROLD_INTERPRETER_TIMEOUT_SECS`, default 60);
  - add `interpreter_max_steps` (200), `interpreter_max_rewrite_bound` (1000),
    `interpreter_max_solutions` (200), `interpreter_max_term_length` (100_000),
    `interpreter_max_result_length` (1_000_000), `interpreter_max_output_length` (1_000_000);
  - all `gt=0`; update the class docstring.
- `src/harold_mcp/maude/capture.py` (new): `WarningDict`, `CapturedOutput`, `capture_streams(fn)`
  (fd 1 and fd 2 to temp files, restore in `finally`, lossy decode, ANSI strip), `strip_ansi`,
  `parse_warnings` (moved verbatim), `truncate_output(text, max_length)`.
- `src/harold_mcp/maude/worker.py`: `load_diagnostics` uses `capture_streams` and
  `parse_warnings(captured["stderr"])`; stdout is captured and discarded. Extend the docstring:
  nothing may be logged or printed while **both** fds are redirected.
- Move the existing warning-parser unit tests to the new module/imports.

**Test requirements.**

- Unit `tests/unit/test_settings.py` (extend): defaults for every new/renamed field; env overrides;
  rejection of zero/negative values.
- Unit `tests/unit/test_maude_capture.py` (new): fd 1/fd 2 separation (different text to each ends
  up in its own field); restoration after the call; ANSI stripping; lossy decode;
  `truncate_output` unchanged at the limit, marker above it.
- Unit `tests/unit/test_maude_worker.py` (extend): existing parser cases now import
  `capture.parse_warnings`; a fake `sys.modules["maude"]` whose `load` writes a real warning to
  fd 2 and a warning-looking line to fd 1 yields **only** the stderr warning.
- Integration `tests/integration/test_maude_worker_integration.py` (extend): new fixture
  `warns_and_prints.maude` (a module with a `missing is` warning plus an embedded
  `red in … : f .`); `load_diagnostics` returns exactly the stderr warning, `ok=true`, and no
  warning message contains stdout text. Parent-stdout leak regression: capture the parent's fd 1
  around a pooled call and assert the `red` output is absent (run the call in a child process if
  pytest's own capture makes the fd approach fragile).

**Integration with previous work.** `load_diagnostics` keeps its `{ok, warnings}` shape; the
existing diagnostics tool, provider and tests must stay green.

**Demo.** `make test-unit` green; an integration run shows the `red` output captured (not leaked)
and the warning set unchanged.

### Implementation notes (Step 1)

**What landed.**

- `Settings`: `maude_worker_timeout_secs` → `diagnostics_timeout_secs` (env
  `HAROLD_DIAGNOSTICS_TIMEOUT_SECS`, breaking rename) and the seven new
  `interpreter_*` fields, all `gt=0`. `MaudeExecutor` (log line, init pings,
  `_run_task`) now reads `diagnostics_timeout_secs`.
- `maude/capture.py`: `WarningDict`, `CapturedOutput`, `strip_ansi`,
  `parse_warnings` (moved verbatim from the worker), `capture_streams`, and
  `truncate_output`. Stdlib-only; safe to import in the server process.
- `worker.load_diagnostics` is built on `capture_streams`: fd 2 is parsed, fd 1
  is captured and discarded (closing the latent MCP-stdio leak); its docstring
  states that nothing may be logged or printed while both fds are redirected.
- Tests: parser cases moved to `tests/unit/test_maude_capture.py`;
  `test_maude_worker.py` keeps init + fake-`load` tests; new fixture
  `warns_and_prints.maude`; integration coverage for exact warnings and the
  parent-stdout leak regression.

**Deviations and decisions.**

1. `truncate_output` appends the marker *after* the retained prefix, so a
   truncated string is `max_length + len(marker)` long. The design wording did
   not say whether the marker counts toward the cap; the docstring now states
   the choice explicitly (the cap bounds interpreter output, not the marker).
   Step 2 must use this helper as-is when building `CapturedOutput`.
2. Added the public `TRUNCATION_MARKER` constant (`... [output truncated]`) so
   tests and the session engine share one spelling.
3. `capture_streams` uses PEP 695 type parameters (`def capture_streams[T]`),
   required by ruff `UP047`; the planned `TypeVar` was removed.
4. The leak regression test creates a **dedicated pool inside the fd-1
   redirect** (a module-scoped pool would not catch a leak: its workers
   inherited the original stdout when spawned). It reads the pipe
   non-blocking: multiprocessing's resource tracker can also inherit the write
   end, and a blocking read-to-EOF hung when the test ran in isolation.
   Verified by temporarily restoring the old stderr-only capture: the test
   fails on the leaked `reduce in WARNS-AND-PRINTS` text.
5. Added `test_legacy_worker_timeout_env_var_is_ignored`, pinning the breaking
   rename (the old env var now configures nothing).
6. README/docs were intentionally left for Step 6 per the plan, so the README
   env-var table is temporarily stale about the rename.

**Implications for later steps.** Forced by the design; recorded here because
later steps depend on them:

- `capture_streams` returns the callable's result plus already-decoded,
  ANSI-stripped `stdout`/`stderr`; the session engine must parse the **full**
  `stderr` before applying `truncate_output` to the returned strings.
- `diagnostics_timeout_secs` is now the worker subsystem default; Step 2 adds
  the `timeout` parameter to `_run_task` without changing `diagnostics()`.
- The new `interpreter_*` settings are intentionally unused until Steps 2–5;
  `CHANGELOG.md` must call out the env-var rename when Step 6 lands.

---

## Step 2: Worker session engine and executor (reduce only)

**Objective.** Add the hermetic session engine with load, module selection and `reduce` steps, and
expose it through `MaudeExecutor`.

**General implementation guidance.**

- `src/harold_mcp/maude/session.py` (new; lazy `import maude` inside `run_session`):
  - TypedDicts from the design (§5.4), including `max_output_length` in `SessionRequest`;
  - `run_session(request)`: `getModules()` snapshot → `capture_streams(lambda: maude.load(path))` →
    `defined_modules` diff → `parse_warnings` on the **full** stderr → `load_ok` →
    `getModule(module)` + `module_type` → step loop;
  - step loop for `reduce`: resolve `term` or current, `parseTerm` (`None` → `parse-error` with the
    joined warning messages), `reduce()`, serialize with `str()`, apply
    `max_result_length` (`too-large`), truncate captured output with `max_output_length`, stop at
    the first failure, update the current term.
  - Use explicit `is not None` checks for optional numeric arguments (never `or`).
- `src/harold_mcp/maude/executor.py`: `_run_task(..., timeout: float | None = None)` (default
  `diagnostics_timeout_secs`) and `run_session(request, timeout=None)`.
- `src/harold_mcp/maude/__init__.py`: export the session request/result types needed by the tool.

**Test requirements.**

- Unit `tests/unit/test_maude_executor.py` (extend): `_run_task` passes the effective timeout to
  `future.result`; `run_session` delegates to `session.run_session` with the request and timeout;
  `diagnostics()` keeps the default timeout.
- Integration `tests/integration/test_maude_session_integration.py` (new; distinct basename):
  reduce of `HELLO-WORLD.f` → `2` with `rewrites > 0`; `parse-error` for an undeclared operator;
  `module_found=false` for a missing module with `defined_modules` populated; load warnings present
  and evaluation still proceeds (`broken-recoverable.maude`); load of a file with an embedded `red`
  whose output appears in `load_output.stdout`; `too-large` and output truncation with tiny limits;
  hermeticity (the module defined by call 1 is not found in call 2).

**Integration with previous work.** Uses the Step 1 settings and capture helper; the diagnostics
path is untouched.

**Demo.** A direct executor call returns a session result reducing `f` to `2`, and a second call
proves hermeticity.

### Implementation notes (Step 2)

**What landed.**

- `maude/session.py`: the §5.4 TypedDicts (`StepRequest`, `SessionRequest`,
  `BindingDict`, `SolutionDict`, `StepOutcomeDict`, `SessionResult`) and
  `run_session` with the load → module selection → step loop. `_reduce` parses
  and reduces under one capture, emits `ok` / `parse-error` / `too-large`,
  applies `max_result_length` and truncates the returned capture to
  `max_output_length`; warnings and parse-error messages are parsed from the
  full stderr first. The current term threads through `reduce` steps.
- `MaudeExecutor._run_task(..., timeout=None)` resolves `None` to
  `diagnostics_timeout_secs`; `diagnostics()` and `start()` keep that default.
  `run_session(request, timeout=None)` delegates to `session.run_session`.
- `harold_mcp.maude` exports `SessionRequest`, `SessionResult`, `StepRequest`,
  `StepOutcomeDict` (plus `CapturedOutput` and `WarningDict` for the tool).
- Tests: executor unit tests record the timeout passed to `future.result`
  (default and explicit, session delegation); new
  `tests/integration/test_maude_session_integration.py` covers reduce, current
  term threading, parse-error, missing module with defined modules, warnings
  plus evaluation, embedded `red` in `load_output.stdout`, `too-large`, output
  truncation and hermeticity.

**Deviations and decisions.**

1. `module_type` is `UNKNOWN_MODULE_TYPE = -1` when the load failed or the
   module is missing (real types start at `FUNCTIONAL_MODULE = 0`). The tool
   checks `module_found` before using the value.
2. The `parse-error` message joins the parsed warning messages with `\n`; the
   design only said "joined". A failure that prints no `Warning:` lines yields
   an empty message (no observed case).
3. `_run_step` raises `ValueError` (with `# noqa: TRY003`) for an unsupported
   command or a missing subject: both are programming errors that Step 3's
   validation prevents, not user errors.
4. The executor is decoupled from the diagnostics timeout (user review,
   2026-10-22): `_run_task` and `run_session` now require an explicit `timeout`,
   `diagnostics()` passes `diagnostics_timeout_secs` itself, and the lifespan
   passes the same setting to `start(timeout)`. **Step 3 must pass** the
   settings' `interpreter_timeout_secs` (or the per-call override) explicitly to
   `run_session`.
5. `SessionRequest.max_solutions` is carried but unused until Step 5, and
   `_outcome` sets the `matches`/`solutions`/`truncated` fields to `None` until
   the corresponding commands land.
6. Added an integration test for `reduce` current-term threading (the loop
   already maintained the current term, so the behavior needed pinning).
7. No unit tests mock the session engine: the `maude` module is `Any`, so a fake
   would only re-assert the dict plumbing; the integration suite exercises the
   real parse/reduce behavior where it matters.

**Implications for later steps.** Steps 4–5 extend `_run_step`/`_outcome` and
consume `max_solutions`; the Step 3 adapter can rely on `UNKNOWN_MODULE_TYPE`
only after a `module_found` check and on exactly one outcome per executed step
(stop-at-first-failure is implemented in `run_session`).

---

## Step 3: `maude_run` tool end to end (reduce only)

**Objective.** Expose the first vertical slice as an MCP tool: path resolution, input validation,
the full result envelope, whole-call errors, timeout selection, registration — with `reduce` as the
only command for now.

**General implementation guidance.**

- `src/harold_mcp/server/tools/interpreter.py` (new): wire models from the design §5 (input union
  with `ReduceStep` only for now; `MaudeRunResult`, `MaudeLoadInfo`, `MaudeStepOutcome`,
  `MaudeCapturedOutput`, `MaudeLoadWarning`); `MaudeRunError`; `_resolve_path` (resolve +
  `is_file`, no `diagnostics.SourceFile` import); `_validate_steps` (step count, length caps,
  threading feasibility); `_to_request`; `_to_wire_result`; `maude_run` with
  `Depends(get_maude_executor)` + `Depends(get_settings)`, the read-only annotations, the
  `INTERPRETER` tag and a description covering the reduce slice (extended in later steps).
- Whole-call error mapping: load false, module missing, theory module type, worker
  `MaudeError`/unexpected exception (chained causes), timeout selection
  (`timeout_secs` else `interpreter_timeout_secs`).
- `src/harold_mcp/server/tools/__init__.py`: import `maude_run`.
- `src/harold_mcp/server/tags.py`: drop "planned" from the `interpreter` comment.

**Test requirements.**

- Unit `tests/unit/test_interpreter_tool.py` (new): path errors; validation (empty step list,
  over-cap step count/term length, `reduce` first step without a term); adapter (ok outcome,
  `completed`, warnings, output, parse-error, too-large); error mapping with a fake executor
  (load false, module missing with defined modules, theory, timeout chained, unexpected exception);
  timeout selection and the request's cap fields.
- Integration `tests/integration/test_maude_run_integration.py` (new): an end-to-end tool call
  reducing `f` in `HELLO-WORLD`; a missing module error listing the defined modules; a broken file
  error.

**Integration with previous work.** Builds on Steps 1–2; the tool is registered on the shared
`mcp` instance exactly like the diagnostics tool.

**Demo.** An MCP client (or `tests/integration` call) invokes `maude_run` with
`[{"command": "reduce", "term": "f"}]` and receives `term="2"`, `completed=true`, and the load info.

### Implementation notes (Step 3)

**What landed.**

- `server/tools/interpreter.py`: `ReduceStep` (the input union for now), the result
  models (`MaudeCapturedOutput`, `MaudeLoadWarning`, `MaudeLoadInfo`,
  `MaudeStepOutcome`, `MaudeRunResult`), `MaudeRunError`, `_resolve_path`,
  `_validate_steps`, `_to_request`, the adapters, and the `maude_run` tool with
  `harold_tags(INTERPRETER)` and the read-only annotation profile.
- Whole-call errors: missing/unreadable path, `load_ok=false` (with the stripped load
  stderr), module not found (naming the module, the file and the defined modules and
  pointing at `maude_program_diagnostics`), theory module, worker failure
  (`MaudeWorkerError` chained) and a safety-net mapping for any other exception.
- The timeout is chosen explicitly: `timeout_secs` when supplied, else
  `settings.interpreter_timeout_secs`.
- Registration: `server/tools/__init__.py` imports `maude_run`; the `INTERPRETER`
  tag comment no longer says "planned".
- Tests: 18 unit tests in `tests/unit/test_interpreter_tool.py` (path and input
  validation, request/caps/timeout mapping, adapter for ok/parse-error/too-large,
  every error path with chained causes) and 3 integration tests in
  `tests/integration/test_maude_run_integration.py` (end-to-end reduce, missing
  module listing, broken file).

**Deviations and decisions.**

1. Empty step lists are guarded twice: the parameter is
   `Annotated[list[MaudeStep], Field(min_length=1)]` (the MCP schema shows
   `minItems: 1`), and `_validate_steps` also raises `MaudeRunError` because direct
   tool calls (tests, in-process clients) bypass FastMCP's validation.
2. `MaudeStepOutcome` carries only the reduce-relevant fields for now
   (`term`, `rewrites`, `message`, `limit`, `output`); `matches`, `solutions` and
   `truncated` arrive with Steps 4–5. Its `command` field already uses the full
   six-command `Literal` from design §5.3, so the output schema does not widen later.
3. `MaudeLoadWarning.line` is `int` as designed; the adapter casts
   `WarningDict.line` (`int | None`) because `parse_warnings` only emits positioned
   warnings today.
4. Theory module types are a local `frozenset({2, 3, 7, 11})` with the binding names
   in a comment: importing `maude.Module` in the server process is forbidden.
5. `_resolve_path` resolves with `expanduser().resolve()` and raises the tool's
   `MaudeRunError`, deliberately not reusing `diagnostics.SourceFile` (no coupling to
   the diagnostics seam).
6. The `steps` parameter is named `steps` in the schema; `timeout_secs` renders as
   `int|null` with `exclusiveMinimum: 0` and is excluded from the required set.
   Verified against the FastMCP tools documentation (Annotated/Field constraints,
   docstring descriptions, `Depends` exclusion) and the served schema.
7. The description is the reduce-only slice of design §4.8; Step 5 replaces it with
   the final six-command text as planned.
8. `tests/integration/test_diagnostics_integration.py::test_mcp_smoke` now expects
   two tools: it switched to a name-keyed dict and additionally asserts the
   `maude_run` input properties, description and read-only annotations.

**Implications for later steps.** Step 4 widens `MaudeStep` to the discriminated
union, fills `bound`/`gas` in `_to_step_request`, adds the bound cap and the
`match`/`search` threading rules to `_validate_steps`, and relies on the session
engine's stop-at-first-failure. Step 5 adds the match/search result fields and the
final description; the adapter's `Literal` casts already accept every command.

---

## Step 4: Rewriting family and current-term threading

**Objective.** Add `rewrite`, `frewrite` and `erewrite` with every binding bound (`bound`, `gas`),
and complete the REPL-style threading semantics.

**General implementation guidance.**

- Input models: `RewriteStep`, `FrewriteStep`, `ErewriteStep` with `bound` (`ge=0`, ≤
  `interpreter_max_rewrite_bound`) and `gas` (`ge=0`); explicit `is not None` handling when calling
  the bindings (0 means "no rewrites", 0 depth has meaning, etc.).
- Session engine: `reduce` and the three rewrite commands share subject resolution; use the mutated
  subject for `rewrite`/`frewrite`, the returned term for `erewrite`; update the current term;
  document that `rewrites` includes equational rewrites.
- Validation: `bound` cap; threading already validated in Step 3.

**Test requirements.**

- Unit: input validation (bound 0 accepted, cap+1 rejected, gas forwarded); adapter fields
  (`rewrites`, `term`).
- Integration: values and counters for all four commands; `bound=0` leaves the term unchanged;
  `erewrite` does not alter the original (pipeline: `reduce` → `erewrite`); a three-step pipeline
  where the second step fails returns exactly two outcomes and `completed=false`.

**Integration with previous work.** Extends the Step 3 union and adapter; the tool description
gains the three commands.

**Demo.** A pipeline `reduce f` → `rewrite` (term omitted, uses the previous result) returns both
intermediate terms; a failing middle step stops the run.

---

## Step 5: `match` and `search`, final tool description

**Objective.** Add `match` and `search` with pattern/subject/depth/search-type inputs, matches,
solutions and truncation flags, and publish the final tool description.

**General implementation guidance.**

- Input models: `MatchStep` (`pattern`, optional `subject`, optional `depth` → `maxDepth`) and
  `SearchStep` (`search_type` literal for the five Maude types). No deprecated `withExtension`.
- Session engine: parse the pattern in the module; `subject.match(pattern, maxDepth=depth if depth
  is not None else -1)` iterating `(Substitution, context)`; `subject.search(constant, pattern,
  depth=…)` iterating `(Term, Substitution, path, rewrites)`; cap both at `max_solutions` with
  `islice(cap + 1)` to set `truncated`; serialize bindings as `{variable, value}` pairs; do not
  change the current term.
- Wire models: `MaudeMatch`, `MaudeBinding`, `MaudeSearchSolution`; adapter.
- Replace the incremental docstring with the final description from the design §4.8 (bounded
  session, statelessness, threading, all commands, load warnings, stop-at-first-failure, output
  truncation, timeout semantics).

**Test requirements.**

- Unit: pattern required; subject/threading rules; adapter for matches/solutions/truncated.
- Integration: match hit/miss; `depth` variants (`-1`, `0`, anywhere) on an assoc module; search
  for all five types (including `=>*` including the initial state and a ground `=>1` target);
  `truncated=true` with a tiny `interpreter_max_solutions`.

**Integration with previous work.** Completes the six-command surface from Steps 3–4; the final
description matches the implemented behavior.

**Demo.** One call matches a pattern against the current term and then searches from the original
term; a capped search returns `truncated=true`.

---

## Step 6: Documentation, release bookkeeping, full validation

**Objective.** Ship the tool with accurate user documentation and a clean full validation run.

**General implementation guidance.**

- `README.md`: add `maude_run` to the tool list with a short example (“reduce a term, rewrite the
  result”); update the env-var table (renamed diagnostics timeout, interpreter timeout, five caps
  plus the output cap) and the timeout semantics note (best effort, covers startup).
- `docs/modules.md`: add `harold_mcp.maude.capture`, `harold_mcp.maude.session`,
  `harold_mcp.server.tools.interpreter`.
- `CHANGELOG.md`: new section; call out the env-var rename and the tool.
- `pyproject.toml`: bump to `0.1.0` (from `0.0.5.dev0`).
- Suggest a `.agents/summary/` refresh and `AGENTS.md` convention updates (timeout rename, new
  modules, worker-op split) in the final message.
- Run `UV_CACHE_DIR=/tmp/uv-cache make check`, `make test`, and `make docs-test` (or
  `make release`).

**Test requirements.** No new functionality; `make docs-test` must stay strict-green and the full
suite must pass. If any doc example is executable/doctested, add it here.

**Integration with previous work.** Documents exactly the implemented behavior; no orphaned
settings or undocumented modules.

**Demo.** `make release` green; the MkDocs site documents the new tool and modules; the README
configuration table matches `Settings`.
