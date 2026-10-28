"""Interpreter tool: run a bounded Maude session (`maude_run`).

Runs in the MCP server process: it resolves the input path, validates the request,
builds the worker request, and adapts the worker result to the wire models. The
interpreter itself only lives in the worker process; this module never imports the
`maude` SWIG bindings.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Literal, cast

from fastmcp.dependencies import Depends
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from harold_mcp.maude import (
    BindingDict,
    CapturedOutput,
    CommandName,
    MaudeExecutor,
    MaudeWorkerError,
    SessionRequest,
    SessionResult,
    SolutionDict,
    StepOutcomeDict,
    StepRequest,
    StepStatus,
    WarningDict,
    get_maude_executor,
)
from harold_mcp.server.server import mcp
from harold_mcp.server.tags import INTERPRETER, harold_tags
from harold_mcp.settings import Settings, get_settings

# `maude.Module` theory types: FUNCTIONAL_THEORY, SYSTEM_THEORY, STRATEGY_THEORY and
# OBJECT_ORIENTED_THEORY. Spelled out because the server process never imports `maude`.
_THEORY_MODULE_TYPES = frozenset({2, 3, 7, 11})


class MaudeRunError(RuntimeError):
    """Whole-call failure of `maude_run`.

    Missing or unreadable path, a load that fails outright, a module that is not
    defined after the load, a theory module, or a worker crash/timeout. `MaudeError`
    causes are chained.
    """


class _ResultModel(BaseModel):
    """Base for the tool input and result models.

    Attribute docstrings are promoted to JSON Schema field descriptions, so they
    reach MCP clients through the tool schemas.
    """

    model_config = ConfigDict(use_attribute_docstrings=True)


class _StepBase(_ResultModel):
    """Fields shared by every step command."""

    term: str | None = None
    """Term text; omitted means the current term (invalid for the first step)."""


class _BoundedStep(_StepBase):
    """Fields shared by the rewriting commands that accept a rewrite bound."""

    bound: Annotated[int | None, Field(ge=0)] = None
    """Maximum rule rewrites; omitted means unbounded (the interpreter default)."""


class _GassedStep(_BoundedStep):
    """Fields shared by the rewriting commands that accept a per-position gas."""

    gas: Annotated[int | None, Field(ge=0)] = None
    """Maximum rule rewrites per position; omitted means the bindings' default."""


class ReduceStep(_StepBase):
    """Reduce a term to normal form with the module's equations."""

    command: Literal["reduce"]
    """The command to execute."""


class RewriteStep(_BoundedStep):
    """Rewrite a term with the default strategy, up to `bound` rule rewrites."""

    command: Literal["rewrite"]
    """The command to execute."""


class FrewriteStep(_GassedStep):
    """Rewrite a term with the fair strategy, with an optional per-position gas."""

    command: Literal["frewrite"]
    """The command to execute."""


class ErewriteStep(_GassedStep):
    """Rewrite like `frewrite`, with external-object support; the original term is kept."""

    command: Literal["erewrite"]
    """The command to execute."""


class _PatternStep(_ResultModel):
    """Fields shared by the pattern commands (`match`, `search`)."""

    pattern: str
    """Pattern text to match against the subject (or the search target)."""

    subject: str | None = None
    """Subject term text; omitted means the current term."""

    depth: int | None = None
    """Maude's matching/search depth: -1 = on top without extension, 0 = on top with
    extension, 2147483647 = anywhere in the term; omitted means -1."""


class MatchStep(_PatternStep):
    """Match `pattern` against the subject and return the substitutions."""

    command: Literal["match"]
    """The command to execute."""


class SearchStep(_PatternStep):
    """Search from the subject for states matching `pattern`."""

    command: Literal["search"]
    """The command to execute."""

    search_type: Literal["one-step", "at-least-one-step", "any-steps", "normal-form", "branch"]
    """The Maude search type: `=>1`, `=>+`, `=>*`, `=>!` or `=>#`."""


MaudeStep = Annotated[
    ReduceStep | RewriteStep | FrewriteStep | ErewriteStep | MatchStep | SearchStep,
    Field(discriminator="command"),
]
"""Input steps: a tagged union on `command`."""


