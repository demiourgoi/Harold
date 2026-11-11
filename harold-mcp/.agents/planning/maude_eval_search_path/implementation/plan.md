# Implementation plan — search paths in `maude_run`

## Checklist

- [x] Step 1: Add the `interpreter_max_path_steps` setting
- [x] Step 2: Define the path contract and the reconstruction helper
- [x] Step 3: Reconstruct paths in the session engine
- [ ] Step 4: Expose paths through `maude_run`
- [ ] Step 5: Documentation and release metadata

## Working agreements

Proceed step by step:

- After each step, ask me for confirmation before completing it
- When completing a step, add an "Implementation notes" subsection to its section in the plan, summarizing what we did, focusing on deviations from the plan, why we made them, and implications for subsequent steps

Additional agreements:

- The design at `../design/detailed-design.md` (revision 4) is the source of truth. If
  the code contradicts it, stop and update the design (and this plan) before continuing.
- Test-driven: write or update the tests for a step together with its code. Run the
  targeted tests first, then `make check` and the relevant test split.
- In sandboxed environments prefix commands with `UV_CACHE_DIR=/tmp/uv-cache`, e.g.
  `UV_CACHE_DIR=/tmp/uv-cache make check`. For a single test:
  `UV_CACHE_DIR=/tmp/uv-cache uv run python -m pytest tests/unit/test_maude_session.py`.
- Do not commit or stage anything; the user commits. Do not regenerate
  `.agents/summary/` in a code step; Step 5 records the refresh suggestion.
- After each step: tick the checklist item and append the required "Implementation
  notes" subsection to that step, including any deviation and its implications.

---

## Step 1: Add the `interpreter_max_path_steps` setting

**Objective.** Make the path-depth cap a normal configuration entry, exactly like the
other interpreter caps.

**Guidance.**

- Add `interpreter_max_path_steps: int = Field(default=100, gt=0)` to `Settings` in
  `src/harold_mcp/settings.py`, next to the other `interpreter_max_*` fields.
- Document it in the `Settings` class docstring: `HAROLD_INTERPRETER_MAX_PATH_STEPS`,
  default `100`, maximum transitions per search solution path.
- No other module needs to read it yet; Step 2 carries it in the session request.

**Tests.**

- `tests/unit/test_settings.py`: add the env var to `_ENV_VARS`, assert the default in
  `test_defaults`, add an override to `test_env_overrides`, and let the existing
  non-positive parametrization cover `0`/negative rejection.

**Integration with previous work.** None; this is the foundation the request contract
consumes in Step 2.

**Demo.** `Settings().interpreter_max_path_steps == 100`;
`HAROLD_INTERPRETER_MAX_PATH_STEPS=5` yields `5`; `...=0` fails fast at startup.

### Implementation notes

Implemented exactly as planned: the field sits between `interpreter_max_result_length`
and `interpreter_max_output_length` in `Settings`, the docstring documents
`HAROLD_INTERPRETER_MAX_PATH_STEPS` (default `100`, maximum transitions per search
solution path), and `tests/unit/test_settings.py` covers the default, an override,
and `0`/negative rejection (via the existing parametrization, which picks the new
env var up from `_ENV_VARS`). No deviations. Reviewed with the ponytail-review
skill (1 round, no findings).

---

## Step 2: Define the path contract and the reconstruction helper

**Objective.** Establish the worker/wire data contract and implement path assembly as a
pure, unit-testable helper, without changing what `maude_run` returns yet.

**Guidance.**

- In `src/harold_mcp/maude/session.py`:
  - add `PathRuleDict`, `PathTransitionDict`, `PathDict`;
  - add `path_mode: str | None` to `StepRequest` (the worker key is `path_mode`, not
    `path`, to avoid colliding with the file path in `SessionRequest`);
  - add `max_path_steps: int` to `SessionRequest`;
  - add `path: PathDict | None` to `SolutionDict`; `_collect_solutions` temporarily sets
    `"path": None` so the TypedDict stays total and behavior is unchanged;
  - add the `_PathResult` NamedTuple carrying `limit` and `message` (the collection
    result type changes in Step 3, keeping this step additive);
  - implement `_reconstruct_path(iterator, state_number, mode, max_path_steps,
    max_result_length) -> _PathResult` per design §5.2/§6: parent walk with early stop
    over cap, root-safe serialization, labels vs full, per-string cap. It must never call
    `getRule` for the root and never call `pathTo`.
- In `src/harold_mcp/maude/__init__.py`: import and re-export the three new TypedDicts in
  `__all__`.
