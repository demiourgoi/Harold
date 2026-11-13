"""Interpreter tool: run a bounded Maude session (`maude_run`).

Runs in the MCP server process: it resolves the input path, validates the request,
builds the worker request, and adapts the worker result to the wire models. The
interpreter itself only lives in the worker process; this module never imports the
`maude` SWIG bindings.
"""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Annotated, Literal, cast

from fastmcp.dependencies import Depends
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from harold_mcp.errors import format_context, format_error_report
from harold_mcp.logging import get_logger
from harold_mcp.maude import (
    BindingDict,
    CapturedOutput,
    CommandName,
    MaudeExecutor,
    MaudeWorkerError,
    PathDict,
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

_log = get_logger(__name__)

# `maude.Module` theory types: FUNCTIONAL_THEORY, SYSTEM_THEORY, STRATEGY_THEORY and
# OBJECT_ORIENTED_THEORY. Spelled out because the server process never imports `maude`.
_THEORY_MODULE_TYPES = frozenset({2, 3, 7, 11})

# Maude's `UNBOUNDED` depth: the maximum C `int`. Spelled out (rather than
# `sys.maxsize`, which is the platform word size) because the server process never
# imports `maude` and the SWIG parameters are C ints.
_MAUDE_UNBOUNDED_DEPTH = 2**31 - 1


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

    depth: Annotated[int | None, Field(ge=-1, le=_MAUDE_UNBOUNDED_DEPTH)] = None
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

    path: Literal["none", "labels", "full"] = "labels"
    """How much of each solution's rewrite path to return: `"labels"` (the rule
    sequence, the default), `"full"` (also the rule text and intermediate states),
    or `"none"`."""


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


class MaudeRuleRef(_ResultModel):
    """The rule applied in one path transition."""

    label: str | None
    """The rule's label; `null` when the rule has no label."""

    text: str | None
    """The full rule statement; `null` unless the step requested `path="full"`."""


class MaudePathTransition(_ResultModel):
    """One transition of a search path: the rule applied and the state it produced."""

    rule: MaudeRuleRef
    """The rule that produced this state."""

    state: str | None
    """The state the transition produced; `null` unless the step requested `path="full"`."""


class MaudeSearchPath(_ResultModel):
    """The rewrite path from the search subject to a solution."""

    initial: str
    """The search subject the path started from."""

    transitions: list[MaudePathTransition]
    """The ordered rule applications leading to the solution (empty for a reflexive or
    branching zero-transition path)."""


class MaudeSearchSolution(_ResultModel):
    """One solution produced by a `search` step."""

    term: str
    """The state the search reached."""

    rewrites: int
    """The interpreter's rewrite counter for this solution (includes equational rewrites)."""

    bindings: list[MaudeBinding]
    """The variable/value pairs that make the target match this state."""

    path: MaudeSearchPath | None
    """The rewrite path from the search subject to this state; `null` when the step
    requested `path="none"`. A path always exists for a search solution."""


class MaudeStepOutcome(_ResultModel):
    """The outcome of one executed step."""

    index: int
    """0-based position of the step in the input list."""

    command: CommandName
    """The command that produced this outcome."""

    status: StepStatus
    """`"ok"`, `"parse-error"` (a term, pattern or subject did not parse), or `"too-large"`
    (the result exceeded the limit)."""

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
    """The interpreter's message (`"parse-error"`), or Harold's reason for exceeding a
    limit (`"too-large"`), naming the setting to raise."""

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
    """Resolve the input path (the worker's working directory is not the client's).

    Implemented locally rather than through `diagnostics.SourceFile`: the interpreter
    tool loads the file, it does not read it, and it must not depend on the
    diagnostics seam.
    """
    return Path(path).expanduser().resolve()


def _require_file(resolved: Path, context: Mapping[str, object]) -> None:
    """Reject a missing or non-regular input file before any worker is spawned."""
    if not resolved.is_file():
        raise MaudeRunError(_with_context(f"Maude program file not found or unreadable: {str(resolved)!r}", context))


def _call_context(resolved: Path, module: str, steps: Sequence[MaudeStep], timeout: int) -> dict[str, object]:
    """The context line shared by every whole-call failure of this invocation."""
    return {"path": str(resolved), "module": module, "steps": len(steps), "timeout": f"{timeout}s"}


def _with_context(message: str, context: Mapping[str, object]) -> str:
    """Append the call-context line to a whole-call input error message."""
    rendered = format_context(context)
    return f"{message}\ncontext: {rendered}" if rendered is not None else message


def _validate_step_lengths(index: int, step: MaudeStep, max_length: int, context: Mapping[str, object]) -> None:
    """Reject a step input longer than the configured term-length cap."""
    if isinstance(step, _PatternStep):
        for field_name, value in (("pattern", step.pattern), ("subject", step.subject)):
            if value is not None and len(value) > max_length:
                raise MaudeRunError(
                    _with_context(
                        f"Step {index}: {field_name} is {len(value)} characters long (maximum {max_length})",
                        context,
                    )
                )
    elif step.term is not None and len(step.term) > max_length:
        raise MaudeRunError(
            _with_context(f"Step {index}: term is {len(step.term)} characters long (maximum {max_length})", context)
        )


def _validate_step_threading(
    index: int,
    step: MaudeStep,
    has_current: bool,
    context: Mapping[str, object],
) -> bool:
    """Reject a step without a subject, and report whether a current term now exists.

    Rewriting commands need a term and produce one; `match`/`search` need a subject and
    leave the current term unchanged.
    """
    if isinstance(step, _PatternStep):
        if step.subject is None and not has_current:
            raise MaudeRunError(
                _with_context(
                    f"Step {index} has no subject and there is no current term: "
                    "provide an explicit subject for this step",
                    context,
                )
            )
        return has_current
    if step.term is None and not has_current:
        raise MaudeRunError(
            _with_context(
                f"Step {index} has no term and there is no current term: provide an explicit term for this step",
                context,
            )
        )
    return True


def _validate_steps(steps: Sequence[MaudeStep], settings: Settings, context: Mapping[str, object]) -> None:
    """Enforce the input caps and the current-term threading rules."""
    if not steps:
        raise MaudeRunError(_with_context("steps must contain at least one command", context))
    if len(steps) > settings.interpreter_max_steps:
        raise MaudeRunError(
            _with_context(f"Too many steps: {len(steps)} (maximum {settings.interpreter_max_steps})", context)
        )
    max_length = settings.interpreter_max_term_length
    has_current = False
    for index, step in enumerate(steps):
        _validate_step_lengths(index, step, max_length, context)
        if (
            isinstance(step, _BoundedStep)
            and step.bound is not None
            and step.bound > settings.interpreter_max_rewrite_bound
        ):
            raise MaudeRunError(
                _with_context(
                    f"Step {index}: bound is {step.bound} (maximum {settings.interpreter_max_rewrite_bound})",
                    context,
                )
            )
        has_current = _validate_step_threading(index, step, has_current, context)


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
        "path_mode": step.path if isinstance(step, SearchStep) else None,
    }


