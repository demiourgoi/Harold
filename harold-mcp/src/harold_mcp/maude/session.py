"""Bounded Maude interpreter session: the worker-side implementation of `maude_run`.

This module runs in the worker process; the `maude` SWIG bindings are imported
**lazily** inside `run_session`, so importing it never loads the interpreter outside
a worker.

A session is hermetic: the executor runs it in a fresh worker process (one call per
process), it loads one file, selects one module, and runs the requested steps. The
caller carries state across sessions by re-submitting a saved result term or by
writing a wrapper module.
"""

from typing import Any, Literal, NamedTuple, TypedDict, cast

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
    path_mode: str | None


class SessionRequest(TypedDict):
    """A whole session: one file, one module, an ordered list of steps and the caps."""

    path: str
    module: str
    steps: list[StepRequest]
    max_solutions: int
    max_result_length: int
    max_path_steps: int
    max_output_length: int


class BindingDict(TypedDict):
    """A variable binding (`variable` is the name Maude printed, e.g. `N`)."""

    variable: str
    value: str


class PathRuleDict(TypedDict):
    """The rule of one path transition; `text` is set only in `"full"` mode."""

    label: str | None
    text: str | None


class PathTransitionDict(TypedDict):
    """One path transition: the rule applied and the state it produced.

    `state` is set only in `"full"` mode.
    """

    rule: PathRuleDict
    state: str | None


class PathDict(TypedDict):
    """The rewrite path from the search subject to a solution.

    `initial` is the parsed subject; `transitions` is the ordered rule
    applications (empty for a reflexive or branching zero-transition path).
    """

    initial: str
    transitions: list[PathTransitionDict]


class SolutionDict(TypedDict):
    """One `search` solution.

    `path` is the reconstructed rewrite path when the step requested one, `None`
    otherwise (the tool owns the `"labels"` default; the worker only does what the
    request asks).
    """

    term: str
    rewrites: int
    bindings: list[BindingDict]
    path: PathDict | None


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
            message="result exceeds interpreter_max_result_length",
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


class _CollectionResult(NamedTuple):
    """Result of a capped `match`/`search` collection: the items, or the exceeded limit."""

    status: Literal["ok", "too-large"]
    items: list[Any]
    truncated: bool
    limit: int | None
    message: str | None


def _collect_matches(
    subject: Any,
    pattern: Any,
    depth: int,
    max_solutions: int,
    max_result_length: int,
) -> _CollectionResult:
    """Collect a capped list of match substitutions, enforcing the result term cap.

    The match iterator is lazy: at most `max_solutions` substitutions are consumed,
    plus one extra only to set `truncated`. A serialized binding string (variable or
    value) longer than `max_result_length` makes the whole collection `too-large`.
    """
    matches: list[list[BindingDict]] = []
    truncated = False
    for substitution, _context in subject.match(pattern, maxDepth=depth):
        if len(matches) == max_solutions:
            truncated = True
            break
        bindings = _bindings(substitution)
        if _bindings_too_large(bindings, max_result_length):
            return _CollectionResult(
                status="too-large",
                items=[],
                truncated=False,
                limit=max_result_length,
                message="result exceeds interpreter_max_result_length",
            )
        matches.append(bindings)
    return _CollectionResult(status="ok", items=matches, truncated=truncated, limit=None, message=None)


