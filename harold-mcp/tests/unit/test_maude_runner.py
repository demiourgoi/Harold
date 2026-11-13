"""Unit tests for the process runner (`harold_mcp.maude.runner`) with fakes.

A fake multiprocessing context supplies a fake connection and process, so these
tests exercise spawn, the one-shot exchange, deadline handling, error mapping,
the shutdown registration window and the active-process registry without
spawning anything or loading Maude.
"""

import json
import threading
from collections.abc import Callable
from typing import Any

import pytest

from harold_mcp.maude.errors import (
    MaudeInitError,
    MaudeWorkerCancelledError,
    MaudeWorkerCrashedError,
    MaudeWorkerProtocolError,
    MaudeWorkerRemoteError,
    MaudeWorkerSpawnError,
    MaudeWorkerTimeoutError,
)
from harold_mcp.maude.runner import PipeProcessRunner
from harold_mcp.settings import Settings


class FakeConnection:
    """A minimal `multiprocessing.Connection` stand-in with scriptable behavior."""

    def __init__(
        self,
        *,
        response: bytes = b"",
        recv_error: BaseException | None = None,
        poll_result: bool = True,
        send_error: BaseException | None = None,
    ) -> None:
        self.response = response
        self.recv_error = recv_error
        self.poll_result = poll_result
        self.send_error = send_error
        self.sent: list[bytes] = []
        self.closed = False
        self.poll_timeouts: list[float | None] = []
        self.recv_maxlengths: list[int | None] = []

    def send_bytes(self, payload: bytes) -> None:
        if self.send_error is not None:
            raise self.send_error
        self.sent.append(payload)

    def poll(self, timeout: float | None = None) -> bool:
        self.poll_timeouts.append(timeout)
        return self.poll_result

    def recv_bytes(self, maxlength: int | None = None) -> bytes:
        self.recv_maxlengths.append(maxlength)
        if self.recv_error is not None:
            raise self.recv_error
        return self.response

    def close(self) -> None:
        self.closed = True


class FakeProcess:
    """A scriptable child process: records start/kill/join/close."""

    def __init__(
        self,
        pid: int | None = 4242,
        *,
        start_error: BaseException | None = None,
        on_start: Callable[[], None] | None = None,
    ) -> None:
        self.pid = pid
        self.start_error = start_error
        self.on_start = on_start
        self.started = False
        self.killed = False
        self.closed = False
        self.joins: list[float | None] = []
        self._alive = False

    def start(self) -> None:
        if self.start_error is not None:
            raise self.start_error
        self.started = True
        self._alive = True
        if self.on_start is not None:
            self.on_start()

    def is_alive(self) -> bool:
        return self._alive

    def kill(self) -> None:
        self.killed = True
        self._alive = False

    def join(self, timeout: float | None = None) -> None:
        self.joins.append(timeout)
        self._alive = False

    def close(self) -> None:
        self.closed = True


class FakeContext:
    """A fake `multiprocessing` spawn context."""

    def __init__(
        self, parent: FakeConnection, process: FakeProcess, *, pipe_error: BaseException | None = None
    ) -> None:
        self.parent = parent
        self.child = FakeConnection()
        self.process = process
        self.pipe_error = pipe_error
        self.pipe_calls = 0
        self.process_args: tuple[Any, tuple[Any, ...], bool] | None = None

    def Pipe(self) -> tuple[FakeConnection, FakeConnection]:
        if self.pipe_error is not None:
            raise self.pipe_error
        self.pipe_calls += 1
        return self.parent, self.child

    def Process(self, *, target: Callable[[Any], None], args: tuple[Any, ...], daemon: bool) -> FakeProcess:
        self.process_args = (target, args, daemon)
        return self.process


def _runner(
    *,
    parent: FakeConnection | None = None,
    process: FakeProcess | None = None,
    settings: Settings | None = None,
    pipe_error: BaseException | None = None,
) -> tuple[PipeProcessRunner, FakeConnection, FakeProcess, FakeContext]:
    parent = parent if parent is not None else FakeConnection()
    process = process if process is not None else FakeProcess()
    context = FakeContext(parent, process, pipe_error=pipe_error)
    runner = PipeProcessRunner(
        settings if settings is not None else Settings(maude_workers=1),
        target=lambda conn: None,
        context=context,
    )
    return runner, parent, process, context


def _ok(result: Any) -> bytes:
    return json.dumps({"status": "ok", "result": result}).encode()


def _error(
    category: str,
    *,
    type_: str = "X",
    message: str = "boom",
    traceback_text: str = "remote traceback",
    context: dict[str, object] | None = None,
) -> bytes:
    return json.dumps({
        "status": "error",
        "error": {
            "category": category,
            "type": type_,
            "message": message,
            "traceback": traceback_text,
            "context": context if context is not None else {},
        },
    }).encode()


