"""Unit tests for the `maude_program_diagnostics` tool (mocked executor)."""

import os
from pathlib import Path

import pytest

from harold_mcp.diagnostics import (
    DiagnosticCollectionError,
    DiagnosticProviderError,
    FixEdit,
    FixSuggestion,
    ProviderDiagnostic,
    SourceFileNotFoundError,
)
from harold_mcp.maude import MaudeWorkerCrashedError
from harold_mcp.maude.worker import LoadDiagnosticsResult
from harold_mcp.server.tools.diagnostics import (
    MaudeFix,
    MaudePosition,
    MaudeProgramDiagnosticsResult,
    MaudeRange,
    MaudeTextEdit,
    _build_result,
    maude_program_diagnostics,
)

APOSTROPHE = "\u2019"


class FakeMaudeExecutor:
    """Fake executor returning a scripted worker result, or raising a scripted error."""

    def __init__(self, result: LoadDiagnosticsResult | None = None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error
        self.calls: list[str] = []

    def diagnostics(self, path: str) -> LoadDiagnosticsResult:
        self.calls.append(path)
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


def _write(path: Path, text: str = "fmod X is endfm\n") -> str:
    _ = path.write_text(text)
    return str(path)


def _run(path: str, result: LoadDiagnosticsResult) -> MaudeProgramDiagnosticsResult:
    return maude_program_diagnostics(path, maude_executor=FakeMaudeExecutor(result))


def test_clean_program_returns_success(tmp_path: Path) -> None:
    path = tmp_path / "hello.maude"
    content = _write(path)
    fake = FakeMaudeExecutor({"ok": True, "warnings": []})
    result = maude_program_diagnostics(content, maude_executor=fake)

    assert result.path == content
    assert result.success is True
    assert result.summary.info == 0
    assert result.summary.warning == 0
    assert result.summary.error == 0
    assert result.diagnostics == []
    assert fake.calls == [content]  # the path is passed through unchanged


def test_recoverable_warning_marks_failure(tmp_path: Path) -> None:
    path = tmp_path / "broken.maude"
    content = _write(path, "fmod X\nendfm\n")
    result = _run(content, {"ok": True, "warnings": [{"line": 2, "message": "missing is keyword."}]})

    assert result.success is False
    assert result.summary.info == 0
    assert result.summary.warning == 1
    assert result.summary.error == 0
    assert len(result.diagnostics) == 1
    diagnostic = result.diagnostics[0]
    assert diagnostic.severity == "warning"
    assert diagnostic.source == "interpreter"
    assert diagnostic.code == "compiler"
    assert diagnostic.range is not None
    assert diagnostic.range.start.line == 2
    assert diagnostic.range.start.column is None
    assert diagnostic.range.end is None
    assert diagnostic.message == "missing is keyword."
    assert diagnostic.fix is None


def test_hard_failure_adds_synthesized_error(tmp_path: Path) -> None:
    path = tmp_path / "broken.maude"
    content = _write(path, "garbage\n")
    result = _run(
        content,
        {"ok": False, "warnings": [{"line": 1, "message": "skipped unexpected token: fmo"}]},
    )

    assert result.success is False
    assert result.summary.warning == 1
    assert result.summary.error == 1
    assert len(result.diagnostics) == 2
    error = result.diagnostics[1]
    assert error.severity == "error"
    assert error.source == "interpreter"
    assert error.code == "compiler"
    assert error.range is None  # whole-file problem: no line number available
    assert error.message == "Failed to load Maude program: unrecoverable parse error."


def test_hard_failure_without_warnings(tmp_path: Path) -> None:
    path = tmp_path / "binary.maude"
    _ = path.write_bytes(b"\x00\x01\x02")
    result = _run(str(path), {"ok": False, "warnings": []})

    assert result.success is False
    assert result.summary.info == 0
    assert result.summary.error == 1
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].severity == "error"
    assert result.diagnostics[0].range is None


def test_warning_without_line_uses_whole_file_range(tmp_path: Path) -> None:
    path = tmp_path / "broken.maude"
    content = _write(path, "x\n")
    result = _run(content, {"ok": True, "warnings": [{"line": None, "message": "something file-wide"}]})

    assert result.success is False
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].range is None


def test_info_only_result_succeeds() -> None:
    """LP8: observations that do not affect the load are successful."""
    result = _build_result(
        "program.maude",
        [
            ProviderDiagnostic(
                source="heuristic-linter",
                severity="info",
                code="non-ascii-character",
                message="non-ASCII character",
                line=2,
                column=8,
                end_column=9,
            )
        ],
    )

    assert result.success is True
    assert result.summary.info == 1
    assert result.summary.warning == 0
    assert result.summary.error == 0


