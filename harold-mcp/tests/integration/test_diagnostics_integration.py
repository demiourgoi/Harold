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

from harold_mcp.diagnostics import DiagnosticCollectionError, DiagnosticProviderError
from harold_mcp.maude import MaudeExecutor, MaudeWorkerCrashedError, worker
from harold_mcp.server.tools.diagnostics import (
    MaudeDiagnostic,
    MaudeProgramDiagnosticsResult,
    maude_program_diagnostics,
)
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


@pytest.fixture(scope="module")
def heuristic_executor() -> Iterator[MaudeExecutor]:
    """A dedicated worker for the fixtures the heuristic provider is asserted on.

    Loading `no_new_module.maude` leaves a deferred `q .` syntax error in the Maude
    bindings, which is flushed (and attributed to that file) during the *next* load.
    These tests therefore do not share the worker that loads it.
    """
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
    assert result.summary.info == 0
    assert result.summary.warning == 0
    assert result.summary.error == 0
    assert result.diagnostics == []


def test_recoverable_program(executor: MaudeExecutor) -> None:
    result = _diagnose(executor, "broken-recoverable.maude")
    assert result.success is False
    assert result.summary.info == 0
    assert result.summary.warning == 1
    assert result.summary.error == 0
    assert len(result.diagnostics) == 1
    diagnostic = result.diagnostics[0]
    assert diagnostic.severity == "warning"
    assert diagnostic.source == "interpreter"
    assert diagnostic.code == "compiler"
    assert diagnostic.range is not None and diagnostic.range.start.line == 2
    assert diagnostic.range.start.column is None  # Maude reports no columns
    assert diagnostic.range.end is None
    assert diagnostic.fix is None
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
    assert all(d.source == "interpreter" and d.code == "compiler" for d in result.diagnostics)


def test_program_without_modules(executor: MaudeExecutor) -> None:
    result = _diagnose(executor, "no_new_module.maude")
    assert result.success is True
    assert result.diagnostics == []


def test_non_ascii_apostrophe_reports_info_with_a_fix(heuristic_executor: MaudeExecutor) -> None:
    """Rule 1 positive: the interpreter is silent, the heuristic fixes a typographic paste."""
    result = _diagnose(heuristic_executor, "nonascii_apostrophe.maude")

    assert result.success is True  # info-only results succeed (LP8)
    assert result.summary.info == 1
    assert result.summary.warning == 0
    assert result.summary.error == 0
    assert [d.source for d in result.diagnostics] == ["heuristic-linter"]  # interpreter silent
    diagnostic = result.diagnostics[0]
    assert diagnostic.code == "non-ascii-character"
    assert diagnostic.severity == "info"
    assert diagnostic.range is not None
    assert diagnostic.range.start.line == 3
    assert diagnostic.range.start.column == 9
    assert diagnostic.range.end is not None and diagnostic.range.end.column == 10  # exclusive
    assert diagnostic.fix is not None
    assert len(diagnostic.fix.edits) == 1
    edit = diagnostic.fix.edits[0]
    assert (edit.range.start.line, edit.range.start.column, edit.range.end.column) == (3, 9, 10)
    assert edit.new_text == "'"  # applying it turns the file into ASCII


def test_string_with_specials_is_clean(heuristic_executor: MaudeExecutor) -> None:
    """Rules 1-4 must not fire inside a string literal (`when`, `--`, `=` and `café` are literal text)."""
    result = _diagnose(heuristic_executor, "string_with_specials.maude")

    assert result.success is True
    assert result.diagnostics == []


def _heuristic_diagnostics(result: MaudeProgramDiagnosticsResult) -> list[MaudeDiagnostic]:
    return [diagnostic for diagnostic in result.diagnostics if diagnostic.source == "heuristic-linter"]


def _interpreter_diagnostics(result: MaudeProgramDiagnosticsResult) -> list[MaudeDiagnostic]:
    return [diagnostic for diagnostic in result.diagnostics if diagnostic.source == "interpreter"]