def _collect_solutions(
    subject: Any,
    search_type: int,
    pattern: Any,
    depth: int,
    max_solutions: int,
    max_result_length: int,
    path_mode: str | None,
    max_path_steps: int,
) -> _CollectionResult:
    """Collect a capped list of search solutions, with optional rewrite paths.

    The search iterator is lazy: at most `max_solutions` solutions are consumed,
    plus one extra only to set `truncated` (no path work is done for it). For each
    returned solution the term and bindings are checked against `max_result_length`
    **before** any path work; then, when `path_mode` is `"labels"` or `"full"`, the
    solution's state number is read from `iterator.getStateNr()` while the iterator
    is positioned on that solution, and the path is reconstructed iteratively
    (see `_reconstruct_path`). A path over `max_path_steps` transitions, or any path
    string over `max_result_length`, makes the whole collection `too-large` naming
    the exceeded cap; `path_mode` `None`/`"none"` skips path work entirely.
    """
    solutions: list[SolutionDict] = []
    truncated = False
    iterator = subject.search(search_type, pattern, depth=depth)
    for solution, substitution, _path, rewrites in iterator:
        if len(solutions) == max_solutions:
            truncated = True
            break
        term_text = str(solution)
        bindings = _bindings(substitution)
        if len(term_text) > max_result_length or _bindings_too_large(bindings, max_result_length):
            return _CollectionResult(
                status="too-large",
                items=[],
                truncated=False,
                limit=max_result_length,
                message="result exceeds interpreter_max_result_length",
            )
        path: PathDict | None = None
        if path_mode in ("labels", "full"):
            state_number = iterator.getStateNr()
            path_result = _reconstruct_path(iterator, state_number, path_mode, max_path_steps, max_result_length)
            if path_result.status == "too-large":
                return _CollectionResult(
                    status="too-large",
                    items=[],
                    truncated=False,
                    limit=path_result.limit,
                    message=path_result.message,
                )
            path = path_result.path
        solutions.append({"term": term_text, "rewrites": int(rewrites), "bindings": bindings, "path": path})
    return _CollectionResult(status="ok", items=solutions, truncated=truncated, limit=None, message=None)


class _PathResult(NamedTuple):
    """Result of reconstructing one solution's path: the path, or the exceeded limit."""

    status: Literal["ok", "too-large"]
    path: PathDict | None
    limit: int | None
    message: str | None


def _reconstruct_path(
    iterator: Any,
    state_number: int,
    mode: str,
    max_path_steps: int,
    max_result_length: int,
) -> _PathResult:
    """Reconstruct the rewrite path from the search root to the state `state_number`.

    `state_number` must be read from `iterator.getStateNr()` while the iterator is
    positioned on the solution; both resolve the state at call time, not at yield
    time. The path is built iteratively from the search graph's parent links (the
    bindings' `pathTo` is recursive and overflows the Python stack on deep paths):
    the parent walk collects state numbers only, stops as soon as the chain exceeds
    `max_path_steps` transitions (at most `max_path_steps + 2` `getStateParent`
    calls, and no string is formatted for an over-cap path), and only then are the
    states serialized forward.

    `getRule` is called only for states after the root: the root has no incoming
    rule and `getRule` on it crashes the interpreter process. In `"labels"` mode only
    the rule labels are returned; in `"full"` mode also the rule text and the
    intermediate states. Every produced string is checked against
    `max_result_length`; an overflow is a `too-large` result naming that cap.
    """
    chain = [state_number]
    parent = iterator.getStateParent(state_number)
    while parent >= 0:
        chain.append(parent)
        parent = iterator.getStateParent(parent)
        if len(chain) > max_path_steps + 1:
            return _PathResult(
                status="too-large",
                path=None,
                limit=max_path_steps,
                message="path exceeds interpreter_max_path_steps",
            )
    chain.reverse()

    initial = str(iterator.getStateTerm(chain[0]))
    if len(initial) > max_result_length:
        return _PathResult(
            status="too-large",
            path=None,
            limit=max_result_length,
            message="path element exceeds interpreter_max_result_length",
        )

    transitions: list[PathTransitionDict] = []
    for state in chain[1:]:
        rule = iterator.getRule(state)
        label = rule.getLabel()
        text = str(rule) if mode == "full" else None
        state_text = str(iterator.getStateTerm(state)) if mode == "full" else None
        for element in (label, text, state_text):
            if element is not None and len(element) > max_result_length:
                return _PathResult(
                    status="too-large",
                    path=None,
                    limit=max_result_length,
                    message="path element exceeds interpreter_max_result_length",
                )
        transitions.append({"rule": {"label": label, "text": text}, "state": state_text})
    return _PathResult(
        status="ok",
        path={"initial": initial, "transitions": transitions},
        limit=None,
        message=None,
    )


