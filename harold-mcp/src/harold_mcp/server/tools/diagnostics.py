"""Diagnostics tool for Maude programs.

`maude_program_diagnostics` runs every diagnostic provider over one Maude source file
and reports the merged result: the Maude interpreter load (in the dedicated worker
process) and Harold's heuristic checks on the file text (in the server process). This
module owns the MCP surface (wire models, description, annotations, tags) and the
adapter from the provider seam to the wire models.
"""

from collections.abc import Sequence

from fastmcp.dependencies import Depends
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict

from harold_mcp.diagnostics import (
    DiagnosticProvider,
    DiagnosticSource,
    FixEdit,
    FixSuggestion,
    ProviderDiagnostic,
    Severity,
    SourceFile,
    collect_diagnostics,
)
from harold_mcp.heuristic import HeuristicLinterProvider
from harold_mcp.maude import InterpreterDiagnosticProvider, MaudeExecutor, get_maude_executor
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
    """1-based column; `null` when the producer does not report columns (the Maude interpreter)."""


class MaudeRange(_ResultModel):
    """A range between two positions (LSP-style)."""

    start: MaudePosition
    """The position the problem starts at."""

    end: MaudePosition | None = None
    """Exclusive end position; `null` when the producer reports a line only or a whole-file problem."""


class MaudeTextEdit(_ResultModel):
    """One replacement in the source text (LSP-style `TextEdit`)."""

    range: MaudeRange
    """The span to replace; `end` is exclusive and always populated."""

    new_text: str
    """The text to put in its place."""


class MaudeFix(_ResultModel):
    """A deterministic correction for a diagnostic (a suggestion; the tool never applies it)."""

    description: str
    """Short description of the correction, independent of positions."""

    edits: list[MaudeTextEdit]
    """Replacements; they are disjoint, so applying them in any order is safe."""


class MaudeDiagnostic(_ResultModel):
    """A single problem found in a Maude source file."""

    severity: Severity
    """`"info"` for observations that do not affect the load, `"warning"` for problems that may be
    real, `"error"` for definite failures; the meaning depends on `source` (see the tool description)."""

    source: DiagnosticSource
    """Provider that reported it: `"interpreter"` (Maude load) or `"heuristic-linter"` (pattern checks)."""

    code: str
    """`"compiler"` for interpreter diagnostics; for `"heuristic-linter"` findings, the rule that
    fired: `non-ascii-character`, `when-guard`, `dash-comment`, `eq-in-term`,
    `non-linear-pattern`, `undeclared-identifier`, or `prelude-sort-redeclared`."""

    range: MaudeRange | None
    """Where the problem is; `null` means a whole-file problem (no known location)."""

    message: str
    """The problem text, with the explanation and the suggested fix for heuristic findings."""

    fix: MaudeFix | None
    """A deterministic correction, when one exists (never applied by this tool)."""


class MaudeDiagnosticsSummary(_ResultModel):
    """Per-severity counts of the diagnostics."""

    info: int
    """Number of `"info"` diagnostics."""

    warning: int
    """Number of `"warning"` diagnostics."""

    error: int
    """Number of `"error"` diagnostics."""


class MaudeProgramDiagnosticsResult(_ResultModel):
    """Result of diagnosing a Maude source file."""

    path: str
    """The input path, echoed back as given."""

    success: bool
    """`true` only when no diagnostic has severity `"warning"` or `"error"` (`"info"`-only results succeed)."""

    summary: MaudeDiagnosticsSummary
    """Per-severity counts of `diagnostics`."""

    diagnostics: list[MaudeDiagnostic]
    """One entry per problem, ordered by line (whole-file problems last), then source, then column."""


def _to_range(diagnostic: ProviderDiagnostic) -> MaudeRange | None:
    """Build the wire range from provider-native positions; `None` for whole-file problems."""
    if diagnostic.line is None:
        return None
    start = MaudePosition(line=diagnostic.line, column=diagnostic.column)
    end = (
        MaudePosition(line=diagnostic.line, column=diagnostic.end_column) if diagnostic.end_column is not None else None
    )
    return MaudeRange(start=start, end=end)