def test_success_returns_the_result_and_cleans_up() -> None:
    runner, parent, process, context = _runner(parent=FakeConnection(response=_ok({"ok": True})))

    result = runner.run("diagnostics", {"path": "x.maude"}, 5.0, {"path": "/abs/x.maude"})

    assert result == {"ok": True}
    assert json.loads(parent.sent[0]) == {"operation": "diagnostics", "payload": {"path": "x.maude"}}
    assert "version" not in json.loads(parent.sent[0])
    assert parent.closed
    assert context.child.closed
    assert process.killed
    assert process.closed
    assert runner.active_count() == 0


def test_response_receive_uses_the_configured_cap() -> None:
    settings = Settings(maude_workers=1, ipc_max_response_bytes=4096)
    runner, parent, _, _ = _runner(parent=FakeConnection(response=_ok(None)), settings=settings)

    _ = runner.run("ping", None, 5.0, {})

    assert parent.recv_maxlengths == [4096]


def test_eof_is_a_crash() -> None:
    runner, _, process, _ = _runner(parent=FakeConnection(recv_error=EOFError()))

    with pytest.raises(MaudeWorkerCrashedError) as exc_info:
        _ = runner.run("ping", None, 5.0, {})

    assert exc_info.value.context["pid"] == process.pid
    assert runner.active_count() == 0


def test_mid_message_oserror_is_a_crash() -> None:
    runner, _, _, _ = _runner(parent=FakeConnection(recv_error=OSError("got end of file during message")))

    with pytest.raises(MaudeWorkerCrashedError):
        _ = runner.run("ping", None, 5.0, {})


def test_other_oserror_is_a_crash() -> None:
    runner, _, _, _ = _runner(parent=FakeConnection(recv_error=OSError("broker error")))

    with pytest.raises(MaudeWorkerCrashedError):
        _ = runner.run("ping", None, 5.0, {})


def test_no_response_before_the_deadline_is_a_timeout() -> None:
    runner, _, process, _ = _runner(parent=FakeConnection(poll_result=False))

    with pytest.raises(MaudeWorkerTimeoutError) as exc_info:
        _ = runner.run("ping", None, 5.0, {})

    assert exc_info.value.context["pid"] == process.pid
    assert process.killed
    assert runner.active_count() == 0


def test_oversized_response_names_the_setting() -> None:
    settings = Settings(maude_workers=1, ipc_max_response_bytes=1024)
    runner, _, _, _ = _runner(
        parent=FakeConnection(recv_error=OSError("bad message length")),
        settings=settings,
    )

    with pytest.raises(MaudeWorkerProtocolError) as exc_info:
        _ = runner.run("ping", None, 5.0, {})

    assert "HAROLD_IPC_MAX_RESPONSE_BYTES" in exc_info.value.reason
    assert "1024" in exc_info.value.reason
    assert 'path="labels"' in exc_info.value.reason


def test_send_failure_is_a_crash() -> None:
    runner, _, _, _ = _runner(parent=FakeConnection(send_error=BrokenPipeError()))

    with pytest.raises(MaudeWorkerCrashedError):
        _ = runner.run("ping", None, 5.0, {})


def test_spawn_failure_is_a_spawn_error_without_a_pid() -> None:
    runner, parent, _, context = _runner(process=FakeProcess(start_error=OSError("cannot spawn")))

    with pytest.raises(MaudeWorkerSpawnError) as exc_info:
        _ = runner.run("ping", None, 5.0, {"path": "/abs/x.maude"})

    assert "OSError: cannot spawn" in exc_info.value.reason
    assert exc_info.value.context["pid"] is None
    assert exc_info.value.context["path"] == "/abs/x.maude"
    assert parent.closed
    assert context.child.closed
    assert runner.active_count() == 0


def test_pipe_failure_is_a_spawn_error() -> None:
    runner, _, _, _ = _runner(pipe_error=OSError("cannot create pipe"))

    with pytest.raises(MaudeWorkerSpawnError) as exc_info:
        _ = runner.run("ping", None, 5.0, {})

    assert "cannot create pipe" in exc_info.value.reason
    assert exc_info.value.context["pid"] is None


def test_shutdown_before_registration_cancels_and_kills_the_child() -> None:
    holder: dict[str, PipeProcessRunner] = {}
    process = FakeProcess(on_start=lambda: holder["runner"].kill_all())
    runner, parent, _, _ = _runner(process=process)
    holder["runner"] = runner

    with pytest.raises(MaudeWorkerCancelledError):
        _ = runner.run("ping", None, 5.0, {})

    assert process.killed
    assert parent.closed
    assert runner.active_count() == 0


def test_kill_all_kills_and_reaps_active_children() -> None:
    started = threading.Event()
    release = threading.Event()

    class BlockingConnection(FakeConnection):
        def poll(self, timeout: float | None = None) -> bool:
            self.poll_timeouts.append(timeout)
            started.set()
            _ = release.wait(timeout=5)
            return False

    parent = BlockingConnection()
    runner, _, process, _ = _runner(parent=parent)
    outcomes: list[BaseException] = []

    def call() -> None:
        try:
            _ = runner.run("ping", None, 5.0, {})
        except BaseException as exc:
            outcomes.append(exc)

    thread = threading.Thread(target=call)
    thread.start()
    assert started.wait(timeout=5)
    assert runner.active_count() == 1

    runner.kill_all()

    assert process.killed
    assert parent.closed
    assert runner.active_count() == 0
    release.set()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert len(outcomes) == 1
    assert isinstance(outcomes[0], MaudeWorkerTimeoutError)