class MaudeCapturedOutput(_ResultModel):
    """Captured interpreter output for one phase (load or step)."""

    stdout: str
    """Standard output, with ANSI color codes stripped and truncated to the configured limit."""

    stderr: str
    """Standard error, with ANSI color codes stripped and truncated to the configured limit."""


class MaudeLoadWarning(_ResultModel):
    """A warning Maude printed while loading the file."""

    file: str
    """The file the warning belongs to, as Maude printed it (the file, a dependency, or `<standard input>`)."""

    line: int
    """1-based line number Maude reported."""

    message: str
    """The warning text."""


class MaudeLoadInfo(_ResultModel):
    """What happened while loading the file (evaluation still proceeds after warnings)."""

    warnings: list[MaudeLoadWarning]
    """Warnings Maude printed while loading the file and its dependencies."""

    output: MaudeCapturedOutput
    """Output captured during the load (including commands embedded in the file)."""


class MaudeBinding(_ResultModel):
    """One variable binding in a match or search solution."""

    variable: str
    """The variable name Maude printed (usually just the base name; see the probe notes)."""

    value: str
    """The term the variable is bound to."""


class MaudeMatch(_ResultModel):
    """One substitution produced by a `match` step."""

    bindings: list[MaudeBinding]
    """The variable/value pairs of the substitution (empty for a ground match)."""


class MaudeSearchSolution(_ResultModel):
    """One solution produced by a `search` step."""

    term: str
    """The state the search reached."""

    rewrites: int
    """The interpreter's rewrite counter for this solution (includes equational rewrites)."""

    bindings: list[MaudeBinding]
    """The variable/value pairs that make the target match this state."""


class MaudeStepOutcome(_ResultModel):
    """The outcome of one executed step."""

    index: int
    """0-based position of the step in the input list."""

    command: CommandName
    """The command that produced this outcome."""

    status: StepStatus
    """`"ok"`, `"parse-error"` (the term did not parse), or `"too-large"` (the result exceeded the limit)."""

    term: str | None
    """The result term (`"ok"` only)."""

    rewrites: int | None
    """The interpreter's rewrite counter (`"ok"` only); it includes equational rewrites, so it is
    not the number of rule applications."""

    matches: list[MaudeMatch] | None
    """The substitutions found by a `match` step (`"ok"` only)."""

    solutions: list[MaudeSearchSolution] | None
    """The solutions found by a `search` step (`"ok"` only)."""

    truncated: bool | None
    """`true` when a `match`/`search` hit the configured solution cap (`"ok"` only)."""

    message: str | None
    """The interpreter's message (`"parse-error"` only)."""

    limit: int | None
    """The exceeded limit (`"too-large"` only)."""

    output: MaudeCapturedOutput
    """Output captured while executing this step."""


class MaudeRunResult(_ResultModel):
    """Result of a bounded interpreter session."""

    path: str
    """The input file path, made absolute (`Path.resolve()`)."""

    module: str
    """The requested module name."""

    load: MaudeLoadInfo
    """Load-time warnings and captured output."""

    completed: bool
    """`true` when every requested step produced `"ok"`."""

    steps: list[MaudeStepOutcome]
    """One entry per executed step; shorter than the request when a step failed (the run stops)."""


def _resolve_path(path: str) -> Path:
    """Resolve the input path and require an existing regular file.

    Implemented locally rather than through `diagnostics.SourceFile`: the new tool
    must not depend on the diagnostics seam (the interpreter tool loads the file, it
    does not read it). Resolution matters because the worker's working directory is
    not the client's.
    """
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise MaudeRunError(f"Maude program file not found or unreadable: {str(resolved)!r}")  # noqa: TRY003
    return resolved


