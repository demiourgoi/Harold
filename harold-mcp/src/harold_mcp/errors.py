"""Bounded, self-contained error reports for MCP tool responses.

Stdlib-only: shared by the tools, the diagnostics aggregation and the Maude
subsystem. A report has a stable shape so clients can parse its first line, while
the server log always holds the full detail: callers render the report twice,
uncapped (`max_chars <= 0`) for the log and capped for the client text, so the
truncation marker points at a log entry with the missing detail.

The formatter renders any exception object, including one stored outside its
`except` block (the diagnostics aggregation formats provider failures after their
handler returned); `traceback.format_exc()` would render `NoneType: None` there.
It never reads environment variables, unrelated process state or file contents.
"""

import traceback
from collections.abc import Mapping

DEFAULT_ERROR_DETAIL_MAX_CHARS = 4000
"""Default cap for the client-visible error text (`HAROLD_ERROR_DETAIL_MAX_CHARS`)."""

TRUNCATION_MARKER = "... [error detail truncated; see the server log]"
"""Marker appended when the cap shortened the report."""


def format_context(context: Mapping[str, object]) -> str | None:
    """Render an ordered `key=value, ...` list; `None` when nothing is renderable.

    `None` values are skipped: a context entry that is not known (for example the
    worker pid of a call that never spawned a process) must not render as
    `pid=None`.
    """
    pairs = [f"{key}={value}" for key, value in context.items() if value is not None]
    return ", ".join(pairs) if pairs else None


def format_exception_text(exc: BaseException) -> str:
    """Render an exception with its traceback, even outside its handler.

    `traceback.format_exc()` renders `NoneType: None` for a stored exception;
    passing the exception object renders it reliably.
    """
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))


def _cause_chain(exc: BaseException) -> list[str]:
    """Render the exception itself, then its `__cause__`/`__context__` chain.

    Each element is `Type: message`. The identity set stops a cycle (a stored
    exception can point back to itself). For a remote failure the remote exception
    is appended as the final element, because it has no local cause.
    """
    entries: list[str] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        message = str(current).strip()
        entries.append(f"{type(current).__name__}: {message}" if message else type(current).__name__)
        current = current.__cause__ if current.__cause__ is not None else current.__context__
    remote_type = getattr(exc, "remote_type", None)
    remote_message = getattr(exc, "remote_message", None)
    if isinstance(remote_type, str) and remote_type:
        entries.append(f"{remote_type}: {remote_message}" if remote_message else remote_type)
    return entries


def _traceback_text(exc: BaseException) -> str | None:
    """The originating traceback: the first remote one in the chain, else the local one.

    A wrapper such as `DiagnosticProviderError` does not carry the remote traceback
    itself; its cause does, and that is the traceback worth showing.
    """
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        remote = getattr(current, "remote_traceback", None)
        if isinstance(remote, str) and remote.strip():
            return remote.strip()
        current = current.__cause__ if current.__cause__ is not None else current.__context__
    rendered = format_exception_text(exc).strip()
    return rendered or None


def _with_marker(parts: list[str]) -> str:
    """Join report sections and mark the result as truncated."""
    return "\n".join([*parts, TRUNCATION_MARKER])


def _truncate_report(
    *,
    first_line: str,
    prefix: str,
    context_line: str | None,
    cause_line: str,
    traceback_section: str | None,
    max_chars: int,
) -> str:
    """Shorten a report to `max_chars`: traceback, then causes, then the message.

    The first line (or at least its `category:`/`Type:` prefix) is always kept, and
    the marker is appended because the caller only reaches this function when the
    full report does not fit.
    """
    base = [first_line]
    if context_line is not None:
        base.append(context_line)
    base.append(cause_line)

    # 1. Keep the beginning of the traceback while it fits.
    if traceback_section is not None:
        budget = max_chars - len(_with_marker(base)) - 1
        if budget > 0:
            return _with_marker([*base, traceback_section[:budget]])
    report = _with_marker(base)
    if len(report) <= max_chars:
        return report

    # 2. Shorten the cause chain from the end.
    head = [first_line]
    if context_line is not None:
        head.append(context_line)
    budget = max_chars - len(_with_marker(head)) - 1
    if budget > 0:
        return _with_marker([*head, cause_line[:budget]])

    # 3. Drop the context line.
    report = _with_marker([first_line])
    if len(report) <= max_chars:
        return report

    # 4. Last resort: truncate the message, keeping the category/type prefix.
    budget = max_chars - len(_with_marker([prefix]))
    if budget > 0:
        return _with_marker([first_line[: len(prefix) + budget]])
    return first_line[:max_chars]


def format_error_report(
    exc: BaseException,
    *,
    context: Mapping[str, object],
    max_chars: int,
    category: str | None = None,
    message: str | None = None,
) -> str:
    """Render a bounded, self-contained error report for a tool response.

    Sections, in order:

    1. `<category>: <message>` (or `<Type>: <message>` when no category applies);
       `message` overrides `str(exc)` for callers whose exception text already
       carries a prefix.
    2. `context: key=value, ...` — the exception's own `context` merged with the
       caller's, the caller winning on collision, `None` values skipped.
    3. `cause: Type: message <- ...` — the exception itself, then its
       `__cause__`/`__context__` chain (cycle-guarded), then the remote cause of a
       remote failure.
    4. `traceback:` — the remote traceback when the exception carries one, else the
       local one.

    `max_chars <= 0` disables truncation and is used for the server-log rendering;
    the client text always uses the configured cap. When the report does not fit,
    the traceback is shortened first, then the cause chain, then the first line's
    message (its prefix is kept), and the truncation marker is appended.
    """
    resolved_category = category if category is not None else getattr(exc, "category", None)
    if not isinstance(resolved_category, str) or not resolved_category:
        resolved_category = None
    label = resolved_category if resolved_category is not None else type(exc).__name__
    detail = (message if message is not None else str(exc)).strip()
    first_line = f"{label}: {detail}" if detail else label
    prefix = f"{label}: " if detail else label

    own_context = getattr(exc, "context", None)
    merged: dict[str, object] = {}
    if isinstance(own_context, Mapping):
        merged.update(own_context)
    merged.update(context)
    rendered_context = format_context(merged)
    context_line = f"context: {rendered_context}" if rendered_context is not None else None

    cause_line = "cause: " + " <- ".join(_cause_chain(exc))
    traceback_text = _traceback_text(exc)
    traceback_section = f"traceback:\n{traceback_text}" if traceback_text is not None else None

    sections = [first_line]
    if context_line is not None:
        sections.append(context_line)
    sections.append(cause_line)
    if traceback_section is not None:
        sections.append(traceback_section)
    report = "\n".join(sections)
    if max_chars <= 0 or len(report) <= max_chars:
        return report
    return _truncate_report(
        first_line=first_line,
        prefix=prefix,
        context_line=context_line,
        cause_line=cause_line,
        traceback_section=traceback_section,
        max_chars=max_chars,
    )
