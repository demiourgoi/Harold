"""Unit tests for the Maude worker configuration (`HAROLD_*` env vars)."""

import pytest
from pydantic import ValidationError

from harold_mcp.maude import Settings


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start each test from a clean HAROLD_* environment."""
    monkeypatch.delenv("HAROLD_MAUDE_WORKERS", raising=False)
    monkeypatch.delenv("HAROLD_MAUDE_WORKER_TIMEOUT_SECS", raising=False)


def test_defaults() -> None:
    settings = Settings()
    assert settings.maude_workers == 1
    assert settings.maude_worker_timeout_secs == 60


def test_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAROLD_MAUDE_WORKERS", "3")
    monkeypatch.setenv("HAROLD_MAUDE_WORKER_TIMEOUT_SECS", "120")
    settings = Settings()
    assert settings.maude_workers == 3
    assert settings.maude_worker_timeout_secs == 120


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
