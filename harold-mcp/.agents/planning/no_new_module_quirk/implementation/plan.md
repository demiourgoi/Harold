# Implementation plan — fixing the deferred `q .` warning quirk via per-call interpreter isolation

Checklist (tick as each step lands):

- [x] Step 1: fixtures + failing regression tests (red)
- [x] Step 2: `max_tasks_per_child=1` + test-suite rework (isolation/race green)
- [x] Step 3: `HAROLD_MAUDE_WORKERS` default change
- [x] Step 4: dependency-warning misattribution fix (worker + provider)
- [x] Step 5: path absolutization in `SourceFile.from_path`
- [ ] Step 6: tool description + README + CHANGELOG
- [ ] Step 7: maude-bindings bug report artifact
- [ ] Step 8: full validation + knowledge-base refresh

The plan follows the design in [`../design/detailed-design.md`](../design/detailed-design.md).
Every step ends with a demoable, working increment; tests are written before or
alongside the code they cover (red-green-refactor). Commands use the Makefile
(`UV_CACHE_DIR=/tmp/uv-cache make …` inside a sandbox, per `AGENTS.md`).

---

## Step 1: fixtures + failing regression tests (red)

Objective: pin the bugs as failing tests before any production change.

1. Add fixtures to `tests/integration/fixtures/`:
   - `quit_command.maude` — `red in NAT : 1 + 2 .` + `quit .`;
   - `q_with_trailing_text.maude` — `red in NAT : 1 + 2 .`, `q .  foo bar`, and a
     trailing `fmod` whose commands must never be parsed anywhere;
   - `dep_q.maude` (`red …` + `q .`) and `loads_dependency_q.maude`
     (`load dep_q.maude .` + a small fmod);
   - `dep_clean.maude` (clean module) and `loads_dependency.maude`
     (`load dep_clean.maude .` + a fmod using it);
   - `dep_bad.maude` (module with a syntax problem) and `loads_bad_dependency.maude`;
   - `loads_missing_dependency.maude` (`load missing.maude .` + `including NOPE`).
2. Write the new integration tests in `tests/integration/test_diagnostics_integration.py`
   (design §7.2–7.4): the four isolation tests, the race test
   (`test_parallel_diagnostics_do_not_share_interpreter_state` with the
   interpreter-clean set extended to the new clean fixtures), and the three dependency
   tests. The isolation tests run on the shared module-scoped `executor` fixture; the
   race test uses its own `MaudeExecutor(settings=Settings(maude_workers=2))`.
3. Run `UV_CACHE_DIR=/tmp/uv-cache make test -k` targeted at the new tests →
   **red**: isolation tests fail with a spurious `syntax error` on `hello.maude`; the
   race test fails deterministically; the `loads_bad_dependency` test fails with the
   misattributed warning. The pre-existing suite (with the `heuristic_executor`
   workaround) stays green.

Demo: `pytest tests/integration/test_diagnostics_integration.py -k "contaminate or parallel_diagnostics or dependency"` shows exactly the bugs from the planning README failing for the right reasons.

### Implementation notes (Step 1)

Done as planned, with three notable details:

- **Test placement moved earlier than the plan implied.** The new tests are inserted right
  after `test_non_recoverable_program` (before `test_program_without_modules`), not after
  the heuristic tests. Reason: the red phase runs on a shared warm worker, and
  `test_program_without_modules` schedules residue that would contaminate the new
  *pin* tests (clean dependency / missing dependency) that must stay green throughout.
  With this order every new red failure is self-contained (q-file → clean file in the
  same test). The race test keeps its own 2-worker pool, so it is position-independent.
- **New bug found while writing the fixtures (in scope for Step 4).**
  `loads_bad_dependency.maude` produced only one parsed warning: the raw stderr has
  `Warning: "dep_bad.maude", line 9 (fmod DEP-BAD) : unexpected end of tokens.` and
  `_WARNING_RE` requires `):` with no space, so any warning with `) :` is silently
  dropped. The new misattribution test pins the corrected expectation (2 warnings), so
  Step 4 must now also relax the regex (`\)\s*:`) — a scope addition to an already
  touched line, flagged here as a deviation.
- **Missing-dependency pin-test asserts messages, not Maude's line numbers.** Maude's
  lazy-compilation line reporting shifts some warnings (the `load` warning points at
  the line *after* the `load` statement); the test pins the three exact messages and
  the "positioned, not whole-file" attribution instead of the raw line numbers.

