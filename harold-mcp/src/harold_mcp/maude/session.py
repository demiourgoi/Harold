"""Bounded Maude interpreter session: the worker-side implementation of `maude_run`.

This module is imported by the server process only for the function reference the
process pool pickles; the `maude` SWIG bindings are imported **lazily** inside
`run_session`, so importing it never loads the interpreter outside a worker.

A session is hermetic: the executor runs it in a fresh worker process (one task per
process), it loads one file, selects one module, and runs the requested steps. The
caller carries state across sessions by re-submitting a saved result term or by
writing a wrapper module.
"""

from typing import Any, TypedDict

from harold_mcp.maude.capture import CapturedOutput, WarningDict, capture_streams, parse_warnings, truncate_output

# Reported in `SessionResult.module_type` when no module was found. Real module types
# start at 0 (`FUNCTIONAL_MODULE`); the tool checks `module_found` before using it.
UNKNOWN_MODULE_TYPE = -1


class StepRequest(TypedDict):
    """One command to execute, as sent by the tool.

    Every command-specific field is present and `None` when not applicable, so the
    dict shape is stable across commands.
    """

    command: str
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
    """A variable binding (`variable` is Maude's name-plus-sort text)."""

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
    command: str
    status: str
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
    command: str,
    status: str,
    output: CapturedOutput,
    term: str | None = None,
    rewrites: int | None = None,
    message: str | None = None,
    limit: int | None = None,
) -> StepOutcomeDict:
    """Build a flat step outcome; fields that do not apply are `None`.

    `match`/`search` payloads stay `None` until those commands are implemented.
    """
    return {
        "index": index,
        "command": command,
        "status": status,
        "term": term,
        "rewrites": rewrites,
        "matches": None,
        "solutions": None,
        "truncated": None,
        "message": message,
        "limit": limit,
        "output": output,
    }


def _reduce(
    module: Any,
    index: int,
    subject: str,
    max_result_length: int,
    max_output_length: int,
) -> StepOutcomeDict:
    """Parse `subject` in `module`, reduce it, and build the outcome.

    Parsing and the reduction share one capture: a parse failure writes Maude's
    `Warning:` lines to stderr, which become the `parse-error` message. The full
    stderr is parsed before the returned capture is truncated.
    """

    def execute() -> tuple[int | None, str | None]:
        term = module.parseTerm(subject)
        if term is None:
            return None, None
        rewrites = int(term.reduce())
        return rewrites, str(term)

    (rewrites, rendered), captured = capture_streams(execute)
    output = _truncate_capture(captured, max_output_length)
    if rendered is None:
        message = "\n".join(warning["message"] for warning in parse_warnings(captured["stderr"]))
        return _outcome(index=index, command="reduce", status="parse-error", message=message, output=output)
    if len(rendered) > max_result_length:
        return _outcome(
            index=index,
            command="reduce",
            status="too-large",
            limit=max_result_length,
            output=output,
        )
    return _outcome(
        index=index,
        command="reduce",
        status="ok",
        term=rendered,
        rewrites=rewrites,
        output=output,
    )


def _run_step(
    module: Any,
    index: int,
    step: StepRequest,
    current: str | None,
    request: SessionRequest,
) -> StepOutcomeDict:
    """Execute one step against the current term; only `reduce` exists so far."""
    command = step["command"]
    if command != "reduce":
        # Server-side validation only admits implemented commands; a mismatch is a
        # programming error, not a user error.
        raise ValueError(f"unsupported command {command!r} in step {index}")  # noqa: TRY003 - programming error
    subject = step["term"] if step["term"] is not None else current
    if subject is None:
        raise ValueError(f"step {index} has no term and there is no current term")  # noqa: TRY003 - programming error
    return _reduce(module, index, subject, request["max_result_length"], request["max_output_length"])


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
