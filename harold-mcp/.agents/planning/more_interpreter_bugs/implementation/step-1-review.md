# Review — Step 1 of `more_interpreter_bugs`: error model, formatter, and rich tool errors

Reviewed: the uncommitted working-tree changes (15 modified files, 2 new) against
`.agents/planning/more_interpreter_bugs/implementation/plan.md` Step 1 and the
normative design (`.agents/planning/more_interpreter_bugs/design/detailed-design.md`,
ER-1..ER-9, §4.5–4.7, §5.4, §6.1–6.5). Read-only review; `make release` confirmed
green by the user.

**What this change does:** Step 1 of the isolated-worker plan adds a stdlib-only
error formatter (`harold_mcp.errors`) that renders any exception as a bounded,
self-contained report — a stable `<category>: <message>` first line, a `context:`
line, a cycle-guarded cause chain, the originating traceback, and a truncation
marker — plus the `HAROLD_ERROR_DETAIL_MAX_CHARS` setting (default 4000) and the
final worker-error taxonomy (`category`/`context`/`remote_traceback` on
`MaudeWorkerError`; new spawn/remote/cancelled/protocol errors; `MaudeInitError`
re-based onto `MaudeWorkerError`). Both tools now return rich capped error text to
the client and log the uncapped report server-side; the diagnostics collection
error renders one bounded section per failing provider. The pool executor itself
is untouched (Step 3 replaces it).

**Plan compliance.** Every Step 1 item is implemented: the formatter and its
truncation order (traceback, then causes, then first-line message with the prefix
kept), the setting, the executor hierarchy with `reason` preserved, the
`_exception_detail` replacement in `maude_run` (uncapped log, capped raise,
per-step data untouched), the context line on every whole-call input error
(path/steps validation, missing file, missing module, theory module), the
provider-section rendering in `DiagnosticCollectionError`, the diagnostics tool
logging the full report and re-raising, and the provider wrap preserving the
chain plus path/phase context. The deviations (the additive `message=` keyword,
the `format_context`/`format_exception_text` helpers, construction-time
collection rendering with `format_report(max_chars)` re-rendering) are documented
in the step's Implementation notes with rationale, and each matches the design's
intent. The required tests all exist: `test_errors.py` covers first-line shapes,
category resolution, context-merge precedence, the cause chain with the remote
cause, the cycle guard, stored-exception rendering (no `NoneType: None`),
traceback selection, truncation order and marker, the huge-first-line last
resort, `max_chars <= 0`, and the no-secrets rule; `test_interpreter_tool.py`
covers all seven categories reaching the client, the capped text plus uncapped
log record, and the input errors keeping their messages with the context line;
the diagnostics tests cover the chain, the per-provider sections, the cap and
the uncapped re-render, and the unchanged all-or-nothing contract.

**Verification notes.** The truncation budget math is exact — each fallback step
lands on precisely `max_chars` (traceback step: `len(_with_marker(base)) + 1 +
budget`; cause step and last resort follow the same identity). The cause-chain
and traceback walks are cycle-guarded by identity, and `_traceback_text` walking
the chain for the first `remote_traceback` is what makes a wrapped provider
failure show the worker's traceback instead of the wrapper's raise site. The
re-basing of `MaudeInitError` onto `MaudeWorkerError` changes `maude_run`'s
generic branch to the specific `init-failure` branch — that is the design's B5
fix and it is parametrically tested. No caller of a changed signature was left
behind (`collect_diagnostics`, `DiagnosticProviderError`, `DiagnosticCollectionError`,
the executor errors, and `maude_program_diagnostics`' new `settings` parameter
were grepped across `src/`, `tests/`, `docs/` and `README.md`); the seam stays
stdlib-only (`errors.py` imports nothing from the package, `settings.py` imports
only the constant), and the server process still never imports `maude`. The
stale "replaces the worker pool" sentence in the `maude_run` description is a
documented Step 6 deferral, not a finding.

## Findings

### Must fix

None found.

### Should fix

None found.

### Nice to have

1. **Dead bounds-check in the traceback truncation step** (`src/harold_mcp/errors.py:114-116`)
   - **What this is:** The first truncation fallback computes
     `budget = max_chars - len(_with_marker(base)) - 1`, slices the traceback to
     it, and returns the report only `if len(report) <= max_chars`.
   - **Problem:** The budget math guarantees `len(report) == len(_with_marker(base)) + 1 + min(budget, len(traceback_section)) <= max_chars`, so the condition is always true and the branch can never fall through to the next fallback from there.
   - **Fix:** Return unconditionally: `if budget > 0: return _with_marker([*base, traceback_section[:budget]])`.
   - **If we skip it:** Nothing breaks; a future reader may assume the branch can fall through and "correct" the budget math.

2. **Two pre-check tests call the tool without `settings`** (`tests/unit/test_diagnostics.py:248`, `tests/unit/test_diagnostics.py:261`)
   - **What this is:** `test_missing_file_raises_before_touching_the_provider` and `test_unreadable_file_raises_before_touching_the_provider` call `maude_program_diagnostics(...)` without the new `settings=` argument, unlike every other call in the file.
   - **Problem:** They pass only because `SourceFile.from_path` raises before `settings` is read; the parameter's direct-call default is FastMCP's `Depends` marker object. If the tool body ever reads `settings` before the pre-check, these tests fail with `AttributeError: ... no attribute 'error_detail_max_chars'` instead of a clear failure.
   - **Fix:** Pass `settings=_settings()` in both calls, matching the rest of the file.
   - **If we skip it:** The tests keep passing today; a future reorder of the tool body turns them into an opaque failure.

## Verdict

Verdict: Ship.

Lean: -2 lines possible (finding 1).

Not checked: nothing — the review was read-only and the full gate (`make release`)
was confirmed green by the user.
