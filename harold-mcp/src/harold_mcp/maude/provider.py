"""Maude interpreter diagnostics provider.

Runs in the MCP server process and crosses the worker boundary through
`MaudeExecutor`; the Maude error vocabulary (`MaudeWorkerError`) is translated into the
diagnostics layer's `DiagnosticProviderError` here, with the original error kept as
`__cause__`.
"""

from harold_mcp.diagnostics import (
    DiagnosticProviderError,
    DiagnosticSource,
    ProviderDiagnostic,
    SourceFile,
)
from harold_mcp.maude.executor import MaudeExecutor, MaudeWorkerError

_HARD_FAILURE_MESSAGE = "Failed to load Maude program: unrecoverable parse error."
_CODE = "compiler"


class InterpreterDiagnosticProvider:
    """`DiagnosticProvider` over the Maude interpreter load (v1 behavior).

    Reports one `warning` per `Warning:` line Maude printed, and — when the program
    could not be loaded at all — one synthesized whole-file `error`.
    """

    name: DiagnosticSource = "interpreter"

    def __init__(self, executor: MaudeExecutor) -> None:
        self._executor = executor

    def diagnose(self, source: SourceFile) -> list[ProviderDiagnostic]:
        """Load `source.path` in the worker and map its outcome to diagnostics.

        Raises:
            DiagnosticProviderError: the worker crashed or timed out; the original
                `MaudeWorkerError` is the chained cause.
        """
        try:
            # `maude.load` and the worker take strings; the seam speaks `Path`.
            result = self._executor.diagnostics(str(source.path))
        except MaudeWorkerError as exc:
            # The Maude vocabulary stops here: the diagnostics layer reports a provider
            # failure, and `__cause__` keeps the worker error for logs and debugging.
            raise DiagnosticProviderError(self.name, exc.reason) from exc
        diagnostics = [
            ProviderDiagnostic(
                source=self.name,
                severity="warning",
                code=_CODE,
                message=warning["message"],
                line=warning["line"],
            )
            for warning in result["warnings"]
        ]
        if not result["ok"]:
            diagnostics.append(
                ProviderDiagnostic(source=self.name, severity="error", code=_CODE, message=_HARD_FAILURE_MESSAGE)
            )
        return diagnostics
