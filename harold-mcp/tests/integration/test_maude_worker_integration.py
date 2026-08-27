"""Integration tests for `harold_mcp.maude.worker` against the real interpreter.

The worker functions run in a spawned process (the real MCP server layout);
these tests validate the spawn/pickling story and the fd-2 capture on the
repo fixtures.
"""

import multiprocessing
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
    assert result["warnings"] == [{"line": 2, "message": "missing is keyword."}]


def test_non_recoverable_program_reports_all_warnings(pool: ProcessPoolExecutor) -> None:
    result = _diagnose(pool, "broken-non-recoverable.maude")
    assert result["ok"] is True  # maude.load recovers even from badly broken files
    # Deterministic 12 warnings through the Python bindings (the two `syntax error`
    # lines from the REPL transcript are interactive-parser-only).
    assert result["warnings"] == [
        {"line": 1, "message": "skipped unexpected token: fmo"},
        {"line": 1, "message": "skipped unexpected token: HELLO-WORLD"},
        {"line": 2, "message": "skipped unexpected token: pr"},
        {"line": 2, "message": "skipped unexpected token: NAT"},
        {"line": 3, "message": "skipped unexpected token: f"},
        {"line": 3, "message": "skipped unexpected token: :"},
        {"line": 3, "message": "skipped unexpected token: ->"},
        {"line": 3, "message": "skipped unexpected token: Nat"},
        {"line": 4, "message": "skipped unexpected token: f"},
        {"line": 4, "message": "skipped unexpected token: ="},
        {"line": 4, "message": "skipped unexpected token: *"},
        {"line": 5, "message": "skipped unexpected token: endfm"},
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