- In `src/harold_mcp/server/tools/interpreter.py`: `_to_step_request` sets
  `"path_mode": None` for now (the wire input arrives in Step 4); `_to_request` sets
  `"max_path_steps": settings.interpreter_max_path_steps`. Model `__all__` additions are
  deferred to Step 4, when the models exist.
- Update every existing literal/assertion the required keys break: the unit tool tests
  (`test_search_step_forwards_pattern_subject_depth_and_type`,
  `test_request_carries_the_steps_and_configured_caps`, search-solution literals), the
  integration session helpers, and `tests/unit/test_maude_executor.py`'s module-level
  `SESSION_REQUEST`.
- Add `tests/unit/test_maude_session.py` with fake iterator/rule/term objects:
  - labels and full assembly, exact chain order, zero transitions, unlabeled rule;
  - root safety (the fake raises if `getRule` is called with the root number);
  - over-cap early stop (the fake counts `getStateParent` calls; no `getRule`/
    `getStateTerm` calls for an over-cap chain);
  - element cap reporting the result cap;
  - an invalid mode reached through the caller is a `ValueError` (test in Step 3 once the
    collection path exists).

**Tests.** The new unit file plus the updated existing helpers; run
`UV_CACHE_DIR=/tmp/uv-cache make test-unit` and `make check`.

**Integration with previous work.** Consumes the setting from Step 1; gives Step 3 a
tested building block. Tool behavior stays byte-for-byte the same (`path` stays null
everywhere).

**Demo.** The unit suite shows a fake 7-transition path assembled in both modes, a
zero-transition path, an over-cap path rejected after exactly `cap + 2` parent lookups,
and a request carrying `path_mode`/`max_path_steps`.

### Implementation notes

