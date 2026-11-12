# Pool architecture options

The reproduction proves the current shared `ProcessPoolExecutor` cannot satisfy
Harold's isolation requirement: a single timed-out call kills every concurrent call.
This note compares four designs. All behavior claims about the stdlib come from
`cpython-pool-semantics.md`; all pebble claims were verified with
`probes/probe_pebble.py` on pebble 5.2.3.

## Requirements

1. **Per-call isolation** — a crash or timeout in one call must not fail other
   concurrent calls.
2. **Whole-call timeout** — the budget covers queueing, spawn, Maude init and work.
3. **Fresh interpreter per call** — `max_tasks_per_child=1` equivalent.
4. **Bounded concurrency** — at most `maude_workers` interpreters, ~100 MB each.
5. **Distinct failure vocabulary** — crash, timeout, init failure and unexpected
   exceptions must reach the client as different `MaudeRunError`s (or per-step data).
6. **Fail-fast init check** at lifespan start; clean pool teardown at shutdown.
7. **The server process never imports `maude`.**

## O0 — Shared `ProcessPoolExecutor` of N workers (current)

| | |
| --- | --- |
| Isolation | **none**: any `kill_workers()` kills all N workers and fails all in-flight futures |
| Timeout | `future.result(timeout)` kills the whole pool |
| Crash | one worker's death breaks the pool (`BrokenProcessPool` for every pending future) |
| Fresh interpreter | yes (`max_tasks_per_child=1`) |
| Dependencies | stdlib |
| Verdict | rejected: this is the reproduced bug |

Additional defect: a timed-out call that is queued but not started cannot be
distinguished from a running one (`future.cancel() == False` for the first
`N + 1` queued calls), so killing "only if a worker started" is not implementable
on this API.

## O1 — N independent single-worker pools (slot manager)

One `ProcessPoolExecutor(max_workers=1, max_tasks_per_child=1)` per slot; a semaphore
or an idle-slot queue admits at most one in-flight call per pool.

| | |
| --- | --- |
| Isolation | per slot: a failure kills only that slot's pool |
| Timeout | whole-call; killing the slot's pool is always safe because only one call is in flight |
| Crash | breaks that slot only; the slot replaces its pool and reports the crash |
| Fresh interpreter | yes (`max_tasks_per_child=1`) |
| Dependencies | stdlib |
| Complexity | medium: N pool objects, slot admission, per-slot replacement, start/shutdown over N pools |
| Init failure | breaks one slot; the others keep working (start() can still fail fast) |

Why it works: pools share no manager thread, no call queue and no worker processes.
`kill_workers()` on slot A is invisible to slot B. With admission control there is no
queued work inside a slot, so the undecidable queued-vs-running case disappears.
Cost: N manager threads (one per pool) and a slot manager; still far simpler than
owning the IPC.

## O2 — pebble `ProcessPool` (rejected on license)

Probe results (`probes/probe_pebble.py`):

| Scenario | Result |
| --- | --- |
| One worker exits `os._exit(7)`; concurrent healthy task | crashed future → `ProcessExpired(exitcode=7)`; healthy task `ok`; pool active; next task `ok` |
| One task exceeds `schedule(timeout=1)`; concurrent 2 s task | timed-out future → `TimeoutError` at 1.1 s; healthy task `ok`; pool active; next task `ok` |
| Timeout expires while the task is **queued** | timeout **not enforced while queued**; the task ran after the occupant (4.3 s) and returned `ok`; the occupant survived |
| `ProcessFuture.cancel()` on a running task | returns `True`; future raises `CancelledError`; pool active; next task `ok` |
| Initializer raises | first task → `BrokenProcessPool("All workers expired")`; `pool.active == False`; next `schedule` raises `RuntimeError("Unexpected error within the Pool")` |
| `max_tasks=1` | distinct pid per task; initializer ran once per task |

Implications:

- Crash and timeout isolation are built in and match the requirement.
- The per-task `timeout` starts when the task runs, so a queued call can exceed the
  whole-call budget. Harold must add its own `future.result(timeout)` wait and call
  `future.cancel()` on expiry; `cancel()` removes a queued task or kills the running
  worker without harming others. This is a small adapter, not a redesign.
- An initializer failure invalidates the pool; the executor must recreate it. This
  mirrors the current fail-fast behavior, but the pool is not automatically usable
  after `Maude` init fails.
