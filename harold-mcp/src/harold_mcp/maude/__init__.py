"""Maude subsystem: worker-process executor client and worker-side code.

The Maude interpreter runs in a dedicated worker process; importing this
package never imports the SWIG `maude` bindings.
"""

from harold_mcp.maude.capture import CapturedOutput, WarningDict
from harold_mcp.maude.executor import MaudeExecutor, get_maude_executor
from harold_mcp.maude.provider import InterpreterDiagnosticProvider
from harold_mcp.maude.session import (
    BindingDict,
    CommandName,
    PathDict,
    PathRuleDict,
    PathTransitionDict,
    SessionRequest,
    SessionResult,
    SolutionDict,
    StepOutcomeDict,
    StepRequest,
    StepStatus,
)
from harold_mcp.maude.worker_errors import (
    MaudeError,
    MaudeInitError,
    MaudeWorkerCancelledError,
    MaudeWorkerCrashedError,
    MaudeWorkerError,
    MaudeWorkerProtocolError,
    MaudeWorkerRemoteError,
    MaudeWorkerSpawnError,
    MaudeWorkerTimeoutError,
)

__all__ = [
    "BindingDict",
    "CapturedOutput",
    "CommandName",
    "InterpreterDiagnosticProvider",
    "MaudeError",
    "MaudeExecutor",
    "MaudeInitError",
    "MaudeWorkerCancelledError",
    "MaudeWorkerCrashedError",
    "MaudeWorkerError",
    "MaudeWorkerProtocolError",
    "MaudeWorkerRemoteError",
    "MaudeWorkerSpawnError",
    "MaudeWorkerTimeoutError",
    "PathDict",
    "PathRuleDict",
    "PathTransitionDict",
    "SessionRequest",
    "SessionResult",
    "SolutionDict",
    "StepOutcomeDict",
    "StepRequest",
    "StepStatus",
    "WarningDict",
    "get_maude_executor",
]
