"""Unit tests for `harold_mcp.maude.capture` (no interpreter involved).

The warning-parser cases moved here from `test_maude_worker.py` together with the
parser itself. The stream-capture tests write directly to fds 1 and 2 (not through
`sys.stdout`), because the helper redirects the file descriptors, not the Python
stream objects.
"""

import os

import pytest

from harold_mcp.maude.capture import (
    TRUNCATION_MARKER,
    capture_streams,
    parse_warnings,
    strip_ansi,
    truncate_output,
)


def _write_to_streams(stdout: bytes, stderr: bytes) -> None:
    _ = os.write(1, stdout)
    _ = os.write(2, stderr)


def _fd_identity(fd: int) -> tuple[int, int]:
    info = os.fstat(fd)
    return info.st_dev, info.st_ino


def test_capture_streams_separates_stdout_and_stderr() -> None:
    result, captured = capture_streams(lambda: _write_to_streams(b"to stdout\n", b"to stderr\n"))

    assert result is None
    assert captured == {"stdout": "to stdout\n", "stderr": "to stderr\n"}


def test_capture_streams_returns_the_callable_result() -> None:
    result, captured = capture_streams(lambda: 42)

    assert result == 42
    assert captured == {"stdout": "", "stderr": ""}


def test_capture_streams_restores_both_streams() -> None:
    stdout_identity = _fd_identity(1)
    stderr_identity = _fd_identity(2)

    _ = capture_streams(lambda: _write_to_streams(b"first", b"first-err"))
    _, second = capture_streams(lambda: _write_to_streams(b"second", b"second-err"))

    assert _fd_identity(1) == stdout_identity
    assert _fd_identity(2) == stderr_identity
    assert second == {"stdout": "second", "stderr": "second-err"}


def test_capture_streams_restores_streams_when_the_callable_raises() -> None:
    stdout_identity = _fd_identity(1)
    stderr_identity = _fd_identity(2)

    def boom() -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        _ = capture_streams(boom)

    assert _fd_identity(1) == stdout_identity
    assert _fd_identity(2) == stderr_identity


def test_capture_streams_strips_ansi_from_both_streams() -> None:
    _, captured = capture_streams(
        lambda: _write_to_streams(b"\x1b[32mgreen\x1b[0m\n", b"\x1b[31mWarning: \x1b[0mboom\n")
    )

    assert captured == {"stdout": "green\n", "stderr": "Warning: boom\n"}


def test_capture_streams_decodes_invalid_utf8_lossily() -> None:
    _, captured = capture_streams(lambda: _write_to_streams(b"ok \xff\xfe end", b"\xfe"))

    assert captured["stdout"] == "ok \ufffd\ufffd end"
    assert captured["stderr"] == "\ufffd"


def test_strip_ansi_leaves_plain_text_untouched() -> None:
    assert strip_ansi("plain text") == "plain text"


def test_truncate_output_is_unchanged_at_the_limit() -> None:
    text = "a" * 10
    assert truncate_output(text, 10) == text


def test_truncate_output_appends_the_marker_above_the_limit() -> None:
    assert truncate_output("a" * 11, 10) == "a" * 10 + TRUNCATION_MARKER


def test_quoted_file_format() -> None:
    text = 'Warning: "hello.maude", line 3: skipped unexpected token: f'
    assert parse_warnings(text) == [{"file": "hello.maude", "line": 3, "message": "skipped unexpected token: f"}]


def test_context_fragment_format() -> None:
    text = 'Warning: "broken-recoverable.maude", line 2 (fmod HELLO-WORLD): missing is keyword.'
    assert parse_warnings(text) == [{"file": "broken-recoverable.maude", "line": 2, "message": "missing is keyword."}]


def test_context_fragment_with_space_before_the_colon() -> None:
    """Some warnings print `(fmod X) :` with a space before the colon (they used to be dropped)."""
    text = 'Warning: "dep.maude", line 4 (fmod DEP) : unexpected end of tokens.'
    assert parse_warnings(text) == [{"file": "dep.maude", "line": 4, "message": "unexpected end of tokens."}]


def test_standard_input_format() -> None:
    text = "Warning: <standard input>, line 1: skipped unexpected token: fmo"
    assert parse_warnings(text) == [{"file": "<standard input>", "line": 1, "message": "skipped unexpected token: fmo"}]


def test_multiple_warnings_keep_order() -> None:
    text = "\n".join([
        'Warning: "a.maude", line 1: first',
        "Warning: <standard input>, line 2: second",
        'Warning: "a.maude", line 5 (fmod X): third',
    ])
    assert parse_warnings(text) == [
        {"file": "a.maude", "line": 1, "message": "first"},
        {"file": "<standard input>", "line": 2, "message": "second"},
        {"file": "a.maude", "line": 5, "message": "third"},
    ]


def test_unmatched_lines_are_ignored() -> None:
    text = "\n".join([
        "Something else entirely",
        'Warning: "a.maude", line 1: real warning',
        "    continuation line that does not match",
    ])
    assert parse_warnings(text) == [{"file": "a.maude", "line": 1, "message": "real warning"}]


def test_ansi_colorized_warning_is_parsed() -> None:
    """Maude colorizes stderr when it sees a TTY at init time."""
    text = '\x1b[31mWarning: \x1b[0m"broken-recoverable.maude", line 2 (fmod HELLO-WORLD): missing \x1b[35mis\x1b[0m keyword.'
    assert parse_warnings(text) == [{"file": "broken-recoverable.maude", "line": 2, "message": "missing is keyword."}]


def test_empty_text_yields_no_warnings() -> None:
    assert parse_warnings("") == []


def test_advisory_lines_are_ignored() -> None:
    """Advisories (e.g. module redefinitions) are suppressed by advise=False;
    if one ever leaks into the capture, the parser must not treat it as a warning."""
    assert parse_warnings("Advisory: redefining module HELLO-WORLD.\n") == []
