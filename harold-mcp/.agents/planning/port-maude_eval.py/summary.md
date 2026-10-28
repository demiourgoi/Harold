# Summary — `maude_run` (term evaluation / bounded interpreter sessions)

> **Status (2026-10-28): PDD complete and implemented.** `maude_run` landed in the
> unreleased 0.0.5 work: the settings and stream-capture foundation (Step 1), the worker
> session engine and executor (Step 2), the tool (Step 3), the rewriting family (Step 4),
> and `match`/`search` with the final description (Step 5). Step 6's README/module docs,
> `## [0.0.5]` changelog entries and the full `make release` validation are done; the
> version bump to the next WIP release is deferred to the follow-up 0.0.5 session because
> 0.0.5 is not released yet.

## Artifacts

| Artifact | Content |
| --- | --- |
| [`rough-idea.md`](rough-idea.md) | The original idea plus the 2026-10-17 update (current code state, annotations, executor reuse, statelessness, Term API scope, tool-shape alternatives, timeouts, module handling, single input file, output capture). |
| [`idea-honing.md`](idea-honing.md) | Q1–Q11 with the chosen answers and alternatives: new tool, step list, all six commands, REPL-style threading, load policy, caps as settings, timeout settings, name `maude_run`, output representation, outcome vocabulary, whole-call failures. |
| [`research/contribution.md`](research/contribution.md) | Phase-1 record: what `maude_eval.py` contributes (the capability, not the file). |
| [`research/placement.md`](research/placement.md) | Phase-1 record: why term evaluation does not belong in `maude_program_diagnostics`; the new-tool shape. |
| [`research/consumers.md`](research/consumers.md) | Phase-1 record: the `improve-rag` consumers and why they stay separate. |
| [`research/term-api.md`](research/term-api.md) | Bindings 1.6.0 inventory: module selection/enumeration, `parseTerm`, the rewriting family (mutation, counters), `match`, `search`, serialization. |
| [`research/worker-behavior.md`](research/worker-behavior.md) | Streams (stdout vs stderr, ANSI), hung reductions and pool recovery, per-call cost, executor reuse. |
| [`research/probes/`](research/probes/) | `probe_term_ops.py`, `probe_match_search.py`, `probe_streams.py`, `probe_modules.py`, `probe_timeout.py`, `probe_call_cost.py`, `probe_stdout_flush.py` plus transcripts and a README. |
| [`design/detailed-design.md`](design/detailed-design.md) | Standalone design: requirements R1–R16, architecture, components, data models, errors, testing, appendices. |
| [`implementation/plan.md`](implementation/plan.md) | Six TDD steps with checklist, tests and demos per step, plus the step reviews and implementation notes. |
| [`summary.md`](summary.md) | This file. |

## Design in one paragraph

`maude_run` runs a bounded Maude interpreter session in one call: it loads one file into a fresh
worker process (sibling `load`/`in` dependencies resolve automatically), selects an explicit
module, and executes an ordered list of `reduce`/`rewrite`/`frewrite`/`erewrite`/`match`/`search`
steps with REPL-style current-term threading. Every call is hermetic; callers carry state across
calls by re-submitting a saved result term or writing a wrapper module. The worker op
(`maude/session.py`) reuses `MaudeExecutor` (fresh process, crash/timeout recovery) and a new
shared capture helper (`maude/capture.py`) that captures **both** stdout and stderr — which also
closes a latent diagnostics bug where a loaded file's `red` output could reach the MCP stdio
transport. Results carry load warnings, per-phase captured output (truncated to a setting), and
per-step outcomes (`ok`, `parse-error`, `too-large`) that stop at the first failure. All caps and
both timeout knobs are `HAROLD_*` settings, and the tool description documents the semantics for
the agent.

## Key decisions

- **New tool, not a diagnostics provider** (Q1): term outcomes are data, not problems.
- **One tool with a step list** (Q2): subsumes a single-command tool; one fresh interpreter per
  session.