- **License:** pebble is LGPL-3.0 (<https://github.com/noxdafox/pebble>). Harold's
  `LICENSE` is GPL-2.0 with no "or later" statement found in the repository metadata.
  LGPLv3 is compatible with GPLv3, not with GPLv2-only; confirm the licensing position
  before adopting it as a runtime dependency.
- Adds one runtime dependency (pure Python) and a new exception vocabulary
  (`ProcessExpired`, `BrokenProcessPool`).

Docs: <https://pebble.readthedocs.io/en/latest/>.

## O2b — billiard `Pool`

`billiard` is the Celery team's hardened fork of `multiprocessing.Pool`
(`billiard==4.3.2`, BSD-3-Clause, Python >= 3.10). Full evidence in
`billiard.md`; summary:

| | |
| --- | --- |
| Isolation | per job: a crashed or hard-timed-out job kills only its worker |
| Crash | job → `WorkerLostError`; the pool replaces the worker; other jobs continue |
| Hard timeout | job → `TimeLimitExceeded`; only that worker is killed and replaced; other jobs continue |
| Timeout requirements | **must** construct with `enable_timeouts=True` **and** `synack=True`; `apply_async(timeout=...)` alone silently does nothing |
| Queued tasks | timeout starts at acceptance, so a queued task is not timed out; a client-side `get(timeout)` and slot admission (or `terminate_job(pid)`) are still needed |
| Fresh interpreter | `maxtasksperchild=1` gives a distinct pid and initializer run per task |
| Exceptions | arrive wrapped in `ExceptionWithTraceback`; the real exception is `exc.exc` |
| License | BSD-3-Clause: GPL-compatible, unlike pebble |
| Main risk | pool threads call `os._exit(1)` on unexpected exceptions and SIGTERM the parent on `RestartFreqExceeded`; an initializer failure can churn workers and a pool-internal bug can kill the MCP server |
| Complexity | replace the executor internals, unwrap exceptions, add the timeout adapter and pool recreation |

Billiard does fix the reproduced bugs and is the only third-party option that
passes the license bar. It is kept as the fallback to O1, mainly because of the
parent-process-kill behavior and the non-obvious `enable_timeouts`/`synack`
requirements.

## O3 — One dedicated `multiprocessing.Process` per call

Parent spawns a process per call, sends the `SessionRequest` over a `Pipe`/`Queue`,
waits with a deadline, kills on expiry, and relays the result or exception. A
semaphore bounds concurrency.

| | |
| --- | --- |
| Isolation | per call, maximal |
| Timeout | whole-call; kill only this process |
| Crash | only this call; exit code observable |
| Fresh interpreter | yes (new process per call; the initializer is the process target) |
| Dependencies | stdlib |
| Complexity | medium-high: IPC protocol, result/exception pickling, spawn errors, orphan cleanup, grace period for `join()` |
| Advantage | no pool manager, no shared call queue, no broken-pool concept |

This is the most explicit option: every failure is attributable to one process. It
trades the pool's lifecycle management for a small amount of code that Harold would
own and test.

## Comparison

| Criterion | O0 shared pool | O1 N single pools | O2 pebble | O2b billiard | O3 process per call |
| --- | --- | --- | --- | --- | --- |
| Failure isolation | none | per slot | per task | per job | per call |
| Timeout kills only target | no | yes | yes (running; queued via `cancel()`) | yes (hard timeout or `terminate_job`) | yes |
| Whole-call timeout | yes, but kills all | yes | adapter (`result` + `cancel`) | adapter (`get` + `terminate_job` / slot admission) | yes |
| Crash isolation | no | per slot | yes | yes (`WorkerLostError`) | yes |
| Fresh interpreter per call | yes | yes | yes (`max_tasks=1`) | yes (`maxtasksperchild=1`) | yes |
| Extra dependency | no | no | **LGPL-3.0 (blocked)** | **BSD-3-Clause (ok)** | no |
| New code | none | slot manager | adapter + exception mapping | adapter + exception unwrapping + timeout flags | IPC + lifecycle |
| Parent-process risk | no | no | no | **pool threads can `os._exit`/SIGTERM the server** | no |
| Init failure | breaks pool | breaks one slot | breaks pool (recreate) | hangs the job; churns workers | fails one call |

## Recommendation for the design phase

**Primary: O1 (N independent single-worker pools).** It is stdlib-only, has no
license or dependency risk, and one in-flight call per pool makes the
queued-vs-running ambiguity impossible by construction. The slot manager can be a
`queue.SimpleQueue` of `ProcessPoolExecutor(max_workers=1)` slots: acquire a slot,
submit, wait; on crash/timeout kill and replace that slot; other slots are
untouched. `start()` pings one task per slot; `shutdown()` kills every slot.

**Fallback: O2b (billiard)** if the slot manager proves too costly and the team
accepts a BSD dependency plus the parent-process-kill risk. Billiard has the best
per-job semantics, but it does not remove the need for slot admission or a
client-side timeout, and its timeout configuration is a trap.

**O2 (pebble) is rejected** on the LGPL-3.0/GPL-2.0-only incompatibility.
**O3 is not preferred** by the user; it remains the last resort if pool semantics
keep producing surprises.

Open questions for the design:

1. Should a call cancelled by another call's failure be reported as
   `MaudeWorkerCrashedError`, `MaudeWorkerTimeoutError`, or a new
   `MaudeWorkerCancelledError`? (Under O1 the external-cancellation case disappears.)
2. Should `maude_workers` remain the concurrency bound in O1 (slot count)?
3. Keep the attempt-3 instrumentation (pool generation, submit/create logging) or
   reduce it to the tool-level traceback once isolation removes the shared-pool
   cascade?
4. What is the slot policy when a call times out during spawn/init (before the task
   starts)? Killing that slot's pool is safe under O1 and should map to
   `MaudeWorkerTimeoutError`.
