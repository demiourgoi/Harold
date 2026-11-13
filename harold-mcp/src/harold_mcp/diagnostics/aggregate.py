"""Run every diagnostic provider, merge their findings and order the result.

The aggregation is deliberately all-or-nothing (MCP cannot express "error + content",
see `collect_diagnostics`): a failure of any provider fails the whole tool call, and
`DiagnosticCollectionError` names every failing provider with its cause chain, context
and traceback.

This module stays stdlib-only and provider-agnostic: it may import the error
formatter (also stdlib-only), never the Maude, heuristic or wire layers.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import partial

from harold_mcp.diagnostics.provider import (
    DiagnosticProvider,
    DiagnosticProviderError,
    DiagnosticsError,
    DiagnosticSource,
    ProviderDiagnostic,
    SourceFile,
)
from harold_mcp.errors import DEFAULT_ERROR_DETAIL_MAX_CHARS, format_error_report


@dataclass(frozen=True, slots=True)
class ProviderFailure:
    """A provider that failed during a collection run, with what it raised."""

    provider: DiagnosticSource
    error: BaseException


def _render_failure(failure: ProviderFailure, *, context: Mapping[str, object], max_chars: int) -> str:
    """Render one provider section, indented under the collection header.

    The provider name is the report's category and the wrapped failure's reason is
    its message, so the section reads `- interpreter: Maude worker timed out` instead
    of repeating the `source:` prefix the wrapped error already carries.
    """
    error = failure.error
    message = error.reason if isinstance(error, DiagnosticProviderError) else None
    report = format_error_report(
        error,
        context=context,
        max_chars=max_chars,
        category=failure.provider,
        message=message,
    )
    return "- " + report.replace("\n", "\n  ")


def _format_collection(
    failures: Sequence[ProviderFailure],
    *,
    context: Mapping[str, object],
    max_chars: int,
) -> str:
    """Render the collection report: a header plus one bounded section per failure."""
    header = f"Diagnostic collection failed: {len(failures)} provider(s) failed"
    sections = [_render_failure(failure, context=context, max_chars=max_chars) for failure in failures]
    return "\n".join([header, *sections])


class DiagnosticCollectionError(DiagnosticsError):
    """One or more diagnostic providers failed; no diagnostics are returned."""

    failures: tuple[ProviderFailure, ...]
    context: dict[str, object]

    def __init__(
        self,
        failures: Sequence[ProviderFailure],
        *,
        context: Mapping[str, object] | None = None,
        max_chars: int = DEFAULT_ERROR_DETAIL_MAX_CHARS,
    ) -> None:
        self.failures = tuple(failures)
        self.context = dict(context) if context is not None else {}
        super().__init__(_format_collection(self.failures, context=self.context, max_chars=max_chars))

    def format_report(self, max_chars: int) -> str:
        """Re-render the report with another cap (`0` = uncapped, for the server log)."""
        return _format_collection(self.failures, context=self.context, max_chars=max_chars)


def _order(
    provider_order: Mapping[DiagnosticSource, int],
    diagnostic: ProviderDiagnostic,
) -> tuple[bool, int, int, int]:
    """Order by file position, then provider, then column; whole-file problems last.

    `provider_order` (each provider's position in the registry) comes first so the
    caller can bind it with `functools.partial` and let the sort supply the diagnostic.
    A diagnostic whose source is not registered sorts after every registered provider.
    """
    return (
        diagnostic.line is None,
        diagnostic.line or 0,
        provider_order.get(diagnostic.source, len(provider_order)),
        diagnostic.column or 0,
    )


def collect_diagnostics(
    providers: Sequence[DiagnosticProvider],
    source: SourceFile,
    *,
    max_chars: int = DEFAULT_ERROR_DETAIL_MAX_CHARS,
) -> list[ProviderDiagnostic]:
    """Run every provider, then return the merged diagnostics in file order.

    Providers are attempted **in order** (the same order that breaks ties on a line),
    and a failure never short-circuits the remaining providers, so the raised error can
    name all of them. `max_chars` caps the collection error's client-visible text; the
    caller can re-render it uncapped with `DiagnosticCollectionError.format_report(0)`.

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
        raise DiagnosticCollectionError(
            failures,
            context={"path": str(source.path)},
            max_chars=max_chars,
        ) from failures[0].error
    collected.sort(key=partial(_order, provider_order))
    return collected