def _collect_step(
    command: MatchingCommand,
    index: int,
    step: StepRequest,
    subject: Any,
    pattern: Any,
    depth: int,
    max_solutions: int,
    max_result_length: int,
    max_path_steps: int,
) -> _CollectionResult:
    """Dispatch a parsed `match`/`search` step to its capped collection.

    Validates the step's `search_type` and `path_mode` first (a mismatch is a
    programming error: the tool's pydantic boundary only produces valid values).
    """
    if command == "match":
        return _collect_matches(subject, pattern, depth, max_solutions, max_result_length)
    search_type_name = step["search_type"]
    if search_type_name is None or search_type_name not in _SEARCH_TYPES:
        raise ValueError(  # noqa: TRY003 - programming error
            f"step {index} has no valid search_type"
        )
    path_mode = step["path_mode"]
    if path_mode is not None and path_mode not in ("none", "labels", "full"):
        raise ValueError(  # noqa: TRY003 - programming error
            f"step {index} has no valid path_mode"
        )
    return _collect_solutions(
        subject,
        _SEARCH_TYPES[search_type_name],
        pattern,
        depth,
        max_solutions,
        max_result_length,
        path_mode,
        max_path_steps,
    )


def _run_match_or_search(
    module: Any,
    index: int,
    command: MatchingCommand,
    subject_str: str,
    step: StepRequest,
    max_solutions: int,
    max_result_length: int,
    max_path_steps: int,
    max_output_length: int,
) -> StepOutcomeDict:
    """Parse the subject and pattern, run `match` or `search`, and build the outcome.

    Both iterations are capped at `max_solutions`; `truncated` is true when one more
    item existed. The iterators are lazy, so the extra item is consumed only to detect
    the overflow. Every serialized result term (a search solution or a binding value)
    is checked against `max_result_length`: exceeding it produces a `too-large` outcome,
    like the rewriting commands. A `search` step may request the solutions' rewrite
    paths via `path_mode` (`"labels"`, `"full"`, or `None`/`"none"` for no path),
    bounded by `max_path_steps`; a path or result over its cap is a `too-large`
    outcome whose `limit` and `message` name the exceeded setting. Parsing and the
    operation share one capture, so a parse failure's `Warning:` lines become the
    `parse-error` message.
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
        return _collect_step(
            command, index, step, subject, pattern, depth, max_solutions, max_result_length, max_path_steps
        )

    result, captured = capture_streams(execute)
    output = _truncate_capture(captured, max_output_length)
    if result is None:
        message = "\n".join(warning["message"] for warning in parse_warnings(captured["stderr"]))
        return _outcome(index=index, command=command, status="parse-error", message=message, output=output)
    status, items, truncated, limit, limit_message = result
    if status == "too-large":
        return _outcome(
            index=index,
            command=command,
            status="too-large",
            limit=limit,
            message=limit_message,
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
                request["max_path_steps"],
                request["max_output_length"],
            )
        case _:
            # Server-side validation only admits implemented commands; a mismatch is a
            # programming error, not a user error.
            raise ValueError(f"unsupported command {command!r} in step {index}")  # noqa: TRY003 - programming error


def _annotate_worker_context(exc: BaseException, **context: object) -> None:
    """Attach the failing phase to an exception for the IPC error envelope."""
    cast(Any, exc).worker_context = context


def run_session(request: SessionRequest) -> SessionResult:
    """Run a bounded interpreter session in the current worker process.

    Loads the request's file (sibling `load`/`in` dependencies resolve against its
    directory), reports the modules the load defined and any warnings, selects the
    requested module, and executes the steps until the first failure. Outputs are
    truncated to `max_output_length`; warnings and parse-error messages are parsed
    from the **full** stderr before truncation.

    Unexpected exceptions carry `worker_context` (the phase and, for a step, its
    index and command) so `transport.serve_one` can report where the failure
    happened. Per-step `parse-error`/`too-large` outcomes are data and never raise.
    """
    # Lazy import: this module defines the request and result types and is imported by
    # the server process; it must never load the SWIG bindings there.
    import maude

    try:
        modules_before = {header.name for header in maude.getModules()}
        load_ok, load_capture = capture_streams(lambda: bool(maude.load(request["path"])))
        defined_modules = sorted({header.name for header in maude.getModules()} - modules_before)
        # Parse before truncating: a long stderr must not hide a warning.
        warnings = parse_warnings(load_capture["stderr"])
        load_output = _truncate_capture(load_capture, request["max_output_length"])
    except BaseException as exc:
        _annotate_worker_context(exc, phase="load")
        raise

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
        try:
            outcome = _run_step(module, index, step, current, request)
        except BaseException as exc:
            _annotate_worker_context(exc, phase="step", step=index, command=step["command"])
            raise
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
