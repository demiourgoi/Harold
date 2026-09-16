"""The heuristic rules: codes, severities, messages and the detection functions.

Each rule is a plain function over the masked code view (`heuristic.lexical`) plus the
metadata that describes it to clients. The registry order is the evaluation order, and
it doubles as the deterministic tie-break for findings that share a position.

Severities follow the design's model: `info` for observations that do not affect the
load (Maude accepts them), `warning` for suspicious code that may be a false positive.
No rule is `error`: that level is reserved for findings that cannot be false positives.
"""

import re
import unicodedata
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

from harold_mcp.diagnostics import FixEdit, FixSuggestion, Severity
from harold_mcp.heuristic.lexical import CodeLine, SourceView
from harold_mcp.heuristic.prelude_sorts import PRELUDE_SORT_BASES, PRELUDE_SORTS

UNICODE_FIXES: dict[str, str] = {
    "\u2019": "'",  # RIGHT SINGLE QUOTATION MARK
    "\u2018": "'",  # LEFT SINGLE QUOTATION MARK
    "\u201c": '"',  # LEFT DOUBLE QUOTATION MARK
    "\u201d": '"',  # RIGHT DOUBLE QUOTATION MARK
    "\u2013": "-",  # EN DASH
    "\u2014": "-",  # EM DASH
    "\u00a0": " ",  # NO-BREAK SPACE
    "\u2026": "...",  # HORIZONTAL ELLIPSIS
}
"""Deterministic ASCII substitutions for typographic punctuation (ported verbatim)."""

_ASCII_REPLACEMENT_NAMES: dict[str, str] = {
    "'": "an ASCII apostrophe",
    '"': "an ASCII quotation mark",
    "-": "an ASCII hyphen",
    " ": "an ASCII space",
    "...": "three ASCII dots",
}

_REPLACEMENT_CHARACTER = "\ufffd"


@dataclass(frozen=True, slots=True)
class RuleFinding:
    """What a rule found: a message and, when known, a precise span."""

    message: str
    line: int
    column: int | None = None
    end_column: int | None = None
    fix: FixSuggestion | None = None


@dataclass(frozen=True, slots=True)
class Rule:
    """One heuristic check: stable code, severity, and the detection function."""

    code: str
    severity: Severity
    detect: Callable[[SourceView], list[RuleFinding]]


def _non_ascii_message(ch: str) -> str:
    """Model-facing explanation for one non-ASCII character found in code."""
    name = unicodedata.name(ch, hex(ord(ch)))
    replacement = UNICODE_FIXES.get(ch)
    if replacement is None:
        tail = "— replace it with an ASCII equivalent unless it is intentional."
    else:
        ascii_name = _ASCII_REPLACEMENT_NAMES.get(replacement, "an ASCII equivalent")
        tail = f"— replace it with {ascii_name} (a fix is available)."
    return (
        f"Non-ASCII character {ch!r} ({name}): Maude accepts it in identifiers, "
        f"but this is usually a typographic-punctuation paste {tail}"
    )


def _unicode_fix(line: int, column: int, ch: str) -> FixSuggestion | None:
    """The one-character replacement for `ch`, when a safe substitution exists."""
    replacement = UNICODE_FIXES.get(ch)
    if replacement is None:
        return None
    return FixSuggestion(
        description=f"Replace the typographic character {ch!r} with {replacement!r}.",
        edits=(FixEdit(line=line, start_column=column, end_column=column + 1, new_text=replacement),),
    )


def _detect_non_ascii_characters(view: SourceView) -> list[RuleFinding]:
    """Report every non-ASCII character in code, one finding per occurrence.

    The replacement character of the lossy UTF-8 decode is skipped: it is an artifact
    of reading a binary file, not something the author wrote.
    """
    findings: list[RuleFinding] = []
    for line in view.lines:
        for index, ch in enumerate(line.code):
            if ord(ch) <= 127 or ch == _REPLACEMENT_CHARACTER:
                continue
            column = index + 1
            findings.append(
                RuleFinding(
                    message=_non_ascii_message(ch),
                    line=line.number,
                    column=column,
                    end_column=column + 1,
                    fix=_unicode_fix(line.number, column, ch),
                )
            )
    return findings


