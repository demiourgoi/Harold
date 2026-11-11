# Project summary — search paths in `maude_run`

## Status

Requirements, research, design and implementation plan are complete. Implementation has
not started.

## Artifacts

| Artifact | Contents |
| --- | --- |
| `rough-idea.md` | Original request: expose the rewrite path of a search solution, since state numbers do not survive Harold's hermetic calls |
| `idea-honing.md` | Eight settled decisions (delivery mode, shape, caps, default, unlabeled rules, absence, input option, scope) plus the requirements status table |
| `research/maude-bindings-search-path.md` | The bindings' per-solution path API, rule labels/text, state numbers, the lazy-thunk lifetime trap and the `getRule(0)` crash |
| `research/current-implementation.md` | Where the current session engine drops the path, the caps and statuses, and the tests that pin the current shape |
| `research/path-design-options.md` | Delivery/shape/cap options, compatibility impact, and test-case ideas from the probes |
| `research/related-commands.md` | Which Maude commands have path-like data (`search` only, of Harold's steps) and why `show_path`/`metaSearchPath` are out of scope |
| `research/probes/` | Executable probes and captured transcripts for `SHEPHERD`, `UNLABELED`, `CHAIN` and `BRANCH` |
| `design/detailed-design.md` | Revision 4: contract, architecture, data models, correctness constraints, error handling, testing strategy, appendices |
| `design/design-review-v1.md` … `v3.md` | Three review rounds and their findings; all incorporated into revision 4 |
| `implementation/plan.md` | Five-step, test-driven plan with checklist and working agreements |

## Design overview

- `SearchStep` gains `path: "none" | "labels" | "full"` (default `"labels"`).
- A solution's path is `{initial, transitions: [{rule: {label, text}, state}]}`; labels
  mode leaves `text`/`state` null; `path` is present on search solutions and null when
  not requested.
- A new `HAROLD_INTERPRETER_MAX_PATH_STEPS` cap (default 100) plus
  `HAROLD_INTERPRETER_MAX_RESULT_LENGTH` per element bound the payload; an overflow is a
  whole-step `too-large` whose `limit` and `message` name the violated setting.
- The worker reconstructs paths iteratively from the search graph's parent links (never
  through the recursive `pathTo`, which overflows on deep paths), reads the state number
  while the iterator is positioned, and never calls `getRule` on the root (which crashes
  the process).
- The parent walk stops at the cap, so path work is O(cap) regardless of search depth.

## Implementation plan overview

1. **Settings cap** — `interpreter_max_path_steps` and its env var.
2. **Path contract and helper** — worker TypedDicts, request keys, `_reconstruct_path`,
   re-exports, request plumbing, unit tests with fake iterators.
3. **Session engine** — lazy collection, state capture, path assembly, named
   `too-large` reasons, invalid-mode contract, fixture and integration tests.
4. **Tool exposure** — `SearchStep.path`, output models, adapters, tool docstring, end-to-
   end tests.
5. **Documentation and release metadata** — README, CHANGELOG, version, `make release`.

## Next steps

1. Review `implementation/plan.md` and confirm the step order and scope.
2. Start Step 1; after each step, confirm it before moving on (per the working
   agreements) and add the required "Implementation notes".
3. After implementation, re-run the codebase-summary skill so `.agents/summary/` matches
   the new `SolutionDict`/request shapes, and prepare the release section.

## Areas that may need further refinement

- The default `"labels"` is a payload behavior change for existing clients (accepted in
  the requirements; recorded for the changelog).
- Searches over unbounded state spaces still need an explicit `depth` because the engine
  consumes one extra solution for `truncated`; this is existing behavior, documented in
  the design and worth mentioning in the tool description if a future revision touches it.
- The iterative builder duplicates the bindings' `pathTo` accessor pattern; it must be
  revisited if the bindings change their path API.
