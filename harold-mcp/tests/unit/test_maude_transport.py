"""Unit tests for the one-shot worker transport (`harold_mcp.maude.transport`).

The connection and the Maude worker are faked: these tests pin the envelope
shapes, the protocol validation, the error categorization and the stdio-redirect
safety rule, without spawning a process or loading the interpreter.
"""

import json
import os
from typing import Any, cast

import pytest

from harold_mcp.maude import transport
from harold_mcp.maude import worker as worker_module
from harold_mcp.maude.worker import WorkerInitError

# The autouse fixture replaces the module attribute; keep the real function for its test.
_REAL_REDIRECT = transport._redirect_stdio_to_devnull


class FakeConnection:
    """A minimal `multiprocessing.Connection` stand-in."""

    def __init__(self, request: bytes | None = None, *, recv_error: BaseException | None = None) -> None:
        self._request = request
        self._recv_error = recv_error
        self.sent: list[bytes] = []
        self.closed = False

    def recv_bytes(self, maxlength: int | None = None) -> bytes:
        if self._recv_error is not None:
            raise self._recv_error
        assert self._request is not None
        return self._request

    def send_bytes(self, payload: bytes) -> None:
        self.sent.append(payload)

    def close(self) -> None:
        self.closed = True

    def envelope(self) -> dict[str, Any]:
        assert len(self.sent) == 1
        return cast(dict[str, Any], json.loads(self.sent[0]))


