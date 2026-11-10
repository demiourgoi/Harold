# Review — technical design revision 2: search paths in `maude_run` (consolidated second round)

Subject: `.agents/planning/maude_eval_search_path/design/detailed-design.md` (revision 2), checked
against `rough-idea.md`, the settled decisions in `idea-honing.md`, the four research notes and
their probes, review v1 (`design-review-v1.md`), the current code (`maude/session.py`,
`server/tools/interpreter.py`, `settings.py`, `maude/__init__.py`, `maude/executor.py`,
`maude/capture.py`), the tests the design names, and the bindings source
(`maude-bindings/swig/specific/python.i`, `term.i`; installed package `maude` 1.6.0). This document
consolidates the two independent revision-2 review passes (this file's earlier content and
`detailed-design-review-rev1.md`): every finding from either pass was re-verified, the overlapping
ones are merged, and the numbering is final for this round. Read-only; the dynamic checks are
described in findings 1 and 2 and the closing note.

## What this change does

The design attaches the rewrite path — the rule sequence that reached a search solution, and
optionally the rule text and intermediate states — to every `search` solution of `maude_run`. The
client asks per search step with `path: "none" | "labels" | "full"` (default `"labels"`); the path
travels in one wire shape `{initial, transitions: [{rule: {label, text}, state}]}`; a new
`interpreter_max_path_steps` cap (default 100) plus the existing per-string cap bound it, and an
overflow is a whole-step `too-large`. The worker reconstructs the path iteratively from the search
graph's parent links — never through the bindings' recursive `pathTo` — and never calls `getRule`
on the root state, which hard-crashes the process.

Requirements check: all eight settled decisions from `idea-honing.md` are faithfully reflected —
R1 = Q1/Q7 (opt-in enum, default `"labels"`), R2 = Q2 (shape S1, `initial` always present, last
`state` repeats the solution term, zero-transition paths), R3 = Q3/Q4 (dedicated cap plus the
per-element cap, whole-step `too-large`, default 100), R4 = Q5 (`label: null`), R5 = Q6 (`path`
always present, `null` = not requested), R6 = Q8 (attach-only). R7-R9 are sound additions
(compatibility, hermetic materialization, reconstruction safety). The two open questions from
idea-honing are answered: the overflow reports the violated cap's value in `limit` plus a `message`
naming the setting (finding 3 notes the one site missing from the component lists), and the
`maude_run` description wording is sensibly deferred to §4.4's named surfaces. The rough idea's
second ask (which other commands could benefit) is answered by the research and the non-goals,
with the transition shape left generic for strategy search.

Review-v1 feedback check: all five v1 findings are incorporated — 1 (iterative reconstruction, R9,
§6.2 with regression tests; the iterative walk was re-run against the pinned bindings and counts
1500 transitions in about a millisecond), 2 (§4.2: a search step with `path=None` is treated as
`"none"`), 3 (§5.3: `message` names the violated setting), 4 (§4.3: package re-exports), 5 (§8.3:
the expanded test inventory, with the residual misses in finding 4). The §5.2 reconstruction rules
were checked line by line against the installed bindings (`pathTo`, `__next__`, `getStateParent`
all match), and the shepherd example in §5.1 reproduces exactly through the current tool (one
solution, 427 rewrites). Findings:

## Must fix

