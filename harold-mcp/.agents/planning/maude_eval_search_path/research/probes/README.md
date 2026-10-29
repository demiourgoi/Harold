# Probes — search paths for `maude_run`

Executable probes behind the findings in [`../maude-bindings-search-path.md`](../maude-bindings-search-path.md)
and [`../path-design-options.md`](../path-design-options.md). They use the `maude`
package installed in `harold-mcp/.venv` (1.6.0) and the Maude 3.5.1 CLI at
`/home/juanrh/systems/maude/latest/maude`.

Run from the `harold-mcp` directory:

```sh
.venv/bin/python .agents/planning/maude_eval_search_path/research/probes/probe_search_path.py
.venv/bin/python .agents/planning/maude_eval_search_path/research/probes/probe_state_numbers.py
```

Run the CLI probe from this directory (so `in search_path.maude` resolves):

```sh
/home/juanrh/systems/maude/latest/maude < probe_cli_show_path.input
```

| File | Answers |
| --- | --- |
| `search_path.maude` | Fixtures: `SHEPHERD` (the river-crossing example from the rough idea), `UNLABELED` (rules without labels), `CHAIN` (unbounded counter for long paths and the laziness probe), `BRANCH` (`=>#` branching). |
| `probe_search_path.py` | Iteration tuple shape, the path thunk, path layout, labels vs full rule text, state numbers, the thunk-lifetime trap, all five search types, unlabeled rules, long-path size, path lifetime after the iterator. |
| `probe_state_numbers.py` | `getStateParent`, `getRule`, `getStateTerm`, `pathTo`. Its **last** call, `getRule(0)`, hard-crashes the process (SIGSEGV; exit 139 under redirection, 255 in an earlier run) with no traceback. This is deliberate: it isolates the crash. |
| `probe_cli_show_path.input` | The same shepherd search through the Maude CLI, plus the three `show path` variants, the unlabeled rules, and a `=>#` solution, to compare CLI output with the bindings. |
| `probe_search_path.out.txt`, `probe_state_numbers.out.txt`, `probe_cli_show_path.out.txt` | Captured transcripts. |

Key results (details in the research notes):

- `search` yields `(term, substitution, path_thunk, rewrite_count)`, where `path_thunk`
  is a Python function that computes the path **to the currently selected state at call
  time** — calling it after advancing the iterator returns the wrong path. Materialize
  it while the iterator is positioned on that solution (or save the state number and
  call `pathTo` later).
- The path is `[term0, rule1, term1, …, rulen, termn]` (`2n+1` elements); a reflexive
  `=>*` solution or a `=>#` branching state has a single term and no transitions.
- Rule labels match `show path labels`; `str(rule)` matches the full `show path` text.
  Unlabeled rules have `getLabel() == None`; the CLI prints `(unlabeled rule)`.
- State numbers from `getStateNr()` match the CLI's `Solution N (state M)` numbers.
- `getRule(0)` (the root state, which has no incoming rule) crashes the process.
  `pathTo`/`pathTo(0)` and `getStateTerm(0)` are safe.