def _span(diagnostic: MaudeDiagnostic) -> tuple[int, int | None, int | None]:
    assert diagnostic.range is not None
    end = diagnostic.range.end
    return (diagnostic.range.start.line, diagnostic.range.start.column, end.column if end is not None else None)


def test_when_guard_is_reported_alongside_the_interpreter_warnings(heuristic_executor: MaudeExecutor) -> None:
    """Rule 2 positive: the Haskell/SML guard the interpreter reports as `bad token when`."""
    result = _diagnose(heuristic_executor, "when_guard.maude")

    assert result.success is False
    heuristic = _heuristic_diagnostics(result)
    assert [diagnostic.code for diagnostic in heuristic] == ["when-guard"]
    assert heuristic[0].severity == "warning"
    assert _span(heuristic[0]) == (23, 58, 62)
    assert _interpreter_diagnostics(result)  # Maude reports the same line as a bad token


def test_dash_comment_is_reported(heuristic_executor: MaudeExecutor) -> None:
    """Rule 3 positive: `--` is not a comment delimiter in Maude.

    The fixture also redeclares the prelude's `NeList{X}`/`List{X}` sorts, so it carries
    `prelude-sort-redeclared` findings too — hence the per-code assertions.
    """
    result = _diagnose(heuristic_executor, "dash_comment.maude")

    assert result.success is False
    dash_comments = [diagnostic for diagnostic in _heuristic_diagnostics(result) if diagnostic.code == "dash-comment"]
    assert [_span(diagnostic) for diagnostic in dash_comments] == [(24, 5, 7), (33, 5, 7)]
    assert all(diagnostic.severity == "warning" for diagnostic in dash_comments)
    assert _interpreter_diagnostics(result)


def test_eq_in_if_term_is_reported(heuristic_executor: MaudeExecutor) -> None:
    """Rule 4 positive: a single `=` inside `if … then` is a real parse error."""
    result = _diagnose(heuristic_executor, "eq_in_if.maude")

    assert result.success is False
    heuristic = _heuristic_diagnostics(result)
    assert [diagnostic.code for diagnostic in heuristic] == ["eq-in-term"]
    assert _span(heuristic[0]) == (13, 20, 21)
    assert _interpreter_diagnostics(result)


def test_quoted_identifiers_are_not_reported(heuristic_executor: MaudeExecutor) -> None:
    """Rules 2-3 negative: `'when` and `'--` are valid quoted identifiers."""
    result = _diagnose(heuristic_executor, "quoted_id_when_dash.maude")

    assert result.success is True
    assert result.diagnostics == []


def test_declaration_lines_are_not_reported(heuristic_executor: MaudeExecutor) -> None:
    """Rules 2-3 negative: `op when`/`op _--_` are legal declarations (probes D and E)."""
    result = _diagnose(heuristic_executor, "declarations_when_dash.maude")

    assert result.success is True
    assert result.diagnostics == []


def test_non_linear_pattern_is_reported_while_the_interpreter_is_silent(heuristic_executor: MaudeExecutor) -> None:
    """Rule 5 positive: the heuristic finds a problem Maude accepts (free-tuples.maude)."""
    result = _diagnose(heuristic_executor, "non_linear_pattern.maude")

    assert result.success is False  # the heuristic warning alone makes the result fail
    assert _interpreter_diagnostics(result) == []
    heuristic = _heuristic_diagnostics(result)
    assert [diagnostic.code for diagnostic in heuristic] == ["non-linear-pattern"]
    assert heuristic[0].severity == "warning"
    assert _span(heuristic[0]) == (23, 23, 31)
    assert "`B-ignore` appears 2 times" in heuristic[0].message


def test_undeclared_identifier_is_reported(heuristic_executor: MaudeExecutor) -> None:
    """Rule 6 positive: `Foo` is neither a declared variable, operator nor sort."""
    result = _diagnose(heuristic_executor, "undeclared_identifier.maude")

    assert result.success is False
    heuristic = _heuristic_diagnostics(result)
    assert [diagnostic.code for diagnostic in heuristic] == ["undeclared-identifier"]
    assert _span(heuristic[0]) == (12, 15, 18)
    assert _interpreter_diagnostics(result)


