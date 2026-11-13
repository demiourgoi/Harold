"""Error vocabulary for the Maude worker subsystem.

Stdlib-only and free of `maude` imports. The hierarchy lives in its own module so
both the client-side executor and the process runner can build these errors
without an import cycle; `harold_mcp.maude.executor` re-exports every class, so
the public import paths stay unchanged.
"""

from collections.abc import Mapping


class MaudeError(RuntimeError):
    """Base error for failures in the Maude worker subsystem."""


class MaudeWorkerError(MaudeError):
    """Base error for failures of a Maude worker call.

    Every whole-call failure carries the machine-readable `category` (used as the
    first line of the client-visible report), an optional `context` supplied by
    the layer that detected the failure (phase, step, pid) and, for a failure
    that crossed the process boundary, the child's `remote_traceback`.
    """

    category: str = "worker-failure"
    reason: str
    context: dict[str, object]
    remote_traceback: str | None

    def __init__(
        self,
        reason: str,
        *,
        context: Mapping[str, object] | None = None,
        remote_traceback: str | None = None,
    ) -> None:
        self.reason = reason
        self.context = dict(context) if context is not None else {}
        self.remote_traceback = remote_traceback
        super().__init__(reason)


class MaudeInitError(MaudeWorkerError):
    """Maude failed to initialize in the worker process."""

    category = "init-failure"

    def __init__(
        self,
        reason: str = "Failed to initialize the Maude interpreter in the worker process",
        *,
        context: Mapping[str, object] | None = None,
        remote_traceback: str | None = None,
    ) -> None:
        super().__init__(reason, context=context, remote_traceback=remote_traceback)


class MaudeWorkerCrashedError(MaudeWorkerError):
    """The worker process died during a call (EOF or a lost connection)."""

    category = "crash"

    def __init__(
        self,
        reason: str = "Maude worker crashed",
        *,
        context: Mapping[str, object] | None = None,
        remote_traceback: str | None = None,
    ) -> None:
        super().__init__(reason, context=context, remote_traceback=remote_traceback)


class MaudeWorkerTimeoutError(MaudeWorkerError):
    """A call timed out; the stuck worker process was killed."""

    category = "timeout"

    def __init__(
        self,
        reason: str = "Maude worker timed out",
        *,
        context: Mapping[str, object] | None = None,
        remote_traceback: str | None = None,
    ) -> None:
        super().__init__(reason, context=context, remote_traceback=remote_traceback)


class MaudeWorkerSpawnError(MaudeWorkerError):
    """The worker process could not be started."""

    category = "spawn-failure"

    def __init__(
        self,
        reason: str = "failed to start the Maude worker",
        *,
        context: Mapping[str, object] | None = None,
        remote_traceback: str | None = None,
    ) -> None:
        super().__init__(reason, context=context, remote_traceback=remote_traceback)


class MaudeWorkerRemoteError(MaudeWorkerError):
    """The worker sent a Python exception instead of a result."""

    category = "remote-exception"
    remote_type: str
    remote_message: str

    def __init__(
        self,
        remote_type: str,
        remote_message: str,
        *,
        context: Mapping[str, object] | None = None,
        remote_traceback: str | None = None,
    ) -> None:
        self.remote_type = remote_type
        self.remote_message = remote_message
        reason = f"{remote_type}: {remote_message}" if remote_message else remote_type
        super().__init__(reason, context=context, remote_traceback=remote_traceback)


class MaudeWorkerCancelledError(MaudeWorkerError):
    """The call was cancelled because the executor is shutting down."""

    category = "cancelled"

    def __init__(
        self,
        reason: str = "cancelled during shutdown",
        *,
        context: Mapping[str, object] | None = None,
        remote_traceback: str | None = None,
    ) -> None:
        super().__init__(reason, context=context, remote_traceback=remote_traceback)


class MaudeWorkerProtocolError(MaudeWorkerError):
    """The worker response was malformed or exceeded the configured size cap."""

    category = "protocol-error"

    def __init__(
        self,
        reason: str = "invalid worker response",
        *,
        context: Mapping[str, object] | None = None,
        remote_traceback: str | None = None,
    ) -> None:
        super().__init__(reason, context=context, remote_traceback=remote_traceback)
