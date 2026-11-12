"""Probe: capture of a bounded `search` step and of a bounded search at EOF.

Attempt 2 reported that a successful `search` step returned its structured
solutions but `output.stdout` was empty, and that the Maude block once surfaced
in a *different* step's stdout. The previous PDD fixed the load-phase flush; this
probe checks whether the same holds for step captures on the current checkout.

Run from ``harold-mcp``::

    UV_CACHE_DIR=/tmp/uv-cache uv run python \
        .agents/planning/more_interpreter_bugs/research/probes/probe_step_output.py
"""

from pathlib import Path

from harold_mcp.maude.executor import MaudeExecutor
from harold_mcp.maude.session import SessionRequest, StepRequest
from harold_mcp.settings import Settings

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def step(**overrides: object) -> StepRequest:
    base = {
        "command": "reduce",
        "term": None,
        "pattern": None,
        "subject": None,
        "bound": None,
        "gas": None,
        "depth": None,
        "search_type": None,
        "path_mode": None,
    }
    base.update(overrides)
    return base  # type: ignore[return-value]


SEARCH_STEP = step(
    command="search",
    subject="a",
    pattern="Z:S",
    search_type="any-steps",
    path_mode="labels",
)


def request(steps: list[StepRequest], *, max_solutions: int) -> SessionRequest:
    return {
        "path": str(FIXTURES / "step_output.maude"),
        "module": "STEPS",
        "steps": steps,
        "max_solutions": max_solutions,
        "max_result_length": 1_000_000,
        "max_path_steps": 100,
        "max_output_length": 1_000_000,
    }


def show(name: str, result) -> None:  # noqa: ANN001 - probe script
    print(f"\n== {name} ==")
    print("load stdout:", repr(result["load_output"]["stdout"]))
    print("load stderr:", repr(result["load_output"]["stderr"]))
    for outcome in result["outcomes"]:
        print(
            f"step {outcome['index']} {outcome['command']}: status={outcome['status']} "
            f"solutions={len(outcome['solutions'] or [])} truncated={outcome['truncated']}"
        )
        print("   stdout:", repr(outcome["output"]["stdout"]))
        print("   stderr:", repr(outcome["output"]["stderr"]))


def main() -> None:
    executor = MaudeExecutor(Settings(maude_workers=1))
    try:
        show(
            "bounded search capped at 1 solution, then reduce",
            executor.run_session(request([SEARCH_STEP, step(command="reduce", term="a")], max_solutions=1), timeout=60),
        )
        show(
            "bounded search capped at 1 solution, last step",
            executor.run_session(request([SEARCH_STEP], max_solutions=1), timeout=60),
        )
        show(
            "exhaustive search (No more solutions), then reduce",
            executor.run_session(request([SEARCH_STEP, step(command="reduce", term="a")], max_solutions=10), timeout=60),
        )
        show(
            "two bounded searches in a row",
            executor.run_session(request([SEARCH_STEP, SEARCH_STEP], max_solutions=1), timeout=60),
        )
        show(
            "parse-error step, then a healthy reduce",
            executor.run_session(
                request([step(command="reduce", term="doesNotExist("), step(command="reduce", term="a")], max_solutions=1),
                timeout=60,
            ),
        )
    finally:
        executor.shutdown()


if __name__ == "__main__":
    main()
