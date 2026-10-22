"""Unit tests for `harold_mcp.maude.worker` (no interpreter involved).

Both the `init_maude` sequence and `load_diagnostics` are exercised with the
`maude` SWIG bindings mocked out: the worker lazy-imports them, so a fake module
in `sys.modules` is enough and the tests stay hermetic. The warning-parser cases
live in `test_maude_capture.py`, next to the parser.
"""

import os
import sys
import types

import pytest

from harold_mcp.maude import worker as worker_module
from harold_mcp.maude.worker import WorkerInitError


class _FakeMaude(types.ModuleType):
    """Scriptable stand-in for the `maude` SWIG bindings.

    Records calls so tests can assert the worker's init sequence without the
    real interpreter (which only ever lives in the worker process).
    """

    def __init__(self, *, init_result: bool = True) -> None:
        super().__init__("maude")
        self._init_result = init_result
        self.init_load_prelude_calls: list[bool] = []
        self.init_advise_calls: list[bool] = []
        self.allow_dir_calls: list[bool] = []
        self.allow_files_calls: list[bool] = []
        self.allow_processes_calls: list[bool] = []

    def init(self, *, loadPrelude: bool = True, advise: bool = True) -> bool:
        self.init_load_prelude_calls.append(loadPrelude)
        self.init_advise_calls.append(advise)
        return self._init_result

    def setAllowDir(self, allow: bool) -> None:
        self.allow_dir_calls.append(allow)

    def setAllowFiles(self, allow: bool) -> None:
        self.allow_files_calls.append(allow)

    def setAllowProcesses(self, allow: bool) -> None:
        self.allow_processes_calls.append(allow)


class _FakeLoadMaude(_FakeMaude):
    """Fake bindings whose `load` writes to both streams, like the real one."""

    def __init__(self, *, load_result: bool = True) -> None:
        super().__init__()
        self._load_result = load_result
        self.load_paths: list[str] = []

    def load(self, path: str) -> bool:
        self.load_paths.append(path)
        _ = os.write(2, b'Warning: "warns_and_prints.maude", line 2 (fmod WARNS-AND-PRINTS): missing is keyword.\n')
        # Warning-shaped stdout text must never reach the parser.
        _ = os.write(1, b'Warning: "warns_and_prints.maude", line 99: printed, not warned\n')
        return self._load_result


def _patch_maude(monkeypatch: pytest.MonkeyPatch, fake: _FakeMaude | None = None) -> _FakeMaude:
    """Make the worker's lazy `import maude` resolve to a scriptable fake."""
    if fake is None:
        fake = _FakeMaude()
    monkeypatch.setitem(sys.modules, "maude", fake)
    monkeypatch.setattr(worker_module, "_maude_initialized", False)
    return fake


def test_init_maude_disables_io(monkeypatch: pytest.MonkeyPatch) -> None:
    """A successful init calls `maude.init(loadPrelude=True, advise=False)` and locks down IO."""
    fake = _patch_maude(monkeypatch)

    worker_module.init_maude()
    worker_module.init_maude()  # already initialized: must be a no-op

    assert fake.init_load_prelude_calls == [True]
    assert fake.init_advise_calls == [False]
    assert fake.allow_dir_calls == [False]
    assert fake.allow_files_calls == [False]
    assert fake.allow_processes_calls == [False]
    assert worker_module._maude_initialized is True


def test_init_maude_failed_init_skips_io_lockdown(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed `maude.init` raises and never touches the IO guards."""
    fake = _patch_maude(monkeypatch, _FakeMaude(init_result=False))

    with pytest.raises(WorkerInitError):
        worker_module.init_maude()

    assert fake.init_load_prelude_calls == [True]
    assert fake.init_advise_calls == [False]
    assert fake.allow_dir_calls == []
    assert fake.allow_files_calls == []
    assert fake.allow_processes_calls == []
    assert worker_module._maude_initialized is False


def test_load_diagnostics_parses_only_the_stderr_capture(monkeypatch: pytest.MonkeyPatch) -> None:
    """Warning-shaped stdout text is captured and discarded, never parsed as a warning."""
    fake = _FakeLoadMaude()
    _patch_maude(monkeypatch, fake)

    result = worker_module.load_diagnostics("warns_and_prints.maude")

    assert fake.load_paths == ["warns_and_prints.maude"]
    assert result == {
        "ok": True,
        "warnings": [{"file": "warns_and_prints.maude", "line": 2, "message": "missing is keyword."}],
    }


def test_load_diagnostics_forwards_the_load_result(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_maude(monkeypatch, _FakeLoadMaude(load_result=False))

    assert worker_module.load_diagnostics("missing.maude")["ok"] is False
