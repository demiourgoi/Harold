"""Maude subsystem: worker-process executor client and worker-side code.

The Maude interpreter runs in a dedicated worker process; importing this
package never imports the SWIG `maude` bindings.
"""

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

__all__ = [
    "InterpreterDiagnosticProvider",
    "MaudeError",
    "MaudeExecutor",
    "MaudeInitError",
    "MaudeWorkerCrashedError",
    "MaudeWorkerError",
    "MaudeWorkerTimeoutError",
    "get_maude_executor",
]
