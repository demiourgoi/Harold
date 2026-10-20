"""Probe: real per-call cost through ``MaudeExecutor`` (spawn + prelude init + task).

The isolation-cost research in ``no_new_module_quirk`` measured ~0.6–1.2 s per
hermetic call. This probe re-measures on the current machine through the real
executor, because the optional per-call timeout includes interpreter startup.

Run from ``harold-mcp`` with the project venv::

    .venv/bin/python .agents/planning/port-maude_eval.py/research/probes/probe_call_cost.py
"""

import time

from harold_mcp.maude import worker
from harold_mcp.maude.executor import MaudeExecutor


def main() -> None:
    executor = MaudeExecutor()
    started = time.monotonic()
    executor.start()
    print(f"start() (pool + init pings): {time.monotonic() - started:.2f}s")
    try:
        for index in range(3):
            started = time.monotonic()
            result = executor.diagnostics("tests/integration/fixtures/hello.maude")
            print(f"diagnostics call {index + 1}: {time.monotonic() - started:.2f}s | {result}")
        for index in range(3):
            started = time.monotonic()
            executor.submit(worker.ping).result()
            print(f"ping call {index + 1}: {time.monotonic() - started:.2f}s")
    finally:
        executor.shutdown()


if __name__ == "__main__":
    main()
