# Review — Step 4: Rewriting family and current-term threading

Diff: [`../changes-c87ee7ce-06ea-43f7-812c-5637cf04693f.diff`](../changes-c87ee7ce-06ea-43f7-812c-5637cf04693f.diff)

What this change does: It adds `rewrite`, `frewrite` and `erewrite` to the `maude_run` tool
(step 4 of the plan). The worker session engine runs all four rewriting commands through one
shared parse-and-capture path, forwards `bound`/`gas` with explicit `is not None` checks (so an
explicit `0` survives), and threads the current term: the mutated subject for
`reduce`/`rewrite`/`frewrite`, the returned term for `erewrite`. The tool side grows a
discriminated step union (each step class is tagged by `command`), a `bound` cap check, an
updated description, and unit plus integration tests for the new commands.

I assumed the load from the repo docs: single-agent IDE use, at most 3 concurrent worker
processes, one fresh interpreter per call. The change adds no shared state and no loops that
grow, so nothing here is scale-sensitive.

## What I verified

- The binding calls match the real SWIG signatures, checked against the local bindings source
  (`maude-bindings/swig/term.i`, `src/easyTerm.cc`): `rewrite(bound=-1)`,
  `frewrite(bound=-1, gas=-1)`, `erewrite(bound=-1, gas=-1)` returning a `(Term, int)` pair.
  Passing `-1` for an omitted `gas` is exactly the bindings' own default; the C++ maps
  `gas == NONE (-1)` to 1 per position, so omitted and default behave identically.
- Subject/result semantics match the design §5.2 table and the probe evidence in
  `research/term-api.md` (bound=3 on the counter reports 6 because equational rewrites are
  counted; `erewrite` leaves the original untouched). The integration expectations match the
  probe numbers.
- Every caller of the changed symbols was grepped: the removed `_CommandName`/`_StepStatus`
  aliases have no other users; the renamed session function `_reduce` → `_run_rewriting` has no
  stale references; the MCP smoke test asserts schema property names only, so the widened union
  does not break it.
- mypy and basedpyright are scoped to `src/` only (`pyproject.toml`), so the test helpers'
  loose typing (`command: str` building a `StepRequest`) is outside the checked surface.
- The new `counter.maude` fixture is loaded by the parallel-diagnostics glob test but is not in
  `INTERPRETER_CLEAN_FIXTURES`, so it cannot fail that test; it is a clean module.

## Should fix

1. **`gas` never reaches the real interpreter in any test** (`tests/integration/test_maude_session_integration.py:181-207`, code at `src/harold_mcp/maude/session.py:165-175`)
   - **What this is:** `gas` is a new input forwarded to a C++ API (`fairRewrite`). The unit
     test only checks the request dict against a fake executor; both integration steps
     (`frewrite`, `erewrite`) pass `gas=None`, which becomes `-1`, the binding default.
   - **Problem:** No test ever sends an explicit `gas` value through the worker to the
     interpreter. If the bindings mishandle a supplied gas (the design says `ge=0`, so `gas=0`
     is accepted input), or a future refactor drops or swaps the argument, every test stays
     green while the tool misbehaves for that input. The project's own
     `summary.md` ("Areas that may need refinement") flagged gas semantics to verify against
     the bindings; only the default path was verified.
   - **Fix:** Add one step with an explicit gas to the existing
     `test_rewriting_family_values_and_counters` (or a small sibling test), e.g.
     `_step("frewrite", "c(0)", bound=3, gas=0)`, and assert the term and counter (confirm the
     expected value against the interpreter when writing it; `gas=0` should mirror the
     `bound=0` test). One line plus the assertion.
   - **If we skip it:** A gas-related regression or bindings upgrade ships silently broken for
     clients that use `gas`.

## Nice to have

2. **Stale module docstring in the session integration tests** (`tests/integration/test_maude_session_integration.py:5-6`)
   - **What this is:** The module docstring still says "The session engine itself only supports
     `reduce` for now."
   - **Problem:** This step added `rewrite`/`frewrite`/`erewrite` to the engine, so the
     sentence is now false and misleads the next reader of exactly the file that tests the new
     commands.
   - **Fix:** Replace it with "supports the four rewriting commands so far" (one line).
   - **If we skip it:** Doc rot in the test suite; no behavior impact.

3. **Step 5 note understates the `_validate_steps` work** (plan Step 4 "Implications for later steps", code at `src/harold_mcp/server/tools/interpreter.py:222-241`)
   - **What this is:** The implications note says the session engine already leaves the current
     term unchanged for `match`/`search` (`outcome["term"] is not None`), which is correct.
   - **Problem:** It does not say that `_validate_steps` also needs rework in Step 5: today it
     rejects any first step whose `term` is `None` (a first `match` that supplies only its
     `subject` would be wrongly rejected), and it sets `has_current = True` after every step,
     which is only correct because all four current commands produce a term. Step 5's own test
     requirements mention "subject/threading rules", so the work is planned; only the pointer
     is missing.
   - **Fix:** Add one sentence to the implications note: "`_validate_steps` must learn the
     `subject` field and must not set `has_current` after `match`/`search` steps."
   - **If we skip it:** Risk that Step 5 implements the engine side and misses the validator,
     letting a valid first `match` step fail validation (or an invalid pipeline pass it).

## Verdict

Verdict: fix 1 first, then ship.

Not checked: I could not run `make check` or the test suites in this session (no shell
approval), so the green suites and type-checker pass are taken from the plan's implementation
notes, not re-run. Binding signatures were verified against the local `maude-bindings` 1.5.0
source; the installed wheel is 1.6.0 (the research notes state the signatures match, and the
integration expectations match the 1.6.0 probe transcripts).
