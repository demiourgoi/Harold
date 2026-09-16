"""Lexical layer of the heuristic linter: the masked code view of a source file.

The rules are textual, so their precision depends on one shared lexical layer. Every
line is masked — comments, string literals, quoted identifiers and statement labels are
blanked to spaces — while keeping its original length, so a character's index always
equals its 1-based column and a rule can report exact spans.

The masking is deliberately line-oriented and conservative: a construct Maude accepts
(anything inside a string literal or a quoted identifier, a label, a declared `when`
operator) is never reported, while constructs the mask cannot recognize degrade to the
plain-text behavior of the source linter this layer was ported from.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # `declarations` imports this module, so the dependency is call-time only
    from harold_mcp.heuristic.declarations import SortDeclaration

_COMMENT_MARKERS = ("***", "---")
_STRING_DELIMITER = '"'
_QUOTED_IDENTIFIER_DELIMITER = "'"
_STATEMENT_KEYWORDS = frozenset({"eq", "ceq", "rl", "crl"})

_IDENTIFIER_PUNCTUATION = frozenset("_'-?$")


def is_identifier_char(ch: str) -> bool:
    """Maude identifier material: letters, digits, `_ ' - ? $` and bytes ≥ 0x80.

    Used for the token-boundary test that decides whether `"` opens a string literal
    and whether `'` starts a quoted identifier (a `'` after identifier material belongs
    to the identifier: `A'`, `A'b`).
    """
    if ord(ch) > 127:
        return True
    return ch.isalnum() or ch in _IDENTIFIER_PUNCTUATION


@dataclass(frozen=True, slots=True)
class CodeLine:
    """One source line, masked (comments, string literals, quoted identifiers and
    statement labels blanked to spaces).

    The line is the same length as in the file, so columns map 1:1 onto the source.
    """

    number: int
    """1-based line number."""

    code: str
    """The masked line: same length as the source line, with non-code regions blanked."""


def _opens_construct(line: str, index: int) -> bool:
    """Whether the character at `index` sits at a token boundary.

    A `"` or `'` preceded by identifier material belongs to that identifier
    (`A'`, `A'b`); only at a boundary does it open a string literal or a quoted
    identifier.
    """
    return index == 0 or not is_identifier_char(line[index - 1])


def _mask_string_literal(masked: list[str], line: str, start: int) -> int:
    """Blank the string literal starting at `start`; return the index after it.

    Strings cannot span lines (Maude reports `skipped: "` instead), so an unterminated
    literal blanks the rest of the line, like the delimiter of a complete one.
    """
    masked[start] = " "
    index = start + 1
    while index < len(line):
        masked[index] = " "
        if line[index] == _STRING_DELIMITER:
            return index + 1
        index += 1
    return index


def _mask_quoted_identifier(masked: list[str], line: str, start: int) -> int:
    """Blank the quoted identifier starting at `start`; return the index after it.

    A quoted identifier runs to the next whitespace: `'a b` is the quoted identifier
    `'a` followed by the identifier `b` (probe `quoted_identifier_range`).
    """
    index = start
    while index < len(line) and not line[index].isspace():
        masked[index] = " "
        index += 1
    return index


def _mask_comment(masked: list[str], start: int) -> None:
    """Blank from the comment marker at `start` to the end of the line."""
    for index in range(start, len(masked)):
        masked[index] = " "


def _mask_statement_label(masked: list[str], line: str, start: int) -> int | None:
    """Blank the `[label]` slot at `start` when it follows a statement keyword.

    Maude labels are not term tokens, so masking them keeps rule 6 from flagging
    `eq [Rewrite] : ...`. Returns the index after the label, or `None` when there is
    no label at `start`.
    """
    cursor = start - 1
    while cursor >= 0 and line[cursor].isspace():
        cursor -= 1
    token_end = cursor + 1
    while cursor >= 0 and is_identifier_char(line[cursor]):
        cursor -= 1
    if line[cursor + 1 : token_end] not in _STATEMENT_KEYWORDS:
        return None
    index = start
    while index < len(line):
        masked[index] = " "
        if line[index] == "]":
            return index + 1
        index += 1
    return index


def _mask_line(line: str) -> str:
    """Build the masked `code` view of one physical line (length-preserving)."""
    masked = list(line)
    index = 0
    while index < len(line):
        ch = line[index]
        if ch == _STRING_DELIMITER and _opens_construct(line, index):
            index = _mask_string_literal(masked, line, index)
            continue
        if ch == _QUOTED_IDENTIFIER_DELIMITER and _opens_construct(line, index):
            index = _mask_quoted_identifier(masked, line, index)
            continue
        if line.startswith(_COMMENT_MARKERS, index):
            _mask_comment(masked, index)
            break
        if ch == "[":
            after_label = _mask_statement_label(masked, line, index)
            if after_label is not None:
                index = after_label
                continue
        index += 1
    return "".join(masked)


def code_view(text: str) -> tuple[CodeLine, ...]:
    """Split `text` on physical newlines and build the masked `code` view of each line."""
    return tuple(
        CodeLine(number=number, code=_mask_line(line)) for number, line in enumerate(text.split("\n"), start=1)
    )


@dataclass(frozen=True, slots=True)
class Declarations:
    """The file-wide declaration picture rules 5 and 6 need."""

    variables: frozenset[str]
    """`var`/`vars` names plus inline `X:Sort` names."""

    operators: frozenset[str]
    """Identifier tokens of `op`/`ops` declarations."""

    sort_references: frozenset[str]
    """Base names used after `:` anywhere in the file (annotations and usages)."""


_VARS_RE = re.compile(r"^\s*vars?\s+(.+?)\s*:\s*\S+\s*\.")
_OPS_RE = re.compile(r"^\s*ops?\s+(.+?)\s*:")
# Inline annotations (`V:Vector`), with no space before the colon, as in the source linter.
_INLINE_ANNOTATION_RE = re.compile(r"\b([A-Za-z][\w'-]*):(?=[A-Za-z])")
# Names used after a colon: sorts imported from another module or the prelude that are
# only *used*, never declared locally (`op f : List{X} -> List{X} .` → `List`).
_SORT_REFERENCE_RE = re.compile(r":\s*([A-Za-z_$][\w'\-?]*)")
_IDENTIFIER_RE = re.compile(r"[A-Za-z][\w'-]*")


def declaration_index(lines: Sequence[CodeLine]) -> Declarations:
    """Build the declaration index of one file from its masked code view."""
    variables: set[str] = set()
    operators: set[str] = set()
    sort_references: set[str] = set()
    for line in lines:
        code = line.code
        declared_vars = _VARS_RE.match(code)
        if declared_vars:
            variables.update(declared_vars.group(1).split())
        declared_ops = _OPS_RE.match(code)
        if declared_ops:
            operators.update(_IDENTIFIER_RE.findall(declared_ops.group(1)))
        variables.update(_INLINE_ANNOTATION_RE.findall(code))
        sort_references.update(_SORT_REFERENCE_RE.findall(code))
    return Declarations(
        variables=frozenset(variables),
        operators=frozenset(operators),
        sort_references=frozenset(sort_references),
    )


@dataclass(frozen=True, slots=True)
class SourceView:
    """Everything the heuristic rules read from one source file."""

    lines: tuple[CodeLine, ...]
    """The masked code view, one entry per physical line."""

    sort_declarations: tuple[SortDeclaration, ...]
    """Every real `sort`/`sorts` declaration (rule 6's allow-list, rule 7, the snapshot)."""

    declarations: Declarations
    """Declared variables, operators and sort references."""

    @classmethod
    def from_text(cls, text: str) -> SourceView:
        """Build the view the rules run over from the file's text."""
        from harold_mcp.heuristic.declarations import iter_sort_declarations  # avoids an import cycle

        lines = code_view(text)
        return cls(
            lines=lines,
            sort_declarations=tuple(iter_sort_declarations(lines)),
            declarations=declaration_index(lines),
        )

    @property
    def sort_bases(self) -> frozenset[str]:
        """Declared sort names without their parameters (`List{X}` → `List`)."""
        return frozenset(declaration.name.split("{", 1)[0] for declaration in self.sort_declarations)
