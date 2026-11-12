# Billiard assessment (license + verified capability)

Evaluated `billiard==4.3.2` (`uv run --with billiard`, Python 3.14.2) with
`probes/probe_billiard.py`. Billiard is the Celery team's fork of the Python 2.7
multiprocessing package.

## License

- `LICENSE.txt` on `main` is the **3-clause BSD license** ("Copyright (c) 2006-2008,
  R Oudkerk and Contributors"). PyPI metadata: `License: BSD`, classifier
  `License :: OSI Approved :: BSD License`.
- BSD-3-Clause is GPL-compatible, so it can be combined with Harold's GPL-2.0-only
  code and distributed. Unlike pebble (LGPL-3.0), there is no licensing blocker.

Other package facts: `Requires-Python >=3.10`, maintained by the Celery team, used in
production by Celery. It is a dependency, not a stdlib module.

## Verified capabilities

Pool construction used for every scenario:

```python
Pool(
    processes=N,
    maxtasksperchild=1,
    initializer=init_maude,
    context=billiard.get_context("spawn"),
    allow_restart=True,
    synack=True,
    enable_timeouts=True,
    lost_worker_timeout=1.0,
)
```

| Scenario | Observed result |
| --- | --- |
| Worker exits `os._exit(7)` while another task runs | crashed job → `WorkerLostError("Worker exited prematurely: exitcode 7 Job: 0.")`; concurrent job `ok`; pool usable; replacement worker served the next job |
| Job exceeds a 1 s hard timeout while another job runs | timed-out job → `TimeLimitExceeded(1.0)` after ~2 s (the timeout handler polls every 1 s); concurrent job `ok`; the timed-out worker got SIGTERM; pool usable; next job `ok` |
| `Pool.terminate_job(pid)` on a running job | job → `Terminated(15)`; concurrent job `ok`; pool usable |
| `maxtasksperchild=1`, three tasks | three distinct pids; initializer ran three times (fresh interpreter per task) |
| Initializer raises | the submitted job never gets accepted: it hangs until the caller's `get(timeout)` raises `TimeoutError`; workers restart repeatedly; the pool stays in a restarting state |

Every job exception arrives wrapped in `billiard.einfo.ExceptionWithTraceback`
(`Pool._wrap_exception = True`; the source comment says it cannot be disabled yet).
The real exception is `exc.exc`, and `str(exc)` is the worker traceback text. The
executor must unwrap before mapping.

## Sharp edges

1. **Per-job `timeout=` alone does nothing.** The timeout handler is only created
   when the pool is constructed with `enable_timeouts=True` (or a pool-level
   `timeout`/`soft_timeout`), and `_time_accepted` is only recorded when the job is
   acknowledged by a worker, which requires `synack=True`. Verified: with only
   `apply_async(..., timeout=1.0)`, a 30 s task ran to completion. Both flags are
   mandatory.
2. **Timeouts start at acceptance, not submission.** A queued job is not timed out;
   verified with a one-worker pool (a queued 0.1 s job with `timeout=1.0` ran after
   the 4 s occupant, and the occupant survived). Harold's `timeout_secs` is a
   whole-call budget, so the executor still needs a client-side `get(timeout=...)`.
3. **Client-side timeout has no clean per-job kill for unaccepted jobs.** For an
   accepted job, `result.worker_pids()` gives the pid and `pool.terminate_job(pid)`
   kills only that worker. For a job still waiting for a worker, there is no public
   pid; `ApplyResult._cancel()` is private and only meaningful with `synack`. A slot
   admission scheme (one in-flight job per pool, or a semaphore in front of a pool)
   removes the queued case.
4. **Pool threads can kill the parent process.** `PoolThread.run` calls `os._exit(1)`
   on an unexpected exception and `_kill(os.getpid(), SIGTERM)` on
   `RestartFreqExceeded`. In the MCP server, a pool-internal bug or an initializer
   failure that exhausts the restart budget can terminate the whole server rather
   than failing one call. This is the main technical objection to embedding billiard
   in the server process.
5. **Initializer failure is not a clean pool error.** The job hangs until the caller
   times out, and workers churn. The lifespan's fail-fast ping must catch a broken
   Maude installation; a mid-call init failure needs the client-side timeout and pool
   replacement.
6. The timeout handler polls once per second, so a hard timeout can overrun its
   budget by up to ~1 s.

## Fit for Harold

Billiard can replace `ProcessPoolExecutor` and fixes the reproduced bugs:

- a stuck reduction raises `TimeLimitExceeded` for its own job and kills only its
  worker;
- a worker crash raises `WorkerLostError` for its own job;
- other jobs continue, and the pool remains usable;
- `maxtasksperchild=1` preserves the fresh-interpreter guarantee.

The cost is a runtime dependency, an adapter for `ExceptionWithTraceback` and the
`enable_timeouts`/`synack` requirements, and the parent-process-kill risk in edge
cases. It does **not** remove the need for a whole-call timeout scheme; either a slot
admission scheme or 2 + `terminate_job` is required.

## Verdict

Technically viable and license-compatible. The parent-kill behavior and the
`enable_timeouts`/`synack` trap make it a less predictable foundation than N
single-worker `ProcessPoolExecutor` pools for a long-lived MCP server; the design
should treat billiard as the fallback if option B proves too costly to implement.