def _to_request(path: Path, module: str, steps: Sequence[MaudeStep], settings: Settings) -> SessionRequest:
    """Build the worker request, carrying the configured caps."""
    return {
        "path": str(path),
        "module": module,
        "steps": [_to_step_request(step) for step in steps],
        "max_solutions": settings.interpreter_max_solutions,
        "max_result_length": settings.interpreter_max_result_length,
        "max_path_steps": settings.interpreter_max_path_steps,
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


def _to_path(path: PathDict) -> MaudeSearchPath:
    """Adapt a worker path to the wire model."""
    return MaudeSearchPath(
        initial=path["initial"],
        transitions=[
            MaudePathTransition(
                rule=MaudeRuleRef(label=transition["rule"]["label"], text=transition["rule"]["text"]),
                state=transition["state"],
            )
            for transition in path["transitions"]
        ],
    )


def _to_solutions(solutions: list[SolutionDict]) -> list[MaudeSearchSolution]:
    """Adapt worker search solutions to the wire model."""
    return [
        MaudeSearchSolution(
            term=solution["term"],
            rewrites=solution["rewrites"],
            bindings=_to_bindings(solution["bindings"]),
            path=_to_path(solution["path"]) if solution["path"] is not None else None,
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


def _to_wire_result(
    result: SessionResult,
    path: Path,
    module: str,
    context: Mapping[str, object],
) -> MaudeRunResult:
    """Reject whole-call failures and adapt a successful session result.

    Per-step failures are data and do not raise; the load/module/type checks are the
    whole-call conditions from the design.
    """
    if not result["load_ok"]:
        detail = result["load_output"]["stderr"].strip()
        suffix = f": {detail}" if detail else ""
        raise MaudeRunError(_with_context(f"Failed to load the Maude program {str(path)!r}{suffix}", context))
    if not result["module_found"]:
        defined = _defined_modules_detail(result["defined_modules"])
        raise MaudeRunError(
            _with_context(
                f'Module "{module}" is not defined by "{path}" '
                f"(modules defined by the load: {defined}). "
                "Run maude_program_diagnostics on the file if the load did not behave as expected.",
                context,
            )
        )
    if result["module_type"] in _THEORY_MODULE_TYPES:
        raise MaudeRunError(
            _with_context(
                f'Module "{module}" is a theory: terms cannot be parsed in a theory; '
                "select a functional or system module instead.",
                context,
            )
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
      and an optional `depth`. Each solution carries its rewrite path (`path`):
      `"labels"` (the default) returns the ordered rule labels; `"full"` also returns
      the full rule text and the intermediate states; `"none"` omits the path.

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
    the cap was reached. Each search solution's `path` is `{initial, transitions}`, where
    `initial` is the search subject and each transition carries the applied rule (label,
    and text in `"full"` mode) and, in `"full"` mode, the state it produced (the last
    state equals the solution's `term`); `path` is `null` when the step requested
    `"none"`. Paths are bounded by the configured maximum transitions per path
    (default 100), and every returned string by the configured maximum result length; a
    path or result exceeding its cap makes the step `too-large` with the limit and a
    message naming the setting to raise. The whole call is bounded by timeout_secs
    (default: the server's interpreter timeout). The timeout covers interpreter startup
    and is best effort: a non-terminating reduction fails the call and replaces the
    worker pool, so allow more time for long evaluations.

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
    timeout = timeout_secs if timeout_secs is not None else settings.interpreter_timeout_secs
    context = _call_context(resolved, module, steps, timeout)
    _require_file(resolved, context)
    _validate_steps(steps, settings, context)
    request = _to_request(resolved, module, steps, settings)
    try:
        result = executor.run_session(request, timeout=timeout)
    except MaudeWorkerError as exc:
        # The client text is capped; the log keeps the full chain and traceback so the
        # truncation marker points at an actionable record.
        detail = format_error_report(exc, context=context, max_chars=settings.error_detail_max_chars)
        _log.error(
            "maude_run failed for %s (module %s):\n%s",
            resolved,
            module,
            format_error_report(exc, context=context, max_chars=0),
        )
        raise MaudeRunError(f"Maude interpreter session failed: {detail}") from exc  # noqa: TRY003
    except Exception as exc:
        detail = format_error_report(exc, context=context, max_chars=settings.error_detail_max_chars)
        _log.exception(
            "Unexpected failure running the Maude interpreter session for %s (module %s):\n%s",
            resolved,
            module,
            format_error_report(exc, context=context, max_chars=0),
        )
        raise MaudeRunError(f"Unexpected failure running the Maude interpreter session: {detail}") from exc  # noqa: TRY003
    return _to_wire_result(result, resolved, module, context)


__all__ = [
    "ErewriteStep",
    "FrewriteStep",
    "MatchStep",
    "MaudeBinding",
    "MaudeCapturedOutput",
    "MaudeLoadInfo",
    "MaudeLoadWarning",
    "MaudeMatch",
    "MaudePathTransition",
    "MaudeRuleRef",
    "MaudeRunError",
    "MaudeRunResult",
    "MaudeSearchPath",
    "MaudeSearchSolution",
    "MaudeStep",
    "MaudeStepOutcome",
    "ReduceStep",
    "RewriteStep",
    "SearchStep",
    "maude_run",
]
