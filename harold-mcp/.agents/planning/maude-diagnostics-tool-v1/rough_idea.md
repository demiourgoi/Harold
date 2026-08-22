# Maude diagnostics tool v1

## Goal

We want to implement in src/harold_mcp/tools/diagnostics.py a new MCP tool to diagnose Maude programs.
This is a first minimal version that should basically just load a source code file and check if it compiles

The new tool as a function called `maude_program_diagnostics` 
- defined in src/harold_mcp/tools/diagnostics.py 
- it's annotated with `@mcp.tool` for `mcp` from src/harold_mcp/server.py
- uses a concise and effective docstring, that will be used as MCP tool description per the FastMCP conventions

## Open questions

### Tool schema

The tool will take a string for the filepath of a Maude source code file (typically extension `.maude`, but do NOT validate the extension)
The schema of the output is still TBD

- Note in FastMCP the type annotations in tools determine the schema of the tool. Note we can use pydantic types, feel free to use them.
- Consider getting inspiration from the generic diagnostics tool you have available
  - See source code of that tool on:
    - https://raw.githubusercontent.com/zed-industries/zed/refs/heads/main/docs/src/diagnostics.md
    - https://raw.githubusercontent.com/zed-industries/zed/refs/heads/main/crates/diagnostics/src/diagnostics.rs
    - https://raw.githubusercontent.com/zed-industries/zed/refs/heads/main/crates/diagnostics/src/diagnostic_renderer.rs
  - See also "experiments with the diagnostics tool" below 
- See also https://en.wikipedia.org/wiki/Program_slicing for ideas 


#### experiments with the diagnostics tool you have available

- Input parameters:
```json


```json
{
  "name": "diagnostics",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {
        "type": ["string", "null"],
        "description": "The path to get diagnostics for. If not provided, returns a project-wide summary."
      }
    },
    "additionalProperties": false
  }
}
```

- Output seems to be free text. For example running the tool on src/harold_mcp/maude.py we get the following output:

```
Diagnostics successfully refreshed.

warning at line 15: Stub file not found for "maude"
warning at line 33: Type annotation for attribute `program_path` is required because this class is not decorated with `@final`
warning at line 41: Type annotation for attribute `module_name` is required because this class is not decorated with `@final`
warning at line 80: Type annotation for attribute `_lock` is required because this class is not decorated with `@final`
warning at line 89: Return type is Any
warning at line 89: Type `Any` is not allowed
warning at line 92: Type of "module" is unknown
warning at line 92: Type of "getModule" is partially unknown
  Type of "getModule" is "(name: Unknown) -> Unknown"
warning at line 95: Return type is unknown
warning at line 101: Type of "load" is partially unknown
  Type of "load" is "(name: Unknown) -> Unknown"
warning at line 104: Return type is Any
warning at line 104: Type `Any` is not allowed
warning at line 107: Return type is Any
```

**Observed output schema** (it's plain text, not JSON):

1. **Status line** — `Diagnostics successfully refreshed.` (or an error message if refresh failed).
2. **Zero or more diagnostic entries**, each formatted as:
   - `warning at line <N>: <message>` or `error at line <N>: <message>`
   - Some entries have **multi-line messages**, with the continuation indented under the primary line (e.g. the `getModule` detail: `Type of "getModule" is "(name: Unknown) -> Unknown"`).

So each entry carries: **severity** (`warning`/`error`), **line number**, and **message** (possibly multi-line). No column, file name (implied by the query), or structured metadata like codes is included.


### How can we programmatically detect a failure loading a Maude program?

For the programs:

```bash
juanrh@localhost:~/git/demiourgoi/Harold/harold-mcp/tests/integration/fixtures> cat broken-recoverable.maude
fmod HELLO-WORLD
    pr NAT .
    op f : -> Nat .
    eq f = 1 * 2 .
endfm

--- red in HELLO-WORLD : f .
--- q .
juanrh@localhost:~/git/demiourgoi/Harold/harold-mcp/tests/integration/fixtures> cat broken-non-recoverable.maude
fmo HELLO-WORLD
    pr NAT
    op f : -> Nat .
    eq f = 1 * 2 .
endfm

--- red in HELLO-WORLD : f .
--- q .
juanrh@localhost:~/git/demiourgoi/Harold/harold-mcp/tests/integration/fixtures>
```

- With the Maude REPL:

```bash
juanrh@localhost:~/git/demiourgoi/Harold/harold-mcp/tests/integration/fixtures> maude
		     \||||||||||||||||||/
		   --- Welcome to Maude ---
		     /||||||||||||||||||\
	    Maude 3.5.1 built: Jul 16 2025 12:00:00
	     Copyright 1997-2025 SRI International
		   Sat Aug 22 12:33:17 2026
