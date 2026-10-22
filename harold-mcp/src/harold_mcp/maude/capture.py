"""Capture of the Maude interpreter's stdout and stderr from worker code.

Both `load_diagnostics` and the interpreter session engine run inside the worker
process and need the output Maude writes directly from C++. The capture uses temp
**files**, not pipes: a regular file cannot block on a full pipe buffer, and the
worker is single-threaded.

This module imports only the standard library. Importing it in the MCP server
process is safe; the `maude` SWIG bindings are never imported here.
"""

import os
import re
import tempfile
from collections.abc import Callable
from typing import BinaryIO, TypedDict

TRUNCATION_MARKER = "... [output truncated]"


class WarningDict(TypedDict):
    """A single parsed Maude warning.

    `file` is the name Maude printed for the file the warning belongs to — the
    diagnosed file, a file it loaded via `load`/`in`, or `<standard input>` for
    some first-line warnings. The provider uses it to attribute the warning.
    """

    file: str
    line: int | None
    message: str


class CapturedOutput(TypedDict):
    """The decoded, ANSI-stripped stdout and stderr of one execution phase."""

    stdout: str
    stderr: str


# `(fmod X) :` (space before the colon) is a real Maude spelling; requiring `):`
# used to drop those warnings silently. A message may contain colons, so the
# message group is greedy and last.
_WARNING_RE = re.compile(r'Warning:\s+"?([^",]+)"?,\s+line\s+(\d+)\s*(?:\([^)]*\))?\s*:\s*(.*)')
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def strip_ansi(text: str) -> str:
    """Remove ANSI CSI escape sequences (Maude colorizes stderr on a TTY)."""
    return _ANSI_ESCAPE_RE.sub("", text)


def parse_warnings(text: str) -> list[WarningDict]:
    """Parse `Warning:` lines from captured stderr into structured diagnostics.

    ANSI escapes are stripped first: Maude decides at init time whether stderr
    is a TTY and then colorizes its output, so captures can contain CSI
    sequences around `Warning:` and inside messages. The embedded file name is
    kept (`WarningDict.file`) so the provider can attribute warnings Maude
    raised about other files (dependencies) instead of pinning them on the
    diagnosed file.
    """
    warnings_out: list[WarningDict] = []
    for line in strip_ansi(text).splitlines():
        match = _WARNING_RE.match(line)
        if match:
            warnings_out.append({"file": match.group(1), "line": int(match.group(2)), "message": match.group(3)})
        # Unmatched lines are ignored for v1; hardening is a final-testing item.
    return warnings_out


def _decode_capture(capture: BinaryIO) -> str:
    """Rewind a capture temp file and decode it lossily (Maude emits raw C++ bytes)."""
    _ = capture.seek(0)
    return capture.read().decode("utf-8", errors="replace")


def capture_streams[T](fn: Callable[[], T]) -> tuple[T, CapturedOutput]:
    """Run `fn` with fd 1 and fd 2 redirected to temp files.

    Returns the result of `fn` plus the decoded, ANSI-stripped output of both
    streams. The fd swap is restored in `finally`, so it also holds when `fn`
    raises (the exception propagates). Nothing may be logged or printed while
    both fds are redirected: the output would be swallowed by the capture.
    """
    with (
        tempfile.TemporaryFile(mode="w+b") as stdout_capture,
        tempfile.TemporaryFile(mode="w+b") as stderr_capture,
    ):
        saved_stdout = os.dup(1)
        saved_stderr = os.dup(2)
        try:
            _ = os.dup2(stdout_capture.fileno(), 1)
            _ = os.dup2(stderr_capture.fileno(), 2)
            result = fn()
        finally:
            _ = os.dup2(saved_stdout, 1)
            _ = os.dup2(saved_stderr, 2)
            os.close(saved_stdout)
            os.close(saved_stderr)
        stdout = strip_ansi(_decode_capture(stdout_capture))
        stderr = strip_ansi(_decode_capture(stderr_capture))
    return result, {"stdout": stdout, "stderr": stderr}


def truncate_output(text: str, max_length: int) -> str:
    """Truncate `text` to `max_length` characters, appending a marker when longer.

    The marker is appended after the retained prefix, so a truncated result is
    longer than `max_length` by the marker's length: the cap bounds the
    interpreter output, not the marker that flags the truncation.
    """
    if len(text) <= max_length:
        return text
    return text[:max_length] + TRUNCATION_MARKER
