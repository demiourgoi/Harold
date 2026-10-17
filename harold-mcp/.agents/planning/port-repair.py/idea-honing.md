# Idea Honing — Port `repair.py` into Harold

> Requirements clarification log for the rough idea in [`rough-idea.md`](rough-idea.md).
> Q&A are appended in order; decision dates are recorded per question.
> Research that supports the answers: [`research/repair-py-analysis.md`](research/repair-py-analysis.md),
> [`research/contribution.md`](research/contribution.md), [`research/placement.md`](research/placement.md).

## Q1 — Go/no-go: is porting `repair.py` worth it, and where would any of it live?

**Context.** `improve-rag/improvement/repair.py` is the compile-and-repair loop of the improve-rag
optimization harness: one LLM generation followed by local verification (linter → interpreter load
→ differential tests against the original's outputs) and up to `--max-iters` repair rounds, with
configurable RAG context and an offline scripted connector. The rough idea asked whether that
contributes to Harold's `maude_program_diagnostics`, whether it fits the extensible design or
needs a different tool, and whether some of its ideas belong in `MaudeDiagnostic.fix`.

**Answer (2026-10-17).** **Do not port.** The loop is a fixed workflow whose purpose is to serve
as an **evaluation device for the RAG implemented by improve-rag** (its docstring advertises the
loop as a way to compare RAG backends; the README groups it with the comparison tooling). Harold
provides MCP tools to existing coding agents (Zed, opencode, Cline, …), so **control of the
evaluation flow stays with the agent**: an agent-controlled loop is strictly more flexible than a
fixed workflow (single prompt, fixed pipeline, fixed iteration cap, no user dialogue), and that is
exactly what a coding session with Zed or opencode already does natively.

- *What repair.py is composed of, and where each ingredient lives:*
  - lint rules, deterministic Unicode fixes, interpreter load + warning capture — **already
    ported** to Harold (often in better form: the ported `fix` is per-character on code lines
    only, report-only; repair.py's `autofix` is a global `str.replace`);
  - term evaluation (parse/reduce/values) — **already decided**: the paused `port-maude_eval.py`
    cycle said yes to the capability, as a new deferred tool (`maude_evaluate_terms`);
  - differential oracle (compare candidate vs original outputs) — a **client-side composition**
    that becomes trivial once the evaluation tool exists;
  - LLM connectors, prompts, RAG injection, the loop itself — the **MCP client's job**; porting
    them would invert Harold's division of labor.
- *Not in `maude_program_diagnostics`:* the tool's contract is `{path}` in, positioned problems
  out (v1 R2, LP3–LP8); a repair returns a transformed program, not findings, and would be
  non-deterministic, stateful and destructive under a read-only/idempotent annotation profile.
  See [`research/placement.md`](research/placement.md) §1.
- *Not a new server-side repair tool either:* it would need LLM API keys and network in the
  server, minutes-long stateful calls, and would duplicate the orchestration every target client
  already performs. "Repair programs with an LLM" is not one of Harold's three planned tool
  families. See [`research/contribution.md`](research/contribution.md) §3.
- *The `fix` question:* the only deterministic-edit idea repair.py had (the Unicode autofix) is
  already in `MaudeDiagnostic.fix`, ported more precisely than the original; everything else in
  repair.py is non-deterministic and not `fix` material by definition. See
  [`research/placement.md`](research/placement.md) §3.
- *Result:* the loop stays in improve-rag as its RAG-evaluation harness; Harold keeps providing
  the verification primitives the agent composes.

**Alternatives considered.**

| Alternative | Why rejected |
| --- | --- |
| Extend `maude_program_diagnostics` (repair provider or extra args) | Contract mismatch on every wire-model field: repair produces a program, not positioned diagnostics; the annotation profile would be false. Rejected on design grounds. |
| New MCP tool `maude_repair_program` (LLM in the server) | API keys/network/statefulness/non-determinism in a passive read-only server; duplicates the client's agent loop with a fixed prompt and iteration cap; no roadmap goal or tag category. |
| New verifier-only tool (`{path, terms}` → per-term verdicts) | That is the deferred `port-maude_eval.py` project (`maude_evaluate_terms` + client-side diff), not this one. |
| Client-side repair recipe (documented diagnose → fix → re-diagnose → evaluate → compare workflow) | Not rejected — kept as a candidate follow-up (option E in the research), outside Harold server code. |

**Requirements clarification complete.** The only requirement-bearing question was the go/no-go
itself; with "do not port" chosen, there is no feature to specify, so the requirements phase
closes here (same single-question shape as `port-maude_eval.py/idea-honing.md`).