def test_adapter_maps_columns_and_fixes() -> None:
    """The span/fix machinery is exercised with synthetic provider diagnostics."""
    fix = FixSuggestion(
        description="Replace the typographic apostrophe.",
        edits=(FixEdit(line=3, start_column=8, end_column=9, new_text="'"),),
    )
    result = _build_result(
        "program.maude",
        [
            ProviderDiagnostic(
                source="heuristic-linter",
                severity="info",
                code="non-ascii-character",
                message="Non-ASCII character",
                line=3,
                column=8,
                end_column=9,
                fix=fix,
            )
        ],
    )

    diagnostic = result.diagnostics[0]
    assert diagnostic.range == MaudeRange(start=MaudePosition(line=3, column=8), end=MaudePosition(line=3, column=9))
    assert diagnostic.fix == MaudeFix(
        description="Replace the typographic apostrophe.",
        edits=[
            MaudeTextEdit(
                range=MaudeRange(start=MaudePosition(line=3, column=8), end=MaudePosition(line=3, column=9)),
                new_text="'",
            )
        ],
    )


def test_adapter_keeps_line_only_diagnostics_unchanged() -> None:
    """A line-only diagnostic keeps `column=None` and acquires no `end`."""
    result = _build_result(
        "program.maude",
        [
            ProviderDiagnostic(
                source="heuristic-linter",
                severity="warning",
                code="when-guard",
                message="`when` is not Maude syntax",
                line=4,
            )
        ],
    )

    diagnostic = result.diagnostics[0]
    assert diagnostic.range == MaudeRange(start=MaudePosition(line=4, column=None))
    assert diagnostic.fix is None


def test_missing_file_raises_before_touching_the_provider(tmp_path: Path) -> None:
    fake = FakeMaudeExecutor({"ok": True, "warnings": []})
    missing = tmp_path / "does-not-exist.maude"

    with pytest.raises(SourceFileNotFoundError, match="does-not-exist"):
        _ = maude_program_diagnostics(str(missing), maude_executor=fake)

    assert fake.calls == []  # the pre-check fires before any provider call


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses permission checks")
def test_unreadable_file_raises_before_touching_the_provider(tmp_path: Path) -> None:
    fake = FakeMaudeExecutor({"ok": True, "warnings": []})
    path = tmp_path / "unreadable.maude"
    _ = path.write_text("x\n")
    path.chmod(0o000)

    with pytest.raises(SourceFileNotFoundError, match="unreadable"):
        _ = maude_program_diagnostics(str(path), maude_executor=fake)

    assert fake.calls == []


def test_provider_failure_propagates_as_a_collection_error(tmp_path: Path) -> None:
    path = tmp_path / "hello.maude"
    content = _write(path)
    fake = FakeMaudeExecutor(error=MaudeWorkerCrashedError())

    with pytest.raises(DiagnosticCollectionError) as exc_info:
        _ = maude_program_diagnostics(content, maude_executor=fake)

    assert str(exc_info.value) == "Diagnostics failed: interpreter (Maude worker crashed)"
    provider_error = exc_info.value.__cause__
    assert isinstance(provider_error, DiagnosticProviderError)
    assert isinstance(provider_error.__cause__, MaudeWorkerCrashedError)


def test_heuristic_finding_carries_columns_and_an_applyable_fix(tmp_path: Path) -> None:
    """Rule 1 through the tool: an `info` finding whose span has columns and a 1-char fix."""
    path = tmp_path / "nonascii.maude"
    content = _write(path, f"fmod T is\n    op L{APOSTROPHE} : -> Nat .\nendfm\n")
    before = path.read_bytes()

    result = maude_program_diagnostics(content, maude_executor=FakeMaudeExecutor({"ok": True, "warnings": []}))

    assert result.success is True  # info only: the load itself is fine
    assert result.summary.info == 1
    assert result.summary.warning == 0
    diagnostic = result.diagnostics[0]
    assert diagnostic.source == "heuristic-linter"
    assert diagnostic.code == "non-ascii-character"
    assert diagnostic.severity == "info"
    assert diagnostic.range == MaudeRange(start=MaudePosition(line=2, column=9), end=MaudePosition(line=2, column=10))
    assert diagnostic.fix is not None
    assert diagnostic.fix.edits == [
        MaudeTextEdit(
            range=MaudeRange(start=MaudePosition(line=2, column=9), end=MaudePosition(line=2, column=10)),
            new_text="'",
        )
    ]
    assert path.read_bytes() == before  # report-only: the file is untouched


def test_same_line_orders_interpreter_before_heuristic(tmp_path: Path) -> None:
    path = tmp_path / "mixed.maude"
    content = _write(path, f"fmod T is\n    op L{APOSTROPHE} : -> Nat .\nendfm\n")
    fake = FakeMaudeExecutor({"ok": True, "warnings": [{"line": 2, "message": "some warning."}]})

    result = maude_program_diagnostics(content, maude_executor=fake)

    assert result.success is False
    assert [(d.source, d.range.start.column if d.range else None) for d in result.diagnostics] == [
        ("interpreter", None),
        ("heuristic-linter", 9),
    ]