def _validate_step_lengths(index: int, step: MaudeStep, max_length: int) -> None:
    """Reject a step input longer than the configured term-length cap."""
    if isinstance(step, _PatternStep):
        for field_name, value in (("pattern", step.pattern), ("subject", step.subject)):
            if value is not None and len(value) > max_length:
                raise MaudeRunError(  # noqa: TRY003
                    f"Step {index}: {field_name} is {len(value)} characters long (maximum {max_length})"
                )
    elif step.term is not None and len(step.term) > max_length:
        raise MaudeRunError(  # noqa: TRY003
            f"Step {index}: term is {len(step.term)} characters long (maximum {max_length})"
        )


def _validate_step_threading(index: int, step: MaudeStep, has_current: bool) -> bool:
    """Reject a step without a subject, and report whether a current term now exists.

    Rewriting commands need a term and produce one; `match`/`search` need a subject and
    leave the current term unchanged.
    """
    if isinstance(step, _PatternStep):
        if step.subject is None and not has_current:
            raise MaudeRunError(  # noqa: TRY003
                f"Step {index} has no subject and there is no current term: provide an explicit subject for this step"
            )
        return has_current
    if step.term is None and not has_current:
        raise MaudeRunError(  # noqa: TRY003
            f"Step {index} has no term and there is no current term: provide an explicit term for this step"
        )
    return True


def _validate_steps(steps: Sequence[MaudeStep], settings: Settings) -> None:
    """Enforce the input caps and the current-term threading rules."""
    if not steps:
        raise MaudeRunError("steps must contain at least one command")  # noqa: TRY003
    if len(steps) > settings.interpreter_max_steps:
        raise MaudeRunError(  # noqa: TRY003
            f"Too many steps: {len(steps)} (maximum {settings.interpreter_max_steps})"
        )
    max_length = settings.interpreter_max_term_length
    has_current = False
    for index, step in enumerate(steps):
        _validate_step_lengths(index, step, max_length)
        if (
            isinstance(step, _BoundedStep)
            and step.bound is not None
            and step.bound > settings.interpreter_max_rewrite_bound
        ):
            raise MaudeRunError(  # noqa: TRY003
                f"Step {index}: bound is {step.bound} (maximum {settings.interpreter_max_rewrite_bound})"
            )
        has_current = _validate_step_threading(index, step, has_current)


def _to_step_request(step: MaudeStep) -> StepRequest:
    """Map one wire step to the worker-side flat request shape."""
    return {
        "command": step.command,
        "term": step.term if isinstance(step, _StepBase) else None,
        "pattern": step.pattern if isinstance(step, _PatternStep) else None,
        "subject": step.subject if isinstance(step, _PatternStep) else None,
        "bound": step.bound if isinstance(step, _BoundedStep) else None,
        "gas": step.gas if isinstance(step, _GassedStep) else None,
        "depth": step.depth if isinstance(step, _PatternStep) else None,
        "search_type": step.search_type if isinstance(step, SearchStep) else None,
    }


def _to_request(path: Path, module: str, steps: Sequence[MaudeStep], settings: Settings) -> SessionRequest:
    """Build the worker request, carrying the configured caps."""
    return {
        "path": str(path),
        "module": module,
        "steps": [_to_step_request(step) for step in steps],
        "max_solutions": settings.interpreter_max_solutions,
        "max_result_length": settings.interpreter_max_result_length,
        "max_output_length": settings.interpreter_max_output_length,
    }


def _to_output(captured: CapturedOutput) -> MaudeCapturedOutput:
    """Adapt a worker capture to the wire model."""
    return MaudeCapturedOutput(stdout=captured["stdout"], stderr=captured["stderr"])


def _to_load_warning(warning: WarningDict) -> MaudeLoadWarning:
    """Adapt a parsed warning; `parse_warnings` only emits positioned warnings today."""
    return MaudeLoadWarning(
        file=warning["file"],
        line=cast(int, warning["line"]),
        message=warning["message"],
    )


def _to_bindings(bindings: list[BindingDict]) -> list[MaudeBinding]:
    """Adapt worker bindings to the wire model."""
    return [MaudeBinding(variable=binding["variable"], value=binding["value"]) for binding in bindings]


def _to_matches(matches: list[list[BindingDict]]) -> list[MaudeMatch]:
    """Adapt worker match substitutions to the wire model."""
    return [MaudeMatch(bindings=_to_bindings(bindings)) for bindings in matches]


