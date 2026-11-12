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

## O2 — pebble `ProcessPool`

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

| Criterion | O0 shared pool | O1 N single pools | O2 pebble | O3 process per call |
| --- | --- | --- | --- | --- |
| Failure isolation | none | per slot | per task | per call |
| Timeout kills only target | no | yes | yes (running; queued via `cancel()`) | yes |
| Whole-call timeout | yes, but kills all | yes | adapter (`result` + `cancel`) | yes |
| Crash isolation | no | per slot | yes | yes |
| Fresh interpreter per call | yes | yes | yes (`max_tasks=1`) | yes |
| Extra dependency | no | no | **LGPL-3.0** | no |
| New code | none | slot manager | adapter + exception mapping | IPC + lifecycle |
| Init failure | breaks pool | breaks one slot | breaks pool (recreate) | fails one call |

## Recommendation for the design phase

- If adding pebble is acceptable (including the LGPL/GPL check), **O2** is the least
  code for the strongest verified isolation, with one adapter: enforce the whole-call
  budget with `result(timeout)` + `cancel()` rather than relying on `schedule(timeout)`.
- If the project should stay dependency-free, **O1** is the best fit: it keeps the
  stdlib, makes queued-vs-running irrelevant by construction, and isolates failures
  per slot. It is more code than O2 but less than O3.
- **O3** is the fallback if the pool abstractions keep producing surprises; it has no
  hidden shared-fate semantics.
- **O0** must change: the reproduction shows the shared-fate failure is deterministic
  under load, not a rare race.

Open questions for the design:

1. Is a GPL-2.0 project allowed to depend on LGPL-3.0 pebble (license decision)?
2. Should a call cancelled by another call's failure be reported as
   `MaudeWorkerCrashedError`, `MaudeWorkerTimeoutError`, or a new
   `MaudeWorkerCancelledError`?
3. Should `maude_workers` remain the concurrency bound in O1/O2 (slot count vs
   `max_workers`)?
4. Keep the attempt-3 instrumentation (pool generation, submit/create logging) or
   reduce it to the tool-level traceback once isolation removes the shared-pool
   cascade?
