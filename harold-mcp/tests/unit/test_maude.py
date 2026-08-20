"""Unit tests for `harold_mcp.maude`."""

from unittest.mock import MagicMock, patch

import pytest

import harold_mcp.maude as maude_module
from harold_mcp.maude import MaudeRuntime, init_maude


@pytest.fixture(autouse=True)
def _reset_maude_init_state() -> None:
    """Isolate the module-level `_maude_initialized` flag between tests."""
    maude_module._maude_initialized = False
    yield
    maude_module._maude_initialized = False


def test_init_maude_calls_maude_init_once() -> None:
    with patch.object(maude_module.maude, "init") as mock_maude_init:
        init_maude()
        init_maude()
        init_maude()
        mock_maude_init.assert_called_once_with()


def test_init_maude_retries_after_failure() -> None:
    with patch.object(maude_module.maude, "init", side_effect=[RuntimeError("boom"), None]) as mock_maude_init:
        with pytest.raises(RuntimeError, match="boom"):
            init_maude()
        init_maude()
    assert mock_maude_init.call_count == 2
    assert maude_module._maude_initialized


def test_get_module_initializes_and_delegates() -> None:
    fake_module = MagicMock()
    with (
        patch.object(maude_module.maude, "init") as mock_maude_init,
        patch.object(maude_module.maude, "getModule", return_value=fake_module) as mock_get_module,
    ):
        module = MaudeRuntime().get_module("NAT")

    mock_maude_init.assert_called_once_with()
    mock_get_module.assert_called_once_with("NAT")
    assert module is fake_module