def _to_solutions(solutions: list[SolutionDict]) -> list[MaudeSearchSolution]:
    """Adapt worker search solutions to the wire model."""
    return [
        MaudeSearchSolution(
            term=solution["term"],
            rewrites=solution["rewrites"],
            bindings=_to_bindings(solution["bindings"]),
        )
        for solution in solutions
    ]


def _to_step_outcome(outcome: StepOutcomeDict) -> MaudeStepOutcome:
    """Adapt one worker outcome to the wire model."""
    return MaudeStepOutcome(
        index=outcome["index"],
        command=outcome["command"],
        status=outcome["status"],
        term=outcome["term"],
        rewrites=outcome["rewrites"],
        matches=_to_matches(outcome["matches"]) if outcome["matches"] is not None else None,
        solutions=_to_solutions(outcome["solutions"]) if outcome["solutions"] is not None else None,
        truncated=outcome["truncated"],
        message=outcome["message"],
        limit=outcome["limit"],
        output=_to_output(outcome["output"]),
    )


def _defined_modules_detail(defined_modules: Sequence[str]) -> str:
    """Render the modules a load defined for a whole-call error message."""
    return ", ".join(defined_modules) if defined_modules else "none"


def _to_wire_result(result: SessionResult, path: Path, module: str) -> MaudeRunResult:
    """Reject whole-call failures and adapt a successful session result.

    Per-step failures are data and do not raise; the load/module/type checks are the
    whole-call conditions from the design.
    """
    if not result["load_ok"]:
        detail = result["load_output"]["stderr"].strip()
        suffix = f": {detail}" if detail else ""
        raise MaudeRunError(f"Failed to load the Maude program {str(path)!r}{suffix}")  # noqa: TRY003
    if not result["module_found"]:
        defined = _defined_modules_detail(result["defined_modules"])
        raise MaudeRunError(  # noqa: TRY003
            f'Module "{module}" is not defined by "{path}" '
            f"(modules defined by the load: {defined}). "
            "Run maude_program_diagnostics on the file if the load did not behave as expected."
        )
    if result["module_type"] in _THEORY_MODULE_TYPES:
        raise MaudeRunError(  # noqa: TRY003
            f'Module "{module}" is a theory: terms cannot be parsed in a theory; '
            "select a functional or system module instead."
        )
    return MaudeRunResult(
        path=str(path),
        module=module,
        load=MaudeLoadInfo(
            warnings=[_to_load_warning(warning) for warning in result["warnings"]],
            output=_to_output(result["load_output"]),
        ),
        completed=all(outcome["status"] == "ok" for outcome in result["outcomes"]),
        steps=[_to_step_outcome(outcome) for outcome in result["outcomes"]],
    )


@mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    tags=harold_tags(INTERPRETER),
)
def maude_run(
    path: str,
    module: str,
    steps: Annotated[list[MaudeStep], Field(min_length=1)],
    timeout_secs: Annotated[int | None, Field(gt=0)] = None,
    executor: MaudeExecutor = Depends(get_maude_executor),  # noqa: B008 - FastMCP dependency-injection convention
    settings: Settings = Depends(get_settings),  # noqa: B008 - FastMCP dependency-injection convention
) -> MaudeRunResult:
    # FastMCP uses only the free-form text above `Args:` as the MCP tool description;
    # sections like `Returns`, `Raises`, and `Example` are excluded from the
    # description (https://gofastmcp.com/servers/tools#docstring-descriptions), so
    # everything a client needs belongs in the prose above `Args:`.
    """Run a bounded Maude interpreter session: load one Maude file into a fresh
    interpreter, select a module, and execute an ordered list of interpreter commands,
    returning every intermediate result.

    Each call is hermetic. A new interpreter process loads the file from scratch, so
    nothing (loaded modules, the current term, parser state) survives from one call to
    the next. To carry state across calls, save a term from a result and pass it as the
    term or subject of a later call, or write a wrapper module whose equations and rules
    compute everything in one load.

    The `path` argument must be an absolute path: a relative path is resolved against
    the server's working directory, which is not the client's, so it would usually point
    at the wrong file.

    The file's load/in commands pull in its dependencies automatically (they resolve
    against the file's own directory), so pass only the main file.

    Steps and the current term
    --------------------------
    Commands run as in the Maude interpreter on a current term that threads through the
    pipeline: when a step omits its term or subject, it uses the previous step's result.
    `reduce`, `rewrite`, `frewrite` and `erewrite` replace the current term with their
    result; `match` and `search` inspect the current term and leave it unchanged. The
    first step must provide an explicit term (or subject), because the session starts
    with no current term.

    Commands
    --------
    - `reduce`: reduce the term to normal form with the module's equations.
    - `rewrite`: apply rewrite rules with the default strategy, up to `bound` rule
      rewrites (unbounded when omitted).
    - `frewrite`: the same with the fair strategy; `gas` bounds rewrites per position.
    - `erewrite`: the same as `frewrite` with external-object support; the original term
      is kept.
    - `match`: match `pattern` against the current term (or `subject`) and return the
      substitutions; `depth` is Maude's matching depth (-1 = on top without extension,
      0 = on top with extension, 2147483647 = anywhere in the term).
    - `search`: search from the current term (or `subject`) for states matching `pattern`
      using `search_type` (one-step, at-least-one-step, any-steps, normal-form, branch)
      and an optional `depth`.

    Load problems and step failures
    -------------------------------
    Warnings produced while loading the file (and its dependencies) are reported in
    `load`, but evaluation still proceeds; use maude_program_diagnostics for a full
    diagnosis.

    Steps stop at the first failure: `parse-error` when a term, pattern or subject does
    not parse in the module, `too-large` when a result exceeds the configured length
    limit. The result keeps the outcomes of every executed step and sets `completed` to
    false; the remaining steps are not run. A missing path, a load that fails outright,
    a module that is not defined after the load, a theory module, or a worker
    crash/timeout fails the whole call.

    Output and limits
    -----------------
    The load phase and every step report the interpreter's captured stdout and stderr
    (color codes stripped; a stream longer than the configured output limit is truncated
    and marked). A search step returns at most the configured number of solutions and a
    match step at most the configured number of substitutions; `truncated` is true when
    the cap was reached. The whole call is bounded by timeout_secs (default: the server's
    interpreter timeout). The timeout covers interpreter startup and is best effort: a
    non-terminating reduction fails the call and replaces the worker pool, so allow more
    time for long evaluations.

    Args:
        path: Absolute path to the Maude source file to load (typically `.maude`). Pass
            an absolute path: a relative path would be resolved against the server's
            working directory, which is not the client's.
        module: Name of the module to evaluate in; it must be defined by the file or
            one of its dependencies. Case-sensitive; a theory cannot be used because
            terms are parsed in modules.
        steps: Ordered commands to execute; each is a tagged object with `command`
            plus its payload (see Commands).
        timeout_secs: Optional per-call timeout in seconds, overriding the server
            setting.
    """
    resolved = _resolve_path(path)
    _validate_steps(steps, settings)
    request = _to_request(resolved, module, steps, settings)
    timeout = timeout_secs if timeout_secs is not None else settings.interpreter_timeout_secs
    try:
        result = executor.run_session(request, timeout=timeout)
    except MaudeWorkerError as exc:
        raise MaudeRunError(f"Maude interpreter session failed: {exc.reason}") from exc  # noqa: TRY003
    except Exception as exc:
        raise MaudeRunError("Unexpected failure running the Maude interpreter session") from exc  # noqa: TRY003
    return _to_wire_result(result, resolved, module)


__all__ = [
    "ErewriteStep",
    "FrewriteStep",
    "MatchStep",
    "MaudeBinding",
    "MaudeCapturedOutput",
    "MaudeLoadInfo",
    "MaudeLoadWarning",
    "MaudeMatch",
    "MaudeRunError",
    "MaudeRunResult",
    "MaudeSearchSolution",
    "MaudeStep",
    "MaudeStepOutcome",
    "ReduceStep",
    "RewriteStep",
    "SearchStep",
    "maude_run",
]
