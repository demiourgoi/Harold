# Review — technical design: search paths in `maude_run`

Subject: `.agents/planning/maude_eval_search_path/design/detailed-design.md`, checked against
`rough-idea.md`, the settled decisions in `idea-honing.md`, the four research notes, the current
code (`maude/session.py`, `server/tools/interpreter.py`, `settings.py`, `maude/executor.py`,
`maude/__init__.py`), the tests the design names, and the bindings source
(`maude-bindings/swig/specific/python.i`). Read-only; the one dynamic check is described in
finding 1.

## What this change does

The design attaches the rewrite path (the rule sequence that reached a solution, and optionally
the rule text and intermediate states) to every `search` solution of `maude_run`. The client asks
per search step with `path: "none" | "labels" | "full"` (default `"labels"`); the path travels in
one wire shape `{initial, transitions: [{rule: {label, text}, state}]}`; a new
`interpreter_max_path_steps` cap (default 100) plus the existing per-string cap bound it, and an
overflow is a whole-step `too-large`. All reconstruction happens in the worker through the
bindings' per-solution path thunk — no `show path` command, no state numbers, hermeticity kept.

Requirements check: all eight settled decisions from `idea-honing.md` are faithfully reflected —
R1 = Q1/Q7 (opt-in, default `labels`, enum field), R2 = Q2 (shape S1, `initial` always present,
last `state` repeats the solution term, zero-transition paths), R3 = Q3/Q4 (cap C1 + overflow O1,
default 100), R4 = Q5 (`label: null`), R5 = Q6 (`path` always present, `null` = not requested),
R6 = Q8 (attach-only). The rough idea's second ask (which other commands could benefit) is
answered by the research and the non-goals, with the transition shape left generic for strategy
search. Of the two open questions: the `limit` value on overflow is answered (qualified by
finding 3); the exact `maude_run` description wording is sensibly deferred to §4.4's surfaces.
No requirement is dropped or contradicted. Findings:

## Must fix

1. **Deep paths crash the worker instead of returning `too-large`** (design §5.2, §5.3, §6.1;
   `maude-bindings/swig/specific/python.i:128-146`)
   - **What this is:** the design calls the path thunk for every returned solution and checks the
     transition count afterwards. §5.3 records the order explicitly: "`pathTo` materializes the
     full element list before the transition count can be checked."
   - **Problem:** `pathTo` is recursive Python — one stack frame per transition
     (`path = self.pathTo(parent)`). Python's recursion limit is 1000 and nothing in harold-mcp
     or the bindings raises it. I ran the design's flow against the pinned bindings (maude 1.6.0,
     the probe fixture from `research/probes/`): a search for `n(1500)` from `n(0)` on the
     one-rule CHAIN module finds its solution fine (3000 rewrites, milliseconds), and calling the
     thunk raises `RecursionError`. The error crosses the pool unchanged (the executor only maps
     crash/timeout) and `maude_run` turns it into a whole-call
     `MaudeRunError("Unexpected failure running the Maude interpreter session")`. So R3's promise
     — an over-cap path makes the step `too-large` with `limit=100` — is unreachable for paths
     deeper than ~1000 transitions: those fail the whole call with a generic message that names
     no cap. This is a regression on input that works today (the same search without paths
     succeeds, because the current code never calls the thunk). The design's own remedy makes it
     worse: §9 tells users with deeper searches to raise `HAROLD_INTERPRETER_MAX_PATH_STEPS` —
     with the cap raised past ~1000, paths *within* the raised cap still crash. The deepest probe
     in `research/` was 100 transitions, so the hazard zone was never exercised.
   - **Fix:** check the transition count before any recursive reconstruction. While positioned on
     a solution, read `it.getStateNr()` and walk `getStateParent` in a plain loop
     (allocation-free, no recursion; `getStateParent(0) == -1` is safe) to count transitions;
     reject `> max_path_steps` as `too-large` without ever calling `pathTo`; call the thunk only
     when the depth fits. That makes the default cap of 100 safe at any search depth — and then
     either document that the cap must stay well under the recursion limit, or reconstruct the
     path iteratively (collect the parent chain, build forward, calling `getRule`/`getStateTerm`
     only on states that have a parent), which is safe at any depth and any cap. The iterative
     variant needs §6.2's rule restated precisely: the crash is `getRule` on a state with no
     parent (the root); `pathTo` itself walks parents and calls `getRule` on every non-root
     state, so an iterative walk that never touches the root is exactly as safe. Either way the
     formatting order settles for free: the count is known before any `str(rule)`/`str(term)`, so
     an over-cap path in `full` mode never formats megabytes of rule text first. Add the missing
     integration test: a pattern-targeted deep search (e.g. `n(0) =>* n(1500)`) must return
     `too-large` with `limit=100`; under the current design it raises instead.
   - **If we skip it:** the feature's flagship use case — "which rules reach this deep state" —
     fails the whole call with an error that offers no remedy, on input that is legal today.