def test_capitalized_labels_operators_and_annotations_are_not_reported(heuristic_executor: MaudeExecutor) -> None:
    """Rule 6 negative: a label, a capitalized operator and `X:List{Nat}` are all legal."""
    result = _diagnose(heuristic_executor, "capitalized_identifiers_ok.maude")

    assert result.success is True
    assert result.diagnostics == []


def test_redeclared_prelude_sort_is_reported_as_info(heuristic_executor: MaudeExecutor) -> None:
    """Rule 7 positive: `sort Qid .` shadows a prelude sort; the load itself is fine."""
    result = _diagnose(heuristic_executor, "redeclare_prelude.maude")

    assert result.success is True  # info-only findings do not fail the result (LP8)
    assert result.summary.info == 1
    assert result.summary.warning == 0
    assert _interpreter_diagnostics(result) == []
    diagnostic = result.diagnostics[0]
    assert diagnostic.source == "heuristic-linter"
    assert diagnostic.code == "prelude-sort-redeclared"
    assert diagnostic.severity == "info"
    assert _span(diagnostic) == (2, 10, 13)
    assert "module QID" in diagnostic.message
    assert diagnostic.fix is None


def test_elt_sort_declaration_is_not_reported(heuristic_executor: MaudeExecutor) -> None:
    """Rule 7 negative: theory interface sorts are excluded from the snapshot (review D6)."""
    result = _diagnose(heuristic_executor, "elt_sort_declaration.maude")

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
    assert all(d.source == "interpreter" for d in result.diagnostics)
    # The lossy decode's U+FFFD never becomes a rule-1 finding.
    assert not [d for d in result.diagnostics if d.code == "non-ascii-character"]


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
        # the client retries, and the next call succeeds. The interpreter's
        # vocabulary reaches the caller as the chained cause (Q11.5).
        with pytest.raises(DiagnosticCollectionError) as exc_info:
            _diagnose(executor, "hello.maude")
        assert str(exc_info.value) == "Diagnostics failed: interpreter (Maude worker crashed)"
        provider_error = exc_info.value.__cause__
        assert isinstance(provider_error, DiagnosticProviderError)
        assert isinstance(provider_error.__cause__, MaudeWorkerCrashedError)
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

        # The description explains both diagnostic sources and their severity meanings.
        description = tools[0]["description"]
        assert '"interpreter"' in description
        assert '"heuristic-linter"' in description
        assert "prelude-sort-redeclared" in description

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
        payload = json.loads(response["result"]["content"][0]["text"])
        assert payload["success"] is True
        assert payload["summary"] == {"info": 0, "warning": 0, "error": 0}

        # A diagnosed file reports the new provenance fields on the wire.
        _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "maude_program_diagnostics",
                    "arguments": {"path": str(FIXTURES_DIR / "broken-recoverable.maude")},
                },
            },
        )
        payload = json.loads(_recv(proc, 4)["result"]["content"][0]["text"])
        assert payload["success"] is False
        assert payload["summary"] == {"info": 0, "warning": 1, "error": 0}
        diagnostic = payload["diagnostics"][0]
        assert diagnostic["source"] == "interpreter"
        assert diagnostic["code"] == "compiler"
        assert diagnostic["fix"] is None

        # An info-only heuristic finding keeps the call successful (LP8).
        _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "maude_program_diagnostics",
                    "arguments": {"path": str(FIXTURES_DIR / "redeclare_prelude.maude")},
                },
            },
        )
        payload = json.loads(_recv(proc, 5)["result"]["content"][0]["text"])
        assert payload["success"] is True
        assert payload["summary"] == {"info": 1, "warning": 0, "error": 0}
        diagnostic = payload["diagnostics"][0]
        assert diagnostic["source"] == "heuristic-linter"
        assert diagnostic["code"] == "prelude-sort-redeclared"
        assert diagnostic["range"]["start"] == {"line": 2, "column": 10}
    finally:
        proc.terminate()
        proc.wait(timeout=15)
