"""Unit tests for the application configuration (`HAROLD_*` env vars)."""

import pytest
from pydantic import ValidationError

from harold_mcp.settings import Settings, get_settings, settings


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start each test from a clean HAROLD_* environment."""
    monkeypatch.delenv("HAROLD_MAUDE_WORKERS", raising=False)
    monkeypatch.delenv("HAROLD_MAUDE_WORKER_TIMEOUT_SECS", raising=False)


def test_defaults() -> None:
    resolved = Settings()
    assert resolved.maude_workers == 1
    assert resolved.maude_worker_timeout_secs == 60


def test_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAROLD_MAUDE_WORKERS", "3")
    monkeypatch.setenv("HAROLD_MAUDE_WORKER_TIMEOUT_SECS", "120")
    resolved = Settings()
    assert resolved.maude_workers == 3
    assert resolved.maude_worker_timeout_secs == 120


def test_env_names_are_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("harold_maude_workers", "2")
    assert Settings().maude_workers == 2


def test_zero_workers_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAROLD_MAUDE_WORKERS", "0")
    with pytest.raises(ValidationError):
        Settings()


def test_non_numeric_workers_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAROLD_MAUDE_WORKERS", "many")
    with pytest.raises(ValidationError):
        Settings()


def test_negative_timeout_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAROLD_MAUDE_WORKER_TIMEOUT_SECS", "-5")
    with pytest.raises(ValidationError):
        Settings()


def test_get_settings_returns_singleton() -> None:
    assert get_settings() is settings
