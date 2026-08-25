"""Maude subsystem: worker-process executor client and worker-side code.

The Maude interpreter runs in a dedicated worker process; importing this
package never imports the SWIG `maude` bindings.
"""

from harold_mcp.maude.executor import (
    MaudeError,
    MaudeFileNotFoundError,
    MaudeInitError,
    MaudeWorkerError,
    Settings,
    settings,
)

__all__ = [
    "MaudeError",
    "MaudeFileNotFoundError",
    "MaudeInitError",
    "MaudeWorkerError",
    "Settings",
    "settings",
]
