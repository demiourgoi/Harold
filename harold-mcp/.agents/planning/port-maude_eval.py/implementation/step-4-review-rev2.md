# Review — Step 4 rev2 (the reviewed diff contains the Step 5 work)

Diff: [`../changes-99600a55-87e7-4a15-9089-55a200b7e4a4.diff`](../changes-99600a55-87e7-4a15-9089-55a200b7e4a4.diff)
(while this review ran, the four identical `changes-*.diff` snapshots in the planning directory were
consolidated into [`../changes-39ac7135-2001-4e86-8bb7-587fa17cecfc.diff`](../changes-39ac7135-2001-4e86-8bb7-587fa17cecfc.diff);
the content is the same, and this review covers that content).

What this change does: The diff implements plan **Step 5**, not Step 4: it adds `match` and `search`
to `maude_run`. The worker session engine (`_run_match_or_search`) parses a subject and pattern under
one output capture, runs Maude's match/search iterators capped at `max_solutions` (one extra item is
consumed to set `truncated`), and never changes the current term. The tool side adds the
`MatchStep`/`SearchStep` input models, subject/threading validation, the `matches`/`solutions`/
`truncated` outcome fields, the final six-command tool description (plus an absolute-path wording
change in both tools), a new probe with transcript, and unit plus integration tests. It also deletes
the `update-changelog-for-release` agent skill and ignores `.agents/skills`.

**The diff/step label does not match.** The task calls this "implementation step 4", but plan Step 4
(rewriting family) is already complete in the diff's base — `RewriteStep`/`_run_rewriting` appear as
unchanged context — and the diff itself marks the Step 5 checklist item done and adds the Step 5
implementation notes. I therefore did both jobs: (a) re-checked the Step 4 state in the tree as a
rev2 (all rev1 findings are fixed — evidence below), and (b) reviewed the diff's actual changes
against design §4.3/§5. Findings 1 and 4–7 are about the Step 5 changes.

I assumed the load from the repo docs: single-agent IDE use, at most 3 concurrent worker processes,
one fresh interpreter per call. The only scale-sensitive finding is 1.

## Step 4 rev1 fixes — all present in the tree

1. `test_explicit_gas_reaches_the_interpreter`
   (`tests/integration/test_maude_session_integration.py:215-232`) sends `gas=0` through the worker
   for both `frewrite` and `erewrite` and asserts the unchanged term and zero rewrites — a dropped
   `gas` would default to 1 and reach `c(3)` with 6 rewrites. Fixed.
2. `probe_term_ops.py:80-87` runs the explicit gas 0/1/2 matrix for both commands; the regenerated
   transcript records `frewrite(3, gas=0) | steps: 0 | term after: 'c(0)'` and `gas=1` → 6 / `c(3)`.
   Fixed.
3. The session integration docstring now says the engine "supports the rewriting family and the
   `match`/`search` commands" (no longer "only supports `reduce`"). Fixed.
4. The plan's Step 4 implications note records that `_validate_steps` must learn `subject` and must
   not set `has_current` after `match`/`search`; Step 5 implemented exactly that. Fixed.

Nothing new to report against the Step 4 code paths (`_run_rewriting`, the bounded/gassed step
models, the bound cap, the threading validator). Note that the rewriting family is also the one
path that *does* enforce the result-length cap — which is what makes finding 1 a gap in the new
commands, not in Step 4.

## What I verified

- Live runs through the running MCP server (which serves this code; every call is a fresh
  interpreter, read-only): all five search types on `counter.maude` — one-step `[c(1)]`,
  at-least-one-step `[c(1), c(2)]`, any-steps `[c(0), c(1), c(2)]` with 0 rewrites for the initial
  state, normal-form `[]`, branch `[]`; normal-form vs branch distinguished with a canonical subject
  (`0`, which the `inc` rule cannot rewrite): normal-form → `[0]`, branch → `[]`; the `match` depth
  modes on `assoc_match.maude` (omitted → no extension match, `0` → `X=3`, `2147483647` → a ground
  pattern matches inside the sequence and through `wrap`); a bad pattern → `parse-error` with
  `bad token … / no parse for term.` and stop-at-first-failure; a rewrite → match → search pipeline
  threading the current term exactly as the new integration test asserts.
