"""Unit tests for the Maude warning parser (no interpreter involved)."""

from harold_mcp.maude.worker import _parse_warnings


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