## Should fix

2. **A search step with `path=None` has no defined meaning in the worker** (design §4.2)
   - **What this is:** `StepRequest.path` is `str | None`, commented
     `"none" | "labels" | "full" | None (non-search)`, and `_collect_solutions` gains
     `path_mode: str`. The design never says what `None` on a *search* step means.
   - **Problem:** the tool always sends a concrete value, but the session engine is also called
     directly by the integration tests, whose `_step` helper builds every `StepRequest` field
     explicitly (`tests/integration/test_maude_session_integration.py:31-50`) and will produce
     `path=None` search steps. The implementer must guess: `"labels"` duplicates the tool default
     in a second place; `"none"` leaves the existing exact-dict assertions with `path: null`.
     Two implementers could pick differently and the tests would silently pin whichever they
     picked.
   - **Fix:** one sentence in §4.2, e.g. "a search step with `path=None` is treated as `"none"`"
     (recommended — the worker does only what was asked, the tool owns the default, and it
     matches R5's "null means not requested").

3. **`limit` cannot say which cap was violated when the two caps are equal** (design §5.3, §7)
   - **What this is:** on a path overflow the outcome's `limit` carries the numeric value of the
     violated cap, and §5.3 claims this "makes the failure actionable (the client can raise the
     right setting or request `"labels"` instead of `"full"`)."
   - **Problem:** both caps are free-form positive ints, so nothing stops
     `HAROLD_INTERPRETER_MAX_PATH_STEPS` and `HAROLD_INTERPRETER_MAX_RESULT_LENGTH` from being
     equal (both 100 is a plausible constrained setup). Then `too-large` with `limit=100` does
     not say whether to raise the path cap, raise the result cap, or switch modes — the
     actionability claim fails exactly when the user has customized the caps.
   - **Fix:** also set the outcome's `message` on `too-large` (it is `None` today) to name the
     violated setting, e.g. `path exceeds interpreter_max_path_steps` /
     `result exceeds interpreter_max_result_length`. One line per site, no schema change; the
     `message` docstring gains the `too-large` case.

## Nice to have

4. **§4 misses the `harold_mcp.maude` package re-exports** (design §4.2-§4.3)
   - **What this is:** the tool layer imports the worker TypedDicts from the package root
     (`from harold_mcp.maude import BindingDict, ...`; `maude/__init__.py` re-exports them).
     §4 adds `PathDict`/`PathRuleDict`/`PathTransitionDict` to `session.py` and uses them in
     `interpreter.py`, but never says to add them to `maude/__init__.py`'s imports and `__all__`.
   - **Problem:** following §4.3 verbatim, the path adapter needs `PathDict` in an annotation
     (mypy `disallow_untyped_defs`), and the conventional import from `harold_mcp.maude` fails
     until the re-export is added. Discovered in minutes, but §4 lists the other plumbing points
     precisely and it is the contract the implementation plan is written from.
   - **Fix:** add the three TypedDicts to the §4.3 plumbing list.

5. **§8 does not inventory the existing tests and helpers the new fields break** (design §8)
   - **What this is:** §8 lists the new tests and the `test_search_outcome_is_adapted` update,
     but not (a) the integration `_step`/`_request` helpers, which build `StepRequest`/
     `SessionRequest` literals with every key — the new required keys mean both helpers must be
     updated (mypy fails on the missing keys, and the worker raises `KeyError` on `step["path"]`
     for a search step built without it), or (b) `test_search_types_and_ground_targets` and its
     ground/canonical variants, which compare solution dicts exactly and need `path` added.
   - **Problem:** every miss is a loud failure (mypy or pytest), so nothing wrong can ship — but
     the implementer hits a round of unlisted breakage. R7 states the principle; §8.2 just does
     not list the affected tests.
   - **Fix:** add a short "existing tests to update" list to §8.2.

## Verdict

Verdict: fix 1 first; 2 and 3 are one sentence each and should land in the same revision.

Not checked: `implementation/plan.md` — `implementation/` is empty, the plan does not exist yet
(expected at design-review time in the PDD flow). The recursion crash in finding 1 was reproduced
against the pinned bindings with an inline probe (no files written); everything else was checked
by reading.
