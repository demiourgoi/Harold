"""Unit tests for the `maude_program_diagnostics` tool (mocked executor)."""

import os
from pathlib import Path

import pytest

from harold_mcp.maude import MaudeFileNotFoundError
from harold_mcp.maude.worker import LoadDiagnosticsResult
from harold_mcp.server.tools.diagnostics import (
    MaudeProgramDiagnosticsResult,
    maude_program_diagnostics,
)


class FakeMaudeExecutor:
    """Fake executor returning a scripted worker result."""

    def __init__(self, result: LoadDiagnosticsResult) -> None:
        self._result = result
        self.calls: list[str] = []

    def diagnostics(self, path: str) -> LoadDiagnosticsResult:
        self.calls.append(path)
        return self._result


def _run(path: str, result: LoadDiagnosticsResult) -> MaudeProgramDiagnosticsResult:
    return maude_program_diagnostics(path, maude_executor=FakeMaudeExecutor(result))


def test_clean_program_returns_success(tmp_path: Path) -> None:
    path = tmp_path / "hello.maude"
    _ = path.write_text("fmod HELLO-WORLD is endfm\n")
    fake = FakeMaudeExecutor({"ok": True, "warnings": []})
    result = maude_program_diagnostics(str(path), maude_executor=fake)

    assert result.path == str(path)
    assert result.success is True
    assert result.summary.warning == 0
    assert result.summary.error == 0
    assert result.diagnostics == []
    assert fake.calls == [str(path)]  # the path is passed through unchanged


def test_recoverable_warning_marks_failure(tmp_path: Path) -> None:
    path = tmp_path / "broken.maude"
    _ = path.write_text("fmod X\nendfm\n")
    result = _run(str(path), {"ok": True, "warnings": [{"line": 2, "message": "missing is keyword."}]})

    assert result.success is False
    assert result.summary.warning == 1
    assert result.summary.error == 0
    assert len(result.diagnostics) == 1
    diagnostic = result.diagnostics[0]
    assert diagnostic.severity == "warning"
    assert diagnostic.range is not None
    assert diagnostic.range.start.line == 2
    assert diagnostic.range.start.column is None
    assert diagnostic.range.end is None
    assert diagnostic.message == "missing is keyword."


def test_hard_failure_adds_synthesized_error(tmp_path: Path) -> None:
    path = tmp_path / "broken.maude"
    _ = path.write_text("garbage\n")
    result = _run(
        str(path),
        {"ok": False, "warnings": [{"line": 1, "message": "skipped unexpected token: fmo"}]},
    )

    assert result.success is False
    assert result.summary.warning == 1
    assert result.summary.error == 1
    assert len(result.diagnostics) == 2
    error = result.diagnostics[1]
    assert error.severity == "error"
    assert error.range is None  # whole-file problem: no line number available
    assert error.message == "Failed to load Maude program: unrecoverable parse error."


def test_hard_failure_without_warnings(tmp_path: Path) -> None:
    path = tmp_path / "binary.maude"
    _ = path.write_bytes(b"\x00\x01\x02")
    result = _run(str(path), {"ok": False, "warnings": []})

    assert result.success is False
    assert result.summary.error == 1
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].severity == "error"
    assert result.diagnostics[0].range is None


def test_warning_without_line_uses_whole_file_range(tmp_path: Path) -> None:
    path = tmp_path / "broken.maude"
    _ = path.write_text("x\n")
    result = _run(str(path), {"ok": True, "warnings": [{"line": None, "message": "something file-wide"}]})

    assert result.success is False
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].range is None


def test_missing_file_raises_before_touching_worker(tmp_path: Path) -> None:
    fake = FakeMaudeExecutor({"ok": True, "warnings": []})
    missing = tmp_path / "does-not-exist.maude"

    with pytest.raises(MaudeFileNotFoundError, match="does-not-exist"):
        maude_program_diagnostics(str(missing), maude_executor=fake)

    assert fake.calls == []  # the pre-check fires before any worker call


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses permission checks")
def test_unreadable_file_raises(tmp_path: Path) -> None:
    fake = FakeMaudeExecutor({"ok": True, "warnings": []})
    path = tmp_path / "unreadable.maude"
    _ = path.write_text("x\n")
    path.chmod(0o000)

    with pytest.raises(MaudeFileNotFoundError, match="unreadable"):
        _ = maude_program_diagnostics(str(path), maude_executor=fake)

    assert fake.calls == []
