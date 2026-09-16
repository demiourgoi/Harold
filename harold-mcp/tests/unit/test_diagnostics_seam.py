"""Unit tests for the diagnostics seam (`harold_mcp.diagnostics.provider`)."""

import os
from pathlib import Path

import pytest

from harold_mcp.diagnostics import (
    DiagnosticCollectionError,
    DiagnosticProviderError,
    DiagnosticsError,
    FixEdit,
    FixSuggestion,
    ProviderDiagnostic,
    SourceFile,
    SourceFileNotFoundError,
)
from harold_mcp.maude import MaudeError


def _diagnostic(**overrides: object) -> ProviderDiagnostic:
    fields: dict[str, object] = {
        "source": "heuristic-linter",
        "severity": "warning",
        "code": "when-guard",
        "message": "`when` is not Maude syntax",
    }
    fields.update(overrides)
    return ProviderDiagnostic(**fields)  # type: ignore[arg-type]


def test_diagnostics_errors_are_not_maude_errors() -> None:
    """The diagnostics subsystem has its own vocabulary, independent of the interpreter's."""
    assert not issubclass(DiagnosticsError, MaudeError)
    assert issubclass(SourceFileNotFoundError, DiagnosticsError)
    assert issubclass(DiagnosticProviderError, DiagnosticsError)
    assert issubclass(DiagnosticCollectionError, DiagnosticsError)
    assert not issubclass(DiagnosticCollectionError, MaudeError)


def test_source_file_not_found_reports_the_path(tmp_path: Path) -> None:
    error = SourceFileNotFoundError(tmp_path / "nope.maude")

    assert error.path == tmp_path / "nope.maude"
    assert "nope.maude" in str(error)
    assert "not found or unreadable" in str(error)


def test_diagnostic_provider_error_formats_source_and_reason() -> None:
    error = DiagnosticProviderError("interpreter", "Maude worker crashed")

    assert error.source == "interpreter"
    assert error.reason == "Maude worker crashed"
    assert str(error) == "interpreter: Maude worker crashed"


def test_position_invariants_reject_inconsistent_positions() -> None:
    with pytest.raises(ValueError, match="without a line cannot carry a column"):
        _ = _diagnostic(column=3)
    with pytest.raises(ValueError, match="end_column requires column"):
        _ = _diagnostic(line=2, end_column=4)
    with pytest.raises(ValueError, match="end_column requires column"):
        _ = _diagnostic(end_column=4)
    with pytest.raises(ValueError, match="column must be 1-based"):
        _ = _diagnostic(line=2, column=0)
    with pytest.raises(ValueError, match="end_column must be 1-based"):
        _ = _diagnostic(line=2, column=1, end_column=0)

    # Valid shapes: whole-file (no positions), line-only, and a full span.
    assert _diagnostic().line is None
    assert _diagnostic(line=2).column is None
    assert _diagnostic(line=2, column=3, end_column=4).end_column == 4


def test_fix_values_are_frozen_and_hold_their_edits() -> None:
    edit = FixEdit(line=2, start_column=8, end_column=9, new_text="'")
    fix = FixSuggestion(description="Replace the typographic apostrophe.", edits=(edit,))

    assert fix.edits == (edit,)
    assert edit.end_column == edit.start_column + 1  # exclusive end
    with pytest.raises(AttributeError):  # frozen
        edit.new_text = "x"  # type: ignore[misc]


def test_source_file_from_path_reads_a_regular_file(tmp_path: Path) -> None:
    path = tmp_path / "hello.maude"
    _ = path.write_text("fmod HELLO is endfm\n")

    source = SourceFile.from_path(path)

    assert source.path == Path(path)
    assert source.text == "fmod HELLO is endfm\n"


def test_source_file_from_path_accepts_a_string(tmp_path: Path) -> None:
    path = tmp_path / "hello.maude"
    _ = path.write_text("fmod HELLO is endfm\n")

    source = SourceFile.from_path(str(path))

    assert source.path == path


def test_source_file_from_path_rejects_a_missing_path(tmp_path: Path) -> None:
    with pytest.raises(SourceFileNotFoundError, match="does-not-exist"):
        _ = SourceFile.from_path(tmp_path / "does-not-exist.maude")


def test_source_file_from_path_rejects_a_directory(tmp_path: Path) -> None:
    with pytest.raises(SourceFileNotFoundError):
        _ = SourceFile.from_path(tmp_path)


def test_source_file_from_path_rejects_a_non_regular_file(tmp_path: Path) -> None:
    fifo = tmp_path / "pipe.maude"
    os.mkfifo(fifo)

    with pytest.raises(SourceFileNotFoundError):
        _ = SourceFile.from_path(fifo)


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses permission checks")
def test_source_file_from_path_rejects_an_unreadable_file(tmp_path: Path) -> None:
    path = tmp_path / "unreadable.maude"
    _ = path.write_text("fmod X is endfm\n")
    path.chmod(0o000)

    with pytest.raises(SourceFileNotFoundError):
        _ = SourceFile.from_path(path)


def test_source_file_from_path_decodes_undecodable_bytes_lossily(tmp_path: Path) -> None:
    path = tmp_path / "binary.maude"
    _ = path.write_bytes(b"\xff\xfe caf\xe9 \x00")

    source = SourceFile.from_path(path)

    assert "\ufffd" in source.text  # the replacement character, not an exception


def test_source_file_from_path_normalizes_newlines(tmp_path: Path) -> None:
    path = tmp_path / "crlf.maude"
    _ = path.write_bytes(b"fmod X is\r\nendfm\r\n")

    source = SourceFile.from_path(path)

    assert source.text == "fmod X is\nendfm\n"
    assert source.text.split("\n")[:2] == ["fmod X is", "endfm"]
