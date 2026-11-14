"""Integration tests for per-call process isolation and the historical bug matrix.

The cascade reproduces the reported B1/B2/B3 recipe: three occupying calls hold
every interpreter slot, a queued non-terminating call with a short timeout is
admitted only after them, and four healthy searches are queued behind it. Before
the per-call architecture one timeout replaced the shared pool, so the occupiers
and healthy calls failed with ``Maude worker crashed``/``CancelledError``; here
only the trigger times out and every other call completes.

The injected target is also the test seam from the design: it serves ``ping``,
serves real operations through the production dispatch, and lets the occupiers
hold a slot until the test drops a release marker (no sleeps as synchronization).
"""

import json
import os
import threading
import time
from collections.abc import Callable
from concurrent.futures import CancelledError
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any

import pytest

from harold_mcp.maude import (
    MaudeExecutor,
    MaudeWorkerCancelledError,
    MaudeWorkerTimeoutError,
    transport,
)
from harold_mcp.maude.runner import PipeProcessRunner
from harold_mcp.maude.session import SessionRequest
from harold_mcp.settings import Settings

FIXTURES_DIR = Path(__file__).parent / "fixtures"
CALL_TIMEOUT_SECS = 60
TRIGGER_TIMEOUT_SECS = 2
_WAIT_STEP_SECS = 0.01


def _occupier_request(directory: Path, index: int) -> SessionRequest:
    """A request whose path marks the process as an occupier for the target."""
    return {
        "path": str(directory / f"occupier-{index}.occupier"),
        "module": "OCCUPIER",
        "steps": [],
        "max_solutions": 200,
        "max_result_length": 1_000_000,
        "max_path_steps": 100,
        "max_output_length": 1_000_000,
    }


