"""One-shot JSON request/response transport for a per-call Maude child process.

The child runs `serve_one` as its process target. It reads exactly one request
from the `multiprocessing` Pipe, performs the requested operation and sends
exactly one response; the process then exits and the parent reaps it.

Before touching the interpreter the child points fds 0, 1 and 2 at `os.devnull`:
a spawned child inherits the server's descriptors, and a stray library write to
fd 1 would corrupt the MCP stdio transport. `capture_streams` still redirects
fds 1/2 around Maude work, so captured output is unaffected.

The worker and session modules are imported lazily inside `serve_one`, so
importing this module never loads the `maude` SWIG bindings. There is no protocol
version field: the child is spawned from the same package and is one-shot, so a
version mismatch cannot occur.
"""

import json
import os
import traceback
from multiprocessing.connection import Connection
from typing import Any, NoReturn

_OPERATIONS = frozenset({"ping", "diagnostics", "session"})


class ChildProtocolError(Exception):
    """The request does not follow the one-shot protocol."""


def _fail_request(message: str) -> NoReturn:
    """Raise a request-protocol error (keeps the message out of raise statements)."""
    raise ChildProtocolError(message)


def _format_exc(exc: BaseException) -> str:
    """Render an exception with its traceback, even outside its handler."""
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))


def _worker_context(exc: BaseException) -> dict[str, object]:
    """Read the phase annotation the session engine attached to an exception."""
    context = getattr(exc, "worker_context", None)
    return dict(context) if isinstance(context, dict) else {}


def _redirect_stdio_to_devnull() -> None:
    """Point fds 0, 1 and 2 at `os.devnull`, before any Maude import or init."""
    devnull = os.open(os.devnull, os.O_RDWR)
    try:
        for fd in (0, 1, 2):
            _ = os.dup2(devnull, fd)
    finally:
        os.close(devnull)


def _encode(message: dict[str, Any]) -> bytes:
    """Serialize one envelope as UTF-8 JSON."""
    return json.dumps(message, ensure_ascii=False).encode("utf-8")


def _send_ok(conn: Connection, result: Any) -> None:
    """Send a successful response envelope."""
    conn.send_bytes(_encode({"status": "ok", "result": result}))


def _send_error(
    conn: Connection,
    *,
    category: str,
    error_type: str,
    message: str,
    traceback_text: str,
    context: dict[str, object] | None = None,
) -> None:
    """Send a failure response envelope."""
    conn.send_bytes(
        _encode({
            "status": "error",
            "error": {
                "category": category,
                "type": error_type,
                "message": message,
                "traceback": traceback_text,
                "context": context if context is not None else {},
            },
        })
    )


def _validate_request(raw: bytes) -> tuple[str, Any]:
    """Decode a request envelope and validate its operation and payload shape."""
    request = json.loads(raw)
    if not isinstance(request, dict):
        _fail_request("request must be a JSON object")
    operation = request.get("operation")
    payload = request.get("payload")
    if not isinstance(operation, str):
        _fail_request("request.operation must be a string")
    if operation not in _OPERATIONS:
        _fail_request(f"unknown operation {operation!r}")
    if operation == "diagnostics":
        if not isinstance(payload, dict):
            _fail_request("request.payload must be a JSON object for diagnostics")
        if not isinstance(payload.get("path"), str):
            _fail_request("request.payload.path must be a string")
    elif operation == "session" and not isinstance(payload, dict):
        _fail_request("request.payload must be a JSON object for session")
    return operation, payload


def _dispatch(operation: str, payload: Any) -> Any:
    """Initialize Maude once, then run the requested one-shot operation."""
    from harold_mcp.maude import worker

    # Always initialized first (idempotent per process), so `ping` is a real
    # initialization check and every other operation starts from a ready interpreter.
    worker.init_maude()
    if operation == "ping":
        return None
    if operation == "diagnostics":
        return worker.load_diagnostics(payload["path"])
    if operation == "session":
        from harold_mcp.maude import session

        return session.run_session(payload)
    _fail_request(f"unknown operation {operation!r}")


def serve_one(conn: Connection) -> None:
    """Serve exactly one request, send one response and return.

    This is the process target for a call. A stdio-redirect failure exits via
    `os._exit(1)` without printing, so multiprocessing's bootstrap cannot write a
    traceback to the inherited fd 2; the parent observes EOF and reports a crash.
    """
    try:
        _redirect_stdio_to_devnull()
    except BaseException:
        os._exit(1)
    from harold_mcp.maude.worker import WorkerInitError

    try:
        try:
            raw = conn.recv_bytes()
        except EOFError, OSError:
            # The parent closed the pipe (shutdown) or died: treat as a closed peer.
            return
        try:
            operation, payload = _validate_request(raw)
        except Exception as exc:
            _send_error(
                conn,
                category="protocol",
                error_type=type(exc).__name__,
                message=str(exc),
                traceback_text=_format_exc(exc),
            )
            return
        try:
            result = _dispatch(operation, payload)
        except BaseException as exc:
            category = (
                "protocol"
                if isinstance(exc, ChildProtocolError)
                else "init"
                if isinstance(exc, WorkerInitError)
                else "remote"
            )
            _send_error(
                conn,
                category=category,
                error_type=type(exc).__name__,
                message=str(exc),
                traceback_text=_format_exc(exc),
                context=_worker_context(exc),
            )
        else:
            _send_ok(conn, result)
    finally:
        conn.close()