_DECLARATION_KEYWORDS = frozenset({"op", "ops", "var", "vars", "sort", "sorts", "subsort", "subsorts"})
_WHEN_RE = re.compile(r"\bwhen\b")
# The source linter's boundary regex: `--` is reported only when it is delimited by
# whitespace (or the line ends), which is what makes it a comment attempt in practice.
_DASH_COMMENT_RE = re.compile(r"(?:^|\s)(--)(?!-)(?=\s|$)")
_IF_THEN_RE = re.compile(r"\bif\b(.*?)\bthen\b")
# A single `=`: not preceded by another operator character, not followed by `=` or `/`,
# so `==`, `=/=`, `<=`, `>=`, `/\` and `\/` are all excluded.
_LONE_EQUALS_RE = re.compile(r"(?<![=<>~/\\])=(?![=/])")

_WHEN_GUARD_MESSAGE = (
    "`when` is not Maude syntax (it is a Haskell/SML guard): write a conditional equation "
    "or rule instead, `ceq <lhs> = <rhs> if <condition> .`"
)
_DASH_COMMENT_MESSAGE = (
    "`--` does not start a comment in Maude (only `***` and `---` do), so the rest of the line "
    "is parsed as code — use `***` or `---`."
)
_EQ_IN_TERM_MESSAGE = (
    "A single `=` is not a test in a term: inside `if … then … else … fi` use `==` "
    "(the `=` sign only separates the two sides of an equation or rule)."
)


def _is_declaration_line(line: CodeLine) -> bool:
    """Whether the line's first token declares an operator, variable or sort.

    `when` is not a Maude keyword, so `op when : Bool -> Bool .` is legal; rules 2 and 3
    must not fire on the declaration itself (probes `when_operator`, `dashdash_operator`).
    """
    tokens = line.code.split()
    return bool(tokens) and tokens[0] in _DECLARATION_KEYWORDS


def _detect_when_guards(view: SourceView) -> list[RuleFinding]:
    """Report every whole-word `when` in code, except on declaration lines."""
    findings: list[RuleFinding] = []
    for line in view.lines:
        if _is_declaration_line(line):
            continue
        for match in _WHEN_RE.finditer(line.code):
            findings.append(
                RuleFinding(
                    message=_WHEN_GUARD_MESSAGE,
                    line=line.number,
                    column=match.start() + 1,
                    end_column=match.end() + 1,
                )
            )
    return findings


def _detect_dash_comments(view: SourceView) -> list[RuleFinding]:
    """Report every whitespace-delimited `--` in code, except on declaration lines."""
    findings: list[RuleFinding] = []
    for line in view.lines:
        if _is_declaration_line(line):
            continue
        for match in _DASH_COMMENT_RE.finditer(line.code):
            findings.append(
                RuleFinding(
                    message=_DASH_COMMENT_MESSAGE,
                    line=line.number,
                    column=match.start(1) + 1,
                    end_column=match.end(1) + 1,
                )
            )
    return findings


def _detect_eq_in_terms(view: SourceView) -> list[RuleFinding]:
    """Report every lone `=` inside an `if … then` span, one finding per occurrence."""
    findings: list[RuleFinding] = []
    for line in view.lines:
        for if_span in _IF_THEN_RE.finditer(line.code):
            offset = if_span.start(1)
            for match in _LONE_EQUALS_RE.finditer(if_span.group(1)):
                column = offset + match.start() + 1
                findings.append(
                    RuleFinding(
                        message=_EQ_IN_TERM_MESSAGE,
                        line=line.number,
                        column=column,
                        end_column=column + 1,
                    )
                )
    return findings


_STATEMENT_START_RE = re.compile(r"^\s*(?:c?eq|c?rl)\b")
_LHS_RE = re.compile(r"\s*(?:eq|ceq)\s+(.*?)\s=(?!=)\s")
_IDENTIFIER_TOKEN_RE = re.compile(r"[A-Za-z][\w'-]*")
_CAPITALIZED_TOKEN_RE = re.compile(r"\b[A-Z][\w'-]*\b")

MAUDE_KEYWORDS = frozenset({
    "eq",
    "ceq",
    "rl",
    "crl",
    "mb",
    "cmb",
    "if",
    "then",
    "else",
    "fi",
    "and",
    "or",
    "not",
    "true",
    "false",
    "owise",
    "otherwise",
    "is",
    "sort",
    "sorts",
    "op",
    "ops",
    "var",
    "vars",
    "subsort",
    "subsorts",
    "protecting",
    "including",
    "extending",
    "rem",
    "quo",
    "gcd",
    "lcm",
    "min",
    "max",
    "sd",
    "abs",
    "ctor",
    "assoc",
    "comm",
    "id",
    "prec",
    "gather",
    "endfm",
    "endm",
})
"""The source linter's keyword allow-list, kept verbatim (and compared lowercased)."""