1. **Three of the design's own regression tests hang the call or pass only by accident**
   (design §6.2 "Tests:", §6.3 "Regression test", §8.2 test table;
   `research/probes/probe_search_path.py:62-124`)
   - **What this is:** CHAIN is an infinite state space (`n(N) => n(N + 1)`), the engine always
     consumes one solution beyond the cap to set `truncated`, and an omitted step `depth` means
     unbounded. Three rows specify no `depth`:
     (a) "Reflexive `=>*` (`n(0) =>* n(0)`)" — §6.3's root-state safety test and §8.2's
     zero-transition row; (b) "CHAIN, `n(0) =>* n(1500)`, `max_path_steps=2000`" — §6.2's deep-path
     `ok` test; (c) "CHAIN, `n(0) =>* n(1500)`, default cap" — §6.2's deep-path `too-large` test.
   - **Problem:** a ground pattern has exactly one match, so after the one real solution the
     truncation pull explores the chain forever. Verified dynamically against the pinned bindings
     (probe fixture): the reflexive search's first solution is instant (state 0, 0 rewrites) and
     the pull was still running when the 30 s kill fired; the `n(1500)` search's first solution
     arrives in ~1 ms (3000 rewrites) and its pull was still running at the 60 s kill. Rows (a)
     and (b) cannot pass as written — the call dies as a whole-call timeout, the exact
     "whole-call error" the tests assert cannot happen. Row (c) passes only because its
     `too-large` fires on the first solution, before the truncation pull — an implementation
     that materializes solutions before path work (the very shape §6.1 warns about) would hang it
     too. The research probes never hit this because every probe passes an explicit `depth`
     (`depth=3`, `depth=100`) and consumes its solutions by hand.
   - **Fix:** one word per row: `depth=1500` on both `n(1500)` rows (the default-cap row too, so
     the test does not depend on the early-return order) and `depth=3` on the reflexive row —
     exactly what the probes do. Verified: with `depth=1500` the pull raises `StopIteration`
     instantly (one solution, `truncated=false`); with `depth=3` the reflexive solution returns.
     Add one sentence to §8.2: a search on an infinite state space needs a `depth`, because the
     engine always consumes one extra solution for `truncated`.
   - **If we skip it:** the implementer transcribes the table, watches the flagship regression
     tests (the root-state safety test and the deep-path tests) time out, and debugs a subtle
     engine/timeout interaction the design could have prevented with a word.

## Should fix

2. **An over-cap path pays O(depth) walk time and memory before the cap is checked** (design §5.2
   steps 2-3, §5.3, §1 Goals)
   - **What this is:** §5.2 walks the entire parent chain, collecting every state number, and only
     then compares `len(states) - 1` against `max_path_steps`.
   - **Problem:** §5.3 says an over-cap path "costs O(depth) `getStateParent` calls and nothing
     else" — but it also builds an O(depth) list of state numbers, all to conclude "over the
     100-step cap". Measured against the pinned bindings: the walk costs ~124 ns per call (10^6
     states in 0.12 s), and the search itself costs ~2 µs per level (10^6 levels in 2.05 s), so
     the walk is roughly 16x cheaper than the search per level — it is rarely the dominant cost,
     but in the deep regime it is the straw that breaks a near-timeout call (a search that used
     ~57 s plus a ~4 s walk fails the 60 s budget mid-walk), and at depth 10^7 it allocates a
     ~360 MB transient Python list per solution on top of the search graph's own memory — an
     OOM window the same search without paths does not have. §1's goal — "an over-cap path is a
     per-step `too-large`, never a whole-call failure" — therefore holds only conditionally, not
     at any depth as §9 claims.
   - **Fix:** stop the walk as soon as the collected chain is longer than `max_path_steps + 1`
     states: the path is then over cap whatever remains, so return `too-large` immediately — no
     need to reach the root to prove an over-cap. Over-cap paths then cost O(cap) calls and
     memory at any depth; in-cap paths are unchanged. Extend the §8.1 depth-pin unit test to
     assert the walk stops at the cap (the fake iterator counts `getStateParent` calls).
   - **If we skip it:** extreme-depth searches get a timeout/OOM whole-call error instead of the
     named-cap `too-large`; the depths in the design's own tests (≤ 1500) are unaffected.

