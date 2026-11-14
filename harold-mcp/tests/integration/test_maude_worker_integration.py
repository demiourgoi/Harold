"""Integration tests for the worker's load capture against the real interpreter.

Calls go through `MaudeExecutor.diagnostics`, which runs
`worker.load_diagnostics` in a per-call child; these tests validate the spawn
story, the warning shapes and the fd capture on the repo fixtures.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from harold_mcp.maude import MaudeExecutor
from harold_mcp.maude.worker import LoadDiagnosticsResult
from harold_mcp.settings import Settings

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def executor() -> Iterator[MaudeExecutor]:
    settings = Settings(maude_workers=1)
    resolved = MaudeExecutor(settings=settings)
    resolved.start(settings.diagnostics_timeout_secs)
    try:
        yield resolved
    finally:
        resolved.shutdown()


def _diagnose(executor: MaudeExecutor, fixture_name: str) -> LoadDiagnosticsResult:
    return executor.diagnostics(str(FIXTURES_DIR / fixture_name))


def test_clean_program_loads_without_warnings(executor: MaudeExecutor) -> None:
    result = _diagnose(executor, "hello.maude")
    assert result["ok"] is True
    assert result["warnings"] == []


def test_recoverable_program_reports_warning(executor: MaudeExecutor) -> None:
    result = _diagnose(executor, "broken-recoverable.maude")
    assert result["ok"] is True
    assert result["warnings"] == [{"file": "broken-recoverable.maude", "line": 2, "message": "missing is keyword."}]


def test_non_recoverable_program_reports_all_warnings(executor: MaudeExecutor) -> None:
    result = _diagnose(executor, "broken-non-recoverable.maude")
    assert result["ok"] is True  # maude.load recovers even from badly broken files
    # Deterministic 12 warnings through the Python bindings (the two `syntax error`
    # lines from the REPL transcript are interactive-parser-only).
    assert result["warnings"] == [
        # The first two warnings of this badly broken file are attributed to
        # `<standard input>` by Maude (the provider maps those back to the
        # diagnosed file).
        {"file": "<standard input>", "line": 1, "message": "skipped unexpected token: fmo"},
        {"file": "<standard input>", "line": 1, "message": "skipped unexpected token: HELLO-WORLD"},
        {"file": "broken-non-recoverable.maude", "line": 2, "message": "skipped unexpected token: pr"},
        {"file": "broken-non-recoverable.maude", "line": 2, "message": "skipped unexpected token: NAT"},
        {"file": "broken-non-recoverable.maude", "line": 3, "message": "skipped unexpected token: f"},
        {"file": "broken-non-recoverable.maude", "line": 3, "message": "skipped unexpected token: :"},
        {"file": "broken-non-recoverable.maude", "line": 3, "message": "skipped unexpected token: ->"},
        {"file": "broken-non-recoverable.maude", "line": 3, "message": "skipped unexpected token: Nat"},
        {"file": "broken-non-recoverable.maude", "line": 4, "message": "skipped unexpected token: f"},
        {"file": "broken-non-recoverable.maude", "line": 4, "message": "skipped unexpected token: ="},
        {"file": "broken-non-recoverable.maude", "line": 4, "message": "skipped unexpected token: *"},
        {"file": "broken-non-recoverable.maude", "line": 5, "message": "skipped unexpected token: endfm"},
    ]


def test_program_without_modules_loads_clean(executor: MaudeExecutor) -> None:
    result = _diagnose(executor, "no_new_module.maude")
    assert result["ok"] is True
    assert result["warnings"] == []


def test_each_call_gets_a_fresh_interpreter(executor: MaudeExecutor) -> None:
    """Reloading a program cannot redefine a module: every call is a fresh process."""
    assert _diagnose(executor, "hello.maude")["ok"] is True
    result = _diagnose(executor, "hello.maude")
    assert result["ok"] is True
    assert result["warnings"] == []


def test_embedded_red_output_is_discarded_not_parsed(executor: MaudeExecutor) -> None:
    """A loaded file's top-level `red` prints to stdout; only stderr is parsed as warnings."""
    result = _diagnose(executor, "warns_and_prints.maude")

    assert result["ok"] is True
    assert result["warnings"] == [{"file": "warns_and_prints.maude", "line": 2, "message": "missing is keyword."}]


def _diagnose_with_parent_stdout_captured(fixture_name: str) -> tuple[LoadDiagnosticsResult, bytes]:
    """Load a fixture in a fresh child while the parent's fd 1 goes to a pipe.

    The child is spawned inside the redirect, so it inherits the pipe as its stdout
    (the MCP stdio transport analogue) before `serve_one` points its own fds at
    `os.devnull`. Output that escapes the child's capture lands in the pipe and can
    be asserted on; the child is per-call, so no long-lived worker keeps the write end.
    """
    read_fd, write_fd = os.pipe()
    saved_stdout = os.dup(1)
    result: LoadDiagnosticsResult
    try:
        _ = os.dup2(write_fd, 1)
        os.close(write_fd)
        executor = MaudeExecutor(settings=Settings(maude_workers=1))
        try:
            result = executor.diagnostics(str(FIXTURES_DIR / fixture_name))
        finally:
            executor.shutdown()
    finally:
        _ = os.dup2(saved_stdout, 1)
        os.close(saved_stdout)
        # Non-blocking: a long-lived helper process (e.g. multiprocessing's resource
        # tracker) may also hold the write end, so waiting for EOF could hang. The
        # child is already shut down, so every leak that could happen has happened.
        os.set_blocking(read_fd, False)
        chunks: list[bytes] = []
        try:
            while chunk := os.read(read_fd, 65536):
                chunks.append(chunk)
        except BlockingIOError:
            pass
        finally:
            os.close(read_fd)
    return result, b"".join(chunks)


def test_embedded_red_output_does_not_reach_the_parent_stdout() -> None:
    """Regression: stdout was not captured, so a loaded `red` wrote into the MCP transport."""
    result, leaked = _diagnose_with_parent_stdout_captured("warns_and_prints.maude")

    assert result["ok"] is True
    assert b"reduce in WARNS-AND-PRINTS" not in leaked
    assert b"result Nat: 2" not in leaked
    assert b"rewrites:" not in leaked