def _to_text_edit(edit: FixEdit) -> MaudeTextEdit:
    """Convert one provider fix edit; its range always carries both columns."""
    return MaudeTextEdit(
        range=MaudeRange(
            start=MaudePosition(line=edit.line, column=edit.start_column),
            end=MaudePosition(line=edit.line, column=edit.end_column),
        ),
        new_text=edit.new_text,
    )


def _to_fix(fix: FixSuggestion | None) -> MaudeFix | None:
    """Convert a provider fix suggestion, when the diagnostic carries one."""
    if fix is None:
        return None
    return MaudeFix(description=fix.description, edits=[_to_text_edit(edit) for edit in fix.edits])


def _to_diagnostic(diagnostic: ProviderDiagnostic) -> MaudeDiagnostic:
    """Adapt one provider diagnostic to the wire model."""
    return MaudeDiagnostic(
        severity=diagnostic.severity,
        source=diagnostic.source,
        code=diagnostic.code,
        range=_to_range(diagnostic),
        message=diagnostic.message,
        fix=_to_fix(diagnostic.fix),
    )


def _build_result(path: str, diagnostics: Sequence[ProviderDiagnostic]) -> MaudeProgramDiagnosticsResult:
    """Map the merged provider diagnostics onto the result model."""
    return MaudeProgramDiagnosticsResult(
        path=path,
        success=all(diagnostic.severity == "info" for diagnostic in diagnostics),
        summary=MaudeDiagnosticsSummary(
            info=sum(1 for diagnostic in diagnostics if diagnostic.severity == "info"),
            warning=sum(1 for diagnostic in diagnostics if diagnostic.severity == "warning"),
            error=sum(1 for diagnostic in diagnostics if diagnostic.severity == "error"),
        ),
        diagnostics=[_to_diagnostic(diagnostic) for diagnostic in diagnostics],
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
    """Diagnose a Maude source file by loading it into the Maude interpreter and running
    Harold's heuristic checks on its text.

    Use this tool to check whether a Maude program is well formed, and to get a list of
    issues to fix when it is not. Diagnostics come from two sources, identified by the
    `source` field:

    - `"interpreter"`: the Maude interpreter load. `severity` is `"warning"` for problems
      Maude recovers from, and `"error"` for the single whole-file error synthesized when
      the file cannot be loaded at all. `range.start.line` is the 1-based line Maude
      reports; `column` is `null`, because Maude reports no columns.
    - `"heuristic-linter"`: pattern-based checks for common mistakes, with `code` naming
      the rule (`non-ascii-character`, `when-guard`, `dash-comment`, `eq-in-term`,
      `non-linear-pattern`, `undeclared-identifier`, `prelude-sort-redeclared`). They are
      heuristics and may be false positives, so `severity` is `"warning"` for suspicious
      code and `"info"` for observations that do not affect the load (e.g. a sort that
      shadows a prelude sort, or non-ASCII punctuation Maude accepts). Their `range`
      includes exact 1-based columns.

    `success` is `true` only when no diagnostic has severity `"warning"` or `"error"`;
    `"info"`-only results still count as success. `summary` counts the diagnostics per
    severity, and `diagnostics` lists them in file order (whole-file problems last).

    Some diagnostics carry a `fix`: a deterministic correction (for example, replacing
    typographic punctuation with ASCII) with a short `description` and applyable `edits`
    (`range` plus `new_text`, `range.end` exclusive). This tool never modifies the file —
    applying the edits is up to the client.

    Loading the file updates the interpreter's loaded modules (last load wins), like the
    Maude CLI.

    Args:
        path: Absolute path to the Maude source file to diagnose (typically `.maude`).
    """
    source = SourceFile.from_path(path)  # raises SourceFileNotFoundError
    providers: tuple[DiagnosticProvider, ...] = (
        InterpreterDiagnosticProvider(maude_executor),
        HeuristicLinterProvider(),
    )
    diagnostics = collect_diagnostics(providers, source)  # raises DiagnosticCollectionError
    return _build_result(path, diagnostics)
