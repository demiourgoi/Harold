"""Probe: flushing C streams before restoring the capture fds recovers the lost tail.

Research artifact for `.agents/planning/Unexpected_failure_during_search/`; it lives
outside `tests/`, so the normal test suite does not collect it. It calls `init_maude()`
and must run in its own process:

    uv run python -m pytest \
        .agents/planning/Unexpected_failure_during_search/research/probes/test_capture_flush.py \
        -q -s

Passing means `fflush(NULL)` inside the capture window captures the bounded search's
solution, i.e. the tail loss is a buffering bug in `harold_mcp.maude.capture`.
"""

import ctypes
import os
import tempfile
from pathlib import Path

from harold_mcp.maude.worker import init_maude


def test_fflush_before_restore_recovers_tail(tmp_path: Path) -> None:
    probe = tmp_path / "probe.maude"
    probe.write_text(
        "mod PROBE is\n"
        "  sort S .\n"
        "  ops a b c : -> S [ctor] .\n"
        "  rl [step] : a => b .\n"
        "endm\n"
        "\n"
        "search [1] a =>* Z:S .\n"
    )
    init_maude()
    import maude

    with (
        tempfile.TemporaryFile(mode="w+b") as stdout_capture,
        tempfile.TemporaryFile(mode="w+b") as stderr_capture,
    ):
        saved_stdout = os.dup(1)
        saved_stderr = os.dup(2)
        try:
            _ = os.dup2(stdout_capture.fileno(), 1)
            _ = os.dup2(stderr_capture.fileno(), 2)
            _ = maude.load(str(probe))
            libc = ctypes.CDLL(None)
            libc.fflush.argtypes = [ctypes.c_void_p]
            libc.fflush.restype = ctypes.c_int
            _ = libc.fflush(None)
        finally:
            _ = os.dup2(saved_stdout, 1)
            _ = os.dup2(saved_stderr, 2)
            os.close(saved_stdout)
            os.close(saved_stderr)
        _ = stdout_capture.seek(0)
        captured = stdout_capture.read().decode("utf-8", errors="replace")

    print("\nCAPTURED WITH FFLUSH:", repr(captured))
    assert "Solution 1" in captured
