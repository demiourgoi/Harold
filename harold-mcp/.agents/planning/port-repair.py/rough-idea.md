# Port repair.py as part of the diagnostics tool

On improve-rag/improvement/repair.py we have a linter tool that corresponds to the following requirements:

> repair.py assembles these into a compile-and-repair loop: generate with RAG context, autofix, lint, load, run the differential tests against the original's outputs, and if anything fails, send the diagnostic back to the model together with the original program — at most a configurable number of iterations. A scripted connector replays canned responses so the whole loop is testable offline; the loop was validated by replaying the six real failures against the real Maude interpreter before spending a single token.


We want to consider incorporating that into the diagnostics tool at harold-mcp/src/harold_mcp/server/tools/diagnostics.py.  
We have to figure out:

- What repair.py would contribute to our diagnostics tool. Is it really worth to add it to the tool?
- Does it fit in the extensible design for the MCP tool `maude_program_diagnostics` from harold-mcp/src/harold_mcp/server/tools/diagnostics.py  ? Or should we add a different tool? We must keep the code cohesive, simple and extensible and with low coupling
- Can we just take some ideas and add that to `MaudeDiagnostic.fix`

Also take into account

- improve-rag/.agents/summary/index.md
- harold-mcp/.agents/summary/index.md