3. **The rewriting commands' `too-large` message is missing from the component list and the error
   list** (design §4.2, §7 vs §4.3, §5.3, §8.3; `maude/session.py::_run_rewriting`)
   - **What this is:** §4.3 redefines `MaudeStepOutcome.message` as "the interpreter's message
     (`parse-error`) or Harold's reason for exceeding a limit (`too-large`)", §5.3 says `message`
     names the setting "for the non-path `too-large` cases", and §8.3 says
     `test_too_large_result_is_an_outcome` gains `message` coverage — that test is a `reduce`
     step. But §4.2, the component list the implementation plan is written from, only changes
     `_collect_matches`, `_collect_solutions` and `_run_match_or_search`; and §7's bullet list
     covers the path cap, the path element, and the oversized solution term or binding — not the
     oversized *rewriting* result.
   - **Problem:** `_run_rewriting` is the `too-large` site for `reduce`/`rewrite`/`frewrite`/
     `erewrite`. An implementer following §4 and §7 verbatim leaves it without a message, the §8.3
     test update then fails, and the new output-schema description overpromises for rewriting
     steps. The design contradicts itself between §4/§7 and §4.3/§5.3/§8.3.
   - **Fix:** one line in §4.2 (`_run_rewriting` sets `message` naming
     `interpreter_max_result_length` on its `too-large` outcome) and one bullet in §7 ("Oversized
     rewriting result term — unchanged status/limit, gains the same `message`").
   - **If we skip it:** caught by the failing test in minutes, but the fix then lands outside the
     reviewed contract, or the schema description is slightly wrong for `reduce`/`rewrite` steps.

## Nice to have

4. **§4.3/§8.3 miss four one-line updates the new keys force** (design §4.3, §8.3;
   `tests/unit/test_interpreter_tool.py:298-347`, `tests/unit/test_maude_executor.py:26-33`,
   `src/harold_mcp/server/tools/interpreter.py:572-590`)
   - **What this is:** the plumbing and test inventories name most of the breakage, but not:
     (a) `test_search_step_forwards_pattern_subject_depth_and_type` asserts a whole `StepRequest`
     dict, which gains `"path": "labels"`; (b)
     `test_request_carries_the_steps_and_configured_caps` asserts whole step dicts for two reduce
     steps and the caps, which gain `"path": None` and `max_path_steps`; (c)
     `test_maude_executor.py`'s module-level `SESSION_REQUEST` literal needs the new required
     `max_path_steps` key (mypy fails on the missing key); (d) the tool module's `__all__`
     conventionally lists every public model, so `MaudeRuleRef`, `MaudePathTransition` and
     `MaudeSearchPath` belong there.
   - **Problem:** (a)-(c) fail loudly (pytest or mypy), so nothing wrong ships — but §8.3 was
     added precisely to spare the implementer this round, and this is the same class as
     design-review-v1 finding 5. (d) is silent: no lint enforces `__all__` completeness, so the
     convention drifts.
   - **Fix:** add the four items to the §4.3 plumbing list and the §8.3 inventory.
   - **If we skip it:** minutes of unlisted fixing; no wrong behavior can ship.

5. **No `=>!` (normal-form) path test** (design §8.2, §B)
   - **What this is:** §B states the bindings yield a path "for all five search types", and the
     probe measured the normal-form one (`a =>! c` on `BRANCH`: 1 transition, label `ac`). The
     §8.2 table pins four types (`=>1`, `=>+`, `=>*`, `=>#`) but not `=>!`.
   - **Problem:** the fifth type's path shape is unpinned; a regression that breaks only
     normal-form paths surfaces later as an integration surprise.
   - **Fix:** one row: `BRANCH`, `a =>! c`, labels mode — 1 transition, label `ac`, final state
     `c`.

## Verdict

Verdict: fix 1 before implementation starts; fold 2 into §5.2 while editing. 3 is one sentence in
two sections; 4 and 5 can land with the implementation.

Not checked: `implementation/plan.md` — the `implementation/` directory is still empty, the plan
does not exist yet (expected at design-review time in the PDD flow). The `getRule(0)` SIGSEGV and
the `pathTo` `RecursionError` rest on the research probes and the v1 review's reproduction; the
bindings source was verified statically (the recursion and the call-time `getStateNr()` are in the
installed 1.6.0 shadow code), but those two probes were not re-run this round. The dynamic checks
run for this review, all against the pinned `maude` 1.6.0 with the probe fixture and no files
written: the reflexive-row hang (first solution instant, truncation pull killed at 30 s), the
`n(1500)` hang and its `depth=1500` correction (first solution ~1 ms, pull killed at 60 s without
a depth; instant `StopIteration` with it), the iterative walk at depth 1500 (1500 transitions,
~1 ms) and at depth 10^6 (10^6 states in 0.12 s, ~124 ns per call; search 2.05 s), and the
shepherd example through the current tool (one solution, 427 rewrites). Everything else was
checked by reading.
