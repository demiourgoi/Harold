"""Unit tests for diagnostic aggregation (`harold_mcp.diagnostics.aggregate`)."""

from collections.abc import Sequence
from pathlib import Path

import pytest

from harold_mcp.diagnostics import (
    DiagnosticCollectionError,
    DiagnosticProviderError,
    DiagnosticsError,
    ProviderDiagnostic,
    SourceFile,
    collect_diagnostics,
)
from harold_mcp.diagnostics.aggregate import ProviderFailure
from harold_mcp.diagnostics.provider import DiagnosticSource
from harold_mcp.maude import MaudeError, MaudeWorkerCrashedError


class FakeProvider:
    """Provider returning scripted diagnostics, or raising a scripted error."""

    def __init__(
        self,
        name: DiagnosticSource,
        diagnostics: Sequence[ProviderDiagnostic] = (),
        error: Exception | None = None,
    ) -> None:
        self.name = name
        self._diagnostics = list(diagnostics)
        self._error = error
        self.calls: list[SourceFile] = []

    def diagnose(self, source: SourceFile) -> list[ProviderDiagnostic]:
        self.calls.append(source)
        if self._error is not None:
            raise self._error
        return list(self._diagnostics)


def _diagnostic(source: DiagnosticSource, line: int | None, column: int | None = None) -> ProviderDiagnostic:
    return ProviderDiagnostic(
        source=source,
        severity="warning",
        code="compiler" if source == "interpreter" else "when-guard",
        message=f"{source} finding",
        line=line,
        column=column,
    )


def _source(tmp_path: Path) -> SourceFile:
    path = tmp_path / "program.maude"
    _ = path.write_text("fmod X is endfm\n")
    return SourceFile.from_path(path)


def _interpreter_failure() -> DiagnosticProviderError:
    """Build the error the interpreter provider raises on a worker crash, cause included."""
    crash = MaudeWorkerCrashedError()

    def raise_wrapped() -> None:
        raise DiagnosticProviderError("interpreter", crash.reason) from crash

    with pytest.raises(DiagnosticProviderError) as exc_info:
        raise_wrapped()
    return exc_info.value


def test_merges_provenance_and_orders_by_line_then_provider_then_column(tmp_path: Path) -> None:
    interpreter = FakeProvider(
        "interpreter",
        [_diagnostic("interpreter", 2), _diagnostic("interpreter", None), _diagnostic("interpreter", 1)],
    )
    heuristic = FakeProvider(
        "heuristic-linter",
        [
            _diagnostic("heuristic-linter", 2, 5),
            _diagnostic("heuristic-linter", 2, 1),
            _diagnostic("heuristic-linter", 1, 3),
        ],
    )

    merged = collect_diagnostics([interpreter, heuristic], _source(tmp_path))

    assert [(d.source, d.line, d.column) for d in merged] == [
        ("interpreter", 1, None),  # file order first
        ("heuristic-linter", 1, 3),  # same line: provider order, then column
        ("interpreter", 2, None),  # Maude's line-only position stays with its provider
        ("heuristic-linter", 2, 1),
        ("heuristic-linter", 2, 5),
        ("interpreter", None, None),  # whole-file problems last
    ]


def test_same_position_keeps_registry_order(tmp_path: Path) -> None:
    """The sort is stable, so diagnostics sharing a key keep rule/registry order."""
    heuristic = FakeProvider(
        "heuristic-linter",
        [
            ProviderDiagnostic(
                source="heuristic-linter",
                severity="warning",
                code=code,
                message=code,
                line=3,
                column=1,
            )
            for code in ("when-guard", "dash-comment", "eq-in-term")
        ],
    )

    merged = collect_diagnostics([heuristic], _source(tmp_path))

    assert [d.code for d in merged] == ["when-guard", "dash-comment", "eq-in-term"]


def test_every_provider_receives_the_source(tmp_path: Path) -> None:
    source = _source(tmp_path)
    interpreter = FakeProvider("interpreter")
    heuristic = FakeProvider("heuristic-linter")

    assert collect_diagnostics([interpreter, heuristic], source) == []
    assert interpreter.calls == [source]
    assert heuristic.calls == [source]


def test_no_diagnostics_is_not_a_failure(tmp_path: Path) -> None:
    assert collect_diagnostics([FakeProvider("interpreter")], _source(tmp_path)) == []


def test_one_failing_provider_fails_the_call_without_partial_results(tmp_path: Path) -> None:
    provider_error = _interpreter_failure()
    interpreter = FakeProvider("interpreter", error=provider_error)
    heuristic = FakeProvider("heuristic-linter", [_diagnostic("heuristic-linter", 1, 1)])

    with pytest.raises(DiagnosticCollectionError) as exc_info:
        _ = collect_diagnostics([interpreter, heuristic], _source(tmp_path))

    error = exc_info.value
    assert str(error) == "Diagnostics failed: interpreter (Maude worker crashed)"
    assert error.failures == (ProviderFailure(provider="interpreter", error=provider_error),)
    assert error.__cause__ is provider_error
    assert isinstance(error.__cause__.__cause__, MaudeWorkerCrashedError)
    assert isinstance(error, DiagnosticsError)
    assert not isinstance(error, MaudeError)


def test_remaining_providers_are_still_attempted_after_a_failure(tmp_path: Path) -> None:
    """LP4: a failure never short-circuits the run, so the error can name every failure."""
    interpreter = FakeProvider("interpreter", error=_interpreter_failure())
    heuristic = FakeProvider("heuristic-linter", error=ValueError("boom"))

    with pytest.raises(DiagnosticCollectionError) as exc_info:
        _ = collect_diagnostics([interpreter, heuristic], _source(tmp_path))

    assert heuristic.calls  # it ran despite the earlier failure
    assert str(exc_info.value) == (
        "Diagnostics failed: interpreter (Maude worker crashed); heuristic-linter (ValueError: boom)"
    )


def test_unexpected_provider_bug_is_reported_with_its_type(tmp_path: Path) -> None:
    buggy = FakeProvider("heuristic-linter", error=ValueError("rule exploded"))

    with pytest.raises(DiagnosticCollectionError) as exc_info:
        _ = collect_diagnostics([FakeProvider("interpreter"), buggy], _source(tmp_path))

    assert str(exc_info.value) == "Diagnostics failed: heuristic-linter (ValueError: rule exploded)"
    assert isinstance(exc_info.value.__cause__, ValueError)
