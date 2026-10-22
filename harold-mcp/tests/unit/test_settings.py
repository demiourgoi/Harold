"""Unit tests for the application configuration (`HAROLD_*` env vars)."""

import os

import pytest
from pydantic import ValidationError

from harold_mcp.settings import Settings, get_settings, settings

_ENV_VARS = [
    "HAROLD_MAUDE_WORKERS",
    "HAROLD_DIAGNOSTICS_TIMEOUT_SECS",
    "HAROLD_INTERPRETER_TIMEOUT_SECS",
    "HAROLD_INTERPRETER_MAX_STEPS",
    "HAROLD_INTERPRETER_MAX_REWRITE_BOUND",
    "HAROLD_INTERPRETER_MAX_SOLUTIONS",
    "HAROLD_INTERPRETER_MAX_TERM_LENGTH",
    "HAROLD_INTERPRETER_MAX_RESULT_LENGTH",
    "HAROLD_INTERPRETER_MAX_OUTPUT_LENGTH",
]

_POSITIVE_INT_SETTINGS = [env_var for env_var in _ENV_VARS if env_var != "HAROLD_MAUDE_WORKERS"]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start each test from a clean HAROLD_* environment."""
    for env_var in _ENV_VARS:
        monkeypatch.delenv(env_var, raising=False)


def test_defaults() -> None:
    resolved = Settings()
    assert resolved.maude_workers == max(1, min(3, (os.cpu_count() or 0) // 2))
    assert resolved.diagnostics_timeout_secs == 60
    assert resolved.interpreter_timeout_secs == 60
    assert resolved.interpreter_max_steps == 200
    assert resolved.interpreter_max_rewrite_bound == 1000
    assert resolved.interpreter_max_solutions == 200
    assert resolved.interpreter_max_term_length == 100_000
    assert resolved.interpreter_max_result_length == 1_000_000
    assert resolved.interpreter_max_output_length == 1_000_000


def test_workers_default_scales_with_cpu_count(monkeypatch: pytest.MonkeyPatch) -> None:
    """Half the logical CPUs, capped at 3, floored at 1 (`cpu_count` can be None)."""
    cases: list[tuple[int | None, int]] = [(12, 3), (8, 3), (4, 2), (2, 1), (1, 1), (None, 1)]
    for cpus, expected in cases:
        monkeypatch.setattr(os, "cpu_count", lambda cpus=cpus: cpus)
        assert Settings().maude_workers == expected, f"cpu_count={cpus}"


def test_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    overrides = {
        "HAROLD_MAUDE_WORKERS": ("maude_workers", 3),
        "HAROLD_DIAGNOSTICS_TIMEOUT_SECS": ("diagnostics_timeout_secs", 120),
        "HAROLD_INTERPRETER_TIMEOUT_SECS": ("interpreter_timeout_secs", 90),
        "HAROLD_INTERPRETER_MAX_STEPS": ("interpreter_max_steps", 5),
        "HAROLD_INTERPRETER_MAX_REWRITE_BOUND": ("interpreter_max_rewrite_bound", 7),
        "HAROLD_INTERPRETER_MAX_SOLUTIONS": ("interpreter_max_solutions", 11),
        "HAROLD_INTERPRETER_MAX_TERM_LENGTH": ("interpreter_max_term_length", 13),
        "HAROLD_INTERPRETER_MAX_RESULT_LENGTH": ("interpreter_max_result_length", 17),
        "HAROLD_INTERPRETER_MAX_OUTPUT_LENGTH": ("interpreter_max_output_length", 19),
    }
    for env_var, (_, value) in overrides.items():
        monkeypatch.setenv(env_var, str(value))

    resolved = Settings()

    for field, value in overrides.values():
        assert getattr(resolved, field) == value, field


def test_env_names_are_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("harold_maude_workers", "2")
    assert Settings().maude_workers == 2


def test_legacy_worker_timeout_env_var_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    """The pre-rename env var no longer configures anything (breaking change, pre-1.0)."""
    monkeypatch.setenv("HAROLD_MAUDE_WORKER_TIMEOUT_SECS", "120")
    assert Settings().diagnostics_timeout_secs == 60


def test_zero_workers_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAROLD_MAUDE_WORKERS", "0")
    with pytest.raises(ValidationError):
        Settings()


def test_non_numeric_workers_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAROLD_MAUDE_WORKERS", "many")
    with pytest.raises(ValidationError):
        Settings()


@pytest.mark.parametrize("env_var", _POSITIVE_INT_SETTINGS)
@pytest.mark.parametrize("value", ["0", "-5"])
def test_non_positive_values_rejected(monkeypatch: pytest.MonkeyPatch, env_var: str, value: str) -> None:
    monkeypatch.setenv(env_var, value)
    with pytest.raises(ValidationError):
        Settings()


def test_get_settings_returns_singleton() -> None:
    assert get_settings() is settings