Observed red/green split on the current code: 6 red — the four isolation tests
(`syntax error` on `hello.maude` in each; the trailing-text case also leaks
`foo`/`bar`/`NoSuchSort`), the misattribution test (`1 != 2` warnings) and the race
test (6–7 spurious findings across the clean fixtures) — and 2 green pins (clean and
missing dependencies). The full integration suite is `6 failed, 36 passed`, i.e. every
pre-existing test (with the `heuristic_executor` workaround) still passes. New
scratch records: `scratch_fixture_dump.py`, `scratch_dep_raw.py`, `scratch_dep_raw2.py`.

## Step 2: `max_tasks_per_child=1` + test-suite rework (green for isolation/race)

Objective: apply option A and remove the workaround.

1. `src/harold_mcp/maude/executor.py::_default_executor` — add
   `max_tasks_per_child=1` to the `ProcessPoolExecutor(...)` call; update the class
   docstring (per-task process recycling; `start()` keeps its fail-fast role but no
   longer warms anything; session semantics gone).
2. `tests/integration/test_diagnostics_integration.py` — delete the
   `heuristic_executor` fixture and its comment; point its users at `executor`.
3. `tests/integration/test_maude_executor_integration.py` —
   `test_two_workers_are_used_for_parallel_diagnostics`: measure the per-task init
   cost first (`time` a `diagnostics("hello.maude")`), then run the two sleeps and
   assert two distinct pids and `elapsed < init_cost + 1.5` (each sleep now pays
   spawn+init before its 1 s sleep; the bound still proves parallelism).
4. Run the full integration suite → the isolation tests, the race test, and the
   workaround-free heuristic tests are **green**; `test_dependency_warnings_are_attributed_to_the_dependency` stays red (fixed in Step 4).

Demo: `make test` — integration suite green except the one dependency-attribution test; `scratch_race.py`-equivalent test passes with 2 workers.

### Implementation notes (Step 2)

Done as planned for the isolation fix and the workaround removal, with two deviations:

- **`max_tasks_per_child=1` and docstrings**: `_default_executor` now recycles the
  worker after every task; the class and `start()` docstrings state that calls are
  hermetic (fresh interpreter per call) and that the warm-up pings are a fail-fast
  check rather than a warm-up. `heuristic_executor` is gone; all heuristic tests share
  `executor`.
- **Deviation — two-workers test uses interval witnesses, not a wall-clock budget.**
  The planned "measure the init cost, assert `elapsed < init_cost + 1.5`" is unsound
  with recycling: the pool eagerly keeps pre-initialized replacement processes, so a
  measured init cost is not what a task actually pays (it can measure ≈0, making the
  budget too tight for the two sleep tasks). Instead, `worker.sleep_witness(seconds)`
  (new test-support helper next to `sleep`) returns the pid plus the task's monotonic
  start/end; the test asserts two distinct pids and that the two intervals overlap
  (`max(starts) < min(ends)`). Deterministic, and independent of spawn+init jitter.
- **Deviation (per user request during verification) — suite trim + Makefile targets.**
  No integration test was converted to a unit test; only coverage overlaps *between
  integration tests* were removed:
  - `tests/integration/test_maude_executor_integration.py` shrank to its unique
    coverage (real concurrent execution across workers). Removed: the four fixture
    round-trips (the same fixtures are asserted with exact raw shapes at the worker
    level in `test_maude_worker_integration.py` and end to end at the tool level) and
    the crash test (duplicated verbatim by `test_tool_reports_crash_and_recovers`,
    which additionally asserts the chained error vocabulary). The module docstring
    points at where the coverage lives.
  - Removed `test_tool_with_parallel_workers`: the race test exercises concurrent tool
    calls on a 2-worker pool with per-file result routing, and `test_recoverable_program`
    asserts the same fixture's result.
  - `Makefile`: new `test-unit` (fast, no Maude interpreter) and `test-integration`
    targets for quick iteration; `make test` keeps the full coverage flags.

