"""Integration tests for the one-shot transport and runner with real `spawn` processes.

The production transport (`transport.serve_one`) is exercised against the real
interpreter in `test_ping_and_diagnostics_through_the_runner`; the remaining tests
inject top-level targets (crash, sleep, echo, large response) to prove process
isolation, deadlines, large payloads and the response cap without special
production operations.
"""

import json
import os
import threading
import time
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any, cast

import pytest

from harold_mcp.maude import transport
from harold_mcp.maude.errors import (
    MaudeWorkerCrashedError,
    MaudeWorkerProtocolError,
    MaudeWorkerTimeoutError,
)
from harold_mcp.maude.runner import PipeProcessRunner
from harold_mcp.settings import Settings

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _crash_target(conn: Connection) -> None:
    """Die abruptly without sending a response (deterministic SIGSEGV analogue)."""
    os._exit(7)


def _sleep_after_read_target(conn: Connection) -> None:
    """Read the request, then hang, so the parent's deadline expires."""
    try:
        _ = conn.recv_bytes()
    except EOFError, OSError:
        return
    time.sleep(120)


def _echo_target(conn: Connection) -> None:
    """Report the request size, so large-request round-trips are observable."""
    raw = conn.recv_bytes()
    conn.send_bytes(json.dumps({"status": "ok", "result": {"bytes": len(raw)}}, ensure_ascii=False).encode("utf-8"))
    conn.close()


def _large_response_target(conn: Connection) -> None:
    """Send a 10 kB result, to exercise the parent's response-size cap."""
    try:
        _ = conn.recv_bytes()
    except EOFError, OSError:
        return
    conn.send_bytes(json.dumps({"status": "ok", "result": "x" * 10_000}, ensure_ascii=False).encode("utf-8"))
    conn.close()


def _runner(target: Any = transport.serve_one, **settings_overrides: Any) -> PipeProcessRunner:
    return PipeProcessRunner(Settings(maude_workers=1, **settings_overrides), target=target)


def test_ping_and_diagnostics_through_the_runner() -> None:
    """The real transport spawns a child, initializes Maude and round-trips results."""
    runner = _runner()
    try:
        assert runner.run("ping", None, 60, {}) is None
        result = runner.run("diagnostics", {"path": str(FIXTURES_DIR / "hello.maude")}, 60, {})
        assert result == {"ok": True, "warnings": []}
        assert runner.active_count() == 0
    finally:
        runner.kill_all()


def test_crash_target_fails_only_its_own_call() -> None:
    """A child that exits abruptly fails its call; a concurrent healthy call succeeds."""
    crash_runner = _runner(target=_crash_target)
    healthy_runner = _runner()
    barrier = threading.Barrier(2)
    results: dict[str, object] = {}

    def call(name: str, runner: PipeProcessRunner) -> None:
        barrier.wait()
        try:
            results[name] = runner.run("ping", None, 60, {})
        except BaseException as exc:
            results[name] = exc

    threads = [
        threading.Thread(target=call, args=("crash", crash_runner)),
        threading.Thread(target=call, args=("healthy", healthy_runner)),
    ]
    for thread in threads:
        thread.start()
    try:
        for thread in threads:
            thread.join(timeout=60)
    finally:
        crash_runner.kill_all()
        healthy_runner.kill_all()

    assert isinstance(results.get("crash"), MaudeWorkerCrashedError)
    assert results.get("healthy", "missing") is None
    assert crash_runner.active_count() == 0
    assert healthy_runner.active_count() == 0


def test_timeout_kills_only_its_own_process_and_a_follow_up_succeeds() -> None:
    timed_runner = _runner(target=_sleep_after_read_target)
    healthy_runner = _runner()
    try:
        with pytest.raises(MaudeWorkerTimeoutError):
            _ = timed_runner.run("ping", None, 1.0, {})
        assert timed_runner.active_count() == 0
        # The timed-out process was killed; an independent call still works.
        assert healthy_runner.run("ping", None, 60, {}) is None
    finally:
        timed_runner.kill_all()
        healthy_runner.kill_all()


def test_large_request_round_trips() -> None:
    """A request larger than the 64 KiB pipe buffer is framed and delivered intact."""
    runner = _runner(target=_echo_target)
    blob = "x" * 100_000
    try:
        result = runner.run("echo", {"blob": blob}, 30, {})
        assert cast(dict[str, Any], result)["bytes"] > 100_000
    finally:
        runner.kill_all()


def test_large_response_under_the_default_cap_round_trips() -> None:
    runner = _runner(target=_large_response_target)
    try:
        assert runner.run("ping", None, 30, {}) == "x" * 10_000
    finally:
        runner.kill_all()


def test_oversized_response_names_the_setting() -> None:
    runner = _runner(target=_large_response_target, ipc_max_response_bytes=1024)
    try:
        with pytest.raises(MaudeWorkerProtocolError) as exc_info:
            _ = runner.run("ping", None, 30, {})
        assert "HAROLD_IPC_MAX_RESPONSE_BYTES" in exc_info.value.reason
        assert "1024" in exc_info.value.reason
    finally:
        runner.kill_all()
