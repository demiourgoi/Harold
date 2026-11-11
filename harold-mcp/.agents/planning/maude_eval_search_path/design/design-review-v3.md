# Review — technical design revision 3: search paths in `maude_run`

Subject: `.agents/planning/maude_eval_search_path/design/detailed-design.md` (revision 3), checked
against `rough-idea.md`, the settled decisions in `idea-honing.md`, the four research notes and
their probes, design review v2 (`design-review-v2.md`), the current code (`maude/session.py`,
`server/tools/interpreter.py`, `settings.py`, `maude/__init__.py`, `maude/executor.py`), the tests
the design names, and the installed `maude` 1.6.0 bindings. Read-only; the dynamic checks are
listed in the closing note.

## What this change does

The design attaches the rewrite path — the rule sequence that reached a search solution, and
optionally the rule text and intermediate states — to every `search` solution of `maude_run`. The
client asks per search step with `path: "none" | "labels" | "full"` (default `"labels"`); the path
travels in one wire shape `{initial, transitions: [{rule: {label, text}, state}]}`; a new
`interpreter_max_path_steps` cap (default 100) plus the existing per-string cap bound it, and an
overflow is a whole-step `too-large` naming the violated setting. The worker reconstructs the path
iteratively from the search graph's parent links — never through the bindings' recursive `pathTo`,
which overflows the Python stack on deep paths — and never calls `getRule` on the root state, which
hard-crashes the process.

## Requirements check

All eight settled decisions from `idea-honing.md` are faithfully reflected:

- R1 = Q1/Q7: opt-in enum on `SearchStep`, default `"labels"` (I1).
- R2 = Q2: shape S1, `initial` always present, last `state` repeats the solution term,
  zero-transition paths `{initial, transitions: []}`.
- R3 = Q3/Q4: dedicated `interpreter_max_path_steps` (`HAROLD_INTERPRETER_MAX_PATH_STEPS`,
  default 100) plus `interpreter_max_result_length` per element; whole-step `too-large` (C1 + O1,
  D1).
- R4 = Q5: `label: null` for unlabeled rules, no synthetic labels (U1).
- R5 = Q6: `path` always present on search solutions, `null` = not requested (N1).
- R6 = Q8: attach-only; no `show_path` step, no state numbers (P1).
- R7-R9 (compatibility, hermetic materialization, reconstruction safety) are sound additions
  consistent with the repo's architecture rules.

The two open questions from idea-honing are answered: the overflow reports the violated cap's value
in `limit` plus a `message` naming the setting (§5.3, with the wording for both path cases), and
the `maude_run` description wording is assigned to §4.4's named surfaces. The rough idea's second
ask (which other commands could benefit) is answered by the research and the non-goals: `search` is
the only exposed step with a per-solution path, and the transition shape leaves room for a future
strategy-search transition without a breaking change.

## Review-v2 feedback check

All five v2 findings are incorporated:

1. Explicit `depth` on every unbounded-search test row: `depth=1500` on both `n(1500)` rows
   (§6.2, §8.2), `depth=3` on the reflexive row (§6.3, §8.2), plus the "a search over an unbounded
   state space must set `depth`" sentence in §8.2 and §D.
2. Early-stop parent walk: §5.2 step 2 stops as soon as the collected chain exceeds
   `max_path_steps + 1` states ("do not walk to the root just to count"), §5.3 bounds the cost at
   `max_path_steps + 2` `getStateParent` calls and O(cap) memory, and the §8.1 depth-pin test
   counts `getStateParent` calls.
3. The rewriting `too-large` message: §4.2 (`_run_rewriting` sets `message` naming
   `interpreter_max_result_length`) and the §7 bullet.
4. The four one-line updates: `test_search_step_forwards_pattern_subject_depth_and_type` gains
   `"path": "labels"` (§8.3), `test_request_carries_the_steps_and_configured_caps` gains
   `"path": None` and `max_path_steps` (§8.3), `test_maude_executor.py`'s `SESSION_REQUEST` gains
   `max_path_steps` (§8.3), and the package re-exports plus the tool `__all__` entries (§4.3).
5. The `=>!` row: `BRANCH`, `a =>! c`, one transition, label `ac`, final state `c` (§8.2).

The v1 findings are transitively covered (v2 verified them in revision 2; all five are still
present in revision 3).

## Findings

### Should fix

1. **The worker's contract for an invalid `path` string is unspecified** (design §4.2;
   `maude/session.py::_run_match_or_search`)
   - **What this is:** §4.2 specifies that a search step's `path=None` is treated as `"none"`, and
     the tool's pydantic boundary only produces `"none" | "labels" | "full"`. But `StepRequest.path`
     is typed `str | None`, and the worker's behavior for any other string — reachable only by a
     direct session-engine caller, i.e. a programming error — is defined nowhere.
   - **Problem:** the module's own precedent for exactly this shape is `search_type`: an invalid
     value raises a defensive `ValueError` ("programming error, not a user error"). An implementer
     following §4.2 alone picks a behavior silently (raise, treat as `"none"`, or fall through to
     `"labels"`), and the worker protocol stays unpinned on the input closest to a validated one.
   - **Fix:** one sentence in §4.2, e.g. "a `path` value other than `"labels"`/`"full"` (including
     `None` and `"none"`) does no path work; any other string raises the same programming-error
     `ValueError` as an invalid `search_type`" — or explicitly "anything unrecognized is treated as
     `"none"`".
   - **If we skip it:** nothing wrong can ship through the tool (pydantic rejects it); the gap only
     bites a future direct caller or a worker-contract test.

### Nice to have