def _non_terminating_request() -> SessionRequest:
    """An unbounded rewrite on the self-looping CHAIN module."""
    return {
        "path": str(FIXTURES_DIR / "search_path.maude"),
        "module": "CHAIN",
        "steps": [
            {
                "command": "rewrite",
                "term": "n(0)",
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


def _healthy_request() -> SessionRequest:
    """A small real search on COUNTER: enough work to prove the call ran."""
    return {
        "path": str(FIXTURES_DIR / "counter.maude"),
        "module": "COUNTER",
        "steps": [
            {
                "command": "search",
                "term": None,
                "pattern": "c(N)",
                "subject": "c(0)",
                "bound": None,
                "gas": None,
                "depth": 2,
                "search_type": "any-steps",
                "path_mode": None,
            }
        ],
        "max_solutions": 200,
        "max_result_length": 1_000_000,
        "max_path_steps": 100,
        "max_output_length": 1_000_000,
    }


def _cascade_target(conn: Connection) -> None:
    """Serve pings and real operations; occupiers block until the release marker."""
    request = json.loads(conn.recv_bytes())
    operation = request["operation"]
    payload = request.get("payload")
    if operation == "ping":
        transport._send_ok(conn, None)
        conn.close()
        return
    path = payload.get("path") if isinstance(payload, dict) else None
    if isinstance(path, str) and path.endswith(".occupier"):
        directory = Path(path).parent
        (directory / f"started-{os.getpid()}").touch()
        deadline = time.monotonic() + CALL_TIMEOUT_SECS
        while time.monotonic() < deadline and not (directory / "release").exists():
            time.sleep(_WAIT_STEP_SECS)
        result: dict[str, Any] = {
            "load_ok": True,
            "module_found": True,
            "module_type": 0,
            "defined_modules": ["OCCUPIER"],
            "warnings": [],
            "load_output": {"stdout": "", "stderr": ""},
            "outcomes": [],
        }
        transport._send_ok(conn, result)
        conn.close()
        return
    try:
        result = transport._dispatch(operation, payload)
    except BaseException as exc:
        transport._send_error(
            conn,
            category=transport._error_category(exc),
            error_type=type(exc).__name__,
            message=str(exc),
            traceback_text=transport._format_exc(exc),
            context=transport._worker_context(exc),
        )
    else:
        transport._send_ok(conn, result)
    finally:
        conn.close()


def _record(bucket: list[object], call: Callable[[], object]) -> None:
    """Run `call`, recording its result or exception (thread target helper)."""
    try:
        bucket.append(call())
    except BaseException as exc:
        bucket.append(exc)


def _wait_until(predicate: Callable[[], bool], *, timeout: float = 30.0, what: str) -> None:
    """Poll `predicate` until it holds or the deadline expires (markers, no fixed sleeps)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(_WAIT_STEP_SECS)
    pytest.fail(f"timed out waiting for {what}")


def _is_session_result(value: object) -> bool:
    return isinstance(value, dict) and "outcomes" in value


def _is_ok_outcome(value: object) -> bool:
    return _is_session_result(value) and value["outcomes"][0]["status"] == "ok"


def test_historical_cascade_has_no_cancelled_error(tmp_path: Path) -> None:
    settings = Settings(maude_workers=3)
    runner = PipeProcessRunner(settings, target=_cascade_target)
    executor = MaudeExecutor(settings=settings, runner_factory=lambda: runner)
    executor.start(settings.diagnostics_timeout_secs)
    occupiers: list[object] = []
    trigger: list[object] = []
    healthy: list[object] = []

    def occupier(index: int) -> None:
        _record(occupiers, lambda: executor.run_session(_occupier_request(tmp_path, index), timeout=CALL_TIMEOUT_SECS))

    def trigger_call() -> None:
        _record(trigger, lambda: executor.run_session(_non_terminating_request(), timeout=TRIGGER_TIMEOUT_SECS))

    def healthy_call() -> None:
        _record(healthy, lambda: executor.run_session(_healthy_request(), timeout=CALL_TIMEOUT_SECS))

    try:
        occupier_threads = [threading.Thread(target=occupier, args=(index,)) for index in range(3)]
        for thread in occupier_threads:
            thread.start()
        _wait_until(
            lambda: len(list(tmp_path.glob("started-*"))) >= 3,
            what="the three occupiers to hold their slots",
        )

        trigger_thread = threading.Thread(target=trigger_call)
        trigger_thread.start()
        healthy_threads = [threading.Thread(target=healthy_call) for _ in range(4)]
        for thread in healthy_threads:
            thread.start()

        # The trigger waits for a slot the occupiers hold and times out on its own.
        trigger_thread.join(timeout=30)
        assert len(trigger) == 1
        assert isinstance(trigger[0], MaudeWorkerTimeoutError)

        # Releasing the occupiers lets the queued healthy calls run to completion.
        _ = (tmp_path / "release").touch()
        for thread in [*occupier_threads, *healthy_threads]:
            thread.join(timeout=120)
    finally:
        executor.shutdown()

    every_outcome = [*occupiers, *trigger, *healthy]
    assert not [
        outcome for outcome in every_outcome if isinstance(outcome, (CancelledError, MaudeWorkerCancelledError))
    ]
    assert len(occupiers) == 3
    assert all(_is_session_result(outcome) and outcome["load_ok"] for outcome in occupiers)
    assert len(healthy) == 4
    assert all(_is_ok_outcome(outcome) for outcome in healthy)
    assert runner.active_count() == 0


def test_running_timeout_kills_only_its_own_process_and_a_follow_up_succeeds() -> None:
    settings = Settings(maude_workers=2)
    executor = MaudeExecutor(settings=settings)
    executor.start(settings.diagnostics_timeout_secs)
    slow: list[object] = []
    peer: list[object] = []
    try:
        slow_thread = threading.Thread(
            target=lambda: _record(
                slow,
                lambda: executor.run_session(_non_terminating_request(), timeout=TRIGGER_TIMEOUT_SECS),
            )
        )
        peer_thread = threading.Thread(
            target=lambda: _record(peer, lambda: executor.run_session(_healthy_request(), timeout=CALL_TIMEOUT_SECS))
        )
        slow_thread.start()
        peer_thread.start()
        slow_thread.join(timeout=60)
        peer_thread.join(timeout=60)

        assert len(slow) == 1
        assert isinstance(slow[0], MaudeWorkerTimeoutError)
        assert not isinstance(slow[0], MaudeWorkerCancelledError)
        assert len(peer) == 1
        assert _is_ok_outcome(peer[0])
        # The killed process did not poison the executor: a later call succeeds.
        assert _is_ok_outcome(executor.run_session(_healthy_request(), timeout=CALL_TIMEOUT_SECS))
    finally:
        executor.shutdown()


def test_shutdown_inflight_call_is_cancelled_and_leaves_no_orphans() -> None:
    settings = Settings(maude_workers=1)
    runner = PipeProcessRunner(settings)
    executor = MaudeExecutor(settings=settings, runner_factory=lambda: runner)
    executor.start(settings.diagnostics_timeout_secs)
    outcomes: list[object] = []
    try:
        thread = threading.Thread(
            target=lambda: _record(
                outcomes,
                lambda: executor.run_session(_non_terminating_request(), timeout=CALL_TIMEOUT_SECS),
            )
        )
        thread.start()
        _wait_until(lambda: runner.active_count() == 1, what="the in-flight child")
        executor.shutdown()
        thread.join(timeout=30)

        assert len(outcomes) == 1
        error = outcomes[0]
        assert isinstance(error, MaudeWorkerCancelledError)
        pid = error.context.get("pid")
        assert isinstance(pid, int)
        assert runner.active_count() == 0
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
    finally:
        executor.shutdown()