def _detect_non_linear_patterns(view: SourceView) -> list[RuleFinding]:
    """Report declared variables repeated in an `eq`/`ceq` left-hand side."""
    findings: list[RuleFinding] = []
    declared = view.declarations.variables
    if not declared:
        return findings
    for line in view.lines:
        lhs_match = _LHS_RE.match(line.code)
        if lhs_match is None:
            continue
        lhs = lhs_match.group(1)
        offset = lhs_match.start(1)
        counts: Counter[str] = Counter(token.group(0) for token in _IDENTIFIER_TOKEN_RE.finditer(lhs))
        first_occurrence: dict[str, int] = {}
        for token in _IDENTIFIER_TOKEN_RE.finditer(lhs):
            name = token.group(0)
            if name in declared and name not in first_occurrence:
                first_occurrence[name] = token.start()
        for name, first in sorted(first_occurrence.items(), key=lambda item: item[1]):
            count = counts[name]
            if count < 2:
                continue
            column = offset + first + 1
            findings.append(
                RuleFinding(
                    message=(
                        f"The variable `{name}` appears {count} times in the left-hand side "
                        "(non-linear pattern): legal in Maude (it forces the matched subterms to be "
                        "equal) but often unintentional — use a fresh variable if equality was not "
                        "intended."
                    ),
                    line=line.number,
                    column=column,
                    end_column=column + len(name),
                )
            )
    return findings


def _detect_undeclared_identifiers(view: SourceView) -> list[RuleFinding]:
    """Report capitalized identifiers in statements that nothing in the file declares."""
    findings: list[RuleFinding] = []
    allowed = (
        view.declarations.variables
        | view.declarations.operators
        | view.declarations.sort_references
        | view.sort_bases
        | PRELUDE_SORT_BASES
    )
    for line in view.lines:
        if not _STATEMENT_START_RE.match(line.code):
            continue
        first_occurrence: dict[str, int] = {}
        for match in _CAPITALIZED_TOKEN_RE.finditer(line.code):
            token = match.group(0)
            if token in first_occurrence:
                continue  # one finding per token per line, at its first occurrence
            if token in allowed or token.lower() in MAUDE_KEYWORDS:
                continue
            first_occurrence[token] = match.start()
        for token, start in sorted(first_occurrence.items(), key=lambda item: item[1]):
            column = start + 1
            findings.append(
                RuleFinding(
                    message=(
                        f"`{token}` is used in a statement but is not declared as a variable, operator, "
                        f"or sort: if it is a variable, declare it (`var {token} : Nat .`) or annotate "
                        f"it inline (`{token}:Nat`)."
                    ),
                    line=line.number,
                    column=column,
                    end_column=column + len(token),
                )
            )
    return findings


def _detect_prelude_sort_redeclarations(view: SourceView) -> list[RuleFinding]:
    """Report sorts that shadow a sort the Maude prelude already declares.

    Theory sorts are not in the snapshot (review D6), so a natural `sort Elt .` is not
    reported: user modules are expected to redeclare theory interface sorts when they
    instantiate a theory.
    """
    findings: list[RuleFinding] = []
    for declaration in view.sort_declarations:
        prelude_module = PRELUDE_SORTS.get(declaration.name)
        if prelude_module is None:
            continue
        findings.append(
            RuleFinding(
                message=(
                    f"The sort `{declaration.name}` is already declared by the Maude prelude "
                    f"(module {prelude_module}): redeclaring it shadows the prelude sort in this "
                    "module — rename it unless the shadowing is intentional."
                ),
                line=declaration.line,
                column=declaration.column,
                end_column=declaration.column + len(declaration.name),
            )
        )
    return findings


RULES: tuple[Rule, ...] = (
    Rule(code="non-ascii-character", severity="info", detect=_detect_non_ascii_characters),
    Rule(code="when-guard", severity="warning", detect=_detect_when_guards),
    Rule(code="dash-comment", severity="warning", detect=_detect_dash_comments),
    Rule(code="eq-in-term", severity="warning", detect=_detect_eq_in_terms),
    Rule(code="non-linear-pattern", severity="warning", detect=_detect_non_linear_patterns),
    Rule(code="undeclared-identifier", severity="warning", detect=_detect_undeclared_identifiers),
    Rule(code="prelude-sort-redeclared", severity="info", detect=_detect_prelude_sort_redeclarations),
)
"""The rule registry; order is the evaluation order and the position tie-break."""
