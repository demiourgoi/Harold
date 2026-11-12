"""Probe: load/step output tails are lost when libmaude's stdio buffer is not flushed.

Research artifact for `.agents/planning/Unexpected_failure_during_search/`; it lives
outside `tests/`, so the normal test suite does not collect it. Run it explicitly:

    uv run python -m pytest \
        .agents/planning/Unexpected_failure_during_search/research/probes/test_load_output_truncation.py \
        -q -s

Before the fix, `test_a_bounded_search_last` captured only the search header (the
solution was flushed after the capture ended) and `test_f_...` found those bytes on the
worker's inherited stdout. With the capture flush in place, these probes assert the
post-fix behavior: the solution is in `load_output` and nothing leaks.
"""

import os
import tempfile
from pathlib import Path
from typing import Any

from harold_mcp.maude.executor import MaudeExecutor
from harold_mcp.maude.session import SessionRequest, SessionResult
from harold_mcp.settings import Settings


def _probe(tmp_path: Path, trailing: str) -> Path:
    path = tmp_path / "probe.maude"
    path.write_text(
        "mod PROBE is\n"
        "  sort S .\n"
        "  ops a b c : -> S [ctor] .\n"
        "  rl [step] : a => b .\n"
        "endm\n"
        "\n"
        f"{trailing}\n"
    )
    return path


def _request(path: Path, steps: list[dict[str, Any]] | None = None) -> SessionRequest:
    settings = Settings()
    return {
        "path": str(path),
        "module": "PROBE",
        "steps": steps or [],
        "max_solutions": settings.interpreter_max_solutions,
        "max_result_length": settings.interpreter_max_result_length,
        "max_path_steps": settings.interpreter_max_path_steps,
        "max_output_length": settings.interpreter_max_output_length,
    }


def _run(request: SessionRequest) -> SessionResult:
    executor = MaudeExecutor(Settings())
    try:
        return executor.run_session(request, timeout=30)
    finally:
        executor.shutdown()


def _show(label: str, result: SessionResult) -> None:
    print(f"\n===== {label} =====")
    print("LOAD STDOUT:", repr(result["load_output"]["stdout"]))
    for outcome in result["outcomes"]:
        print(f"STEP {outcome['index']} STDOUT:", repr(outcome["output"]["stdout"]))


def test_a_bounded_search_last(tmp_path: Path) -> None:
    result = _run(_request(_probe(tmp_path, "search [1] a =>* Z:S .")))
    _show("search [1] last", result)
    assert "Solution 1" in result["load_output"]["stdout"]
    assert "Z:S --> a" in result["load_output"]["stdout"]


def test_b_unreached_bound_last(tmp_path: Path) -> None:
    _show("search [5] last", _run(_request(_probe(tmp_path, "search [5] a =>* Z:S ."))))


def test_c_reduce_last(tmp_path: Path) -> None:
    _show("reduce last", _run(_request(_probe(tmp_path, "reduce c ."))))


def test_d_bounded_search_then_step(tmp_path: Path) -> None:
    path = _probe(tmp_path, "search [1] a =>* Z:S .")
    step: dict[str, Any] = {
        "command": "reduce",
        "term": "c",
        "pattern": None,
        "subject": None,
        "bound": None,
        "gas": None,
        "depth": None,
        "search_type": None,
        "path_mode": None,
    }
    _show("search [1] last + reduce step", _run(_request(path, [step])))


def test_e_repeat_bounded_search_last(tmp_path: Path) -> None:
    for attempt in range(5):
        result = _run(_request(_probe(tmp_path, "search [1] a =>* Z:S .")))
        captured = result["load_output"]["stdout"]
        print(f"attempt {attempt}: solution_in_load={'Solution 1' in captured!r}")
        assert "Solution 1" in captured


def test_f_no_leftover_flush_to_inherited_stdout(tmp_path: Path) -> None:
    request = _request(_probe(tmp_path, "search [1] a =>* Z:S ."))
    with tempfile.TemporaryFile(mode="w+b") as sink:
        saved_stdout = os.dup(1)
        try:
            _ = os.dup2(sink.fileno(), 1)
            result = _run(request)
        finally:
            _ = os.dup2(saved_stdout, 1)
            os.close(saved_stdout)
        _ = sink.seek(0)
        leaked = sink.read().decode("utf-8", errors="replace")
    print(f"\nLEAKED TO INHERITED STDOUT: {leaked!r}")
    print(f"CAPTURED IN LOAD OUTPUT: {result['load_output']['stdout']!r}")
    assert "Solution 1" in result["load_output"]["stdout"]
    assert "Solution 1" not in leaked
