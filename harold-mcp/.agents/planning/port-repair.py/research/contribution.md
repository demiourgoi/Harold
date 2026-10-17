# Research — what `repair.py` would contribute to Harold

> Phase 1 (decision-oriented) research for the rough idea in [`../rough-idea.md`](../rough-idea.md).
> Question answered here: *"What would `repair.py` contribute to our diagnostics tool? Is it
> really worth adding it to the tool?"* Companion documents:
> [`repair-py-analysis.md`](repair-py-analysis.md) (what the artifact is) and
> [`placement.md`](placement.md) (where any of it belongs). Written 2026-10-17. No code changed.

## 1. Reframing: the loop vs. its ingredients

`repair.py` is not one capability; it is a **composition** of five ingredients around one LLM
call:

| # | Ingredient | Source in repair.py | Status in Harold (target state) |
| --- | --- | --- | --- |
| 1 | Heuristic lint (6 rules) | `linter.py::lint` | **Ported** as `HeuristicLinterProvider` (7 rules, false-positive hardening, exact columns) |
| 2 | Deterministic autofix (8 Unicode substitutions) | `linter.py::autofix` | **Ported, in better form**: per-finding `fix` payloads with exact spans on code lines only (repair.py's version is a global `str.replace` — it rewrites comments and strings too); report-only by design decision |
| 3 | Interpreter load + warning capture | `maude_eval.py` via `evaluer` | **Ported, in better form**: worker process with fd-2 capture, crash/timeout recovery, hermetic calls |
| 4 | Term evaluation (parse/reduce, values out) | `maude_eval.py` | **Decided, deferred**: `port-maude_eval.py` concluded "yes to the capability, as a new tool"; no term ops exist yet |
| 5 | Differential oracle (compare candidate vs original outputs) | `verifier` L280-306 | **Nothing, and nothing planned**: lives in the harness clients (`repair.py`, `best_of.py`, `check.py::MaudeDriver.diff_test`); needs a TOML spec + a reference run, inputs Harold tools do not take |
| 6 | LLM connectors + prompts + RAG context + few-shot exemplar | `Gemini`/`EdenAI`/`Scripted`, `charger_rag`, `exemplaire_similaire` | **Nothing, and nothing planned**: this is the *client's* job in an MCP architecture |
| 7 | The loop itself (state, iteration, trace, output file) | `repair_loop`, `main` | **Nothing, and nothing planned**: same reason |

Three of the seven ingredients are already in Harold (1–3); one is decided-but-deferred (4);
three are orchestration (5–7). The interesting question is only whether ingredients 5–7 have a
Harold home at all.

## 2. What ingredient 5 (differential testing) would buy — and why it stays out

The `verifier`'s feedback is the best part of `repair.py` — it is the only place in
improve-rag that produces *semantic* failure messages:

```
- term `fib(10)` does NOT PARSE in your module, while the original computes `55`.
  You changed the declared operators or sorts. RESTORE the original signatures.
- term `pow(2, 10)` : expected `1024`, got `pow(2, 10)` (did not reduce - an equation
  probably does not match)
```

But it is a **client-side composition**, not a checker:

- It needs a *(file, spec)* pair: the test terms come from a TOML spec and the oracle from a
  second run of the original program. Harold's tools take exactly `{path}`.
- It produces a *verdict*, not a *positioned diagnostic*: "signature changed" / "equation does
  not match" has no line, no column, no deterministic fix — it is exactly the kind of guidance an
  LLM should reason about.
- The comparison step is trivial once term evaluation exists (`port-maude_eval.py` TE2 returns
  per-term values; a client diffing two value lists is a few lines of MCP-client logic).

So the correct decomposition is: **the deferred `maude_evaluate_terms` tool provides ingredient
4, and the MCP client provides ingredient 5 for free** — the same way `repair.py` itself is a
thin client over `maude_eval.py` today. Harold does not need to own the comparison; it needs the
evaluation primitive, which is already planned.

## 3. What ingredients 6–7 would buy — nothing for Harold's architecture

Harold's role (per `AGENTS.md` → *Project goals* and the v1/port-linter designs): a **passive MCP
tool server** for agents under-trained in Maude, with three planned tool families — diagnose
(done), run (planned, `interpreter` tag reserved), docs RAG (planned, `docs` tag reserved).
Harold's clients (opencode, Cline, …) are themselves LLM orchestrators with multi-step
tool-calling loops, context windows, and their own model choices.

Porting the loop would invert that division:

| Consequence | Details |
| --- | --- |
| **API keys and network in the server** | `Settings` would grow `HAROLD_GEMINI_API_KEY`-style secrets; the server would make outbound LLM calls (cost, latency, rate limits, provider choice baked into the tool). |
| **Statefulness** | A repair session is minutes of wall time over several LLM rounds; MCP tools are request/response, and FastMCP's current tool contract is one-shot (`{path}` in, result out). The loop's own output is a *new file on disk* — the first destructive Harold tool. |
| **Non-determinism inside the tool** | Diagnostics' annotation profile is read-only/idempotent; a repair tool is the opposite on every axis. The `Scripted` connector exists in improve-rag precisely because LLM loops cannot be tested otherwise. |
| **Duplication of the client** | Every MCP client already knows how to call a tool, read a result, edit code, and call again — that *is* the agent loop. `repair.py` would re-implement it server-side, with a fixed prompt, a fixed provider list, and a fixed iteration cap, removing client control over all three. |
| **Roadmap divergence** | "Repair programs with an LLM" is not one of the three project goals; the `tags.py` vocabulary has no category for it. |

The *loop's* value proposition — local verification feedback that makes an LLM self-correct —
survives the port decision either way: an MCP client today can already run
`maude_program_diagnostics` (ingredients 1–3), apply `fix` edits, and re-diagnose, which is the
lint/load half of the loop; adding `maude_evaluate_terms` completes the verifier. The loop is
then a client-side skill/recipe, not a server feature.

## 4. Capability-by-capability verdict

| Ingredient | Worth having in Harold? | How |
| --- | --- | --- |
| Lint rules | ✓ | Already in (ported, hardened) |
| Deterministic fixes | ✓ | Already in (report-only `fix`; ported better than the source) |
| Load + warning capture | ✓ | Already in (worker + provider) |
| Term evaluation | ✓ | Planned — `port-maude_eval.py` decision: new tool, deferred |
| Differential oracle | ~ | Client-side composition over the evaluation tool; not a Harold capability |
| LLM connectors / prompts / RAG injection | ✗ | Client's job; prompts are prompt engineering, not server code |
| The loop itself | ✗ | Stateful, non-deterministic, destructive, needs API keys; duplicates the MCP client's orchestration |

**Answer to the rough idea's first question: `repair.py` as a *loop* would contribute nothing
Harold should accept — it belongs to the orchestrator, which is the MCP client. Its *verification
ingredients* were or will be contributed, and three of the four are already done.** The remaining
one (term evaluation) is the paused `port-maude_eval.py` project, not this one.

## Sources

- `improve-rag/improvement/repair.py` (L55-88, L266-307, L314-389), `linter.py` (L34-41).
- `harold-mcp/src/harold_mcp/heuristic/rules.py` (L22-32, L80-88: the ported fix table),
  `server/tags.py` (L28-30), `server/tools/diagnostics.py` (tool contract + annotations).
- `harold-mcp/.agents/planning/port-linter.py/summary.md` (report-only fix decision).
- `harold-mcp/.agents/planning/port-maude_eval.py/summary.md` and `research/contribution.md` §2,
  §3 (the deferred evaluation tool).
