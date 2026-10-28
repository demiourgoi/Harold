"""Bounded Maude interpreter session: the worker-side implementation of `maude_run`.

This module is imported by the server process only for the function reference the
process pool pickles; the `maude` SWIG bindings are imported **lazily** inside
`run_session`, so importing it never loads the interpreter outside a worker.

A session is hermetic: the executor runs it in a fresh worker process (one task per
process), it loads one file, selects one module, and runs the requested steps. The
caller carries state across sessions by re-submitting a saved result term or by
writing a wrapper module.
"""

from itertools import islice
from typing import Any, Literal, TypedDict

from harold_mcp.maude.capture import CapturedOutput, WarningDict, capture_streams, parse_warnings, truncate_output

CommandName = Literal["reduce", "rewrite", "frewrite", "erewrite", "match", "search"]
"""Every step command."""

RewritingCommand = Literal["reduce", "rewrite", "frewrite", "erewrite"]
"""The rewriting commands the session engine implements."""

MatchingCommand = Literal["match", "search"]
"""The pattern commands the session engine implements."""

StepStatus = Literal["ok", "parse-error", "too-large"]
"""Outcome status: a successful step or one of the two per-step failures."""

# Maude's search-type constants (`maude.ONE_STEP`, ...). Spelled out so this module
# can be imported by the server process without touching the bindings.
_SEARCH_TYPES: dict[str, int] = {
    "one-step": 0,  # maude.ONE_STEP
    "at-least-one-step": 1,  # maude.AT_LEAST_ONE_STEP
    "any-steps": 2,  # maude.ANY_STEPS
    "normal-form": 3,  # maude.NORMAL_FORM
    "branch": 4,  # maude.BRANCH
}

# Reported in `SessionResult.module_type` when no module was found. Real module types
# start at 0 (`FUNCTIONAL_MODULE`); the tool checks `module_found` before using it.
UNKNOWN_MODULE_TYPE = -1


class StepRequest(TypedDict):
    """One command to execute, as sent by the tool.

    Every command-specific field is present and `None` when not applicable, so the
    dict shape is stable across commands.
    """

    command: CommandName
    term: str | None
    pattern: str | None
    subject: str | None
    bound: int | None
    gas: int | None
    depth: int | None
    search_type: str | None


class SessionRequest(TypedDict):
    """A whole session: one file, one module, an ordered list of steps and the caps."""

    path: str
    module: str
    steps: list[StepRequest]
    max_solutions: int
    max_result_length: int
    max_output_length: int


class BindingDict(TypedDict):
    """A variable binding (`variable` is the name Maude printed, e.g. `N`)."""

    variable: str
    value: str


class SolutionDict(TypedDict):
    """One `search` solution."""

    term: str
    rewrites: int
    bindings: list[BindingDict]


class StepOutcomeDict(TypedDict):
    """The outcome of one executed step (per-step failures are data, not exceptions)."""

    index: int
    command: CommandName
    status: StepStatus
    term: str | None
    rewrites: int | None
    matches: list[list[BindingDict]] | None
    solutions: list[SolutionDict] | None
    truncated: bool | None
    message: str | None
    limit: int | None
    output: CapturedOutput


class SessionResult(TypedDict):
    """Result of a session, including load diagnostics and the executed step outcomes."""

    load_ok: bool
    module_found: bool
    module_type: int
    defined_modules: list[str]
    warnings: list[WarningDict]
    load_output: CapturedOutput
    outcomes: list[StepOutcomeDict]


def _truncate_capture(captured: CapturedOutput, max_length: int) -> CapturedOutput:
    """Apply the output cap to both streams of a capture."""
    return {
        "stdout": truncate_output(captured["stdout"], max_length),
        "stderr": truncate_output(captured["stderr"], max_length),
    }


def _outcome(
    *,
    index: int,
    command: CommandName,
    status: StepStatus,
    output: CapturedOutput,
    term: str | None = None,
    rewrites: int | None = None,
    matches: list[list[BindingDict]] | None = None,
    solutions: list[SolutionDict] | None = None,
    truncated: bool | None = None,
    message: str | None = None,
    limit: int | None = None,
) -> StepOutcomeDict:
    """Build a flat step outcome; fields that do not apply are `None`."""
    return {
        "index": index,
        "command": command,
        "status": status,
        "term": term,
        "rewrites": rewrites,
        "matches": matches,
        "solutions": solutions,
        "truncated": truncated,
        "message": message,
        "limit": limit,
        "output": output,
    }


