# Port maude_eval.py as part of the diagnostics tool

On improve-rag/improvement/maude_eval.py we have a linter tool that corresponds to the following requirements:

> maude_eval.py is an isolated subprocess that loads a candidate module with the maude Python bindings, reduces the specification's test terms and captures the parser's stderr, separating load-time warnings (module invalid) from term-parsing warnings (specification issue). 

We want to incorporate that into the diagnostics tool at harold-mcp/src/harold_mcp/server/tools/diagnostics.py. 
We have to figure out:

- What maude_eval.py would contribute to our diagnostics tool. Is it really worth to add it to the tool?
- Does it fit in the extensible design for the MCP tool `maude_program_diagnostics` from harold-mcp/.agents/planning/port-linter.py/implementation/plan.md  ? Or should we add a different tool? We must keepthe code cohesive, simple and extensible and with low coupling

Also take into account

- improve-rag/.agents/summary/index.md
- harold-mcp/.agents/summary/index.md: note the implementation of the design harold-mcp/.agents/planning/port-linter.py/implementation/plan.md is still WIP (an agent is actively writing code right now), but that is the target state we want for  harold-mcp
