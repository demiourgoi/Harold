# Port maude_eval.py as part of the diagnostics tool

On improve-rag/improvement/maude_eval.py we have a linter tool that corresponds to the following requirements:

> maude_eval.py is an isolated subprocess that loads a candidate module with the maude Python bindings, reduces the specification's test terms and captures the parser's stderr, separating load-time warnings (module invalid) from term-parsing warnings (specification issue). 

We want to incorporate that into the diagnostics tool at harold-mcp/src/harold_mcp/server/tools/diagnostics.py. 
We have to figure out:

- What maude_eval.py would contribute to our diagnostics tool. Is it really worth to add it to the tool?
- Does it fit in the extensible design for the MCP tool `maude_program_diagnostics` from harold-mcp/.agents/planning/port-linter.py/implementation/plan.md  ? Or should we add a different tool? We must keepthe code cohesive, simple and extensible and with low coupling

Also take into account

- improve-rag/.agents/summary/index.md
- harold-mcp/.agents/summary/index.md

---

## Update (2026-10-17) — resuming the PDD

The note about the port-linter implementation being WIP is outdated: the heuristic linter
(`port-linter.py/implementation/plan.md`) and the hermetic per-call interpreter redesign
(`no_new_module_quirk/`) are both implemented and shipped. Current state:
`harold-mcp/.agents/summary/index.md` / `AGENTS.md`.

New considerations for the requirements and research steps (user message, 2026-10-17):

- **Tool annotations**: probably the same read-only profile as `maude_program_diagnostics`
  (`server/tools/diagnostics.py`: `readOnlyHint=True`, `destructiveHint=False`,
  `idempotentHint=True`, `openWorldHint=False`).
- **Worker reuse**: rely on the post-`no_new_module_quirk` architecture — every call runs on a
  fresh Maude interpreter process (`max_tasks_per_child=1`). Evaluate whether `MaudeExecutor`
  (`maude/executor.py`) can be reused as is: the new tool should also run each evaluation on a
  fresh process from scratch, loading a **list** of Maude files given as parameters, and
  evaluating in the **module** given as a parameter.
- **Stateless interpreter**: the interpreter is stateless across calls, which simplifies
  everything; a caller that needs state can persist it by (a) saving a resulting term and
  passing it in a later invocation, or (b) writing a more complex Maude wrapper program. The
  tool only launches the entry point — document this idea in the tool description.
- **Term API surface**: support all relevant methods from the `maude.Term` bindings
  (https://fadoss.github.io/maude-bindings/#maude.Term). At minimum support `rewrite` and
  `reduce`, returning the resulting term and the number of reduction steps plus other
  appropriate parameters. Consider whether methods like `Term.match` make sense to expose.
- **Tool shape — evaluate all options**:
  - multiple tools, one per operation; or
  - a single tool with an operation parameter (e.g. `"reduce"`, `"rewrite"`, ... emulating the
    Maude interpreter commands from the Maude manual Appendix A); or
  - a single tool supporting both a single command and a list of commands (a pipeline, e.g.
    reduce a term, then rewrite the result, then match the rewritten result...), returning all
    intermediate results in a list — easier for a coding agent.
- **Tool descriptions**: must be clear enough that the LLM knows how to use the tool.
- **Timeouts**: add a separate execution-timeout setting; consider renaming the existing one
  ("interpreter timeout" vs "diagnostic timeout"). Both timeouts apply to the whole worker call
  including interpreter startup, and are best-effort — document both in the README (which
  describes the params). Also allow a separate per-call timeout on the interpreter tool.
- **Module → term flow** (user comment, same day): in the maude Python bindings a `Module` must
  be loaded first to parse a term string into a `Term`, and the term's methods are then called
  on that `Term`. This settles how the module for evaluation is determined. For the module
  input, v1 only parses terms — module-level functionality like parsing strategies is future
  work.
- **Single input file, not a list** (user comment, same day): the `no_new_module_quirk`
  research (`research/dependencies.md`) found that `load`/`in` inside a file resolve against
  that file's own directory, so passing the main file suffices — dependencies are pulled in
  automatically. A list of input files is not needed; verify with additional research if
  needed.
- **Interpreter output capture** (user comment, same day): the tool should capture the Maude
  interpreter's output and return it as part of the result. Consider generalizing the
  `load_diagnostics` fd-2 capture in `worker.py` into a helper that works both for diagnostics
  and for the new commands, capturing **both stdout and stderr**.
