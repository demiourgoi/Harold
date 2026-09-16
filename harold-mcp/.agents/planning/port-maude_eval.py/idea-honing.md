# Idea Honing — Port `maude_eval.py` into Harold

> Requirements clarification log for the rough idea in [`rough-idea.md`](rough-idea.md).
> Q&A are appended in order; the decision dates are recorded per question.
> Research that supports the answers: [`research/contribution.md`](research/contribution.md),
> [`research/placement.md`](research/placement.md), [`research/consumers.md`](research/consumers.md).

## Q1 — Go/no-go: is porting `maude_eval.py` worth it, and where would the capability live?

**Context.** `improve-rag/improvement/maude_eval.py` is the isolated evaluator of the repair loop:
a subprocess that loads a Maude file, parses/reduces a list of terms, returns the values as JSON
and separates load-phase warnings from term-phase warnings. Harold has the load half already
(`InterpreterDiagnosticProvider` + the worker's fd-2 capture) but nothing that evaluates a term.
The candidate design question was whether that half belongs in `maude_program_diagnostics` —
possibly as one more provider behind the diagnostics seam — or in a tool of its own.

**Answer (2026-09-16).** **Implement it, but not just now, and as a new tool.**

- *Worth it:* yes for the **capability** — evaluating terms against a loaded file is the missing
  semantic half of Harold's feedback loop and the seed of the project's second goal ("run Maude
  programs"). Diagnostics can only report what the loader and text heuristics see; it cannot say
  "this term reduces to 1024" or "this term no longer parses because you changed a signature".
  See [`research/contribution.md`](research/contribution.md) §2.1.
- *Not in `maude_program_diagnostics`:* the diagnostics tool is contractually "`{path}` in,
  problems with that file out" (v1 R2, LP4, LP8); term outcomes are data about a
  *(file, terms)* pair, have no position, and would force a second meaning into `success`,
  `summary` and the `DiagnosticSource` vocabulary. See [`research/placement.md`](research/placement.md) §2.
- *New tool:* a separate MCP tool (working name `maude_evaluate_terms`), one new worker op reusing
  `MaudeExecutor` for crash/timeout recovery, tagged with the already-reserved `interpreter` tag
  (`harold_mcp/server/tags.py` L29). `diagnostics/` stays untouched.
- *Timing:* **deferred** — this cycle produces the decision and the research record only; no code
  changes in `harold-mcp` and `improve-rag`. The work to resume is listed in
  [`summary.md`](summary.md) → Next steps.

**Alternatives considered.**

| Alternative | Why not now |
| --- | --- |
| Add an optional `terms` argument (and a term-evaluation provider) to `maude_program_diagnostics` | Breaks the documented schema (R2) and the "one composite tool, all providers attempted" rule (LP4); overloads `success`/`summary`/ordering with a second meaning. Rejected on design grounds, not just sequencing. |
| Port `maude_eval.py` faithfully, `improve-rag` compatibility included (same JSON, `===TERMES===` protocol, `times`, `rlapp_`/`arlapp_`) | The transport (subprocess per call) is superseded by Harold's worker pool, and the extra fields serve the research harness (ranking, rule-module conventions, TOML specs), which stays in `improve-rag`. See [`research/consumers.md`](research/consumers.md) §2. |
| Do nothing at all | Loses the semantic feedback loop, which is the main gap for models under-trained in Maude; the capability is wanted eventually, so the decision is "defer", not "reject". |
