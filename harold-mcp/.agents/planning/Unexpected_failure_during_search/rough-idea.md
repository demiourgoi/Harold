# Unexpected failure running the Maude interpreter session for `search`

## Issue

When running the following tool call on a coding agent 

```json
{
  "module": "SHEPHERD",
  "path": "/home/juanrh/systems/harold-testing/shepherd.maude",
  "steps": [
    {
      "command": "search",
      "pattern": "< right | right | right | right >",
      "search_type": "any-steps",
      "subject": "initial"
    }
  ]
}
```

we get the following error 

```json
[
  {
    "Text": "Error calling tool 'maude_run': Unexpected failure running the Maude interpreter session"
  }
]
```

that is reported as follows by the agent

> The trace search appears to hang. Let me isolate it — temporarily disabling the embedded command and probing the trace module step by step.

We have to 

- reproduce the error
- find the root cause
- fix the issue

## Analysis in original host

Answer: it's not performance and not a timeout

Evidence:

- The trace search that gets dropped actually completes in **0 ms CPU / 106 states / 2125 rewrites**. Its output did eventually surface once, attached to a later step's `stdout`:
  ```
  Solution 1 (state 105)
  states: 106  rewrites: 2125 in 0ms cpu (0ms real)
  H --> start then carry-sheep then solo then carry-cabbage then carry-sheep then carry-dog then solo then carry-sheep
  ```
- Raising the budget (`timeout_secs: 180`) changes nothing — same truncation.
- The call returns `completed: true` immediately; it isn't killed.

### Minimal reproduction of the tool bug

I narrowed it to a **bounded search that reaches its bound as the last command in the file**. Six-line repro:

```maude
mod PROBE is
  sort S .
  ops a b c : -> S [ctor] .
  rl [step] : a => b .
endm

search [1] a =>* Z:S .
```

Load output returned by `maude_run`:

```
==========================================
search [1] in PROBE : a =>* Z:S .
```

…and nothing more. The command's result is missing.

Discriminating tests I ran:

| Last command in file | Output captured? |
|---|---|
| `reduce c .` | yes |
| `search a =>* Z:S .` (unbounded, terminates → prints `No more solutions.`) | yes |
| `search [5] a =>* Z:S .` (bound not reached → prints `No more solutions.`) | **yes** |
| `search [1] a =>* Z:S .` (bound reached → no terminator) | **no** |
| `search [1, 10] a =>* Z:S .` at end | **no** |
| `search [1, 10] a =>* Z:S .` followed by another command | **yes** |

So the trigger is: **the block's end-of-output marker is missing when a bounded search stops at its bound** — Maude prints no `No more solutions.` in that case. The load phase evidently frames each command's output by such a terminator (`result …`, `No more solutions.`); with no terminator on the final command, the block is never closed, its result is dropped, and the unread bytes desynchronize the session. That also explains why the same bounded search is captured fine mid-file (the next command's block delimits it), why the result once leaked into a *later* step's `stdout`, and why some subsequent calls died with `Unexpected failure running the Maude interpreter session`.

Workarounds for a script: end the file with a command that always prints a terminator (e.g. a `reduce`), put the bounded search before another command, or use a bound large enough to exhaust the state space. `maude_run` **steps** are unaffected — a `search` step in `SHEPHERD-TRACE` returned 20 solutions with full rule-label paths.

### The Maude model and solution

`harold-testing/shepherd.maude` — clean load (`maude_program_diagnostics`: 0 warnings, 0 errors):

- `SHEPHERD-BASE` — sides, items, `safe(S,C,D,Sh)`.
- `SHEPHERD` — state `< shepherd | cabbage | dog | sheep >`, four crossing rules, each guarded by `safe` on the *target* configuration. Verified: goal reachable (`Solution 1 (state 9)`, 10 states) and **no** reachable dangerous state (`No solution.`, exhaustive over the 16-state space).
- `SHEPHERD-TRACE` — same rules plus a crossing log; its search returns the itinerary.

**The solution (7 crossings)**

| # | Move | Resulting state `< shep \| cab \| dog \| sheep >` |
|---|---|---|
| 0 | — | `< left  \| left  \| left  \| left  >` |
| 1 | take the sheep | `< right \| left  \| left  \| right >` |
| 2 | return alone | `< left  \| left  \| left  \| right >` |
| 3 | take the cabbage | `< right \| right \| left  \| right >` |
| 4 | bring the sheep back | `< left  \| right \| left  \| left  >` |
| 5 | take the dog | `< right \| right \| right \| left  >` |
| 6 | return alone | `< left  \| right \| right \| left  >` |
| 7 | take the sheep | `< right \| right \| right \| right >` |

The log Maude returns: `start then carry-sheep then solo then carry-cabbage then carry-sheep then carry-dog then solo then carry-sheep`.

There is also a mirror-image optimum of the same length (cabbage and dog swapped): `carry-sheep, solo, carry-dog, carry-sheep, carry-cabbage, solo, carry-sheep` — the `search` step listed both. The key move is #4: the sheep must be ferried *back* so the dog and cabbage can cross together, since the dog ignores the cabbage.

I deleted the scratch `probe.maude`; `shepherd.maude` is untouched. Want me to apply the workaround (append a trailing `reduce`, or move the trace search before a final command) so the file's own run prints the itinerary end-to-end?