Maude> load broken-non-recoverable.maude
Warning: "broken-non-recoverable.maude", line 1: skipped unexpected token: fmo
Warning: "broken-non-recoverable.maude", line 1: skipped unexpected token: HELLO-WORLD
Warning: "broken-non-recoverable.maude", line 2: skipped unexpected token: pr
Warning: "broken-non-recoverable.maude", line 2: skipped unexpected token: NAT
Warning: "broken-non-recoverable.maude", line 3: syntax error
Warning: "broken-non-recoverable.maude", line 3: skipped unexpected token: f
Warning: "broken-non-recoverable.maude", line 3: skipped unexpected token: :
Warning: "broken-non-recoverable.maude", line 3: skipped unexpected token: ->
Warning: "broken-non-recoverable.maude", line 3: skipped unexpected token: Nat
Warning: "broken-non-recoverable.maude", line 4: syntax error
Warning: "broken-non-recoverable.maude", line 4: skipped unexpected token: f
Warning: "broken-non-recoverable.maude", line 4: skipped unexpected token: =
Warning: "broken-non-recoverable.maude", line 4: skipped unexpected token: *
Warning: "broken-non-recoverable.maude", line 5: skipped unexpected token: endfm
Maude> red in HELLO-WORLD : f .
Warning: <standard input>, line 2: no module HELLO-WORLD.
Maude> load b
broken-non-recoverable.maude  broken-recoverable.maude
Maude> load broken-recoverable.maude
Warning: "broken-recoverable.maude", line 2 (fmod HELLO-WORLD): missing is keyword.
Maude> red in HELLO-WORLD : f .
reduce in HELLO-WORLD : f .
rewrites: 2 in 0ms cpu (0ms real) (~ rewrites/second)
result NzNat: 2
Maude> q .
Bye.
juanrh@localhost:~/git/demiourgoi/Harold/harold-mcp/tests/integration/fixtures>
```

- With Python

```py
>>> from harold_mcp.maude import get_runtime
>>> r = get_runtime()
>>> r.load_program('tests/integration/fixtures/broken-non-recoverable.maude')
Warning: <standard input>, line 1: skipped unexpected token: fmo
Warning: <standard input>, line 1: skipped unexpected token: HELLO-WORLD
Warning: "broken-non-recoverable.maude", line 2: skipped unexpected token: pr
Warning: "broken-non-recoverable.maude", line 2: skipped unexpected token: NAT
Warning: "broken-non-recoverable.maude", line 3: skipped unexpected token: f
Warning: "broken-non-recoverable.maude", line 3: skipped unexpected token: :
Warning: "broken-non-recoverable.maude", line 3: skipped unexpected token: ->
Warning: "broken-non-recoverable.maude", line 3: skipped unexpected token: Nat
Warning: "broken-non-recoverable.maude", line 4: skipped unexpected token: f
Warning: "broken-non-recoverable.maude", line 4: skipped unexpected token: =
Warning: "broken-non-recoverable.maude", line 4: skipped unexpected token: *
Warning: "broken-non-recoverable.maude", line 5: skipped unexpected token: endfm
>>> m = r.get_module('HELLO-WORLD')
Traceback (most recent call last):
  File "<python-input-3>", line 1, in <module>
    m = r.get_module('HELLO-WORLD')
  File "/home/juanrh/git/demiourgoi/Harold/harold-mcp/src/harold_mcp/maude.py", line 94, in get_module
    raise MaudeModuleNotFoundError(module_name)
harold_mcp.maude.MaudeModuleNotFoundError: Module 'HELLO-WORLD' not found
>>> r.load_program('tests/integration/fixtures/broken-recoverable.maude')
Warning: "broken-recoverable.maude", line 2 (fmod HELLO-WORLD): missing is keyword.
>>> m = r.get_module('HELLO-WORLD')
>>> t = m.parseTerm('f')
>>> t.reduce()
2
>>> str(t)
'2'
>>>
```

so in some cases Maude is able to recover and work with source code files that are not well format. Although this diagnostics tools should also point out any recoverable error, so the AI coding that uses the tool tries to fix them

Open questions

- Does the `maude` package provide any way to get a boolean for whether or not the tool was fully well formatted?
- The function `maude.init` has a parameter `advise (boolean, optional) – Whether debug messages should be printed.` We are currently using the default value of `True`, and thus getting the warning output, but that won't be visible to the client of the harold-mcp MCP server. Can we capture that output and use it to produce the output of the `maude_program_diagnostics` tool?  


See https://fadoss.github.io/maude-bindings/#maude.input  below:

```py
maude.init(loadPrelude=True, randomSeed=0, advise=True, handleInterrupts=False)
    Init Maude.

    This function must be called before anything else.

    Parameters:
        - loadPrelude (boolean, optional) – Whether the Maude prelude should be loaded.
        - randomSeed (int, optional) – Seed for the pseudorandom number generator in the RANDOM module.
        - advise (boolean, optional) – Whether debug messages should be printed.
        - handleInterrupts (boolean, optional) – Whether interrupts are handled by Maude.
```
