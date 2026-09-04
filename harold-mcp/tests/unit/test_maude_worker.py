"""Unit tests for `harold_mcp.maude.worker` helpers (no interpreter involved).

Both the warning parser and the `init_maude` sequence are exercised with the
`maude` SWIG bindings mocked out: the worker lazy-imports them, so a fake
module in `sys.modules` is enough and the tests stay hermetic.
"""

import sys
import types

import pytest

from harold_mcp.maude import worker as worker_module
from harold_mcp.maude.worker import WorkerInitError, _parse_warnings


class _FakeMaude(types.ModuleType):
    """Scriptable stand-in for the `maude` SWIG bindings.

    Records calls so tests can assert the worker's init sequence without the
    real interpreter (which only ever lives in the worker process).
    """

    def __init__(self, *, init_result: bool = True) -> None:
        super().__init__("maude")
        self._init_result = init_result
        self.init_advise_calls: list[bool] = []
        self.allow_dir_calls: list[bool] = []
        self.allow_files_calls: list[bool] = []
        self.allow_processes_calls: list[bool] = []

    def init(self, advise: bool = True) -> bool:
        self.init_advise_calls.append(advise)
        return self._init_result

    def setAllowDir(self, allow: bool) -> None:
        self.allow_dir_calls.append(allow)

    def setAllowFiles(self, allow: bool) -> None:
        self.allow_files_calls.append(allow)

    def setAllowProcesses(self, allow: bool) -> None:
        self.allow_processes_calls.append(allow)


def _patch_maude(monkeypatch: pytest.MonkeyPatch, *, init_result: bool = True) -> _FakeMaude:
    """Make `init_maude`'s lazy `import maude` resolve to a scriptable fake."""
    fake = _FakeMaude(init_result=init_result)
    monkeypatch.setitem(sys.modules, "maude", fake)
    monkeypatch.setattr(worker_module, "_maude_initialized", False)
    return fake


def test_init_maude_disables_io(monkeypatch: pytest.MonkeyPatch) -> None:
    """A successful init calls `maude.init(advise=False)` and locks down IO."""
    fake = _patch_maude(monkeypatch)

    worker_module.init_maude()
    worker_module.init_maude()  # already initialized: must be a no-op

    assert fake.init_advise_calls == [False]
    assert fake.allow_dir_calls == [False]
    assert fake.allow_files_calls == [False]
    assert fake.allow_processes_calls == [False]
    assert worker_module._maude_initialized is True


def test_init_maude_failed_init_skips_io_lockdown(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed `maude.init` raises and never touches the IO guards."""
    fake = _patch_maude(monkeypatch, init_result=False)

    with pytest.raises(WorkerInitError):
        worker_module.init_maude()

    assert fake.init_advise_calls == [False]
    assert fake.allow_dir_calls == []
    assert fake.allow_files_calls == []
    assert fake.allow_processes_calls == []
    assert worker_module._maude_initialized is False


def test_quoted_file_format() -> None:
    text = 'Warning: "hello.maude", line 3: skipped unexpected token: f'
    assert _parse_warnings(text) == [{"line": 3, "message": "skipped unexpected token: f"}]


def test_context_fragment_format() -> None:
    text = 'Warning: "broken-recoverable.maude", line 2 (fmod HELLO-WORLD): missing is keyword.'
    assert _parse_warnings(text) == [{"line": 2, "message": "missing is keyword."}]


def test_standard_input_format() -> None:
    text = "Warning: <standard input>, line 1: skipped unexpected token: fmo"
    assert _parse_warnings(text) == [{"line": 1, "message": "skipped unexpected token: fmo"}]


def test_multiple_warnings_keep_order() -> None:
    text = "\n".join([
        'Warning: "a.maude", line 1: first',
        "Warning: <standard input>, line 2: second",
        'Warning: "a.maude", line 5 (fmod X): third',
    ])
    assert _parse_warnings(text) == [
        {"line": 1, "message": "first"},
        {"line": 2, "message": "second"},
        {"line": 5, "message": "third"},
    ]


def test_unmatched_lines_are_ignored() -> None:
    text = "\n".join([
        "Something else entirely",
        'Warning: "a.maude", line 1: real warning',
        "    continuation line that does not match",
    ])
    assert _parse_warnings(text) == [{"line": 1, "message": "real warning"}]


def test_ansi_colorized_warning_is_parsed() -> None:
    """Maude colorizes stderr when it sees a TTY at init time."""
    text = '\x1b[31mWarning: \x1b[0m"broken-recoverable.maude", line 2 (fmod HELLO-WORLD): missing \x1b[35mis\x1b[0m keyword.'
    assert _parse_warnings(text) == [{"line": 2, "message": "missing is keyword."}]


def test_empty_text_yields_no_warnings() -> None:
    assert _parse_warnings("") == []


def test_advisory_lines_are_ignored() -> None:
    """Advisories (e.g. module redefinitions) are suppressed by advise=False;
    if one ever leaks into the capture, the parser must not treat it as a warning."""
    assert _parse_warnings("Advisory: redefining module HELLO-WORLD.\n") == []