def _run_rewriting(
    module: Any,
    index: int,
    command: RewritingCommand,
    term_str: str,
    step: StepRequest,
    max_result_length: int,
    max_output_length: int,
) -> StepOutcomeDict:
    """Parse `term_str`, run one rewriting command, and build the outcome.

    Parsing and the command share one capture: a parse failure writes Maude's
    `Warning:` lines to stderr, which become the `parse-error` message. The full
    stderr is parsed before the returned capture is truncated.

    `reduce`, `rewrite` and `frewrite` mutate the parsed term; `erewrite` leaves it
    untouched and returns a new term. The reported counter is the interpreter's
    rewrite count, which includes equational rewrites. Omitted bounds are passed as
    `-1` (the bindings' unbounded default); an explicit `0` stays `0`.
    """

    def execute() -> tuple[int | None, str | None]:
        term = module.parseTerm(term_str)
        if term is None:
            return None, None
        bound = step["bound"] if step["bound"] is not None else -1
        gas = step["gas"] if step["gas"] is not None else -1
        match command:
            case "reduce":
                rewrites = term.reduce()
            case "rewrite":
                rewrites = term.rewrite(bound)
            case "frewrite":
                rewrites = term.frewrite(bound, gas)
            case "erewrite":
                term, rewrites = term.erewrite(bound, gas)
            case _:
                # Defensive: `_run_step` only dispatches rewriting commands.
                raise ValueError(f"unsupported command {command!r}")  # noqa: TRY003 - programming error
        return int(rewrites), str(term)

    (rewrites, rendered), captured = capture_streams(execute)
    output = _truncate_capture(captured, max_output_length)
    if rendered is None:
        message = "\n".join(warning["message"] for warning in parse_warnings(captured["stderr"]))
        return _outcome(index=index, command=command, status="parse-error", message=message, output=output)
    if len(rendered) > max_result_length:
        return _outcome(
            index=index,
            command=command,
            status="too-large",
            limit=max_result_length,
            output=output,
        )
    return _outcome(
        index=index,
        command=command,
        status="ok",
        term=rendered,
        rewrites=rewrites,
        output=output,
    )


def _bindings(substitution: Any) -> list[BindingDict]:
    """Serialize one Maude substitution as variable/value term pairs.

    Iterating a substitution yields `(variable, value)` term pairs; `str(variable)`
    prints the variable's name (Maude adds a sort suffix only when disambiguating).
    """
    return [{"variable": str(variable), "value": str(value)} for variable, value in substitution]


def _bindings_too_large(bindings: list[BindingDict], max_length: int) -> bool:
    """Whether a serialized binding string (variable or value) exceeds the term cap."""
    return any(len(binding["variable"]) > max_length or len(binding["value"]) > max_length for binding in bindings)


type _CollectionResult = tuple[Literal["ok", "too-large"], list[Any], bool]


def _collect_matches(
    subject: Any,
    pattern: Any,
    depth: int,
    max_solutions: int,
    max_result_length: int,
) -> _CollectionResult:
    """Collect a capped list of match substitutions, enforcing the result term cap."""
    matched = list(islice(subject.match(pattern, maxDepth=depth), max_solutions + 1))
    matches: list[list[BindingDict]] = []
    for substitution, _context in matched[:max_solutions]:
        bindings = _bindings(substitution)
        if _bindings_too_large(bindings, max_result_length):
            return "too-large", [], False
        matches.append(bindings)
    return "ok", matches, len(matched) > max_solutions


def _collect_solutions(
    subject: Any,
    search_type: int,
    pattern: Any,
    depth: int,
    max_solutions: int,
    max_result_length: int,
) -> _CollectionResult:
    """Collect a capped list of search solutions, enforcing the result term cap."""
    found = list(islice(subject.search(search_type, pattern, depth=depth), max_solutions + 1))
    solutions: list[SolutionDict] = []
    for solution, substitution, _path, rewrites in found[:max_solutions]:
        term_text = str(solution)
        bindings = _bindings(substitution)
        if len(term_text) > max_result_length or _bindings_too_large(bindings, max_result_length):
            return "too-large", [], False
        solutions.append({"term": term_text, "rewrites": int(rewrites), "bindings": bindings})
    return "ok", solutions, len(found) > max_solutions


