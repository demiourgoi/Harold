"""Maude interpreter diagnostics provider.

Runs in the MCP server process and crosses the worker boundary through
`MaudeExecutor`; the Maude error vocabulary (`MaudeWorkerError`) is translated into the
diagnostics layer's `DiagnosticProviderError` here, with the original error kept as
`__cause__`.
"""

import re

from harold_mcp.diagnostics import (
    DiagnosticProviderError,
    DiagnosticSource,
    ProviderDiagnostic,
    SourceFile,
)
from harold_mcp.maude.executor import MaudeExecutor
from harold_mcp.maude.worker_errors import MaudeWorkerError

_HARD_FAILURE_MESSAGE = "Failed to load Maude program: unrecoverable parse error."
_CODE = "compiler"
_STANDARD_INPUT = "<standard input>"
_LOAD_RE = re.compile(r"^\s*(?:load|in)\s+(\S+)")
_COMMENT_RE = re.compile(r"^\s*(?:\*\*\*|---)")


def _dependency_names(source: SourceFile) -> set[str]:
    """Return the file names the diagnosed file loads via ``load``/``in``.

    Maude prints warnings with only a file's name, so when a loaded dependency
    shares the diagnosed file's name, there is no way to tell whose warning a
    matching name refers to. The names collected here (targets resolved against
    the diagnosed file's directory, comment lines ignored) let the mapping fall
    back to the whole-file form in that ambiguous case instead of fabricating a
    position in the diagnosed file.

    Known limit: only the direct `load`/`in` targets written in the diagnosed
    file are covered. A transitive dependency (a dependency loading a same-named
    file of its own) can still collide with the diagnosed file's name, in which
    case the warning keeps a line it may not own; reading the loaded files would
    need filesystem access the provider does not have here, and the tool's answer
    is to diagnose dependencies on their own instead.
    """
    names: set[str] = set()
    for line in source.text.splitlines():
        if _COMMENT_RE.match(line):
            continue
        match = _LOAD_RE.match(line)
        if match is None:
            continue
        target = match.group(1)
        if target.endswith(".") and not target.endswith(".."):
            target = target[:-1]
        names.add(source.path.parent.joinpath(target).name)
    return names


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
        """Load `source.path` in a fresh worker and map its outcome to diagnostics.

        Raises:
            DiagnosticProviderError: any `MaudeWorkerError` (timeout, crash, spawn
                failure, init failure, remote exception, cancellation or protocol
                error); the original error is the chained cause and the resolved path
                and load phase are preserved in the context.
        """
        try:
            # `maude.load` and the worker take strings; the seam speaks `Path`.
            result = self._executor.diagnostics(str(source.path))
        except MaudeWorkerError as exc:
            # The Maude vocabulary stops here: the diagnostics layer reports a provider
            # failure, and `__cause__` keeps the worker error for logs and debugging.
            # The path and phase survive the wrap so the error report is self-contained.
            raise DiagnosticProviderError(
                self.name,
                exc.reason,
                context={"path": str(source.path), "phase": "load", **exc.context},
            ) from exc
        dependency_names = _dependency_names(source)
        diagnostics = [
            self._to_diagnostic(
                source,
                file=warning["file"],
                line=warning["line"],
                message=warning["message"],
                dependency_names=dependency_names,
            )
            for warning in result["warnings"]
        ]
        if not result["ok"]:
            diagnostics.append(
                ProviderDiagnostic(source=self.name, severity="error", code=_CODE, message=_HARD_FAILURE_MESSAGE)
            )
        return diagnostics

    def _to_diagnostic(
        self,
        source: SourceFile,
        *,
        file: str,
        line: int | None,
        message: str,
        dependency_names: set[str],
    ) -> ProviderDiagnostic:
        """Map one parsed warning; foreign files become whole-file diagnostics.

        A name matching the diagnosed file keeps its line only when no loaded
        dependency shares that name; Maude prints file names without paths, so
        such a match is ambiguous and falls back to the whole-file form.
        """
        belongs_to_source = file in (_STANDARD_INPUT, source.path.name) and not (
            file == source.path.name and file in dependency_names
        )
        if belongs_to_source:
            return ProviderDiagnostic(source=self.name, severity="warning", code=_CODE, message=message, line=line)
        return ProviderDiagnostic(
            source=self.name,
            severity="warning",
            code=_CODE,
            message=_dependency_message(file, line, message),
            line=None,
        )