2. **§8.3 attributes message assertions to a test that has no `too-large` case** (design §8.3;
   `tests/integration/test_maude_session_integration.py::test_match_and_search_caps_set_the_truncation_flag`)
   - **What this is:** §8.3 says `test_match_and_search_caps_set_the_truncation_flag` and
     `test_match_and_search_result_length_cap` "still pass but gain `message` assertions for the
     `too-large` cases".
   - **Problem:** the truncation-flag test pins `truncated` and solution counts; it produces no
     `too-large` outcome, so there is no message to assert. Only the result-length-cap test (match
     and search `too-large`) gains the assertions.
   - **Fix:** drop the first test from that sentence — it passes unchanged, like
     `test_match_and_search_thread_without_changing_the_current_term`.
   - **If we skip it:** the implementer notices in seconds; no wrong behavior can ship.

3. **No test pins the term-cap-before-path-work ordering** (design §3 sequence diagram, §7, §8.1)
   - **What this is:** §3 and §7 specify that the solution term/binding cap check runs before any
     path work. That ordering decides which limit a `too-large` outcome reports when both caps are
     exceeded on the same solution: the result cap, not the path cap.
   - **Problem:** the §8.1 cap-accounting unit test covers transition overflow, element overflow,
     and the extra truncation solution, but not "oversized term + over-cap path →
     `limit = interpreter_max_result_length`, and no path accessor is called". A regression that
     reorders the checks changes the reported limit in the doubly-pathological case with no failing
     test — the same class of pin the design's own depth-pin test sets for count-before-format.
   - **Fix:** one fake-iterator case in the §8.1 cap-accounting test: a solution whose term exceeds
     `max_result_length` while its path exceeds `max_path_steps` reports the result cap, and the
     fake iterator raises if any path accessor is called.
   - **If we skip it:** the outcome is still a correct `too-large` either way; only the reported
     limit (and some wasted path work) can drift.

4. **`StepRequest.path` collides with `SessionRequest.path`** (design §4.2)
   - **What this is:** the worker request family gains a second, unrelated `path` key:
     `SessionRequest.path` is the Maude file; `StepRequest.path` is the path mode.
   - **Problem:** the design itself uses `path_mode` as the `_collect_solutions` parameter name, so
     the internal vocabulary is split three ways (`path`, `path_mode`, `mode`), and the
     `_run_step`-family plumbing has both request objects in scope, where `request["path"]` (file)
     and `step["path"]` (mode) are one keystroke apart.
   - **Fix:** either rename the worker key to `path_mode` (the wire name `SearchStep.path` is
     user-settled in idea-honing Q7 and stays), or add a one-line note in §4.2 acknowledging the two
     meanings.
   - **If we skip it:** a readability wart; explicit dict keys keep it from becoming a bug.

5. **The session-engine docstring updates are missing from the component list** (design §4.2/§4.4;
   `maude/session.py::_collect_solutions`, `_run_match_or_search`; `docs/modules.md:16`)
   - **What this is:** `docs/modules.md` renders `harold_mcp.maude.session`, so the engine's
     docstrings are public API reference content. `_collect_solutions`'s docstring today reads
     "Collect a capped list of search solutions, enforcing the result term cap" — after the change
     it also reconstructs paths and enforces the path caps; `_run_match_or_search`'s docstring
     likewise describes only the current behavior.
   - **Problem:** §4.4 lists the tool docstring, README, knowledge base and changelog, and §4.2
     lists the signature changes, but neither lists the engine docstrings; an implementer following
     the component list verbatim leaves the rendered reference stale (nothing fails the build —
     `make docs-test` catches warnings, not stale prose).
   - **Fix:** one line in §4.2 or §4.4: update the `_collect_solutions`/`_run_match_or_search`
     docstrings (rendered in the API reference).
   - **If we skip it:** documentation drift in the generated reference until someone rereads the
     module.

## Verdict

Verdict: Ship — fold finding 1 into §4.2 before the implementation plan is written; 2-5 can land
with the plan or the implementation.

Not checked: `implementation/plan.md` — the `implementation/` directory is still empty, the plan
does not exist yet (expected at design-review time in the PDD flow). The `getRule(0)` SIGSEGV was
not re-run (it is a deliberate process crash; it rests on the `probe_state_numbers.out.txt`
transcript and the v1 review's reproduction — the root-parent invariant it depends on,
`getStateParent(root) < 0`, was verified live this round).

Dynamic checks run for this review, all against the pinned `maude` 1.6.0 with the probe fixture and
no files written: `n(0) =>* n(1500)` at depth 1500 on `CHAIN` finds the solution in milliseconds
(3000 rewrites) and the path thunk raises `RecursionError` (confirms §6.2's central claim, which
v2 had verified only statically); the iterative parent walk on the same state returns 1501 states /
1500 transitions, initial `n(0)`, last `n(1500)`, all labels `step` (confirms §5.2's serialization
rules and the §8.2 `max_path_steps=2000` row); the early-stop check at cap 100 stops after 102
collected states and 101 `getStateParent` calls without reaching the root ~1400 states away
(confirms §5.2 step 2 and §5.3's bound). Verified by reading: `pathTo`'s recursion and the
call-time `getStateNr()` thunk in the installed shadow code; the executor maps only
`BrokenProcessPool`/`TimeoutError`, so a worker `RecursionError` surfaces as the generic whole-call
`MaudeRunError` — §6.2's description of the rejected design's failure mode is accurate; the §8.3
breakage inventory against every file that constructs `SessionRequest`/`StepRequest`/`SolutionDict`
(seven files, all covered); the §8.2 expectations against the probe transcripts (NORMAL_FORM on
`BRANCH`: one transition, label `ac`; BRANCH `=>#`: zero transitions; shepherd labels and 427
rewrites). Everything else was checked by reading.
