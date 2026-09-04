"""End-to-end integration tests for `maude_program_diagnostics` (acceptance R18).

These drive the tool against the real Maude interpreter and, in the MCP smoke
test, against the real stdio server.
"""

import json
import select
import subprocess
import sys
from collections.abc import Iterator
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path

import pytest

from harold_mcp.maude import MaudeExecutor, MaudeWorkerCrashedError, worker
from harold_mcp.server.tools.diagnostics import MaudeProgramDiagnosticsResult, maude_program_diagnostics
from harold_mcp.settings import Settings

FIXTURES_DIR = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).parents[2]


@pytest.fixture(scope="module")
def executor() -> Iterator[MaudeExecutor]:
    executor = MaudeExecutor(settings=Settings(maude_workers=1))
    executor.start()
    try:
        yield executor
    finally:
        executor.shutdown()


def _diagnose(executor: MaudeExecutor, fixture_name: str) -> MaudeProgramDiagnosticsResult:
    return maude_program_diagnostics(str(FIXTURES_DIR / fixture_name), maude_executor=executor)


def test_clean_program(executor: MaudeExecutor) -> None:
    result = _diagnose(executor, "hello.maude")
    assert result.path == str(FIXTURES_DIR / "hello.maude")
    assert result.success is True
    assert result.summary.warning == 0
    assert result.summary.error == 0
    assert result.diagnostics == []


def test_recoverable_program(executor: MaudeExecutor) -> None:
    result = _diagnose(executor, "broken-recoverable.maude")
    assert result.success is False
    assert result.summary.warning == 1
    assert result.summary.error == 0
    assert len(result.diagnostics) == 1
    diagnostic = result.diagnostics[0]
    assert diagnostic.severity == "warning"
    assert diagnostic.range is not None and diagnostic.range.start.line == 2
    assert diagnostic.message == "missing is keyword."


def test_non_recoverable_program(executor: MaudeExecutor) -> None:
    result = _diagnose(executor, "broken-non-recoverable.maude")
    assert result.success is False
    assert result.summary.warning == 12
    # maude.load recovers even from this file (ok=True), so no error is
    # synthesized — that path is unit-tested with a mocked ok=False.
    assert result.summary.error == 0
    assert len(result.diagnostics) == 12
    assert all(d.severity == "warning" for d in result.diagnostics)


def test_program_without_modules(executor: MaudeExecutor) -> None:
    result = _diagnose(executor, "no_new_module.maude")
    assert result.success is True
    assert result.diagnostics == []


def test_binary_file_reports_warnings_without_crashing(executor: MaudeExecutor, tmp_path: Path) -> None:
    """Regression: arbitrary bytes must not crash the worker's capture decode."""
    binary = tmp_path / "garbage.maude"
    binary.write_bytes(b"\x00\x01\x02\xff\xfe binary garbage \x00\x00")

    result = maude_program_diagnostics(str(binary), maude_executor=executor)

    assert result.success is False
    assert result.diagnostics  # Maude skips the garbage and reports warnings
    assert all(d.severity == "warning" for d in result.diagnostics)


def test_tool_with_parallel_workers() -> None:
    parallel = MaudeExecutor(settings=Settings(maude_workers=2))
    parallel.start()
    try:
        result = _diagnose(parallel, "broken-recoverable.maude")
        assert result.success is False
        assert result.summary.warning == 1
    finally:
        parallel.shutdown()


def test_tool_reports_crash_and_recovers() -> None:
    executor = MaudeExecutor(settings=Settings(maude_workers=1))
    executor.start()
    try:
        with pytest.raises(BrokenProcessPool):
            executor.submit(worker._crash).result(timeout=60)

        # The first call after the crash reports it (and replaces the pool);
        # the client retries, and the next call succeeds.
        with pytest.raises(MaudeWorkerCrashedError):
            _diagnose(executor, "hello.maude")
        result = _diagnose(executor, "hello.maude")
        assert result.success is True
    finally:
        executor.shutdown()


def _recv(proc: subprocess.Popen, req_id: int, timeout: float = 30.0) -> dict:
    """Read JSON-RPC lines from the server until the response with `req_id` arrives."""
    assert proc.stdout is not None
    while True:
        ready, _, _ = select.select([proc.stdout], [], [], timeout)
        if not ready:
            raise TimeoutError("timeout")
        message = json.loads(proc.stdout.readline())
        if message.get("id") == req_id:
            return message


def _send(proc: subprocess.Popen, message: dict) -> None:
    assert proc.stdin is not None
    proc.stdin.write(json.dumps(message) + "\n")
    proc.stdin.flush()


def test_mcp_smoke() -> None:
    """The tool is served over MCP stdio with schema `{path}`, metadata, and structured results (R18.1)."""
    proc = subprocess.Popen(
        [sys.executable, "-m", "harold_mcp.main"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=REPO_ROOT,
    )
    try:
        _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "pytest-smoke", "version": "0"},
                },
            },
        )
        _recv(proc, 1)
        _send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

        _send(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tools = _recv(proc, 2)["result"]["tools"]
        assert [tool["name"] for tool in tools] == ["maude_program_diagnostics"]
        assert sorted(tools[0]["inputSchema"]["properties"]) == ["path"]

        # Client-visible annotations: the read-only/idempotent/closed-world profile
        # (note `destructiveHint` defaults to true and must be negated explicitly).
        # Tags are not asserted here: with mcp SDK 1.29 (spec 2025-06-18) they are a
        # server-side categorization for visibility control (`mcp.disable(tags=...)`)
        # and are not serialized to clients; see tests/unit/test_tags.py for the
        # vocabulary itself.
        annotations = tools[0]["annotations"]
        assert annotations["readOnlyHint"] is True
        assert annotations["destructiveHint"] is False
        assert annotations["idempotentHint"] is True
        assert annotations["openWorldHint"] is False

        _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "maude_program_diagnostics",
                    "arguments": {"path": str(FIXTURES_DIR / "hello.maude")},
                },
            },
        )
        response = _recv(proc, 3)
        assert response["result"].get("isError") is not True
        text = response["result"]["content"][0]["text"]
        assert json.loads(text)["success"] is True
    finally:
        proc.terminate()
        proc.wait(timeout=15)
