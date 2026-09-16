# Summary — `maude_eval.py` port: decision and research record

> **Status: paused at the decision point (2026-09-16).** Phase 1 research is complete; the
> capability is wanted but deliberately not implemented in this cycle. `design/` and
> `implementation/` are intentionally empty — the work to resume is in [Next steps](#next-steps).

## Artifacts

| Artifact | Content |
| --- | --- |
| [`rough-idea.md`](rough-idea.md) | The original idea: port `improve-rag/improvement/maude_eval.py` into the diagnostics tool, and the two questions to settle first. |
| [`idea-honing.md`](idea-honing.md) | Q1 — go/no-go and placement, with the chosen answer and the alternatives rejected. |
| [`research/contribution.md`](research/contribution.md) | What `maude_eval.py` is, capability-by-capability against Harold's target state, and what it would (and would not) contribute. |
| [`research/placement.md`](research/placement.md) | Fit test against `maude_program_diagnostics` and its provider seam; options A–D; the recommended shape of a future tool; open design questions. |
| [`research/consumers.md`](research/consumers.md) | The `improve-rag` consumers, the de-facto evaluator contract they settled on, and why they should not migrate to Harold. |

No code was changed in `harold-mcp` or in `improve-rag`; no Maude probes were run.

## Decision

- **The capability is worth having**: evaluating terms against a loaded file (parse → reduce →
  value, with per-term outcomes) is the semantic half of Harold's feedback loop and the seed of
  goal #2, "run Maude programs". Today nothing in Harold runs a term, so every claim about
  behaviour is left to the model's reasoning.
- **It does not belong in `maude_program_diagnostics`**: the tool's contract is `{path}` in,
  problems with that file out (v1 R2, LP4, LP8); term outcomes are data about a
  *(file, terms)* pair, have no position, and would give `success`/`summary`/`DiagnosticSource` a
  second meaning.
- **A new tool is the home**: one new worker op reusing `MaudeExecutor` for isolation, crash and
  timeout recovery; its own result models; `harold_tags(INTERPRETER)`; `diagnostics/` untouched
  (recommended shape in [`research/placement.md`](research/placement.md) §3.1).
- **Deferred**: not implemented now (see [`idea-honing.md`](idea-honing.md) Q1).

## Next steps

To resume, start with the Phase 2 probes (they settle the questions that block the design), then
run the requirements step, then design and plan. Nothing below is committed work yet.

### Phase 2 research — `research/worker-term-evaluation.md` (+ `research/probes/`)

Follow the precedent of `port-linter.py/research/` (`probes/` scripts plus the recorded
transcript next to the findings). Probes can run with `harold-mcp/.venv/bin/python` (the `maude`
bindings import fine there) against the local Maude tree at
`/home/juanrh/systems/maude/Maude-3.5.1-linux-x86_64`; sandboxed `make`/`uv` runs need
`UV_CACHE_DIR=/tmp/uv-cache`.

- [ ] **P1 — hard-failure signal.** Fresh interpreter, `maude.init(advise=False)`, then compare
      `maude.load(...)`'s bool with `getCurrentModule()` and `getModule("HELLO-WORLD")` for:
      `tests/integration/fixtures/broken-non-recoverable.maude`, `hello.maude`, and
      `no_new_module.maude` (a legitimate program that defines no modules — v1's counter-example
      against module-set heuristics). **Why:** `maude_eval.py` uses `getCurrentModule() is None`
      to declare the module invalid, and today `InterpreterDiagnosticProvider` reports a wholly
      unparseable file as plain warnings with no `error` (v1 research §2). Either this probe
      yields a *diagnostics* improvement (a real hard-failure case), or it extends the v1 "no
      module heuristics" rejection to the current module. Decide which with the data.
- [ ] **P2 — term-phase stderr.** Does `parseTerm` (and `search`/`rewrite` in the `rlapp`-style
      paths) write to fd 2? Record exact formats for: a term that does not parse, an undeclared
      operator, a successful parse/reduce, and a reduction that warns. **Why:** decides between a
      `===TERMES===`-style sentinel, fd-2 capture scoped to each phase, or nothing.
- [ ] **P3 — value fidelity.** Confirm `Term.reduce()` returns the step count (not the value) and
      that `str(term)` / `prettyPrint(0)` is the value; check whether the sort is reachable
      (`getSort()`); record what a term that reduces to itself prints. **Why:** the result model's
      per-term value representation.
- [ ] **P4 — hang and timeout cost.** Reduce a non-terminating term and observe
      `MaudeWorkerTimeoutError` plus pool replacement, including whether a concurrent call on the
      same pool is affected. **Why:** decides per-term budget vs whole-call timeout
      ([`research/placement.md`](research/placement.md) §4.1).
- [ ] **P5 — module selection and history.** After loading two files, determine which module is
      current; compare current-module `parseTerm` with explicit `getModule(name).parseTerm`; check
      the effect of a preceding diagnostics-style load. **Why:** whether the tool needs an explicit
      `module` parameter for deterministic results (`placement.md` §4.2).

### Requirements step (continue `idea-honing.md` with Q2+)

- [ ] Term scope: plain reduction only, or also `rewrite`/`search` (option B vs D in
      [`research/placement.md`](research/placement.md) §3).
- [ ] Tool name and description (working name `maude_evaluate_terms`); annotation profile.
- [ ] Input model: path + terms list; is an explicit `module` parameter required? Are term lists
      capped (length, value size)?
- [ ] Load policy: is a file whose load produced warnings still evaluated, and how are those
      warnings reported? (The harness says "not usable"; an LLM-facing tool probably should not.)
- [ ] Failure semantics: per-term outcome vocabulary (e.g. `reduced` / `parse-error` /
      `not-reduced` / `timed-out`) and where a whole-call failure (crash, timeout) lands.
- [ ] Interaction with `maude_program_diagnostics`: same worker pool, so loaded-module state is
      shared — confirm that this is acceptable and document it in both tool descriptions.
- [ ] Whether the P1 finding (if it holds) is ported into `InterpreterDiagnosticProvider`
      independently of this tool.

### Design step — `design/detailed-design.md`

- [ ] Per the PDD structure (Overview, Detailed Requirements, Architecture, Components and
      Interfaces, Data Models, Error Handling, Testing Strategy, Appendices), starting from the
      recommended shape in [`research/placement.md`](research/placement.md) §3.1: worker op
      (`maude/worker.py`) → executor method (`MaudeExecutor._run_task`) → value types
      (`maude/evaluation.py`) → tool + wire models (`server/tools/evaluation.py`) →
      `harold_tags(INTERPRETER)` → `docs/modules.md` entry.
- [ ] Reuse the established conventions: fd-2 capture in the worker, `MaudeWorkerError` →
      tool-level error mapping, pydantic result models with attribute docstrings, `Depends` with
      `# noqa: B008`, mypy strict, basedpyright unused-result discipline.

### Implementation step — `implementation/plan.md`

- [ ] TDD, incremental steps, each ending wired end-to-end (a demoable tool call), e.g.:
      (1) worker op + executor method + a minimal tool returning per-term values behind a fake
      executor in unit tests and the real interpreter in integration tests;
      (2) module selection / load-warning reporting;
      (3) timeouts, caps and error semantics;
      (4) documentation, README tool list, `CHANGELOG.md` entry and version bump, knowledge-base
      refresh. Test files need distinct basenames across `tests/unit/` and `tests/integration/`.

### Prerequisite

- [ ] The target architecture this research assumes (the provider seam and the ported heuristic
      linter) is still being implemented by `port-linter.py/implementation/plan.md`; resume this
      project once that work has landed, so the new tool is built against the finished layout.

### Housekeeping

- Nothing to release for this cycle: no code changed, so no `CHANGELOG.md` entry, no version bump,
  and `.agents/summary/` stays accurate as is. The release bookkeeping above applies when the tool
  is actually implemented.
