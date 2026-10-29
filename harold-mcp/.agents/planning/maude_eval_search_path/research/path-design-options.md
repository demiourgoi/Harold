# Research — design options for returning search paths

> Evidence for the design phase. Requirements direction from the user: **keep hermetic
> calls and surface the paths**. The bindings already provide the path with each search
> solution, so the open questions are about the wire contract, not about capability.

## 1. Options for delivering paths

### A. Always return the full path for every search solution

Every `MaudeSearchSolution` carries a `path` object.

| Pros | Cons |
| --- | --- |
| The agent gets the path without knowing to ask; matches the rough idea's "always returning the path". | Payload grows for every search, even when the agent only needs existence/counts. |
| One request; no new input field. | Interacts with caps: a long path can turn a useful search into `too-large`. |
| Simplest tool description. | 200 solutions × long paths can be megabytes (see §5). |

### B. Opt in per search step

`SearchStep` gains a `path` option, e.g. `path: "none" | "labels" | "full"` (JSON-schema
enum, self-documenting) or a bool `include_path`.

| Pros | Cons |
| --- | --- |
| Size and cost controlled by the client. | The agent must discover and set the option; a default of `none` hides the feature. |
| Labels-only is a cheap middle ground (≈10–50 chars per step). | Extra input surface and description text. |
| Backward-compatible request schema (a default value). | The output schema still gains a field (usually `null`). |

Defaults to consider:

| Default | Effect |
| --- | --- |
| `none` | Maximum compatibility; agents must opt in. |
| `labels` | Cheap, immediately useful rule sequence; full path on request. |
| `full` | Same as option A for payload purposes, but with an escape hatch. |

### C. A separate `show_path` step command — rejected

Requires exposing state numbers, only works within the same call (state numbers are
per-search and the interpreter is recycled), and duplicates data the search already
returns. See [`related-commands.md`](related-commands.md) §7.

## 2. Options for the path shape

Probed data: `pathTo` returns `[t0, r1, t1, …, rn, tn]` (`2n+1` elements); rules expose
`getLabel()` (nullable) and `str(rule)` (full statement). A reflexive `=>*` solution and a
`=>#` branching state return `[t0]` (no transitions).

### (a) Faithful interleaved list

```json
"path": [
  {"kind": "state", "term": "st(l, l, l, l)"},
  {"kind": "rule", "label": "crossWithSheep", "text": "crl [crossWithSheep] : ... ."},
  {"kind": "state", "term": "st(r, l, l, r)"}
]
```

Pros: mirrors the bindings and `show path` element-by-element. Cons: verbose schema
repetition; the initial/transitions structure is implicit; bigger JSON.

### (b) Initial state + transitions (recommended shape)

```json
"path": {
  "initial": "st(l, l, l, l)",
  "transitions": [
    {"rule": {"label": "crossWithSheep", "text": "crl [crossWithSheep] : ... ."}, "state": "st(r, l, l, r)"},
    {"rule": {"label": "crossAlone", "text": "crl [crossAlone] : ... ."}, "state": "st(l, l, l, r)"}
  ]
}
```

Pros: natural reading ("start here, then these steps"); the number of transitions is the
path length; empty transitions express reflexive/`=>#` solutions cleanly; the final
transition's `state` equals the solution `term` (documented, slightly redundant); room
for a future non-rule transition (`"strategy": {...}`) without changing the shape.

### (c) Parallel arrays

`{"states": [...], "rules": [{...}]}` — compact, but the relation between arrays is
implicit (rules[i] leads states[i] → states[i+1]) and off-by-one mistakes are easy.

### (d) Labels only

`{"initial": "...", "labels": ["crossWithSheep", "crossAlone", ...]}` — smallest useful
form, mirrors `show path labels`; loses intermediate states and cannot represent an
unlabeled rule faithfully (the CLI prints `(unlabeled rule)`, the bindings return `None`).

## 3. Rules: labels vs text

| Field | Source | Notes |
| --- | --- | --- |
| `label` | `rule.getLabel()` | `None` for unlabeled rules. The CLI prints `(unlabeled rule)`. |
| `text` | `str(rule)` | Full statement, conditions normalized with `= true`; no line wrapping (the CLI wraps). |

A "labels" mode should either emit `null` labels (honest) or a display fallback such as
`"(unlabeled rule)"` (CLI-compatible). A "full" mode always has the rule text.

## 4. State numbers

Do **not** expose them in the solution. They are per-search and die with the interpreter
(`max_tasks_per_child=1`), so they cannot be used in a later call, and the path does not
need them. If a later feature wants them (e.g. `show search graph`), document their
per-call scope explicitly.

## 5. Size, caps and cost

Measured cost: a 100-transition chain path is 201 elements — 101 terms (≤6 chars each)
and 100 rules (30 chars each), ≈3 KB of rule text. The path is reconstructed in O(depth)
string formatting per solution (no extra search).

Worst case with current caps: 200 solutions × depth 1,000 × ~30–200 chars per rule
≈ 6 MB–40 MB of rule text per step, plus terms. Unbounded depth makes this arbitrarily
large. Options:

