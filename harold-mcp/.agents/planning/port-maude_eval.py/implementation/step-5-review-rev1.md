# Review — Step 5: `match` and `search`, final tool description

Diff: [`../changes-39ac7135-2001-4e86-8bb7-587fa17cecfc.diff`](../changes-39ac7135-2001-4e86-8bb7-587fa17cecfc.diff)

What this change does: Step 5 adds the `match` and `search` commands to `maude_run`,
completing the six-command surface. The worker session engine parses the subject and the
pattern under one stream capture, maps `depth` to `maxDepth` (default `-1`) and the five
search types to Maude's constants, caps both iterations at `max_solutions` (consuming one
extra item to set `truncated`), and leaves the current term unchanged. The tool side adds
the `MatchStep`/`SearchStep` input models, the `MaudeBinding`/`MaudeMatch`/
`MaudeSearchSolution` result models, the subject/threading validation rules, the final
design §4.8 description (with the absolute-path requirement, mirrored on the diagnostics
tool), a research probe with transcript, an `assoc_match.maude` fixture, and unit plus
integration tests.

I assumed the load from the repo docs: one agent-driven client, at most 3 concurrent
worker processes, one fresh interpreter per call (same assumption as the Step 4 review).
The change adds no shared state; the one scale-sensitive point is finding 1.

## What I verified

- The live server (which runs this working tree) returns the design §5.2 semantics for
  `search`: `one-step` from `c(0)` at depth 2 → `c(1)`; `at-least-one-step` → `c(1)`,
  `c(2)`; `any-steps` → `c(0)` (0 rewrites), `c(1)`, `c(2)`; `match c(N)` on `c(5)` →
  `N=5`, `truncated=false`, `term=null`. This behaviorally pins search constants 0–2.
- Threading matches R5 and the design table: `match`/`search` use `subject` or the
  current term, never set one, and `_validate_step_threading` enforces exactly that
  (a match step does not create a current term for a later rewriting step).
- The plan's Step 5 test requirements are all present: pattern required, threading rules,
  adapter tests, match hit/miss, the three depth modes on an assoc module, all five search
  types with a ground `=>1` target, and both truncation caps.
- The probe, its transcript, the probes README and `term-api.md` §4 are consistent with
  each other and with the code (`str(variable)` prints the bare name).
- Every caller of the changed symbols was checked: `CommandName`/`RewritingCommand`
  docstrings, the widened `MaudeStep` union, the new `BindingDict`/`SolutionDict` exports,
  and the `_outcome` signature change; the MCP smoke test asserts property names and now
  also the absolute-path wording, and the diagnostics smoke test asserts phrases that the
  description change did not touch.

## Must fix

