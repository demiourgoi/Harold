"""The diagnostics subsystem: provider seam, error vocabulary and aggregation.

`harold_mcp.diagnostics` is provider-agnostic and pure (stdlib only): it defines what a
diagnostic is, how providers are named, how their failures are reported and how their
findings are merged and ordered. Concrete providers live with the capability they
belong to — `harold_mcp.maude.provider` (interpreter) and
`harold_mcp.heuristic.provider` (heuristic linter) — and the MCP tool wires them
together and adapts the merged result to the wire models.
"""

from harold_mcp.diagnostics.aggregate import (
    DiagnosticCollectionError,
    ProviderFailure,
    collect_diagnostics,
)
from harold_mcp.diagnostics.provider import (
    DiagnosticProvider,
    DiagnosticProviderError,
    DiagnosticsError,
    DiagnosticSource,
    FixEdit,
    FixSuggestion,
    ProviderDiagnostic,
    Severity,
    SourceFile,
    SourceFileNotFoundError,
)

__all__ = [
    "DiagnosticCollectionError",
    "DiagnosticProvider",
    "DiagnosticProviderError",
    "DiagnosticSource",
    "DiagnosticsError",
    "FixEdit",
    "FixSuggestion",
    "ProviderDiagnostic",
    "ProviderFailure",
    "Severity",
    "SourceFile",
    "SourceFileNotFoundError",
    "collect_diagnostics",
]
