# Port linter.py as part of the diagnostics tool

On improve-rag/improvement/linter.py we have a linter tool that corresponds to the following requirements:

> parse errors: a 'when' guard borrowed from Haskell/SML, a typographic Unicode apostrophe, '=' used instead of '==' inside an if_then_else_fi term, and a redeclared Qid sort shadowing the built-in. 
> linter.py encodes the observed failure taxonomy — one rule per real failure, with severity levels, safe autofixes (Unicode punctuation) and diagnostics written to be fed back to a model, where the Maude parser often only says 'parsing error'.

We want to incorporate that into the diagnostics tool at harold-mcp/src/harold_mcp/server/tools/diagnostics.py. 
We have to figure out:

- What linter.py would contribute to our diagnostics tool. Is that a set of heuristics corresponding to common programming errors with Maude, and mixing Maude with other programming languages? It is something else? 
- What changes would be required in the model `MaudeProgramDiagnosticsResult` returned by `maude_program_diagnostics` 
- How can we extend `maude_program_diagnostics` with this additional linting logic, while keeping the code cohesive, simple and extensive and with low coupling? What is the right low level technical desing for that? Is extending the diagnostics tool even the right choice, or should we create a new tool? 

Also take into account

- improve-rag/.agents/summary/index.md
- harold-mcp/.agents/summary/index.md
