"""Unit tests for the bounded error-report formatter (`harold_mcp.errors`)."""

from pathlib import Path

import pytest

from harold_mcp.errors import (
    DEFAULT_ERROR_DETAIL_MAX_CHARS,
    TRUNCATION_MARKER,
    format_context,
    format_error_report,
    format_exception_text,
)
from harold_mcp.maude import (
    MaudeInitError,
    MaudeWorkerCancelledError,
    MaudeWorkerCrashedError,
    MaudeWorkerError,
    MaudeWorkerProtocolError,
    MaudeWorkerRemoteError,
    MaudeWorkerSpawnError,
    MaudeWorkerTimeoutError,
)


def _report(
    exc: BaseException,
    *,
    context: dict[str, object] | None = None,
    max_chars: int = 0,
    category: str | None = None,
    message: str | None = None,
) -> str:
    return format_error_report(
        exc,
        context=context if context is not None else {},
        max_chars=max_chars,
        category=category,
        message=message,
    )


def _chained_error() -> ValueError:
    """Build `ValueError("boom") from KeyError("inner")` outside its handler."""

    def inner() -> None:
        raise KeyError("inner")

    def outer() -> None:
        try:
            inner()
        except KeyError as cause:
            raise ValueError("boom") from cause

    try:
        outer()
    except ValueError as exc:
        return exc


def test_first_line_uses_category_and_message() -> None:
    report = _report(MaudeWorkerTimeoutError())

    assert report.splitlines()[0] == "timeout: Maude worker timed out"


def test_categoryless_report_omits_prefix() -> None:
    report = _report(ValueError("boom"))

    assert report.splitlines()[0] == "ValueError: boom"


def test_explicit_category_overrides_the_exception_category() -> None:
    report = _report(MaudeWorkerTimeoutError(), category="custom")

    assert report.splitlines()[0] == "custom: Maude worker timed out"


def test_message_override_replaces_the_exception_text() -> None:
    report = _report(MaudeWorkerTimeoutError(), message="the real reason")

    assert report.splitlines()[0] == "timeout: the real reason"
    assert "Maude worker timed out" not in report.splitlines()[0]


def test_context_merge_caller_wins() -> None:
    error = MaudeWorkerTimeoutError(context={"pid": 7, "phase": "step", "step": 1})

    report = _report(error, context={"step": 3, "path": "/p.maude"})

    assert "context: pid=7, phase=step, step=3, path=/p.maude" in report


def test_context_skips_none_values_and_omits_the_line_when_empty() -> None:
    assert "context:" not in _report(ValueError("boom"), context={"pid": None})

    report = format_error_report(ValueError("boom"), context={"pid": None, "phase": "load"}, max_chars=0)

    assert "context: phase=load" in report


def test_empty_exception_message_renders_the_label_only() -> None:
    report = _report(RuntimeError())

    assert report.splitlines()[0] == "RuntimeError"


def test_cause_chain_starts_with_the_exception_itself() -> None:
    report = _report(_chained_error())

    assert "cause: ValueError: boom <- KeyError: 'inner'" in report


def test_cause_chain_renders_context_when_there_is_no_explicit_cause() -> None:
    def inner() -> None:
        raise KeyError("inner")

    def outer() -> None:
        try:
            inner()
        except KeyError:
            raise ValueError("boom")  # noqa: B904 - exercise the implicit context chain

    try:
        outer()
    except ValueError as exc:
        report = _report(exc)

    assert "cause: ValueError: boom <- KeyError: 'inner'" in report


def test_cycle_guard_stops_a_cause_loop() -> None:
    first = ValueError("first")
    second = RuntimeError("second")
    first.__cause__ = second
    second.__cause__ = first

    report = _report(first)

    cause_line = next(line for line in report.splitlines() if line.startswith("cause: "))
    assert cause_line.count("ValueError: first") == 1
    assert cause_line.count("RuntimeError: second") == 1


def test_remote_error_report_has_type_cause_context_and_traceback() -> None:
    remote = MaudeWorkerRemoteError(
        "ValueError",
        "boom",
        remote_traceback='Traceback (most recent call last):\n  File "worker.py", line 1\nValueError: boom\n',
        context={"phase": "step", "step": 2, "command": "rewrite", "pid": 123},
    )

    report = _report(remote, context={"path": "/abs/program.maude", "module": "M", "timeout": "60s"})

    lines = report.splitlines()
    assert lines[0] == "remote-exception: ValueError: boom"
    assert "phase=step" in report
    assert "step=2" in report
    assert "command=rewrite" in report
    assert "pid=123" in report
    assert "path=/abs/program.maude" in report
    assert "module=M" in report
    assert "cause: MaudeWorkerRemoteError: ValueError: boom <- ValueError: boom" in report
    assert "traceback:\nTraceback (most recent call last):" in report


