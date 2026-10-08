"""Unit tests for the interpreter diagnostics provider (mocked executor)."""

from pathlib import Path

import pytest

from harold_mcp.diagnostics import DiagnosticProviderError, SourceFile
from harold_mcp.maude import MaudeWorkerCrashedError, MaudeWorkerTimeoutError
from harold_mcp.maude.provider import _HARD_FAILURE_MESSAGE, InterpreterDiagnosticProvider
from harold_mcp.maude.worker import LoadDiagnosticsResult


class FakeMaudeExecutor:
    """Fake executor returning a scripted worker result or raising a scripted error."""

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


def _source(tmp_path: Path) -> SourceFile:
    path = tmp_path / "program.maude"
    _ = path.write_text("fmod X\nendfm\n")
    return SourceFile.from_path(path)


def test_warnings_map_to_line_only_warning_diagnostics(tmp_path: Path) -> None:
    source = _source(tmp_path)
    fake = FakeMaudeExecutor({
        "ok": True,
        "warnings": [{"file": "program.maude", "line": 2, "message": "missing is keyword."}],
    })

    diagnostics = InterpreterDiagnosticProvider(fake).diagnose(source)

    assert len(diagnostics) == 1
    diagnostic = diagnostics[0]
    assert diagnostic.source == "interpreter"
    assert diagnostic.severity == "warning"
    assert diagnostic.code == "compiler"
    assert diagnostic.message == "missing is keyword."
    assert diagnostic.line == 2
    assert diagnostic.column is None  # Maude reports no columns
    assert diagnostic.end_column is None
    assert diagnostic.fix is None
    assert fake.calls == [str(source.path)]  # the seam speaks `Path`, the worker takes a string


def test_line_less_warning_has_no_positions(tmp_path: Path) -> None:
    source = _source(tmp_path)
    fake = FakeMaudeExecutor({
        "ok": True,
        "warnings": [{"file": "program.maude", "line": None, "message": "something file-wide"}],
    })

    diagnostics = InterpreterDiagnosticProvider(fake).diagnose(source)

    assert len(diagnostics) == 1
    assert diagnostics[0].line is None
    assert diagnostics[0].column is None


def test_standard_input_warning_is_attributed_to_the_diagnosed_file(tmp_path: Path) -> None:
    """Some first-line warnings are attributed to `<standard input>`; they belong here."""
    source = _source(tmp_path)
    fake = FakeMaudeExecutor({
        "ok": True,
        "warnings": [{"file": "<standard input>", "line": 1, "message": "skipped unexpected token: fmo"}],
    })

    diagnostics = InterpreterDiagnosticProvider(fake).diagnose(source)

    assert len(diagnostics) == 1
    assert diagnostics[0].line == 1
    assert diagnostics[0].message == "skipped unexpected token: fmo"


def test_dependency_warning_becomes_a_whole_file_diagnostic(tmp_path: Path) -> None:
    """A warning Maude attributed to another file names that file; no fabricated position."""
    source = _source(tmp_path)
    fake = FakeMaudeExecutor({
        "ok": True,
        "warnings": [{"file": "dep.maude", "line": 4, "message": "unexpected end of tokens."}],
    })

    diagnostics = InterpreterDiagnosticProvider(fake).diagnose(source)

    assert len(diagnostics) == 1
    diagnostic = diagnostics[0]
    assert diagnostic.line is None
    assert diagnostic.column is None
    assert diagnostic.severity == "warning"
    assert diagnostic.message == (
        'In "dep.maude", line 4: unexpected end of tokens. '
        'Run maude_program_diagnostics on "dep.maude" (resolved relative to the diagnosed file\'s directory) for details.'
    )


def test_dependency_warning_without_line_omits_the_line(tmp_path: Path) -> None:
    source = _source(tmp_path)
    fake = FakeMaudeExecutor({
        "ok": True,
        "warnings": [{"file": "dep.maude", "line": None, "message": "something file-wide"}],
    })

    diagnostics = InterpreterDiagnosticProvider(fake).diagnose(source)

    assert len(diagnostics) == 1
    assert diagnostics[0].line is None
    assert diagnostics[0].message.startswith('In "dep.maude": something file-wide. Run')


def test_hard_failure_adds_a_synthesized_whole_file_error(tmp_path: Path) -> None:
    source = _source(tmp_path)
    fake = FakeMaudeExecutor({
        "ok": False,
        "warnings": [{"file": "program.maude", "line": 1, "message": "skipped unexpected token: fmo"}],
    })

    diagnostics = InterpreterDiagnosticProvider(fake).diagnose(source)

    assert [diagnostic.severity for diagnostic in diagnostics] == ["warning", "error"]
    error = diagnostics[1]
    assert error.source == "interpreter"
    assert error.code == "compiler"
    assert error.message == _HARD_FAILURE_MESSAGE
    assert error.line is None  # whole-file problem
    assert error.fix is None


def test_hard_failure_without_warnings_reports_one_error(tmp_path: Path) -> None:
    source = _source(tmp_path)
    fake = FakeMaudeExecutor({"ok": False, "warnings": []})

    diagnostics = InterpreterDiagnosticProvider(fake).diagnose(source)

    assert len(diagnostics) == 1
    assert diagnostics[0].severity == "error"


def test_worker_crash_becomes_a_provider_error_with_the_cause_chained(tmp_path: Path) -> None:
    source = _source(tmp_path)
    crash = MaudeWorkerCrashedError()
    provider = InterpreterDiagnosticProvider(FakeMaudeExecutor(error=crash))

    with pytest.raises(DiagnosticProviderError) as exc_info:
        _ = provider.diagnose(source)

    error = exc_info.value
    assert error.source == "interpreter"
    assert error.reason == "Maude worker crashed"
    assert str(error) == "interpreter: Maude worker crashed"
    assert error.__cause__ is crash  # the Maude vocabulary stays visible for logs


def test_worker_timeout_becomes_a_provider_error_with_the_cause_chained(tmp_path: Path) -> None:
    source = _source(tmp_path)
    timeout = MaudeWorkerTimeoutError()
    provider = InterpreterDiagnosticProvider(FakeMaudeExecutor(error=timeout))

    with pytest.raises(DiagnosticProviderError) as exc_info:
        _ = provider.diagnose(source)

    assert exc_info.value.reason == "Maude worker timed out"
    assert exc_info.value.__cause__ is timeout