- `_SEARCH_TYPES` (0..4) matches the constant table in `research/term-api.md` §5 and the live
  behavior above.
- Read `session.py`, `interpreter.py`, `capture.py`, `settings.py`, the three touched test files and
  the fixtures; the `_to_step_request`/adapter mappings cross-check against the worker TypedDicts;
  `capture_streams` restores both fds in `finally`, so the `ValueError`s raised inside `execute()`
  cannot leak a redirected fd.
- `assoc_match.maude` loads with zero warnings (live) and is not in `INTERPRETER_CLEAN_FIXTURES`, so
  the parallel-diagnostics glob test makes no claim about it.
- The new tests' expected values match the live interpreter behavior I observed (I could not run
  pytest itself).

## Must fix

1. **`match`/`search` results bypass `max_result_length`** (`src/harold_mcp/maude/session.py:227-295`, call site `:323-337`)
   - **What this is:** `max_result_length` (default 1,000,000 chars) is the cap on any returned
     term; a longer result must become a `too-large` step outcome. `_run_rewriting` enforces it, but
     `_run_match_or_search` never receives the value — the call site passes only `max_solutions` and
     `max_output_length` — so match binding values and search solution terms are serialized with
     `str()` and returned uncapped, and `too-large` can never occur for these two commands.
   - **Problem:** Design §4.3 makes the length check part of every step ("serialize terms with
     `str(term)`, check lengths (R7); exceeding → outcome `too-large`"), §4.1 and the `Settings`
     docstring say the cap applies to "any returned term", and Appendix D bounds the response at
     `max_solutions × max_result_length` per step. Concrete case: a module whose rule has a
     multi-megabyte right-hand side (a normal, loadable file — the file itself is never
     length-capped); `search one-step` from its left-hand side with a variable pattern returns that
     term, and up to 200 such solutions, with no cap and no `too-large`. For `match`, values are
     pieces of the subject, so the 100k input cap incidentally bounds them; for `search`, reached
     states can be arbitrarily larger than the subject. The plan's Step 5 guidance does not repeat
     the check, which is likely why it was missed — the design still requires it.
   - **Fix:** Pass `request["max_result_length"]` into `_run_match_or_search` and check each
     serialized string (solution terms and binding values) as it is built; on exceed, return the
     `too-large` outcome with `limit`, mirroring `_run_rewriting`. Add one session integration test
     with a tiny cap (mirror `test_too_large_result_is_an_outcome`).
   - **If we skip it:** One valid-but-unusual module makes the tool return a response far past every
     documented limit; the LLM client chokes on it and worker/server memory spikes.

## Should fix

2. **The review trail points "step 4 rev2" at the Step 5 diff** (plan checklist hunk in the diff; this file's name)
   - **What this is:** This diff contains none of the Step 4 work (see the header above); the Step 4
     rev1 fixes were already committed before its base.
   - **Problem:** A future reader cannot reconstruct what "step 4 rev2" approved: the file will
     document Step 5 changes under a Step 4 name. A `step-5-review-rev1` session also appears to be
     running on the same diff content (`implementation/step-5-review-rev1.log`), so findings 1 and
     4–7 may be reported twice.
   - **Fix:** Keep this file as the Step 4 rev2 sign-off (the "Step 4 rev1 fixes" section above is
     that record) and let the step-5 review carry the Step 5 findings; add one line to the plan's
     "Step 4 review rev1 fixes" note naming this file, and dedupe overlapping findings before
     applying fixes.
   - **If we skip it:** The PDD record says a "step 4 rev2" approved a Step 5 diff — the next agent
     that reads the trail inherits the confusion.

3. **Unrelated skill deletion and `.gitignore` changes break documented references** (diff hunks: deleted `.agents/skills/update-changelog-for-release/SKILL.md`; `harold-mcp/.gitignore:4` adds `.agents/skills`; root `.gitignore` adds `.opencode`)
   - **What this is:** The diff deletes a committed agent skill from version control and ignores the
     directory, plus ignores `.opencode` at the repo root.
   - **Problem:** None of this belongs to Steps 4/5 and the plan's implementation notes do not
     record it, while live references now dangle: `DEVELOPER_GUIDE.md:170` tells the release process
     to "Use the skill `update-changelog-for-release`", `AGENTS.md:138` calls `.agents/skills/`
     committed agent skills, and `.agents/summary/workflows.md:158` and `review_notes.md:100` point
     at it. Step 6 (release bookkeeping) is next and its documented process starts from that skill.
   - **Fix:** Either drop these three hunks from the change, or keep them and record the decision in
     the plan while updating the four references (naturally Step 6 work if the deletion is intended).
   - **If we skip it:** The next release follows a documented process whose first step no longer
     exists.

4. **The test suite cannot tell `normal-form` from `branch`** (`src/harold_mcp/maude/session.py:32-38`; `tests/integration/test_maude_session_integration.py:316-355`)
   - **What this is:** `_SEARCH_TYPES` hardcodes Maude's search-type constants (0..4) because the
     server process must not import the bindings. The values are right (they match the
     `term-api.md` §5 table and my live runs), but `test_search_types_and_ground_targets` asserts
     `[]` for both `normal-form` and `branch` on the counter fixture, where both are legitimately
     empty.
   - **Problem:** A transcription error (or a future bindings renumbering) that swaps exactly those
     two entries passes the whole suite while returning the wrong search type to clients.
   - **Fix:** Add one step pair to `test_search_types_and_ground_targets` searching from a canonical
     subject the rule cannot rewrite (`0`): `normal-form` must return `[0]` and `branch` `[]` — I
     verified these exact outcomes live.
   - **If we skip it:** Two of the five search types are protected only by research notes, not by
     tests.

## Nice to have

5. **Stale research paragraph contradicts the one inserted above it** (`.agents/planning/port-maude_eval.py/research/term-api.md:108-111`)
   - **What this is:** The diff inserts the Step 5 findings into §4 but leaves the section's old
     "Implications" paragraph below it.
   - **Problem:** The old text promises a `{matched: bool, ...}` outcome shape, a `with_extension`
     flag and "Arbitrary depth matching (UNBOUNDED) is deferred" — all superseded by the design (no
     `matched` field; extension via `depth=0`; `depth=2147483647` exposed) and contradicted by the
     new paragraph directly above it. Agents reading the research trail (and the planned RAG index)
     get contradictory guidance.
   - **Fix:** Delete the four stale lines; the design and the new paragraph carry the truth.
   - **If we skip it:** Doc rot inside the PDD record that future steps consume.

6. **Misleading advice in the no-current-term error** (`src/harold_mcp/server/tools/interpreter.py:303-311`)
   - **What this is:** The validation error ends with "the first step must provide an explicit term"
     (and the match variant "the first match/search step must provide an explicit subject").
   - **Problem:** The message also fires for later steps — e.g. a `reduce` after a `match`, which
     `test_match_does_not_create_a_current_term` triggers exactly — where the first step did provide
     its input and the advice points the client at the wrong fix.
   - **Fix:** Drop the tail, or reword to "this step must provide an explicit term (or subject)".
   - **If we skip it:** An LLM client gets misdirected retries on a common pipeline mistake.

7. **No integration test for a `match`/`search` parse failure** (`tests/integration/test_maude_session_integration.py:248-292`)
   - **What this is:** The `parse-error` branch of `_run_match_or_search` (pattern or subject does
     not parse) is new in this diff; only `reduce`'s parse error is integration-tested.
   - **Problem:** If the branch regresses (e.g. a bad pattern becomes a whole-call error instead of
     a per-step outcome), no test fails. I verified the current behavior live: a bad pattern yields
     `parse-error` with the message and stops the run.
   - **Fix:** Add one step with a bad pattern (and one with a bad subject) to an existing match
     test; assert the outcome and the stop.
   - **If we skip it:** A regression in per-step error handling for the new commands ships
     silently.

## Verdict

Verdict: fix 1, 3 and 4 first.

Lean: −4 lines possible (finding 5).

Not checked: `make check`, the test suites and the type checkers (no shell approval in this
session) — green runs are taken from the plan's implementation notes, and the tests' expected
values were cross-checked against live interpreter behavior instead. The installed `maude` wheel's
source was not on disk, so the search-constant values were verified against the research table and
live tool behavior, not against the bindings' code.
