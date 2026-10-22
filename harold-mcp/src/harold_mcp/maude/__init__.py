"""Maude subsystem: worker-process executor client and worker-side code.

The Maude interpreter runs in a dedicated worker process; importing this
package never imports the SWIG `maude` bindings.
"""

from harold_mcp.maude.capture import CapturedOutput, WarningDict
from harold_mcp.maude.executor import (
    MaudeError,
    MaudeExecutor,
    MaudeInitError,
    MaudeWorkerCrashedError,
    MaudeWorkerError,
    MaudeWorkerTimeoutError,
    get_maude_executor,
)
from harold_mcp.maude.provider import InterpreterDiagnosticProvider
from harold_mcp.maude.session import (
    CommandName,
    SessionRequest,
    SessionResult,
    StepOutcomeDict,
    StepRequest,
    StepStatus,
)

__all__ = [
    "CapturedOutput",
    "CommandName",
    "InterpreterDiagnosticProvider",
    "MaudeError",
    "MaudeExecutor",
    "MaudeInitError",
    "MaudeWorkerCrashedError",
    "MaudeWorkerError",
    "MaudeWorkerTimeoutError",
    "SessionRequest",
    "SessionResult",
    "StepOutcomeDict",
    "StepRequest",
    "StepStatus",
    "WarningDict",
    "get_maude_executor",
]
