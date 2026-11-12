# Step and load output capture (B4/B7)

Probe: `probes/probe_step_output.py` (real worker, `maude_workers=1`, fixture
`fixtures/step_output.maude`, a file whose last command is `search [1] a =>* Z:S .`).

## Load phase — fixed

Every scenario reports the complete bounded-search block in `load_output.stdout`,
even though the bounded search is the **last** command in the file:

```
load stdout: '==========================================\n
search [1] in STEPS : a =>* Z:S .\n\n
Solution 1 (state 0)\n
states: 1  rewrites: 0 in 0ms cpu (0ms real) (~ rewrites/second)\n
Z:S --> a\n'
```

The previous PDD's `fflush(NULL)` inside the capture window (see
`harold_mcp/maude/capture.py::_flush_stdio`) is doing its job. B7 does not reproduce.

## Steps — empty stdout is expected, not lost output

All programmatic commands (`reduce`, `rewrite`, `search`) return values through the
SWIG bindings; they do not print. The bindings' `search` returns an iterator:

```c
// maude-bindings/swig/term.i
RewriteSequenceSearch* search(SearchType type, EasyTerm* target,
                              const Vector<ConditionFragment*> &condition = NO_CONDITION,
                              int depth = -1);

// "An iterator through the solutions of a search."
class RewriteSequenceSearch { ... int getStateNr() const; ... };
```

Probe results (all `status=ok`, solutions are present in the structured field):

| Scenario | Step | `stdout` | `stderr` |
| --- | --- | --- | --- |
| bounded search (cap 1) + reduce | search / reduce | `''` / `''` | `''` / `''` |
| bounded search, last step | search | `''` | `''` |
| exhaustive search + reduce | search / reduce | `''` / `''` | `''` / `''` |
| two bounded searches | search / search | `''` / `''` | `''` / `''` |
| parse-error step + reduce | reduce (parse-error) | `''` | `Warning: <standard input>, line 0: bad token ...` |

The parse-error case confirms that the step capture itself works: warnings that
Maude writes to fd 2 during `parseTerm` are captured and become the `parse-error`
message, while the healthy step after the failure is not executed (the run stops at
the first non-`ok` outcome, as documented).

## Conclusion

- **B4 as reported ("successful search step with empty `output.stdout`") is not a
  defect on this checkout.** The structured `solutions` are the result of a search
  step; stdout is legitimately empty because the bindings do not print.
- The "whole block surfaced inside a different step's stdout" observation from
  attempt 2 matches the pre-fix libmaude buffering leak. `_flush_stdio` runs before
  the redirect and in the `finally` while the capture fds are still installed, so a
  phase's tail is flushed into that phase's capture. No cross-step leak was observed
  in any scenario.
- The step `stderr` path is working and should be kept under regression test (a
  parse-error fixture is enough).

No code change is needed for B4. If anything, the tool documentation could state
that step stdout is normally empty because commands are executed through the API.