1. **`match`/`search` results are never length-checked: `too-large` is unreachable and the
   response size is unbounded** (`src/harold_mcp/maude/session.py:227-295`, call site
   `session.py:329-337`)
   - **What this is:** `_run_rewriting` serializes its result and rejects it with a
     `too-large` outcome when it exceeds `max_result_length` (`session.py:200-207`).
     `_run_match_or_search` does not receive `max_result_length` at all: every solution
     term and every binding value is serialized with `str()` and shipped regardless of
     size.
   - **Problem:** The design requires the check on every step ("serialize terms with
     `str(term)`, check lengths (R7); exceeding → outcome `too-large`", §4.3 step 7) and
     promises "the total response size is bounded by `max_solutions × max_result_length`
     per step" (Appendix D). Concrete case: a `rewrite` step legally produces a current
     term of ~1,000,000 chars, then `match` with pattern `X` and `depth=0` or `2147483647`
     returns up to 200 substitutions whose values are subterms of that subject — order
     200 MB of text in one outcome, pickled across the process boundary, adapted into
     pydantic models and JSON-serialized into the MCP response. For `search` it is worse:
     solution terms are produced by rewriting *inside* the search, so they are not even
     bounded by the input size. This breaks single-user usage, not just load.
   - **Fix:** Pass `request["max_result_length"]` into `_run_match_or_search` and, after
     building the items, return the `too-large` outcome (with `limit=max_result_length`)
     when any serialized solution term or binding value exceeds the cap — the same check
     `_run_rewriting` already performs. `run_session` already stops the run on a non-`ok`
     status. Add one integration test with a tiny `max_result_length` (e.g. match
     `c(N)` on `c(1000000000)` with `max_result_length=5`).
   - **If we skip it:** One call can return hundreds of megabytes, spiking server memory
     and producing an MCP message no client can read; the caps the user explicitly asked
     for (Q6) silently do not apply to two of the six commands.

2. **The diff untracks the committed `update-changelog-for-release` skill and gitignores
   `.agents/skills`** (diff hunks for `harold-mcp/.gitignore`,
   `harold-mcp/.agents/skills/update-changelog-for-release/SKILL.md`, root `.gitignore`)
   - **What this is:** Besides the Step 5 work, the diff (all uncommitted work) deletes
     the committed skill from the index, adds `.agents/skills` to `harold-mcp/.gitignore`
     and `.opencode` to the root `.gitignore`. The file still exists on disk; it would
     simply stop being version-controlled.
   - **Problem:** This contradicts committed documentation that other processes depend on:
     `harold-mcp/AGENTS.md` ("`.agents/skills/` — committed agent skills;
     `update-changelog-for-release/` documents the changelog step of the release
     process"), `DEVELOPER_GUIDE.md` release process step 1 ("Use the skill
     `update-changelog-for-release`"), `CHANGELOG.md` and `.agents/summary/workflows.md`
     / `review_notes.md`. On a fresh clone the skill would not exist while the release SOP
     still references it. It also has nothing to do with Step 5's objective, and the step
     notes do not record it as a decision.
   - **Fix:** Revert these three hunks from this change. If the intent is to stop tracking
     skills, do it as its own change together with the AGENTS.md / DEVELOPER_GUIDE /
     summary updates it requires — Step 6 (documentation and release bookkeeping) is the
     natural place.
   - **If we skip it:** The step lands mixed with an unexplained convention break, and the
     documented release procedure breaks for anyone cloning the repo.

## Should fix

3. **A failing pattern or subject parse in `match`/`search` is untested**
   (`src/harold_mcp/maude/session.py:244-253`)
   - **What this is:** `_run_match_or_search` parses the subject and then the pattern;
     either failing must produce a `parse-error` outcome with the stderr-derived message.
   - **Problem:** Every existing parse-error test (unit and integration) uses a `reduce`
     term; no test feeds a bad pattern (e.g. `pattern="nope("`) or a bad subject to a
     match/search step. If a refactor drops the `pattern is None` check, `match(None, …)`
     raises inside the worker and every suite stays green while the tool turns a user
     error into a whole-call failure.
   - **Fix:** Add one step to an existing session integration test:
     `_step("match", pattern="nope(", subject="c(5)")` and assert
     `status == "parse-error"` with `"no parse"` in the message.
   - **If we skip it:** A parser branch — the riskiest kind — is protected only by
     accident.

4. **The `normal-form` and `branch` constants are pinned only by a comment**
   (`src/harold_mcp/maude/session.py:32-38`)
   - **What this is:** `_SEARCH_TYPES` spells out Maude's constants 0–4 because the server
     process must not import the bindings (correct decision, documented in the notes).
   - **Problem:** Constants 0–2 are behaviorally pinned by the integration test and by my
     live check, but `normal-form` (3) and `branch` (4) both yield `[]` on the counter
     fixture at depth 2, in the probe and in the test. Swapping 3 and 4 in the dict passes
     every test while silently returning branch searches for `normal-form` and vice
     versa.
   - **Fix:** One small integration test that imports the real bindings and asserts the
     mapping, e.g. `assert _SEARCH_TYPES == {"one-step": maude.ONE_STEP, ...,
     "normal-form": maude.NORMAL_FORM, "branch": maude.BRANCH}`. Two lines, pins the
     transcription forever.
   - **If we skip it:** A future retyping of the dict ships wrong search semantics for
     two of the five types with no test failing.

5. **`depth` outside the int32 range becomes an opaque whole-call error**
   (`src/harold_mcp/server/tools/interpreter.py:118-120`)
   - **What this is:** `_PatternStep.depth` is an unconstrained `int | None`, forwarded to
     the SWIG `maxDepth`/`depth` parameters, which are C++ `int`s.
   - **Problem:** A client that sends `depth=3000000000` (an easy guess when "anywhere" is
     2147483647 and the audience is LLM agents) makes the SWIG typemap raise
     `OverflowError` inside the worker; the safety net maps it to
     `MaudeRunError("Unexpected failure running the Maude interpreter session")` — a
     whole-call error with no hint of which input was wrong, instead of the per-step or
     validation error the design's error table promises for bad input.
   - **Fix:** Constrain the field to the documented domain:
     `Annotated[int | None, Field(ge=-1, le=2147483647)]` — the design (R6, Appendix D)
     defines depth as exactly `-1`, `0`, `INT_MAX` and intermediate values. One line; the
     design's raw-integer exposure is unchanged.
   - **If we skip it:** Agents that guess a big depth get an unactionable error and burn a
     whole hermetic call on it.

## Nice to have

6. **Stale implications paragraph above the new probe text**
   (`research/term-api.md:108-111`)
   - **What this is:** Step 5 added a probe paragraph to §4, but the "Implications"
     paragraph below it still says "v1 also offers an optional `with_extension` flag
     mapping to `maxDepth=0`. Arbitrary depth matching (`UNBOUNDED`) is deferred."
   - **Problem:** The implemented tool exposes `depth` (including `2147483647`) and no
     `with_extension` flag — the design R6 explicitly rejected it. The research note now
     contradicts both the design and its own new paragraph.
   - **Fix:** Update the two sentences to the design's decision (depth covers all three
     modes; no `with_extension`).
   - **If we skip it:** The next reader of the research record gets the wrong input
     surface.

7. **Threading error messages say "first" even when the failing step is not first**
   (`src/harold_mcp/server/tools/interpreter.py:302-311`)
   - **What this is:** Both rejection messages end with "the first match/search step must
     provide an explicit subject" / "the first step must provide an explicit term".
   - **Problem:** Before Step 5 these errors could only fire on step 0, so "first" was
     accurate. Step 5 made them reachable later: `[match(subject="s"), match()]` reports
     "Step 1 … the first match/search step must provide an explicit subject" although
     step 0 did provide one and the real rule is that only rewriting steps create a
     current term.
   - **Fix:** Drop the "first" clause, e.g. "a match/search step needs an explicit subject
     unless a rewriting step already produced a current term" (same for the term variant;
     `test_match_does_not_create_a_current_term` matches only "Step 1 has no term", so it
     stays green).
   - **If we skip it:** An LLM client following the message's advice still cannot fix its
     request.

8. **`MaudeStepOutcome.status` docstring narrows `parse-error` to "the term"**
   (`src/harold_mcp/server/tools/interpreter.py:220`)
   - **What this is:** The output-schema description says `parse-error` means "the term
     did not parse".
   - **Problem:** Since this step, the pattern or the subject can be the failing input
     too; the tool description already says "a term, pattern or subject".
   - **Fix:** One line: "a term, pattern or subject did not parse".
   - **If we skip it:** Schema text slightly understates the failure cause; no behavior
     impact.

## Verdict

Verdict: fix 1 and 2 first.

Not checked: I could not run `make check` or the test suites in this session (no shell
approval); green suites and type checks are taken from the plan's implementation notes.
The `normal-form`/`branch` values (3, 4) could not be confirmed against the installed
wheel (no venv or `maude-bindings` checkout visible from the workspace); they rest on the
documented bindings table in `term-api.md` §5 — that is finding 4.