Implemented as planned, with one structural note: the over-cap check runs after the
extra `getStateParent` call, so an over-cap chain is rejected after exactly
`max_path_steps + 2` parent lookups (the count the plan's demo pins); a chain that
fits the cap costs `cap + 1`. The fake-based unit file also covers the
at-exactly-the-cap boundary and the `initial`-string element cap, beyond the plan's
minimum list. `_collect_solutions` sets `"path": None` for now, so tool behavior is
unchanged (all 66 integration tests pass unmodified except for the updated exact
literals). The invalid-mode `ValueError` is deferred to Step 3 with the collection
path, as planned. Reviewed with the ponytail-review skill (1 round, no findings).

---

## Step 3: Reconstruct paths in the session engine

**Objective.** Make `run_session` actually return paths, enforce the path caps, and name
every `too-large` limit — still without exposing the feature through `maude_run`'s wire
input.

**Guidance.**

- Rework `_collect_solutions` (design §5.2/§6):
  - iterate the search lazily (no `islice` + list); consume at most `max_solutions`
    solutions plus one extra for `truncated`;
  - read `iterator.getStateNr()` while positioned on each returned solution, then call
    `_reconstruct_path` for `"labels"`/`"full"`;
  - treat `path_mode is None` or `"none"` as no path; raise the defensive `ValueError`
    for any other value (same precedent as `search_type`);
  - check the solution term and bindings against `max_result_length` **before** any path
    work.
- Update `_collect_matches` to the new `_CollectionResult` shape (introduced in this
  step), and `_run_rewriting` to set `message` naming `interpreter_max_result_length` on
  `too-large`.
- Thread `path_mode` and `max_path_steps` through `_run_match_or_search` and `_run_step`.
- Update the docstrings of `_collect_solutions`, `_run_match_or_search` and
  `_reconstruct_path` (they are rendered in the API reference).
- Add the integration fixture `tests/integration/fixtures/search_path.maude` with
  `SHEPHERD`, `UNLABELED`, `CHAIN`, `BRANCH`.
- Update `_step`/`_request` in `tests/integration/test_maude_session_integration.py`
  (`path_mode=None`, `max_path_steps`) and the exact solution-dict assertions.
- Add the session-level integration tests from design §8.2: shepherd labels and full,
  `=>1`, reflexive (`depth=3`), `=>!`, `=>#`, unlabeled, laziness (`n(0) =>+ n(N)`,
  depth 2), `max_solutions=1`, path cap, element cap, `n(1500)` with `depth=1500` under
  the default and a raised cap, `path_mode="none"`/`None`, the invalid-mode
  `ValueError`, and the ordering pin (an oversized term with an over-cap path reports the
  result cap and calls no path accessor).

**Tests.** `UV_CACHE_DIR=/tmp/uv-cache make test-integration` (or targeted pytest),
then `make check` and `make test-unit`.

**Integration with previous work.** Uses the Step 2 helper and contract; keeps the tool
wire behavior unchanged (the tool sends `path_mode=None` until Step 4).

**Demo.** A direct session request with `path_mode="labels"` returns the shepherd's seven
labels; `"full"` returns rule text and states; `"none"`/`None` returns `path: null`;
`n(0) =>* n(1500)` at depth 1500 returns `too-large`, `limit=100`; a raised cap returns
1500 transitions.

### Implementation notes

Implemented as planned. One deviation: the `search_type`/`path_mode` validation and
the collection dispatch moved into a small `_collect_step` helper, because
`_run_match_or_search` exceeded ruff's cyclomatic-complexity limit (C901, 11 > 10)
with the new `path_mode` branch. Behavior is identical and the defensive `ValueError`
precedent is preserved. The fixture is the research probe's `search_path.maude`
verbatim, and all the design §8.2 session-level tests were added (shepherd labels/full,
`=>1`, reflexive, `=>!`, `=>#`, unlabeled, laziness, `max_solutions=1`, path cap,
element cap, deep search under the default and a raised cap, `"none"`/`None`, the
invalid-mode `ValueError`, and the at-exactly-the-cap boundary). The ordering pin
(oversized term before path work) is covered at the unit level with a fake that
fails on any path accessor. Reviewed with the ponytail-review skill (1 round, no
findings).

---

## Step 4: Expose paths through `maude_run`

**Objective.** Add the user-facing input option and output models so an MCP client
receives paths end to end.

**Guidance.**

- `SearchStep` gains `path: Literal["none", "labels", "full"] = "labels"` with its
  schema-description docstring (design §4.3).
- Add `MaudeRuleRef`, `MaudePathTransition`, `MaudeSearchPath`; add
  `path: MaudeSearchPath | None` to `MaudeSearchSolution`; update the
  `MaudeStepOutcome.message` docstring (interpreter text for `parse-error`, Harold's
  reason for `too-large`).
- `_to_solutions` adapts `solution["path"]` (dict or `None`).
- `_to_step_request` forwards `step.path` as `path_mode`.
- Add the three models to the tool module's `__all__`.
- Extend the `maude_run` docstring: the `search` bullet gets `path` and the three modes;
  "Output and limits" gets the path shape, the default, both caps and the `too-large`
  rule.
- Tests:
  - unit: default mode and invalid value; forwarding; labels/full/None adaptation
    including `label=None`; updated exact `model_dump()`; `too-large` path-cap adaptation
    with `message`;
  - tool-level integration: shepherd labels and full, `path="none"`, path-cap overflow,
    element-cap overflow, and the `=>!` case through `maude_run`.

**Tests.** `UV_CACHE_DIR=/tmp/uv-cache make test-unit`,
`UV_CACHE_DIR=/tmp/uv-cache make test-integration`, `make check`.

**Integration with previous work.** Completes the pipeline wired in Steps 2–3; the
session-level behavior is already covered, so this step only adds the wire surface and
its tests.

**Demo.** An MCP `maude_run` call `search` with default settings returns the seven
shepherd labels in order; `path: "full"` adds rule text and states; `path: "none"` returns
`path: null`.

---

## Step 5: Documentation and release metadata

**Objective.** Bring the user-facing docs and release metadata in line with the new
behavior.

**Guidance.**

- `README.md`: extend the `maude_run` bullet (paths and the three modes) and add
  `HAROLD_INTERPRETER_MAX_PATH_STEPS` to the env-var table.
- `CHANGELOG.md`: add a new version section describing the feature (default labels, full
  mode, cap, `too-large` semantics, unlabeled labels as null).
- `pyproject.toml`: propose the next `0.0.x` version (currently `0.0.5.dev0`, so
  `0.0.6.dev0` is the natural suggestion) and ask the user to confirm before changing it.
- Note in the step outcome that `.agents/summary/` should be refreshed with the
  codebase-summary skill (per the project conventions), and that the knowledge base's
  data-model notes are stale until then.
- `docs/modules.md` needs no entry (no public module is added; the engine docstrings were
  updated in Step 3 and are rendered there automatically).
- Run the full gate: `UV_CACHE_DIR=/tmp/uv-cache make release` (install, check, test,
  docs-test).

**Tests.** `make release` must pass. No new behavior; the step is documentation and
version metadata.

**Integration with previous work.** Describes the behavior implemented in Steps 1–4;
closes the feature.

**Demo.** `make release` green; README and CHANGELOG match the tool behavior; the
version is the agreed next release.