| Cap | Pros | Cons |
| --- | --- | --- |
| Reuse `interpreter_max_result_length` (1 M) per term/rule element | No new setting; consistent with term caps | Does not bound the total path (many small elements). |
| New `interpreter_max_path_steps` (transitions per solution) | Direct, easy to reason about; small default (e.g. 100–1000) bounds most cases | A legitimate long plan can exceed it. |
| New total serialized path length cap | Bounds payload exactly | Requires accumulating lengths while reconstructing; interacts with label/text modes. |

Behavior on overflow:

1. **Whole step `too-large`** — consistent with the existing term/binding cap (any
   oversized result discards the step's solutions). Safest: no misleading partial path.
2. **Return the solutions but omit paths**, with a step-level marker
   (`path_omitted: true` / `path_truncated: true`). Preserves the solutions, but `path:
   null` is easy to confuse with "no path".
3. **Truncate the path prefix** — rejected: a prefix that does not reach the solution is
   not a path to the solution.

Recommendation to evaluate in design: whole-step `too-large` (option 1) for consistency
with `max_result_length`, enforced while reconstructing, with a dedicated
`interpreter_max_path_steps` setting. Paths are computed only for solutions inside the
`max_solutions` cap; the extra solution consumed to set `truncated` needs no path.

## 6. The lifetime trap must be handled in the implementation

`_collect_solutions` currently materializes `max_solutions + 1` tuples with `islice` and
then iterates the list. The path thunk resolves `getStateNr()` **at call time**, so calling
it in the second loop would attribute the last state's path to every solution. Correct
options:

- call the thunk inside the iteration loop, while positioned on that solution; or
- record `it.getStateNr()` per solution and call `it.pathTo(state)` afterwards.

Never reconstruct via `getRule` parent walks: `getRule(0)` on the root state crashes the
process (SIGSEGV). `pathTo` is safe (its base case skips the root rule).

## 7. Compatibility impact

- **Input**: adding an optional `path` field to `SearchStep` is backward-compatible.
- **Output**: any new field on `MaudeSearchSolution` changes `model_dump()` output and
  breaks exact-dict assertions in:
  - `tests/unit/test_interpreter_tool.py::test_search_outcome_is_adapted`;
  - `tests/integration/test_maude_session_integration.py::test_search_types_and_ground_targets`
    and the ground/canonical variants.
  These are test updates, not external breakage (JSON is additive), but the design should
  decide whether `path` is always present (`null` when off) or excluded when off.
- **Docs**: `maude_run` description (Commands section), `README.md` tool bullet and
  env-var table (if a new cap), `.agents/summary/interfaces.md` + `data_models.md`,
  `CHANGELOG.md`, minor version bump.

## 8. Test-case ideas from the probes

Fixture: add the probe's `search_path.maude` (or just `SHEPHERD` + `UNLABELED` + `BRANCH`)
to `tests/integration/fixtures/`. The shepherd path gives a known 7-step answer from the
rough idea.

| Test | What it pins |
| --- | --- |
| Integration: shepherd `st(l,l,l,l) =>* st(r,r,r,r)` | Labels in order; 7 transitions; solution state 9; path ends at the solution term; matches `show path labels` from the manual/rough idea. |
| Integration: `=>1` one-step solution | Path of exactly one transition (3 interleaved elements). |
| Integration: reflexive `=>*` (`n(0) =>* n(0)`) | Initial state only, zero transitions (not `null`). |
| Integration: `=>#` on `BRANCH` (`a =># X:S`) | Zero transitions (CLI: `Empty path.`). |
| Integration: unlabeled rules (`UNLABELED`, `a =>+ c`) | `label` is `null` (or `(unlabeled rule)`), `text` present for both rules. |
| Integration: two solutions of `n(0) =>+ n(N)` | **Laziness regression**: the first solution has 1 transition and the second 2 (would fail with the `islice` trap). |
| Integration: `max_solutions=1` with a longer search | `truncated=true`; one solution; its path is correct (no path work for the extra solution). |
| Integration: small path cap on a 5-step search | `too-large` (or the chosen overflow marker), `limit` set, no misleading partial path. |
| Integration: 100-step `CHAIN` path with a generous cap | Long-path boundary; last state equals the solution term; cap accounting. |
| Integration: `match` and rewriting steps | No path data (field `null`/absent), outcomes unchanged. |
| Unit (`test_interpreter_tool.py`) | `SearchStep.path` is forwarded by `_to_step_request`; `_to_solutions` adapts the path object (including `label=None`); exact `model_dump()` updated. |

## 9. Open questions handed to the design

1. Delivery mode and default: always-on, or opt-in `none`/`labels`/`full`?
2. Shape: initial + transitions (recommended) vs. interleaved list vs. labels-only.
3. Cap: reuse `max_result_length` per element, add `max_path_steps`, or both, and which
   overflow behavior.
4. Unlabeled rules: `null` label vs `(unlabeled rule)` fallback.
5. Whether `path` is always present in the output (null when off) or omitted.
