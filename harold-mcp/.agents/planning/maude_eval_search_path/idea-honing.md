# Requirements clarification — maude_eval_search_path

## Question 1: Should search paths be opt-in per search step, or always returned?

The bindings give a path for every solution of a `search`, but the current
`_collect_solutions` discards it. The core delivery decision:

- **A. Opt-in per search step** — `SearchStep` gains a `path` option (for example
  `"none" | "labels" | "full"`), defaulting to `"none"`. Keeps payloads small and
  backward-compatible, but the agent must know to ask for the path.
- **B. Always return the path** — every `MaudeSearchSolution` carries it. The agent
  gets it without asking (matches the rough idea's first suggestion), but every search
  pays the payload cost, and a long path can flip a useful step to `too-large`.
- **C. Opt-in, but default to a cheap form** — for example default `"labels"` so the
  rule sequence is always visible, with `"full"` on request and `"none"` to opt out.

Which delivery mode do you want, and what default?

### Answer

**Option C — opt-in with a cheap default.**

- The per-search-step option resolves to `"labels"` when the client does not set it, so
the rule sequence is available without asking.
- `"full"` is available on request for the intermediate states and rule text.
- `"none"` lets a client opt out of path data entirely.

Rationale: the path is the main reason to run a `search` from an agent, and a label
sequence is small (tens of bytes per step), so hiding it behind an explicit opt-in
would bury the feature. Payloads stay controlled because the expensive form is opt-in and
`"none"` is available.

## Question 2: What shape should the returned path have, and is it one shape or one per mode?

The bindings' `pathTo(n)` yields an interleaved list `[t0, r1, t1, …, rn, tn]`
(`2n+1` elements: `n` transitions). Candidate wire shapes:

- **S1. Initial state + transitions, one shape for both modes.**
  ```json
  "path": {
    "initial": "st(l, l, l, l)",
    "transitions": [
      {"rule": {"label": "crossWithSheep", "text": null}, "state": "st(r, l, l, r)"}
    ]
  }
  ```
  In `"labels"` mode `rule.text` and `state` are `null`; in `"full"` mode both are
  populated. Self-describing, position-safe, and the transition count is the path length;
  the cost is nulls in the cheap mode.
- **S2. A distinct shape per mode.** `"labels"` returns
  `{"initial": "...", "labels": ["crossWithSheep", ...]}`; `"full"` returns
  `{"initial": "...", "transitions": [...]}`. Minimal nulls, but the client sees two
  different structures depending on the mode, so consuming code must branch.
- **S3. Faithful interleaved list.**
  `[{"kind": "state", "term": ...}, {"kind": "rule", "label": ..., "text": ...}, ...]`.
  Mirrors `pathTo` exactly, but the initial/transition structure is implicit and the JSON
  is larger at equal content.

Should `initial` be included at all (it is the search subject, already known to the
client from the request), and should the final transition's `state` repeat the solution
`term`?

Which shape do you want?

### Answer

**S1 — one shape for both modes, with `initial` included.**

```json
"path": {
  "initial": "st(l, l, l, l)",
  "transitions": [
    {"rule": {"label": "crossWithSheep", "text": null}, "state": null}
  ]
}
```

- `initial` is always present: it is the search subject (small relative to the
  transitions), and having it makes the path readable on its own.
- `"labels"` mode: `rule.label` present, `rule.text` and `state` `null`.
- `"full"` mode: `rule.label` (nullable for unlabeled rules) and `rule.text` present,
  `state` present.
- The final transition's `state` repeats the solution `term`. Explicit redundancy is
  preferred over an implicit relation; it also lets a reader verify that the path ends at
  the solution.
- A zero-transition path (reflexive `=>*`, `=>#`) is `{"initial": "...", "transitions": []}`.

Rejected: S2 (two shapes force clients to branch on the mode), S3 (implicit structure and
larger payload for the same content).

## Question 3: How should path size be bounded, and what happens when a path exceeds the bound?

Paths are on by default (`"labels"`), so a bound matters both for payload size and for
not making previously fine searches fail. Data points from the probes: a 100-transition
path is 201 elements and ≈3 KB of rule text; the current caps allow 200 solutions per
step with unbounded depth (`interpreter_max_result_length` is 1,000,000 chars for a single
term or binding value).

Bounding options:

- **C1. New configuration entry `interpreter_max_path_steps`** — a field on the
  `Settings` class in `src/harold_mcp/settings.py` (pydantic-settings with
  `env_prefix="HAROLD_"`), so it is set through the environment variable
  **`HAROLD_INTERPRETER_MAX_PATH_STEPS`** exactly like the existing caps
  (`HAROLD_INTERPRETER_MAX_SOLUTIONS`, `HAROLD_INTERPRETER_MAX_RESULT_LENGTH`, …). It
  means "maximum transitions per solution path" (e.g. default 100 or 1,000), and is also
  documented in the `Settings` docstring and in the README env-var table. Combined with
  reusing `interpreter_max_result_length` per term/label/text element.
- **C2. Reuse `interpreter_max_result_length` per element only** — no new setting, but a
  total path of many small elements stays unbounded.
- **C3. New cap on the total serialized path length per search step.** Bounds the payload
  exactly, but needs accumulation during reconstruction and interacts with both modes.

Overflow behavior options:

- **O1. Whole step `too-large`** — consistent with the existing term/binding cap, no
  misleading partial path, but a search that previously succeeded can now fail because
  paths became default-on.
- **O2. Keep the solutions, drop the paths, and mark the step** (e.g.
  `path_omitted: true` or a per-step warning) — preserves the search result, but
  `path: null` needs a clear meaning.
- **O3. Truncate the path to a prefix** — rejected: a prefix that does not reach the
  solution is not a path to the solution.

Which cap and which overflow behavior?

### Answer

**C1 + O1** — a dedicated `interpreter_max_path_steps` cap
(`HAROLD_INTERPRETER_MAX_PATH_STEPS`), plus reusing `interpreter_max_result_length` per
term/label/text element; a path exceeding either bound makes the whole step `too-large`,
consistent with the existing term/binding cap.

Rationale: simplest option to explain and implement. Harold's purpose is to help an agent
write and iterate on Maude programs quickly; large-scale model checking is expected to run
outside Harold in the user's own Maude interpreter. Tool semantics should therefore stay
easy to understand: one new env-var-backed cap, one existing overflow rule (`too-large`),
no partial-path markers.

## Question 4: What default should `interpreter_max_path_steps` have?

It bounds transitions per solution path (a 7-step shepherd path has 7 transitions).
Measured data: a 100-transition `CHAIN` path is 201 path elements and ≈3 KB of rule text;
reconstruction is O(depth) per solution, so 200 solutions × 100 transitions is the worst
case at a 100 default.

- **D1. 100** — tight and cheap; covers most hand-written plans, but a legitimate
  100+-step search returns `too-large` by default.
- **D2. 1000** — very permissive; a pathological search (200 solutions × 1000
transitions) can still produce megabytes of labels text even though each element fits the
per-element cap.
- **D3. Some other value.**

Which default?

### Answer

**D1 — 100 transitions per solution path.**

Covers typical hand-written plans (the shepherd plan is 7 steps) and keeps the worst case
at 200 solutions × 100 transitions. A user with deeper searches raises
`HAROLD_INTERPRETER_MAX_PATH_STEPS`.

## Question 5: How should unlabeled rules appear in a path?

The bindings return `rule.getLabel()` as `None` for an unlabeled rule (`rl a => b .`),
while `str(rule)` always has the full statement. The Maude CLI's `show path labels`
prints `(unlabeled rule)`.

- **U1. `label: null`, `text` stays as-is.** Honest and machine-friendly: `null` means
  "no label". In `"labels"` mode the client sees a null entry in the sequence.
- **U2. `label: "(unlabeled rule)"`.** Mirrors the CLI's printed output, so an agent
  comparing against manual output sees the same string, but a real rule could plausibly
  be labeled that way and the value stops being a "label or nothing" field.
- **U3. Synthesize a stable identifier** (e.g. `"<unlabeled@1>"`). Informative, but
  invented and not meaningful to Maude or the user.

Which representation?

### Answer

**U1 — `label: null` for unlabeled rules.**

`label` is a genuine "label or nothing" field; `null` is honest and machine-friendly. The
full rule text remains available in `text` in `"full"` mode.

## Question 6: When `path` is `"none"`, what appears in the output?

Under the chosen S1 shape a solution is currently `{term, rewrites, bindings}`.

- **N1. `path` is always present as a field, `null` when `path: "none"` or when the step
  is not a search.** The output schema is stable and every solution has the same keys;
  an explicit `null` says "not requested" rather than "no path exists" (a path always
  exists for a search solution).
- **N2. `path` is omitted when not requested** (`exclude_none`) and only present for
  searches with `labels`/`full`. Smaller JSON, but the key set of a solution depends on
  the request, which is harder for a client to consume and unclear for `match` results.

How should absence be represented?

### Answer

**N1 — `path` is always present on search solutions, `null` when not requested.**

The output schema keeps one key set for every solution; `null` means "path not requested"
(not "no path exists").

## Question 7: What should the per-step input option look like?

The option lives on `SearchStep` and must be self-describing in the JSON schema the agent
sees.

- **I1. `path: "none" | "labels" | "full"`**, default `"labels"`. One enum-valued field;
  the default is documented in its schema description; no separate flag to keep in sync.
- **I2. `include_path: bool`** (default `true`). Smallest input, but it cannot express the
  cheap/full distinction and would need a second flag for rule text.
- **I3. `path_labels: bool` + `path_states: bool`.** Maximum control, but two interacting
  flags and a combinatorial description.

Which input shape, and is the chosen field name (`path`) clear enough for an agent reading
the tool schema?

### Answer

**I1 — `path: "none" | "labels" | "full"`, default `"labels"`.**

One enum-valued field on `SearchStep`, with the default documented in its schema
description (which becomes the tool's output/input documentation). No extra flags to keep
in sync, and the three modes read naturally to an agent.

## Question 8: Should paths be attached to solutions only, or should there also be a `show_path`-style step command?

The rough idea also raised whether to expose a command for showing a path, and whether
other commands would benefit. From the research:

- The bindings attach the path to each search solution, so no second command is needed.
- Maude's `show path` needs a state number from a search in the *same* interpreter;
  Harold recycles the interpreter per call, so state numbers are not durable.
- Only `search` (of the steps Harold exposes) has paths; `srewrite` and narrowing have
  path-like data but are not exposed today, and rewriting/matching have none.

- **P1. Attach-only (recommended).** Paths travel with search solutions; no `show_path`
  step, no exposed state numbers. Smallest surface, no cross-step state, nothing that
  breaks under hermetic calls.
- **P2. Also add a `show_path` step.** Would require returning state numbers from search
  steps and keeping the search result alive within the call; duplicates data the search
  already returned.
- **P3. Attach paths and also expose state numbers** for future commands. Adds a per-call
  concept with no use today.

Which scope?

### Answer

**P1 — attach-only.**

Paths travel with search solutions. No `show_path` step, no exposed state numbers, no
cross-step interpreter state; nothing that depends on the interpreter surviving between
steps or calls. Other commands are out of scope: `search` is the only step Harold exposes
that has a per-solution path.

## Requirements status

Decisions so far:

| # | Topic | Decision |
| --- | --- | --- |
| 1 | Delivery | Opt-in per search step, default `"labels"` (C) |
| 2 | Shape | `{initial, transitions: [{rule: {label, text}, state}]}`; initial always present; last `state` repeats the solution term (S1) |
| 3 | Bounding | New `interpreter_max_path_steps` (`HAROLD_INTERPRETER_MAX_PATH_STEPS`) + `interpreter_max_result_length` per element; overflow is whole-step `too-large` (C1 + O1) |
| 4 | Default cap | 100 transitions per solution path (D1) |
| 5 | Unlabeled rules | `label: null` (U1) |
| 6 | Absence | `path` always present on search solutions, `null` when `"none"` (N1) |
| 7 | Input option | `path: "none" \| "labels" \| "full"`, default `"labels"` (I1) |
| 8 | Scope | Attach-only; no `show_path`, no state numbers (P1) |

Open questions still to settle (or to defer to the design):

- Which `limit` value the outcome reports on a path overflow (e.g. the path cap or the
  per-element cap), so the error is actionable.
- Exact wording of the `maude_run` description for the new option and cap.

Is requirements clarification complete, or is there another aspect to pin down before
design?