def test_init_envelope_maps_to_init_error() -> None:
    response = _error("init", type_="WorkerInitError", message="", traceback_text="init tb", context={"phase": "load"})
    runner, _, process, _ = _runner(parent=FakeConnection(response=response))

    with pytest.raises(MaudeInitError) as exc_info:
        _ = runner.run("ping", None, 5.0, {"module": "M"})

    error = exc_info.value
    assert error.reason == "Failed to initialize the Maude interpreter in the worker process"
    assert error.remote_traceback == "init tb"
    assert error.context["phase"] == "load"
    assert error.context["module"] == "M"
    assert error.context["pid"] == process.pid


def test_remote_envelope_maps_to_remote_error_and_merges_context() -> None:
    response = _error(
        "remote",
        type_="ValueError",
        message="boom",
        traceback_text="worker traceback",
        context={"phase": "step", "step": 1},
    )
    runner, _, process, _ = _runner(parent=FakeConnection(response=response))

    with pytest.raises(MaudeWorkerRemoteError) as exc_info:
        _ = runner.run("session", {}, 5.0, {"path": "/p.maude", "step": 9})

    error = exc_info.value
    assert (error.remote_type, error.remote_message) == ("ValueError", "boom")
    assert error.reason == "ValueError: boom"
    assert error.remote_traceback == "worker traceback"
    assert error.context == {"phase": "step", "step": 9, "path": "/p.maude", "pid": process.pid}


def test_protocol_envelope_maps_to_protocol_error() -> None:
    runner, _, _, _ = _runner(parent=FakeConnection(response=_error("protocol", message="unknown operation 'x'")))

    with pytest.raises(MaudeWorkerProtocolError) as exc_info:
        _ = runner.run("ping", None, 5.0, {})

    assert exc_info.value.reason == "unknown operation 'x'"


def test_unknown_error_category_is_a_protocol_error() -> None:
    runner, _, _, _ = _runner(parent=FakeConnection(response=_error("bogus")))

    with pytest.raises(MaudeWorkerProtocolError, match="unknown error category"):
        _ = runner.run("ping", None, 5.0, {})


def test_invalid_json_is_a_protocol_error() -> None:
    runner, _, _, _ = _runner(parent=FakeConnection(response=b"{not json"))

    with pytest.raises(MaudeWorkerProtocolError, match="invalid worker response"):
        _ = runner.run("ping", None, 5.0, {})


def test_non_object_envelope_is_a_protocol_error() -> None:
    runner, _, _, _ = _runner(parent=FakeConnection(response=b"[]"))

    with pytest.raises(MaudeWorkerProtocolError, match="JSON object"):
        _ = runner.run("ping", None, 5.0, {})


def test_unknown_status_is_a_protocol_error() -> None:
    runner, _, _, _ = _runner(parent=FakeConnection(response=json.dumps({"status": "wat"}).encode()))

    with pytest.raises(MaudeWorkerProtocolError, match="unknown status"):
        _ = runner.run("ping", None, 5.0, {})


def test_missing_error_object_is_a_protocol_error() -> None:
    runner, _, _, _ = _runner(parent=FakeConnection(response=json.dumps({"status": "error"}).encode()))

    with pytest.raises(MaudeWorkerProtocolError, match="missing error object"):
        _ = runner.run("ping", None, 5.0, {})


def test_remote_envelope_without_a_type_is_a_protocol_error() -> None:
    response = json.dumps({"status": "error", "error": {"category": "remote", "message": "boom"}}).encode()
    runner, _, _, _ = _runner(parent=FakeConnection(response=response))

    with pytest.raises(MaudeWorkerProtocolError, match="without a type or message"):
        _ = runner.run("ping", None, 5.0, {})


@pytest.mark.parametrize(
    "parent",
    [
        FakeConnection(recv_error=EOFError()),
        FakeConnection(poll_result=False),
        FakeConnection(response=b"not json"),
    ],
)
def test_active_map_is_cleaned_after_every_error_path(parent: FakeConnection) -> None:
    runner, _, _, _ = _runner(parent=parent)

    with pytest.raises((MaudeWorkerCrashedError, MaudeWorkerTimeoutError, MaudeWorkerProtocolError)):
        _ = runner.run("ping", None, 5.0, {})

    assert runner.active_count() == 0


def test_successful_call_returns_none_for_ping() -> None:
    runner, _, _, _ = _runner(parent=FakeConnection(response=_ok(None)))

    assert runner.run("ping", None, 5.0, {}) is None
    assert runner.active_count() == 0