@pytest.fixture(autouse=True)
def _no_stdio_redirect(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the test process's fds intact; the redirect has its own test."""
    monkeypatch.setattr(transport, "_redirect_stdio_to_devnull", lambda: None)


@pytest.fixture
def no_maude(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make dispatch initialization a no-op (the real one loads Maude)."""
    monkeypatch.setattr(worker_module, "init_maude", lambda: None)


def _request(operation: str, payload: Any = None) -> bytes:
    return json.dumps({"operation": operation, "payload": payload}).encode()


def _serve(request: bytes | None = None, *, recv_error: BaseException | None = None) -> FakeConnection:
    conn = FakeConnection(request, recv_error=recv_error)
    transport.serve_one(conn)
    return conn


def test_ping_request_returns_an_ok_envelope(no_maude: None) -> None:
    conn = _serve(_request("ping"))

    assert conn.envelope() == {"status": "ok", "result": None}
    assert conn.closed is True


def test_envelopes_have_no_version_field(no_maude: None) -> None:
    ok = _serve(_request("ping")).envelope()
    error = _serve(b"[]").envelope()

    assert set(ok) == {"status", "result"}
    assert set(error) == {"status", "error"}
    assert set(cast(dict[str, Any], error["error"])) == {"category", "type", "message", "traceback", "context"}


def test_non_object_json_is_a_protocol_error(no_maude: None) -> None:
    envelope = _serve(b"[]").envelope()

    assert envelope["status"] == "error"
    error = cast(dict[str, Any], envelope["error"])
    assert error["category"] == "protocol"
    assert error["type"] == "ChildProtocolError"
    assert error["message"] == "request must be a JSON object"
    assert error["context"] == {}


def test_invalid_json_is_a_protocol_error(no_maude: None) -> None:
    error = cast(dict[str, Any], _serve(b"{not json").envelope()["error"])

    assert error["category"] == "protocol"
    assert error["type"] == "JSONDecodeError"


def test_non_string_operation_is_a_protocol_error(no_maude: None) -> None:
    error = cast(dict[str, Any], _serve(json.dumps({"operation": 1, "payload": None}).encode()).envelope()["error"])

    assert error["message"] == "request.operation must be a string"


def test_unknown_operation_is_a_protocol_error(no_maude: None) -> None:
    error = cast(dict[str, Any], _serve(_request("bogus")).envelope()["error"])

    assert error["category"] == "protocol"
    assert "unknown operation 'bogus'" in cast(str, error["message"])


@pytest.mark.parametrize("payload", [None, [], "x"])
def test_non_object_diagnostics_payload_is_a_protocol_error(no_maude: None, payload: Any) -> None:
    error = cast(dict[str, Any], _serve(_request("diagnostics", payload)).envelope()["error"])

    assert error["category"] == "protocol"
    assert "must be a JSON object" in cast(str, error["message"])


def test_diagnostics_payload_requires_a_string_path(no_maude: None) -> None:
    error = cast(dict[str, Any], _serve(_request("diagnostics", {"path": 1})).envelope()["error"])

    assert error["message"] == "request.payload.path must be a string"


def test_non_object_session_payload_is_a_protocol_error(no_maude: None) -> None:
    error = cast(dict[str, Any], _serve(_request("session", [])).envelope()["error"])

    assert error["category"] == "protocol"


def test_dispatch_failure_is_a_remote_error(no_maude: None, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(path: str) -> None:
        raise ValueError(f"cannot load {path}")  # noqa: TRY003 - test double

    monkeypatch.setattr(worker_module, "load_diagnostics", boom)
    error = cast(dict[str, Any], _serve(_request("diagnostics", {"path": "x.maude"})).envelope()["error"])

    assert error["category"] == "remote"
    assert error["type"] == "ValueError"
    assert error["message"] == "cannot load x.maude"
    assert "Traceback (most recent call last):" in cast(str, error["traceback"])
    assert error["context"] == {}


def test_worker_context_annotation_reaches_the_envelope(no_maude: None, monkeypatch: pytest.MonkeyPatch) -> None:
    from harold_mcp.maude import session as session_module

    def boom(request: Any) -> None:
        error = RuntimeError("boom")
        error.worker_context = {"phase": "load"}
        raise error

    monkeypatch.setattr(session_module, "run_session", boom)
    error = cast(dict[str, Any], _serve(_request("session", {})).envelope()["error"])

    assert error["category"] == "remote"
    assert error["context"] == {"phase": "load"}


def test_worker_init_error_is_an_init_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail() -> None:
        raise WorkerInitError()

    monkeypatch.setattr(worker_module, "init_maude", fail)
    error = cast(dict[str, Any], _serve(_request("ping")).envelope()["error"])

    assert error["category"] == "init"
    assert error["type"] == "WorkerInitError"
    assert "Traceback (most recent call last):" in cast(str, error["traceback"])


def test_dispatch_calls_init_maude_first(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(worker_module, "init_maude", lambda: calls.append("init"))

    assert transport._dispatch("ping", None) is None
    assert calls == ["init"]


def test_dispatch_of_an_unknown_operation_is_a_protocol_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(worker_module, "init_maude", lambda: None)

    with pytest.raises(transport.ChildProtocolError, match="unknown operation"):
        _ = transport._dispatch("bogus", None)


def test_first_recv_eof_is_treated_as_a_closed_peer(no_maude: None) -> None:
    conn = _serve(recv_error=EOFError())

    assert conn.sent == []
    assert conn.closed is True


def test_first_recv_oserror_is_treated_as_a_closed_peer(no_maude: None) -> None:
    conn = _serve(recv_error=OSError("bad file descriptor"))

    assert conn.sent == []
    assert conn.closed is True


def test_stdio_redirect_failure_exits_without_output(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    def fail() -> None:
        raise OSError("cannot redirect")  # noqa: TRY003 - test double

    exits: list[int] = []

    def fake_exit(code: int) -> None:
        exits.append(code)
        raise SystemExit(code)

    monkeypatch.setattr(transport, "_redirect_stdio_to_devnull", fail)
    monkeypatch.setattr(transport.os, "_exit", fake_exit)
    conn = FakeConnection(_request("ping"))

    with pytest.raises(SystemExit):
        transport.serve_one(conn)

    assert exits == [1]
    assert conn.sent == []
    assert capfd.readouterr() == ("", "")


def test_format_exc_renders_a_stored_exception() -> None:
    exc = ValueError("stored")

    rendered = transport._format_exc(exc)

    assert "ValueError: stored" in rendered
    assert "NoneType: None" not in rendered


def test_worker_context_reads_the_annotation() -> None:
    exc = RuntimeError("boom")
    assert transport._worker_context(exc) == {}

    exc.worker_context = {"phase": "step", "step": 2, "command": "search"}
    assert transport._worker_context(exc) == {"phase": "step", "step": 2, "command": "search"}


def test_error_category_maps_protocol_init_and_remote() -> None:
    assert transport._error_category(transport.ChildProtocolError("bad")) == "protocol"
    assert transport._error_category(WorkerInitError()) == "init"
    assert transport._error_category(ValueError("boom")) == "remote"


def test_redirect_stdio_to_devnull_points_the_standard_fds_at_devnull(monkeypatch: pytest.MonkeyPatch) -> None:
    """The redirect preserves the fd numbers but swaps their targets."""
    devnull_fd = os.open(os.devnull, os.O_RDWR)
    saved = [os.dup(fd) for fd in (0, 1, 2)]
    try:
        _REAL_REDIRECT()
        for fd in (0, 1, 2):
            assert os.fstat(fd).st_rdev == os.fstat(devnull_fd).st_rdev
    finally:
        for fd, duplicate in zip((0, 1, 2), saved, strict=True):
            _ = os.dup2(duplicate, fd)
            os.close(duplicate)
        os.close(devnull_fd)
