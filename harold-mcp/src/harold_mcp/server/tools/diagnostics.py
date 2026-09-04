"""Diagnostics tools for Maude programs.

The `maude_program_diagnostics` tool loads a Maude source file into the
interpreter (running in the dedicated worker process) and reports every
problem it finds, including warnings the interpreter can recover from.
"""

import os
from pathlib import Path
from typing import Literal

from fastmcp.dependencies import Depends
from mcp.types import ToolAnnotations
from pydantic import BaseModel

from harold_mcp.maude import MaudeExecutor, MaudeFileNotFoundError, get_maude_executor
from harold_mcp.maude.worker import WarningDict
from harold_mcp.server.server import mcp
from harold_mcp.server.tags import DIAGNOSTICS, harold_tags


class MaudePosition(BaseModel):
    """A position in a Maude source file (LSP-style)."""

    line: int  # 1-based line number
    column: int | None = None  # Maude reports no columns; reserved for future sources


class MaudeRange(BaseModel):
    """A range between two positions (LSP-style)."""

    start: MaudePosition
    end: MaudePosition | None = None  # Maude reports no spans


class MaudeDiagnostic(BaseModel):
    """A single problem found in a Maude source file."""

    severity: Literal["warning", "error"]  # "error" is synthesized for unrecoverable load failures
    range: MaudeRange | None  # None = whole-file problem
    message: str


class MaudeDiagnosticsSummary(BaseModel):
    """Per-severity counts of the diagnostics."""

    warning: int
    error: int


class MaudeProgramDiagnosticsResult(BaseModel):
    """Result of diagnosing a Maude source file."""

    path: str  # echo of the input path as given
    success: bool  # true only when the file loaded with no warnings and no errors
    summary: MaudeDiagnosticsSummary
    diagnostics: list[MaudeDiagnostic]


_HARD_FAILURE_MESSAGE = "Failed to load Maude program: unrecoverable parse error."


def _range_for_line(line: int | None) -> MaudeRange | None:
    """Build an LSP-style range for a warning line; `None` for whole-file problems."""
    if line is None:
        return None
    return MaudeRange(start=MaudePosition(line=line))


def _build_result(path: str, ok: bool, warnings: list[WarningDict]) -> MaudeProgramDiagnosticsResult:
    """Map the worker's tri-state outcome onto the result model."""
    diagnostics = [
        MaudeDiagnostic(severity="warning", range=_range_for_line(warning["line"]), message=warning["message"])
        for warning in warnings
    ]
    if not ok:
        diagnostics.append(MaudeDiagnostic(severity="error", range=None, message=_HARD_FAILURE_MESSAGE))
    return MaudeProgramDiagnosticsResult(
        path=path,
        success=ok and not warnings,
        summary=MaudeDiagnosticsSummary(
            warning=sum(1 for diagnostic in diagnostics if diagnostic.severity == "warning"),
            error=sum(1 for diagnostic in diagnostics if diagnostic.severity == "error"),
        ),
        diagnostics=diagnostics,
    )


@mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    tags=harold_tags(DIAGNOSTICS),
)
def maude_program_diagnostics(
    path: str,
    maude_executor: MaudeExecutor = Depends(get_maude_executor),  # noqa: B008 - FastMCP dependency-injection convention
) -> MaudeProgramDiagnosticsResult:
    """Diagnose a Maude source file by loading it into the Maude interpreter.

    Loads the file at `path` and reports every problem Maude encounters,
    including warnings the interpreter can recover from. Use this tool to
    check whether a Maude program is well formed, and to get a list of issues
    to fix when it is not.

    Args:
        path: Absolute path to the Maude source file to diagnose (typically `.maude`).

    Returns:
        A structured result with `success` (true only when the file loaded
        with no warnings and no errors), per-severity counts, and one
        diagnostic per problem, with LSP-style ranges.

    Note:
        Loading the file updates the interpreter's loaded modules
        (last load wins), like the Maude CLI.
    """
    if not Path(path).is_file() or not os.access(path, os.R_OK):
        raise MaudeFileNotFoundError(path)
    worker_result = maude_executor.diagnostics(path)
    return _build_result(path, worker_result["ok"], worker_result["warnings"])
