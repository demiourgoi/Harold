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
from pydantic import BaseModel, ConfigDict

from harold_mcp.maude import MaudeExecutor, MaudeFileNotFoundError, get_maude_executor
from harold_mcp.maude.worker import WarningDict
from harold_mcp.server.server import mcp
from harold_mcp.server.tags import DIAGNOSTICS, harold_tags


class _ResultModel(BaseModel):
    """Base for the tool result models.

    Attribute docstrings are promoted to JSON Schema field descriptions, so they
    reach MCP clients through the tool's output schema.
    """

    model_config = ConfigDict(use_attribute_docstrings=True)


class MaudePosition(_ResultModel):
    """A position in a Maude source file (LSP-style)."""

    line: int
    """1-based line number."""

    column: int | None = None
    """Maude reports no columns, so this is always `null` for now; reserved for future sources."""


class MaudeRange(_ResultModel):
    """A range between two positions (LSP-style)."""

    start: MaudePosition
    """The position the problem was reported at."""

    end: MaudePosition | None = None
    """Maude reports no spans, so this is always `null` for now; reserved for future sources."""


class MaudeDiagnostic(_ResultModel):
    """A single problem found in a Maude source file."""

    severity: Literal["warning", "error"]
    """`"warning"` for problems Maude recovers from; `"error"` for unrecoverable load failures."""

    range: MaudeRange | None
    """Where the problem is; `null` means a whole-file problem (no known location)."""

    message: str
    """The problem text, as reported by Maude (synthesized for unrecoverable parse errors)."""


class MaudeDiagnosticsSummary(_ResultModel):
    """Per-severity counts of the diagnostics."""

    warning: int
    """Number of `"warning"` diagnostics."""

    error: int
    """Number of `"error"` diagnostics."""


class MaudeProgramDiagnosticsResult(_ResultModel):
    """Result of diagnosing a Maude source file."""

    path: str
    """The input path, echoed back as given."""

    success: bool
    """`true` only when the file loaded with no warnings and no errors."""

    summary: MaudeDiagnosticsSummary
    """Per-severity counts of `diagnostics`."""

    diagnostics: list[MaudeDiagnostic]
    """One entry per problem, in the order Maude reported them."""


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
    # FastMCP uses only the free-form text above `Args:` as the MCP tool description;
    # sections like `Returns`, `Raises`, and `Example` are excluded from the description
    # but otherwise ignored (https://gofastmcp.com/servers/tools#docstring-descriptions),
    # so everything a client needs belongs in the prose above `Args:`.
    """Diagnose a Maude source file by loading it into the Maude interpreter.

    Loads the file at `path` and reports every problem Maude encounters,
    including warnings the interpreter can recover from. Use this tool to
    check whether a Maude program is well formed, and to get a list of issues
    to fix when it is not.

    The result is a structured object:

    - `path`: the input path, echoed back as given.
    - `success`: `true` only when the file loaded with no warnings and no errors.
    - `summary`: per-severity counts (`warning`, `error`) of the diagnostics.
    - `diagnostics`: one entry per problem, in the order Maude reported them.
      `severity` is `"warning"` for problems Maude recovers from, and `"error"`
      only when the file cannot be loaded at all (a single whole-file error is
      synthesized in that case). `message` is the problem text reported by
      Maude. `range.start.line` is the 1-based line of the problem; `range` is
      `null` for whole-file problems with no known location.

    Loading the file updates the interpreter's loaded modules (last load
    wins), like the Maude CLI.

    Args:
        path: Absolute path to the Maude source file to diagnose (typically `.maude`).
    """
    if not Path(path).is_file() or not os.access(path, os.R_OK):
        raise MaudeFileNotFoundError(path)
    worker_result = maude_executor.diagnostics(path)
    return _build_result(path, worker_result["ok"], worker_result["warnings"])