def _run_match_or_search(
    module: Any,
    index: int,
    command: MatchingCommand,
    subject_str: str,
    step: StepRequest,
    max_solutions: int,
    max_result_length: int,
    max_output_length: int,
) -> StepOutcomeDict:
    """Parse the subject and pattern, run `match` or `search`, and build the outcome.

    Both iterations are capped at `max_solutions`; `truncated` is true when one more
    item existed. The iterators are lazy, so the extra item is consumed only to detect
    the overflow. Every serialized result term (a search solution or a binding value)
    is checked against `max_result_length`: exceeding it produces a `too-large` outcome,
    like the rewriting commands. Parsing and the operation share one capture, so a
    parse failure's `Warning:` lines become the `parse-error` message.
    """

    def execute() -> _CollectionResult | None:
        subject = module.parseTerm(subject_str)
        if subject is None:
            return None
        pattern_text = step["pattern"]
        if pattern_text is None:
            raise ValueError(f"step {index} is a {command} without a pattern")  # noqa: TRY003 - programming error
        pattern = module.parseTerm(pattern_text)
        if pattern is None:
            return None
        depth = step["depth"] if step["depth"] is not None else -1
        if command == "match":
            return _collect_matches(subject, pattern, depth, max_solutions, max_result_length)
        search_type_name = step["search_type"]
        if search_type_name is None or search_type_name not in _SEARCH_TYPES:
            raise ValueError(  # noqa: TRY003 - programming error
                f"step {index} has no valid search_type"
            )
        return _collect_solutions(
            subject,
            _SEARCH_TYPES[search_type_name],
            pattern,
            depth,
            max_solutions,
            max_result_length,
        )

    result, captured = capture_streams(execute)
    output = _truncate_capture(captured, max_output_length)
    if result is None:
        message = "\n".join(warning["message"] for warning in parse_warnings(captured["stderr"]))
        return _outcome(index=index, command=command, status="parse-error", message=message, output=output)
    status, items, truncated = result
    if status == "too-large":
        return _outcome(
            index=index,
            command=command,
            status="too-large",
            limit=max_result_length,
            output=output,
        )
    if command == "match":
        return _outcome(
            index=index,
            command=command,
            status="ok",
            matches=items,
            truncated=truncated,
            output=output,
        )
    return _outcome(
        index=index,
        command=command,
        status="ok",
        solutions=items,
        truncated=truncated,
        output=output,
    )


def _run_step(
    module: Any,
    index: int,
    step: StepRequest,
    current: str | None,
    request: SessionRequest,
) -> StepOutcomeDict:
    """Execute one step against the current term."""
    command = step["command"]
    match command:
        case "reduce" | "rewrite" | "frewrite" | "erewrite":
            term_str = step["term"] if step["term"] is not None else current
            if term_str is None:
                raise ValueError(  # noqa: TRY003 - programming error
                    f"step {index} has no term and there is no current term"
                )
            return _run_rewriting(
                module,
                index,
                command,
                term_str,
                step,
                request["max_result_length"],
                request["max_output_length"],
            )
        case "match" | "search":
            subject_str = step["subject"] if step["subject"] is not None else current
            if subject_str is None:
                raise ValueError(  # noqa: TRY003 - programming error
                    f"step {index} has no subject and there is no current term"
                )
            return _run_match_or_search(
                module,
                index,
                command,
                subject_str,
                step,
                request["max_solutions"],
                request["max_result_length"],
                request["max_output_length"],
            )
        case _:
            # Server-side validation only admits implemented commands; a mismatch is a
            # programming error, not a user error.
            raise ValueError(f"unsupported command {command!r} in step {index}")  # noqa: TRY003 - programming error


def run_session(request: SessionRequest) -> SessionResult:
    """Run a bounded interpreter session in the current worker process.

    Loads the request's file (sibling `load`/`in` dependencies resolve against its
    directory), reports the modules the load defined and any warnings, selects the
    requested module, and executes the steps until the first failure. Outputs are
    truncated to `max_output_length`; warnings and parse-error messages are parsed
    from the **full** stderr before truncation.
    """
    # Lazy import: the server process imports this module for the function reference
    # the pool pickles, and must never load the SWIG bindings.
    import maude

    modules_before = {header.name for header in maude.getModules()}
    load_ok, load_capture = capture_streams(lambda: bool(maude.load(request["path"])))
    defined_modules = sorted({header.name for header in maude.getModules()} - modules_before)
    # Parse before truncating: a long stderr must not hide a warning.
    warnings = parse_warnings(load_capture["stderr"])
    load_output = _truncate_capture(load_capture, request["max_output_length"])

    if not load_ok:
        return {
            "load_ok": False,
            "module_found": False,
            "module_type": UNKNOWN_MODULE_TYPE,
            "defined_modules": defined_modules,
            "warnings": warnings,
            "load_output": load_output,
            "outcomes": [],
        }

    module = maude.getModule(request["module"])
    if module is None:
        return {
            "load_ok": True,
            "module_found": False,
            "module_type": UNKNOWN_MODULE_TYPE,
            "defined_modules": defined_modules,
            "warnings": warnings,
            "load_output": load_output,
            "outcomes": [],
        }

    outcomes: list[StepOutcomeDict] = []
    current: str | None = None
    for index, step in enumerate(request["steps"]):
        outcome = _run_step(module, index, step, current, request)
        outcomes.append(outcome)
        if outcome["status"] != "ok":
            break
        # Rewriting outcomes carry the new current term; match/search outcomes have
        # `term=None` and leave the current term unchanged.
        if outcome["term"] is not None:
            current = outcome["term"]
    return {
        "load_ok": True,
        "module_found": True,
        "module_type": int(module.getModuleType()),
        "defined_modules": defined_modules,
        "warnings": warnings,
        "load_output": load_output,
        "outcomes": outcomes,
    }
