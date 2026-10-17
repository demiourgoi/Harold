# Summary — `repair.py` port: decision and research record

> **Status: closed at the decision point (2026-10-17).** Research and requirements are complete;
> the decision is **not to port**. `design/` and `implementation/` are intentionally empty — there
> is no Harold feature to design or implement; the candidate follow-ups are in
> [Next steps](#next-steps).

## Artifacts

| Artifact | Content |
| --- | --- |
| [`rough-idea.md`](rough-idea.md) | The original idea: consider incorporating `improve-rag/improvement/repair.py` into the diagnostics tool, and the three questions to settle. |
| [`idea-honing.md`](idea-honing.md) | Q1 — go/no-go and placement, with the chosen answer and the alternatives rejected. |
| [`research/repair-py-analysis.md`](research/repair-py-analysis.md) | Deep analysis of `repair.py`: the compile-and-repair loop, its component inventory, the inputs it needs (TOML spec, reference oracle, LLM endpoint, optional RAG), and its nature as a research harness. |
| [`research/contribution.md`](research/contribution.md) | The capability-by-capability answer: repair.py decomposes into seven ingredients; three are already ported to Harold, one is the deferred `port-maude_eval.py` decision, three are the client's job. |
| [`research/placement.md`](research/placement.md) | Fit test against `maude_program_diagnostics` (rejected), the options A–E (loop stays in improve-rag), and the `MaudeDiagnostic.fix` question (already absorbed, plus two independent fix-extension candidates). |

No code was changed in `harold-mcp` or in `improve-rag`; no Maude probes were run.

## Decision

- **The loop is not worth porting.** `repair.py` is a fixed workflow built as an **evaluation
  device for improve-rag's RAG** (its `--rag` switch compares retrieval backends inside the loop;
  the README groups it with the comparison tooling). Harold's purpose is different: it provides
  MCP tools to existing coding agents (Zed, opencode, Cline), so the **control of the evaluation
  flow stays with the agent**. An agent-controlled loop is more flexible than a fixed workflow
  (single prompt, fixed pipeline, fixed iteration cap, no user dialogue) and is what those clients
  already do natively.
- **It does not belong in `maude_program_diagnostics`** — a repair returns a transformed program,
  not positioned diagnostics, and would violate the tool's `{path}`-in/problems-out contract and
  its read-only/idempotent annotation profile — **nor in a new server-side repair tool**, which
  would need LLM API keys, network, statefulness and non-determinism inside a passive read-only
  server, duplicating the client's orchestration.
- **The decomposition instead:** lint rules, deterministic fixes and interpreter load are already
  ported; term evaluation (the missing verifier half) is the paused `port-maude_eval.py` decision
  (yes to the capability, new deferred tool `maude_evaluate_terms`); the differential oracle and
  the loop are client-side compositions.
- **The `fix` question:** repair.py's only deterministic-edit idea (the Unicode autofix) is
  already `MaudeDiagnostic.fix`, ported more precisely than the original (per-character spans on
  code lines, report-only, vs. a global `str.replace`). Nothing else in repair.py is fix material.
- **Decision recorded** in [`idea-honing.md`](idea-honing.md) Q1.

## Next steps

1. **(Optional follow-up — completes the agent-side verifier.)** Resume
   `port-maude_eval.py` (Phase 2 probes → requirements → design → plan) to build
   `maude_evaluate_terms`. With it, an MCP client can run the full repair.py-style verification —
   diagnose, apply `fix` edits, evaluate terms, compare against the original — under its own
   control.
2. **(Optional follow-up — richer fixes, independent of repair.py.)** The two deterministic fix
   candidates found during research: `dash-comment` (`--` → `***`) and `eq-in-term` (`=` → `==`).
   Both come from the linter rules, not from repair.py; their safety was desk-checked, not
   probe-verified (the `port-linter.py` probe style would settle it). A small requirements/design
   cycle of their own if wanted.
3. **(Optional follow-up — client-side recipe.)** Option E from
   [`research/placement.md`](research/placement.md) §2: a documented client-side repair recipe
   (e.g. an opencode skill) over Harold's tools. No Harold server code involved.
4. **(Knowledge-base housekeeping.)** Suggest re-running the codebase-summary skill so
   `AGENTS.md`'s `.agents/planning/` list includes this project (like the other cycles).

### Housekeeping

Nothing to release for this cycle: no code changed, so no `CHANGELOG.md` entry and no version bump
in `pyproject.toml`. `README.md` is unaffected (the tool list is unchanged).

## Points that may deserve further refinement

- **The agent-loop premise is client-dependent.** "Every MCP client can orchestrate the loop" is
  true for the target clients (Zed, opencode, Cline) but not for every MCP client; a client that
  cannot run multi-step tool loops would get less value from Harold's primitive-tools approach
  than from a monolithic repair tool. The project goals explicitly target coding agents, so this
  is accepted as a non-issue — noted for completeness.
- **The two fix candidates need probes.** Their safety arguments (whitespace-delimited `--` only
  fires on comment attempts; a lone `=` is never legal in an `if…then` span) are regex-level
  reasoning, not interpreter-verified.
