"""Run every diagnostic provider, merge their findings and order the result.

The aggregation is deliberately all-or-nothing (MCP cannot express "error + content",
see `collect_diagnostics`): a failure of any provider fails the whole tool call, and
`DiagnosticCollectionError` names every failing provider with its cause.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from harold_mcp.diagnostics.provider import (
    DiagnosticProvider,
    DiagnosticProviderError,
    DiagnosticsError,
    DiagnosticSource,
    ProviderDiagnostic,
    SourceFile,
)


@dataclass(frozen=True, slots=True)
class ProviderFailure:
    """A provider that failed during a collection run, with what it raised."""

    provider: DiagnosticSource
    error: BaseException


class DiagnosticCollectionError(DiagnosticsError):
    """One or more diagnostic providers failed; no diagnostics are returned."""

    failures: tuple[ProviderFailure, ...]

    def __init__(self, failures: Sequence[ProviderFailure]) -> None:
        self.failures = tuple(failures)
        super().__init__("Diagnostics failed: " + "; ".join(_describe(failure) for failure in self.failures))


def _describe(failure: ProviderFailure) -> str:
    """Describe one failure: `interpreter (Maude worker crashed)`.

    An unwrapped provider bug (not a `DiagnosticProviderError`) keeps its type name, so
    the message says what actually broke.
    """
    error = failure.error
    reason = error.reason if isinstance(error, DiagnosticProviderError) else f"{type(error).__name__}: {error}"
    return f"{failure.provider} ({reason})"


def collect_diagnostics(
    providers: Sequence[DiagnosticProvider],
    source: SourceFile,
) -> list[ProviderDiagnostic]:
    """Run every provider, then return the merged diagnostics in file order.

    Providers are attempted **in order** (the same order that breaks ties on a line),
    and a failure never short-circuits the remaining providers, so the raised error can
    name all of them.

    Raises:
        DiagnosticCollectionError: at least one provider failed. The successful
            providers' diagnostics are discarded, and the error chains the first
            failure (`__cause__`).
    """
    collected: list[ProviderDiagnostic] = []
    failures: list[ProviderFailure] = []
    provider_order = {provider.name: index for index, provider in enumerate(providers)}
    for provider in providers:
        try:
            collected.extend(provider.diagnose(source))
        except Exception as exc:
            failures.append(ProviderFailure(provider=provider.name, error=exc))
    if failures:
        # Deliberately no partial result: MCP reports tool errors only through
        # `isError`, which clients read as a failed call, so returning the
        # successful providers' diagnostics alongside the error is not
        # expressible (MCP spec 2025-06-18; FastMCP raises on tool errors).
        raise DiagnosticCollectionError(failures) from failures[0].error
    fallback_index = len(provider_order)

    def order(diagnostic: ProviderDiagnostic) -> tuple[bool, int, int, int]:
        """Order by file position, then provider, then column; whole-file problems last."""
        return (
            diagnostic.line is None,
            diagnostic.line or 0,
            provider_order.get(diagnostic.source, fallback_index),
            diagnostic.column or 0,
        )

    collected.sort(key=order)
    return collected
