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
_STANDARD_INPUT = "<standard input>"


def _dependency_message(file: str, line: int | None, message: str) -> str:
    """Wrap a foreign-file warning as a whole-file diagnostic message.

    The warning belongs to a file the diagnosed file loaded (via `load`/`in`);
    there is no valid position for it in the diagnosed file, so the message
    names the real source and points at the tool that can diagnose it
    (dependencies resolve relative to the diagnosed file's directory). Maude's
    messages may lack final punctuation (`no parse for statement`), so one is
    added before the suggestion when needed.
    """
    line_info = f", line {line}" if line is not None else ""
    terminator = "" if message.endswith((".", "!", "?")) else "."
    return (
        f'In "{file}"{line_info}: {message}{terminator} '
        f'Run maude_program_diagnostics on "{file}" (resolved relative to the diagnosed file\'s directory) for details.'
    )


class InterpreterDiagnosticProvider:
    """`DiagnosticProvider` over the Maude interpreter load (v1 behavior).

    Reports one `warning` per `Warning:` line Maude printed, and — when the program
    could not be loaded at all — one synthesized whole-file `error`. Warnings
    Maude attributed to the diagnosed file (or to `<standard input>`) keep their
    line; warnings attributed to another file (a dependency loaded from the
    diagnosed file) become whole-file diagnostics naming that file, so the tool
    never fabricates a position in the diagnosed file for them.
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
            self._to_diagnostic(source, file=warning["file"], line=warning["line"], message=warning["message"])
            for warning in result["warnings"]
        ]
        if not result["ok"]:
            diagnostics.append(
                ProviderDiagnostic(source=self.name, severity="error", code=_CODE, message=_HARD_FAILURE_MESSAGE)
            )
        return diagnostics

    def _to_diagnostic(self, source: SourceFile, *, file: str, line: int | None, message: str) -> ProviderDiagnostic:
        """Map one parsed warning; foreign files become whole-file diagnostics."""
        if file in (source.path.name, _STANDARD_INPUT):
            return ProviderDiagnostic(source=self.name, severity="warning", code=_CODE, message=message, line=line)
        return ProviderDiagnostic(
            source=self.name,
            severity="warning",
            code=_CODE,
            message=_dependency_message(file, line, message),
            line=None,
        )
