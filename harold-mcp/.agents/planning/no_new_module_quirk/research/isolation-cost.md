# Research: cost of `max_tasks_per_child=1` and the `HAROLD_MAUDE_WORKERS` default

Scratch script: `scratch_timing.py`. Same machine the user quoted (12 logical cores,
16 GB RAM), project environment. Diagnostics of `hello.maude`, 8 calls per mode.

## Timing

| Mode | Sequential 8 calls | Per call | Parallel 8 calls | Per call |
| --- | --- | --- | --- | --- |
| Warm pool, 1 worker (today) | 0.009 s | ~1 ms | — | — |
| Warm pool, 2 workers (today) | — | — | 0.0 s | ~ms |
| Recycled, 1 worker | 9.94 s | 1.24 s | 9.67 s | 1.21 s |
| Recycled, 2 workers | 6.17 s | 0.77 s | 6.11 s | 0.76 s |
| Recycled, 6 workers | 5.17 s | 0.65 s | 3.63 s | 0.45 s |

Observations:

- The dominant cost is **spawn + `maude.init(loadPrelude=True)`** per call. The
  README measured ≈0.34 s/call; this session measured 0.65–1.24 s/call — machine-load
  dependent, ~1 s is a realistic planning number. Warm pool is ~1 ms/call: the
  regression is **≈3 orders of magnitude per call**, not "2×". (The user's opencode run
  probably hid most of it inside LLM/tool-call overhead.)
- Parallelism only helps concurrent bursts (6 workers: 0.45 s/call effective).
  Sequential callers cannot amortize anything.
- Worker RSS after a task: **~100 MB** per interpreter process. Workers are transient
  with recycling, so this is peak memory during a burst, not standing memory.

## The lifespan warm-up

With `max_tasks_per_child=1`, the `start()` pings spawn workers that are recycled
immediately after the ping. The warm-up no longer warms anything (every call still pays
spawn+init) — it keeps its fail-fast role: it verifies `init_maude` works in `N`
parallel spawns before serving. That role is still worth the ~1 s per ping at startup.

## Default for `HAROLD_MAUDE_WORKERS`

What the number buys: it bounds **how many fresh interpreters may spawn concurrently**
during a burst (and thus peak memory ≈ 100 MB × workers and parallel init CPU). It does
not affect per-call latency for serial callers.

- `os.cpu_count() // 2` (user's proposal): 6 on this machine → 6 parallel spawns,
  ~600 MB peak, a 17-fixture parallel burst lands in ~4–8 s instead of ~40 s at
  workers=1. Matches "diagnostics of many files at once is not so common, but when it
  happens, half the machine is fair".
- 2 or 3: enough for typical single-agent use (an agent issues 1–4 parallel tool
  calls); cheaper peak memory.
- Recommendation: `max(1, os.cpu_count() // 2)` — honor the user's instinct; the knob
  exists for constrained machines. A hard cap (e.g. 8) would only matter on very large
  machines; not needed for the project's target use, but worth a note in the settings
  docstring.

Caveat: `os.cpu_count()` can return `None`; the default must guard with a floor of 1
(the `gt=0` validator stays).
