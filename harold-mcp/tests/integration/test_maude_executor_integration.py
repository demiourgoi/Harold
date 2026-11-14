"""Integration tests for `MaudeExecutor` against the real interpreter.

These prove the production wiring end to end: the real transport runs
`load_diagnostics` and `run_session` in per-call processes, and two concurrent
calls are served by two distinct processes (the injected rendezvous target
completes only once a peer process is running).
"""

import json
import os
import threading
import time
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any

from harold_mcp.maude import MaudeExecutor
from harold_mcp.maude.runner import PipeProcessRunner
from harold_mcp.maude.session import SessionRequest
from harold_mcp.settings import Settings

FIXTURES_DIR = Path(__file__).parent / "fixtures"

SESSION_REQUEST: SessionRequest = {
    "path": str(FIXTURES_DIR / "hello.maude"),
    "module": "HELLO-WORLD",
    "steps": [
        {
            "command": "reduce",
            "term": "f",
            "pattern": None,
            "subject": None,
            "bound": None,
            "gas": None,
            "depth": None,
            "search_type": None,
            "path_mode": None,
        }
    ],
    "max_solutions": 200,
    "max_result_length": 1_000_000,
    "max_path_steps": 100,
    "max_output_length": 1_000_000,
}


def _rendezvous_target(conn: Connection) -> None:
    """Ping immediately; for a diagnostics call, wait for a peer process first.

    The request's `path` is a directory the two calls share. Each process leaves a
    marker there and only replies once it sees a peer's marker, so a result proves
    the calls ran in distinct processes at the same time.
    """
    request = json.loads(conn.recv_bytes())
    payload = request.get("payload")
    if payload is None:
        conn.send_bytes(json.dumps({"status": "ok", "result": None}).encode())
        conn.close()
        return
    directory = Path(payload["path"])
    marker = directory / f"{os.getpid()}.rendezvous"
    marker.touch()
    deadline = time.monotonic() + 30.0
    try:
        while time.monotonic() < deadline:
            if any(peer != marker for peer in directory.glob("*.rendezvous")):
                result = {
                    "ok": True,
                    "warnings": [{"file": "rendezvous.maude", "line": 1, "message": f"pid {os.getpid()}"}],
                }
                conn.send_bytes(json.dumps({"status": "ok", "result": result}).encode())
                return
            time.sleep(0.02)
        conn.send_bytes(
            json.dumps({
                "status": "error",
                "error": {
                    "category": "remote",
                    "type": "TimeoutError",
                    "message": "no peer process arrived",
                    "traceback": "",
                    "context": {},
                },
            }).encode()
        )
    finally:
        conn.close()


def test_diagnostics_uses_the_real_transport() -> None:
    settings = Settings(maude_workers=1)
    executor = MaudeExecutor(settings=settings)
    executor.start(settings.diagnostics_timeout_secs)
    try:
        assert executor.diagnostics(str(FIXTURES_DIR / "hello.maude")) == {"ok": True, "warnings": []}
    finally:
        executor.shutdown()


def test_run_session_uses_the_real_transport() -> None:
    settings = Settings(maude_workers=1)
    executor = MaudeExecutor(settings=settings)
    executor.start(settings.diagnostics_timeout_secs)
    try:
        result = executor.run_session(SESSION_REQUEST, timeout=60)
    finally:
        executor.shutdown()

    assert result["load_ok"] is True
    assert result["module_found"] is True
    assert [outcome["status"] for outcome in result["outcomes"]] == ["ok"]
    assert result["outcomes"][0]["term"] == "2"


def test_two_concurrent_calls_use_two_processes(tmp_path: Path) -> None:
    settings = Settings(maude_workers=2)
    runner = PipeProcessRunner(settings, target=_rendezvous_target)
    executor = MaudeExecutor(settings=settings, runner_factory=lambda: runner)
    executor.start(settings.diagnostics_timeout_secs)
    results: list[dict[str, Any]] = []
    barrier = threading.Barrier(2)

    def call() -> None:
        barrier.wait()
        results.append(executor.diagnostics(str(tmp_path)))

    threads = [threading.Thread(target=call) for _ in range(2)]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
    finally:
        executor.shutdown()

    assert len(results) == 2
    assert all(result["ok"] is True for result in results)
    assert len({result["warnings"][0]["message"] for result in results}) == 2  # two pids