- **All six commands in v1** (Q3): adding them after the first tests the interface.
- **REPL-style threading** (Q4): matches the Maude manual; no re-sending of intermediate terms.
- **Always evaluate; report load warnings** (Q5).
- **Caps as settings** (Q6): 200 steps, 1000 rewrite bound, 200 solutions/matches, 100k term
  length, 1M result length, 1M captured output per stream — all ×10 the initial proposal.
- **Timeouts** (Q7): `HAROLD_DIAGNOSTICS_TIMEOUT_SECS` (renamed) and
  `HAROLD_INTERPRETER_TIMEOUT_SECS`, both best effort and covering interpreter startup, plus a
  per-call `timeout_secs` override.
- **Name and metadata** (Q8): `maude_run`, `INTERPRETER` tag, read-only annotation profile.
- **Output** (Q9): `{stdout, stderr}` per phase.
- **Outcomes** (Q10): `ok`/`parse-error`/`too-large`, stop at the first failure, one outcome per
  executed step.
- **Whole-call errors** (Q11): missing path, load false, module not defined, worker crash/timeout.
- **Binding bounds are exposed** (user review): `bound`, `gas`, `depth`; no deprecated
  `withExtension` (use `depth=0`).
- **IO lockdown retained** (R14): `setAllowDir/File/Processes(False)` in `init_maude`.

## Research highlights that changed the design

- `maude.load` returns `True` even for broken files; `getModule(name)` (case-sensitive) is the
  reliable check, and a `getModules()` diff lists the modules a file defined.
- `reduce`/`rewrite`/`frewrite` mutate in place and return the rewrite **counter** (which includes
  equational rewrites); `erewrite` returns `(Term, count)` and leaves the original intact.
- `str(term)` is the user-facing serialization (mixfix + numbers); `prettyPrint(0)` is internal.
- `match`/`search` iterators are lazy, so the solution cap can stop them.
- Maude's stdout is captured inside the fd-1 redirect (no explicit flush needed); Maude colorizes
  stderr even when redirected, so ANSI stripping is mandatory.
- A hung `reduce` is contained by the existing executor timeout + `kill_workers`, but recovery
  kills the whole pool (best effort, documented).

## Implementation plan

1. Settings and stream-capture foundation (diagnostics behavior unchanged; leak regression tests).
2. Worker session engine and executor (`reduce` only).
3. `maude_run` tool end to end (`reduce` only).
4. Rewriting family and current-thread threading.
5. `match` and `search`, final tool description.
6. Documentation, release bookkeeping, full validation.

All six steps are implemented and validated (`make release` is green). The only deferred
release action is the next-version bump, listed under "Next steps".

## Next steps

1. Finish the remaining 0.0.5 changes in a follow-up PDD session, then complete the release
   bookkeeping: bump `pyproject.toml` to the next WIP version (e.g. `0.0.6.dev0`), add the
   matching empty changelog section, and publish 0.0.5.
2. The knowledge base (`.agents/summary/`) and `AGENTS.md` were refreshed with the new tool,
   modules and settings.
3. Consider follow-ups outside this project: strategy commands (`srewrite`), `parseStrategy`,
   unification/variants, and a friendlier `match`-depth vocabulary.

## Resolved during implementation

- `search` type `BRANCH`: covered by the five-type integration test and the canonical-state
  test (`0` → `normal-form` `[0]`, `branch` `[]`); the probe records both.
- `gas`: verified against the interpreter (probe `probe_term_ops.py` plus an integration
  test); `gas=0` means no rewrites per position, and omitted values use the bindings' default.
- The `HAROLD_MAUDE_WORKER_TIMEOUT_SECS` → `HAROLD_DIAGNOSTICS_TIMEOUT_SECS` rename is
  prominent in the `## [0.0.5]` changelog section.
- The parent-stdout leak regression test uses a dedicated pool created inside the redirect and
  a non-blocking pipe read (multiprocessing's resource tracker can hold the write end); it was
  verified to fail against the old stderr-only capture.
- `match`/`search` enforce `max_result_length` on solution terms and bindings, and `depth` is
  constrained to `-1..2147483647` at the schema.