def test_remote_error_without_a_traceback_falls_back_to_the_local_one() -> None:
    remote = MaudeWorkerRemoteError("ValueError", "boom")

    report = _report(remote)

    assert "MaudeWorkerRemoteError: ValueError: boom" in report
    assert "NoneType: None" not in report


def test_stored_exception_outside_its_handler_has_no_none_type_none() -> None:
    exc = ValueError("stored")

    report = _report(exc)

    assert "NoneType: None" not in report
    assert "ValueError: stored" in report


def test_local_exception_renders_its_traceback() -> None:
    def raise_local() -> None:
        raise RuntimeError("local")

    try:
        raise_local()
    except RuntimeError as exc:
        report = _report(exc)

    assert "traceback:\nTraceback (most recent call last):" in report
    assert "RuntimeError: local" in report


def test_format_exception_text_renders_a_stored_exception() -> None:
    exc = ValueError("stored")

    rendered = format_exception_text(exc)

    assert "ValueError: stored" in rendered
    assert "NoneType: None" not in rendered


def test_report_truncates_traceback_and_keeps_first_line() -> None:
    remote = MaudeWorkerRemoteError("ValueError", "boom", remote_traceback="X" * 5000)

    report = _report(remote, context={"path": "/p"}, max_chars=300)

    assert len(report) <= 300
    assert report.splitlines()[0] == "remote-exception: ValueError: boom"
    assert report.rstrip().endswith(TRUNCATION_MARKER)


def test_long_cause_is_shortened_before_the_first_line() -> None:
    def raise_deep() -> None:
        raise RuntimeError("y" * 1000)

    def raise_wrapped() -> None:
        try:
            raise_deep()
        except RuntimeError as cause:
            raise ValueError("boom") from cause

    try:
        raise_wrapped()
    except ValueError as exc:
        report = _report(exc, max_chars=250)

    assert len(report) <= 250
    assert report.splitlines()[0] == "ValueError: boom"
    assert report.rstrip().endswith(TRUNCATION_MARKER)


def test_huge_exception_message_is_truncated_with_marker() -> None:
    report = _report(ValueError("x" * 5000), max_chars=200)

    assert len(report) <= 200
    assert report.splitlines()[0].startswith("ValueError: ")
    assert TRUNCATION_MARKER in report


def test_report_within_the_cap_has_no_marker() -> None:
    report = _report(ValueError("boom"), max_chars=DEFAULT_ERROR_DETAIL_MAX_CHARS)

    assert TRUNCATION_MARKER not in report


def test_formatter_max_chars_zero_is_unbounded() -> None:
    remote = MaudeWorkerRemoteError("ValueError", "boom", remote_traceback="X" * 5000)

    report = _report(remote, max_chars=0)

    assert len(report) > DEFAULT_ERROR_DETAIL_MAX_CHARS
    assert TRUNCATION_MARKER not in report


def test_report_does_not_leak_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HAROLD_SECRET", "hunter2")

    report = _report(ValueError("boom"))

    assert "hunter2" not in report


def test_format_context_is_ordered_and_skips_none() -> None:
    assert format_context({"a": 1, "b": None, "c": True}) == "a=1, c=True"
    assert format_context({}) is None


@pytest.mark.parametrize(
    ("error", "category"),
    [
        (MaudeInitError(), "init-failure"),
        (MaudeWorkerCrashedError(), "crash"),
        (MaudeWorkerTimeoutError(), "timeout"),
        (MaudeWorkerSpawnError(), "spawn-failure"),
        (MaudeWorkerRemoteError("ValueError", "boom"), "remote-exception"),
        (MaudeWorkerCancelledError(), "cancelled"),
        (MaudeWorkerProtocolError(), "protocol-error"),
    ],
)
def test_error_categories_are_class_attributes(error: MaudeWorkerError, category: str) -> None:
    assert error.category == category
    assert type(error).category == category


def test_maude_init_error_is_a_worker_error() -> None:
    error = MaudeInitError()

    assert isinstance(error, MaudeWorkerError)
    assert error.reason == "Failed to initialize the Maude interpreter in the worker process"
    assert error.__cause__ is None


def test_worker_error_keeps_its_context_and_remote_traceback() -> None:
    error = MaudeWorkerCrashedError(context={"pid": 11}, remote_traceback="trace")

    assert error.context == {"pid": 11}
    assert error.remote_traceback == "trace"
    assert error.reason == "Maude worker crashed"


def test_path_context_is_rendered_verbatim(tmp_path: Path) -> None:
    path = tmp_path / "program.maude"

    report = _report(ValueError("boom"), context={"path": str(path)})

    assert f"path={path}" in report
