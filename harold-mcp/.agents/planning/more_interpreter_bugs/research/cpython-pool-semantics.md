# CPython 3.14 `ProcessPoolExecutor` semantics (verified)

Source: the interpreter installed by `uv` for this project,
`.../cpython-3.14.2-linux-x86_64-gnu/lib/python3.14/concurrent/futures/process.py`
(Python 3.14.2), plus the official docs:
<https://docs.python.org/3/library/concurrent.futures.html#processpoolexecutor>.
Behavior was confirmed with `probes/probe_cpython_pool.py` (10 trials).

## 1. The call queue marks futures RUNNING before a worker starts them

```python
EXTRA_QUEUED_CALLS = 1
# ... a larger number will make Future.cancel() succeed less frequently
# (Futures in the call queue cannot be cancelled).

queue_size = self._max_workers + EXTRA_QUEUED_CALLS
self._call_queue = _SafeQueue(max_size=queue_size, ...)
```

The manager thread moves work items from `pending_work_items` to `call_queue`, and
calls the future's `set_running_or_notify_cancel()` **at that moment**:

```python
def add_call_item_to_queue(self):
    while True:
        if self.call_queue.full():
            return
        ...
        work_item = self.pending_work_items[work_id]
        if work_item.future.set_running_or_notify_cancel():
            self.call_queue.put(_CallItem(...), block=True)
        else:
            del self.pending_work_items[work_id]
```

Consequence: with `max_workers = N`, up to `N + 1` submitted tasks can be
"running" but not executing. `Future.cancel()` returns `False` for all of them, and
`Future.running()` is `True`. Only tasks beyond that buffer remain cancelable.

Observed (probe, 2 workers, 6 tasks submitted while both workers were busy):

```
cancel queued  -> [False, False, False, True, True, True]   # first 3 = 2 + 1
cancel running -> [False, False]
```

Therefore **`future.cancel()` cannot distinguish "a worker started this task" from
"the manager queued it".** Any fix that relies on `cancel()` returning `True` to mean
"no worker is busy with this call" is wrong for the first `N + 1` queued calls.

## 2. `kill_workers()` cancels the call queue and kills every worker

```python
def kill_workers(self):
    """Attempts to kill the executor's workers. ... After killing workers, the
    pool will be in a broken state and no longer usable ..."""
    return self._force_shutdown(operation=_KILL)

def _force_shutdown(self, operation):
    ...
    self.shutdown(wait=False, cancel_futures=True)
    for proc in processes.values():
        ... proc.kill()
```

`shutdown(cancel_futures=True)` cancels only futures for which `cancel()` succeeds
(the ones still in `pending_work_items`). The manager's `_terminate_broken` then does:

```python
for work_id, work_item in self.pending_work_items.items():
    try:
        work_item.future.set_exception(bpe)
    except _base.InvalidStateError:
        # set_exception() fails if the future is cancelled: ignore it.
        pass
```

So the pending work items split into two outcomes:

| Future state when the pool is killed | Outcome |
| --- | --- |
| dispatched to the call queue (RUNNING) | `BrokenProcessPool` |
| still in `pending_work_items` (PENDING) | `CancelledError` (cancel wins) or `BrokenProcessPool` (terminate wins), race |

Observed (2 workers, 2 running + 6 pending, 10 trials):

```
running totals: {'BrokenProcessPool': 20}
pending totals: {'BrokenProcessPool': 30, 'CancelledError': 30}
```

That is exactly 3 dispatched (`max_workers + EXTRA_QUEUED_CALLS`) and 3 truly pending
per trial. `CancelledError` is a plain `Exception`; it is neither
`BrokenProcessPool` nor `TimeoutError`, so `MaudeExecutor._run_task` lets it escape.

## 3. `result(timeout)` does not affect the task

`Future.result(timeout=...)` raises `TimeoutError` on the waiting thread; the task
keeps running (or keeps waiting in the call queue). A timed-out future whose task is
running cannot be cancelled (`cancel() -> False`). This is why a whole-call timeout
alone cannot tell whether a worker is stuck.

## 4. `submit()` after `shutdown()`

```python
def submit(self, fn, /, *args, **kwargs):
    with self._shutdown_lock:
        if self._broken:
            raise BrokenProcessPool(self._broken)
        if self._shutdown_thread:
            raise RuntimeError('cannot schedule new futures after shutdown')
```

Observed: `RuntimeError: cannot schedule new futures after shutdown`.

Reachability in `MaudeExecutor`: `shutdown()` sets `self._executor = None` under
`_executor_lock`; `_submit()` checks/creates the pool under the same lock. A submit
therefore cannot see a shut-down executor through the public path. The only way to
hit this is to keep a reference to a pool after it was shut down.

## 5. Spawn failures

`submit()` calls `_adjust_process_count()`; `_spawn_process()` calls `p.start()` and
does not catch exceptions:

```python
def _spawn_process(self):
    p = self._mp_context.Process(...)
    p.start()
    self._processes[p.pid] = p
```

An `OSError` from `Process.start()` (resource exhaustion, process limit) propagates
out of `submit()` and bypasses the `BrokenProcessPool`/`TimeoutError` mapping. It is
reachable, unlike the shutdown `RuntimeError`, and lands in the tool's generic
wrapper. It leaves no partial process entry (the dict assignment happens after
`start()`), but the executor keeps the same pool object and may retry the spawn on
the next submit.

## 6. `max_tasks_per_child=1` does not change queueing

It forces a fresh process per task, but the call-queue capacity and the
`set_running_or_notify_cancel()` timing are unchanged. Every task may therefore pay
spawn + `init_maude` while its future is already "running".

## 7. Implications for Harold

1. A timed-out call cannot be classified as "queued" or "running" via the future
   API. Killing only stuck workers requires a separate signal (worker-started marker,
   slot admission control, or a pool with per-task worker ownership).
2. Killing a shared pool necessarily kills unrelated calls. Isolation requires
   either **one in-flight task per pool** or **a pool implementation that replaces
   workers per task without breaking the pool**.
3. `CancelledError` must be part of the executor's documented failure vocabulary
   even if the pool design changes, because any future cancellation is observable.
