# PDD summary — `no_new_module_quirk` (deferred `q .` warning quirk)

The user judged the requirements complete and directed a quick PDD: requirements were
consolidated without interactive clarification, research was run, and the design and
implementation plan are ready for execution.

## Artifacts

- [`rough-idea.md`](./rough-idea.md) — the user's original message (thoughts + decisions), verbatim.
- [`idea-honing.md`](./idea-honing.md) — consolidated requirements R1–R7, non-goals, success criteria.
- [`research/`](./research/)
  - [`quirk-inventory.md`](./research/quirk-inventory.md) — full residue inventory: trigger class is
    the undocumented period-terminated `q .`/`quit .`; the documented `quit` (no period) does not even
    stop file parsing; `eof` stops cleanly; the residue is *executable commands*; relative-path rules.
  - [`race-reproduction.md`](./research/race-reproduction.md) — opencode's claim reproduced (21/21
    spurious) and corrected (not a race — serialized execution still fails); fix verified 9/9 clean.
  - [`dependencies.md`](./research/dependencies.md) — `load`/`in` inside a file resolve against that
    file's directory; one-file-at-a-time diagnostics is final.
  - [`misattribution.md`](./research/misattribution.md) — Maude attributes correctly; our parser drops
    the filename; minimal schema-preserving fix proposed.
  - [`isolation-cost.md`](./research/isolation-cost.md) — timing/RSS tables; workers-default decision
    (`max(1, min(3, (os.cpu_count() or 0) // 2))`).
  - [`manual-commands-appendix.txt`](./research/manual-commands-appendix.txt) — text extract of the
    Maude manual Appendix A for reference.
- [`design/detailed-design.md`](./design/detailed-design.md) — the full design (components, data
  models, error handling, testing strategy, appendices).
- [`implementation/plan.md`](./implementation/plan.md) — 8-step TDD plan with a checklist.
- [`summary.md`](./summary.md) — this file.
- Scratch scripts in this directory (`scratch_*.py`) — the experiments behind the research notes.

## Design in one paragraph

Option A: `max_tasks_per_child=1` on the worker `ProcessPoolExecutor`, so every
diagnostics call runs on a fresh Maude interpreter and parser residue cannot leak
across calls (≈0.6–1.2 s/call, documented as a deliberate semantics change). Plus: the
`HAROLD_MAUDE_WORKERS` default becomes half the cores capped at 3; the input path is
absolutized in `SourceFile.from_path`; dependency warnings are attributed honestly
(whole-file diagnostics naming the dependency, with a suggestion to run
`maude_program_diagnostics` on it); the integration suite loses its
`heuristic_executor` workaround and gains red-green tests for the four isolation
scenarios, the parallel-diagnostics race, and file dependencies; and a ready-to-send
GitHub issue proposal for maude-bindings is produced.

## Next steps

1. Review the design and plan; adjust if anything looks off.
2. Start executing [`implementation/plan.md`](./implementation/plan.md) from Step 1
   (fixtures + red tests).