Verification: the user's manual full-suite run before the trim was `1 failed, 213
passed in 76.28s` — the single failure is the Step-4 red
(`test_dependency_warnings_are_attributed_to_the_dependency`, `1 != 2` warnings), so
Step 2's goal is met (all four isolation tests, the race test and the pre-existing
suite are green). After the trim: `make test-unit` 172 passed (1.6 s), the reworked
two-workers test passed (6.5 s), and the tool file collects 27 tests. A full-suite
re-verification happens at Step 8.

## Step 3: `HAROLD_MAUDE_WORKERS` default change

Objective: the new default formula.

1. `src/harold_mcp/settings.py` — `_default_maude_workers()` returning
   `max(1, min(3, (os.cpu_count() or 0) // 2))`; `maude_workers` uses
   `Field(default_factory=_default_maude_workers, gt=0)`; update the class docstring
   (formula, transient workers, ≈100 MB/process during bursts).
2. `tests/unit/test_settings.py` — update `test_defaults` to the formula; add a
   monkeypatched `os.cpu_count` matrix (12 → 3, 4 → 2, 2 → 1, `None` → 1).

Demo: `pytest tests/unit/test_settings.py` green; `HAROLD_MAUDE_WORKERS` still overrides (existing tests unchanged).

### Implementation notes (Step 3)

Done exactly as planned, no deviations:

- `src/harold_mcp/settings.py`: `_default_maude_workers()` returns
  `max(1, min(3, (os.cpu_count() or 0) // 2))`; `maude_workers` uses
  `Field(default_factory=..., gt=0)` (env override and validation unchanged); class
  docstring notes the formula and that the cap bounds concurrent per-call interpreters
  (≈100 MB each), not warm workers.
- `tests/unit/test_settings.py`: `test_defaults` now asserts the formula against the
  live `os.cpu_count()` (env-independence), and the new
  `test_workers_default_scales_with_cpu_count` pins the matrix via a monkeypatched
  `os.cpu_count`: 12→3, 8→3, 4→2, 2→1, 1→1, `None`→1.

Verification: `make test-unit` 173 passed (1.9 s); `make check` fully green (ruff,
lockfile, mypy, basedpyright, deptry). README/CHANGELOG references to the old default
are updated in Step 6.

## Step 4: dependency-warning misattribution fix (worker + provider)

Objective: honest attribution of dependency warnings, with the run-diagnostics suggestion.

1. `src/harold_mcp/maude/worker.py` — `WarningDict` gains `file: str`;
   `_WARNING_RE` gains a filename capture group; `_parse_warnings` fills it
   (`<standard input>` included).
2. `src/harold_mcp/maude/provider.py` — attribution rule per design §4.5: own-file and
   `<standard input>` warnings as today; foreign files become whole-file diagnostics
   (`line=None`) with
   `In "{file}", line {line}: {message}. Run maude_program_diagnostics on "{file}" (resolved relative to the diagnosed file's directory) for details.`
3. Unit tests: `tests/unit/test_maude_worker.py` (filename parsing, including
   `<standard input>`) and `tests/unit/test_maude_provider.py` (foreign → whole-file +
   message; own-file unchanged).
4. `test_dependency_warnings_are_attributed_to_the_dependency` → **green**; assert the
   message names `dep_bad.maude`, its line, and the run-diagnostics suggestion.

Demo: `pytest tests/integration/test_diagnostics_integration.py` fully green (first time since Step 1).

### Implementation notes (Step 4)

Done, plus the flagged regex scope addition; one extra fix surfaced during verification:

- **Worker**: `WarningDict` gained `file`; `_WARNING_RE` gained the filename capture
  group and the relaxed colon (`\s*:`) for the `(fmod X) :` spelling (the Step-1 scope
  addition), with a comment documenting why the message group stays greedy and last.
- **Provider**: own-file and `<standard input>` warnings keep their line (the latter is
  Maude's attribution of some first-line/broken-parse warnings, and it is exactly what
  the tool must map back to the diagnosed file — verified against real data:
  `broken-non-recoverable.maude` has its first two warnings under
  `<standard input>`); any other file becomes a whole-file diagnostic with the
  `In "file", line N: … Run maude_program_diagnostics on "file" (resolved relative to
  the diagnosed file's directory) for details.` message (attribution rule extracted to
  `InterpreterDiagnosticProvider._to_diagnostic`).
- **Extra fix found during verification — message punctuation.** Maude's
  `no parse for statement` carries no trailing period, so the suggestion ran on
  (`…statement Run maude_program_diagnostics …`). `_dependency_message` now appends a
  period when the message lacks final punctuation; both variants are unit-tested.
- **Tests**: unit tests updated for the `file` field plus new cases
  (`test_context_fragment_with_space_before_the_colon`;
  `test_standard_input_warning_is_attributed_to_the_diagnosed_file`;
  `test_dependency_warning_becomes_a_whole_file_diagnostic`;
  `test_dependency_warning_without_line_omits_the_line`); worker integration
  expectations updated with the real `file` values; the tool-level fakes updated so
  their warnings stay attributed to the diagnosed file.

Verification: `make test-unit` 177 passed; worker integration 5 passed; the full tool
integration file 27 passed (84.9 s — the race test dominates); lifespan 3 passed;
`make check` green. The Step-1 red `test_dependency_warnings_are_attributed_to_the_dependency`
is now green, and the previously dropped `unexpected end of tokens.` warning reaches
clients.

## Step 5: path absolutization in `SourceFile.from_path`

Objective: relative inputs can no longer break on the worker's fresh-process path resolution.

1. `src/harold_mcp/diagnostics/provider.py` — after the existing checks, store
   `source_path = source_path.resolve()`; update the `path` docstring ("made absolute").
   `resolve()` runs **after** `is_file()`, so missing files still raise
   `SourceFileNotFoundError`.
2. `tests/unit/test_diagnostics_seam.py` — relative input produces an absolute
   `SourceFile.path`; missing files still raise.
3. `src/harold_mcp/server/tools/diagnostics.py` — `MaudeProgramDiagnosticsResult.path`
   docstring: "The input path, made absolute."

Demo: `pytest tests/unit/test_diagnostics_seam.py` green; a relative-path tool call no longer yields the synthesized load error.

### Implementation notes (Step 5)

Done as planned, with one contract fix surfaced by the new integration test:

- `SourceFile.from_path` stores `Path.resolve()` **after** the `is_file()` pre-check
  (missing/directory/FIFO/unreadable inputs still raise `SourceFileNotFoundError` with
  the path as given); the seam and `from_path` docstrings now state the path is always
  absolute.
- `MaudeProgramDiagnosticsResult.path` docstring → "The input file path, made
  absolute"; the tool docstring's `Args:` line updated (relative paths are resolved
  against the server's working directory).
- **Contract fix**: the tool previously echoed the raw input (`_build_result(path, …)`);
  it now reports `str(source.path)`, i.e. the resolved absolute path, matching the
  documented "made absolute" contract. Found by the new test, not by inspection.
- Tests: new unit test `test_source_file_from_path_resolves_relative_paths` and a new
  integration test `test_relative_path_input_is_resolved_before_the_worker`
  (1 extra Maude call) that pins the end-to-end behavior — a fresh worker cannot
  resolve relative paths, so this is the regression guard for the isolation change.

Verification: `make test-unit` 178 passed; the selected tool integration tests
(relative path + clean program + without modules) green; `make check` green.

---

> **Addition outside the original plan (user request, after Step 5):** add
> `pytest-xdist`, make `make test-integration` parallel with auto-detected worker
> count, and verify stability. Recorded in the section at the end of this file.

## Step 6: tool description + README + CHANGELOG

Objective: the semantics change and new behavior are documented for clients.

1. `src/harold_mcp/server/tools/diagnostics.py` — rewrite the description prose:
   fresh interpreter per call (replaces "last load wins"); whole-load semantics
   (the file plus its `load`/`in` dependencies); dependency problems reported as
   whole-file diagnostics naming the dependency, with the suggestion to diagnose the
   dependency separately; keep sources/severity/fix/ordering text.
2. `tests/integration/test_diagnostics_integration.py::test_mcp_smoke` — extend the
   description assertions to the new sentences (e.g. "fresh" / "dependency").
3. `README.md` — env-var table: `HAROLD_MAUDE_WORKERS` default becomes the formula;
   refresh the tool description paragraph if it duplicates the docstring.
4. `CHANGELOG.md` — new version section (suggest `0.0.5`): isolation via
   `max_tasks_per_child=1` + fresh-per-call semantics, new workers default, path
   absolutization, dependency-warning attribution fix, test-suite rework. Update
   `pyproject.toml` `version` accordingly (confirm the bump with the user).

Demo: `make check` green; `harold-mcp --help` and the MCP smoke test show the new description.

## Step 7: maude-bindings bug report artifact

Objective: a ready-to-send GitHub issue for the bindings.

1. `.agents/planning/no_new_module_quirk/maude-bindings-issue.md` — title, environment
   (`maude==1.6.0` / Maude 3.5.1 / Python 3.14.2 / Linux), steps, minimal
   reproduction, expected vs actual (incl. the executable-residue and relative-path
   variants), impact, workaround (`max_tasks_per_child=1`), and the pointer that the
   documented `eof` already stops cleanly (the behavior the `q .` path should have).
2. `.agents/planning/no_new_module_quirk/repro_minimal.py` — standalone script: two
   temp files + fd-2 capture around two `maude.load` calls, printing the
   contamination.

Demo: `uv run python .agents/planning/no_new_module_quirk/repro_minimal.py` shows the
deferred warning landing in the next load's capture.

## Step 8: full validation + knowledge-base refresh

Objective: everything green and the repo's knowledge base honest.

1. `UV_CACHE_DIR=/tmp/uv-cache make release` (install, check, test, docs-test).
2. Update `.agents/planning/no_new_module_quirk/README.md` status line (fix
   implemented; point to this PDD record) and add the scratch scripts' names to the
   experiment table if useful.
3. Suggest to the user (per project Custom Instructions): re-run the codebase-summary
   skill to refresh `.agents/summary/` + `AGENTS.md`; confirm the `0.0.5` version
   bump and CHANGELOG section; consider the `update-changelog-for-release` skill when
   actually releasing.

Demo: full CI pass (`make release`) and an up-to-date planning record.
