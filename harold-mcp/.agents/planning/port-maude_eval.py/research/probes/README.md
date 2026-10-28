# Probes — `maude_run` research

Executable probes behind the findings in [`../term-api.md`](../term-api.md) and
[`../worker-behavior.md`](../worker-behavior.md). They use only the `maude`
package installed in `harold-mcp/.venv` (1.6.0) and the fixtures in
`tests/integration/fixtures/`.

Run from the `harold-mcp` directory:

```sh
.venv/bin/python .agents/planning/port-maude_eval.py/research/probes/probe_term_ops.py
.venv/bin/python .agents/planning/port-maude_eval.py/research/probes/probe_match_search.py
.venv/bin/python .agents/planning/port-maude_eval.py/research/probes/probe_streams.py
.venv/bin/python .agents/planning/port-maude_eval.py/research/probes/probe_modules.py
.venv/bin/python .agents/planning/port-maude_eval.py/research/probes/probe_timeout.py
.venv/bin/python .agents/planning/port-maude_eval.py/research/probes/probe_call_cost.py
.venv/bin/python .agents/planning/port-maude_eval.py/research/probes/probe_stdout_flush.py flush
```

| Script | Answers |
| --- | --- |
| `probe_term_ops.py` | Return values, in-place mutation, step counts, `match`/`search` iteration, `parseTerm` failures, pretty-print fidelity and round-tripping. |
| `probe_match_search.py` | Substitution serialization (`str(variable)` prints the name only, not the sort), `maxDepth` modes on an assoc module (`-1`/`0`/`UNBOUNDED`), the five search types plus ground `=>1` targets, and that the iterators are lazy. |
| `probe_streams.py` | What each operation writes to fd 1 / fd 2 (parse errors, successful commands, loads). |
| `probe_modules.py` | `getCurrentModule` vs `getModule`, module enumeration/diffing, dependency and broken-file loads. |
| `probe_timeout.py` | A non-terminating reduction: timeout, `kill_workers`, pool replacement, queued/concurrent calls. |
| `probe_call_cost.py` | Real per-call cost through `MaudeExecutor` (spawn + prelude init + task). |
| `probe_stdout_flush.py` | Whether `maude.load`'s stdout lands inside an fd-1 capture or is buffered past the restore. |

The captured transcripts live next to each script as `probe_*.out.txt`.
