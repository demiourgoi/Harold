"""Integration tests for `harold_mcp.maude.worker` against the real interpreter.

The worker functions run in a spawned process (the real MCP server layout);
these tests validate the spawn/pickling story and the fd-2 capture on the
repo fixtures.
"""

import multiprocessing
import os
from collections.abc import Iterator
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pytest

from harold_mcp.maude.worker import LoadDiagnosticsResult, init_maude, load_diagnostics

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def pool() -> Iterator[ProcessPoolExecutor]:
    with ProcessPoolExecutor(
        max_workers=1,
        mp_context=multiprocessing.get_context("spawn"),
        initializer=init_maude,
    ) as worker_pool:
        yield worker_pool


def _diagnose(pool: ProcessPoolExecutor, fixture_name: str) -> LoadDiagnosticsResult:
    return pool.submit(load_diagnostics, str(FIXTURES_DIR / fixture_name)).result(timeout=60)


def test_clean_program_loads_without_warnings(pool: ProcessPoolExecutor) -> None:
    result = _diagnose(pool, "hello.maude")
    assert result["ok"] is True
    assert result["warnings"] == []


def test_recoverable_program_reports_warning(pool: ProcessPoolExecutor) -> None:
    result = _diagnose(pool, "broken-recoverable.maude")
    assert result["ok"] is True
    assert result["warnings"] == [{"file": "broken-recoverable.maude", "line": 2, "message": "missing is keyword."}]


def test_non_recoverable_program_reports_all_warnings(pool: ProcessPoolExecutor) -> None:
    result = _diagnose(pool, "broken-non-recoverable.maude")
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


def test_program_without_modules_loads_clean(pool: ProcessPoolExecutor) -> None:
    result = _diagnose(pool, "no_new_module.maude")
    assert result["ok"] is True
    assert result["warnings"] == []


def test_module_redefinition_advisory_is_suppressed(pool: ProcessPoolExecutor) -> None:
    """Reloading a program redefines its module; the `Advisory:` message is
    suppressed at the source by `advise=False`, so the capture stays clean."""
    assert _diagnose(pool, "hello.maude")["ok"] is True
    result = _diagnose(pool, "hello.maude")
    assert result["ok"] is True
    assert result["warnings"] == []


def test_embedded_red_output_is_discarded_not_parsed(pool: ProcessPoolExecutor) -> None:
    """A loaded file's top-level `red` prints to stdout; only stderr is parsed as warnings."""
    result = _diagnose(pool, "warns_and_prints.maude")

    assert result["ok"] is True
    assert result["warnings"] == [{"file": "warns_and_prints.maude", "line": 2, "message": "missing is keyword."}]


def _diagnose_with_parent_stdout_captured(fixture_name: str) -> tuple[LoadDiagnosticsResult, bytes]:
    """Load a fixture in a fresh pool while the parent's fd 1 goes to a pipe.

    The pool is created inside the redirect, so the spawned worker inherits the pipe
    as its stdout: output the worker lets escape lands in the pipe (the MCP stdio
    transport analogue) and can be asserted on. A module-scoped pool would not do:
    its workers inherited the original stdout before the redirect.
    """
    read_fd, write_fd = os.pipe()
    saved_stdout = os.dup(1)
    result: LoadDiagnosticsResult
    try:
        _ = os.dup2(write_fd, 1)
        os.close(write_fd)
        with ProcessPoolExecutor(
            max_workers=1,
            mp_context=multiprocessing.get_context("spawn"),
            initializer=init_maude,
        ) as worker_pool:
            result = _diagnose(worker_pool, fixture_name)
    finally:
        _ = os.dup2(saved_stdout, 1)
        os.close(saved_stdout)
        # Non-blocking: a long-lived helper process (e.g. multiprocessing's resource
        # tracker) may also hold the write end, so waiting for EOF could hang. The
        # pool is already shut down, so every leak that could happen has happened.
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
