"""Unit tests for `harold_mcp.maude`."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import harold_mcp.maude as maude_module
from harold_mcp.maude import (
    MaudeInitError,
    MaudeLoadError,
    MaudeModuleNotFoundError,
    MaudeRuntime,
    get_runtime,
    init_maude,
)


@pytest.fixture(autouse=True)
def _reset_maude_init_state() -> None:
    """Isolate the module-level `_maude_initialized` flag between tests."""
    maude_module._maude_initialized = False
    yield
    maude_module._maude_initialized = False


def test_init_maude_calls_maude_init_once() -> None:
    with patch.object(maude_module.maude, "init", return_value=True) as mock_maude_init:
        init_maude()
        init_maude()
        init_maude()
        mock_maude_init.assert_called_once_with(advise=False)


def test_init_maude_retries_after_exception() -> None:
    with patch.object(maude_module.maude, "init", side_effect=[RuntimeError("boom"), True]) as mock_maude_init:
        with pytest.raises(RuntimeError, match="boom"):
            init_maude()
        init_maude()
    assert mock_maude_init.call_count == 2
    assert maude_module._maude_initialized


def test_init_maude_raises_and_retries_when_init_fails() -> None:
    with patch.object(maude_module.maude, "init", side_effect=[False, True]) as mock_maude_init:
        with pytest.raises(MaudeInitError, match="Failed to initialize"):
            init_maude()
        init_maude()
    assert mock_maude_init.call_count == 2
    assert maude_module._maude_initialized


def test_get_module_initializes_and_delegates() -> None:
    fake_module = MagicMock()
    with (
        patch.object(maude_module.maude, "init", return_value=True) as mock_maude_init,
        patch.object(maude_module.maude, "getModule", return_value=fake_module) as mock_get_module,
    ):
        module = MaudeRuntime().get_module("NAT")

    mock_maude_init.assert_called_once_with(advise=False)
    mock_get_module.assert_called_once_with("NAT")
    assert module is fake_module


def test_get_module_raises_when_module_is_missing() -> None:
    with (
        patch.object(maude_module.maude, "init", return_value=True),
        patch.object(maude_module.maude, "getModule", return_value=None),
        pytest.raises(MaudeModuleNotFoundError, match="not found"),
    ):
        MaudeRuntime().get_module("NOPE")


def test_load_program_loads_resolved_path() -> None:
    with (
        patch.object(maude_module.maude, "init", return_value=True),
        patch.object(maude_module.maude, "load", return_value=True) as mock_load,
    ):
        MaudeRuntime().load_program(Path("relative") / "hello.maude")

    mock_load.assert_called_once_with(str((Path("relative") / "hello.maude").resolve()))


def test_load_program_raises_when_load_fails() -> None:
    with (
        patch.object(maude_module.maude, "init", return_value=True),
        patch.object(maude_module.maude, "load", return_value=False),
        pytest.raises(MaudeLoadError, match="Failed to load"),
    ):
        MaudeRuntime().load_program("/does-not-exist.maude")


def test_load_module_delegates_to_load_program_and_get_module() -> None:
    fake_module = MagicMock()
    with (
        patch.object(maude_module.maude, "init", return_value=True),
        patch.object(maude_module.maude, "load", return_value=True) as mock_load,
        patch.object(maude_module.maude, "getModule", return_value=fake_module) as mock_get_module,
    ):
        module = MaudeRuntime().load_module("hello.maude", "HELLO-WORLD")

    mock_load.assert_called_once()
    mock_get_module.assert_called_once_with("HELLO-WORLD")
    assert module is fake_module


def test_get_runtime_returns_singleton() -> None:
    assert get_runtime() is get_runtime()
    assert isinstance(get_runtime(), MaudeRuntime)
