"""Sort declaration reader, shared by the lint rule and the prelude snapshot extractor.

The reader is line-oriented (Maude sort statements are, apart from `sorts A B .`
continuing on the next line) and works on the masked code view, so comments cannot be
mistaken for declarations. It is deliberately the single implementation of "what is a
sort declaration": the `prelude-sort-redeclared` rule and the bundled prelude snapshot
(the maintenance CLI regenerates it through `iter_sort_declarations`) can therefore
never disagree on what the prelude declares.
"""

import re
from collections import Counter
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from harold_mcp.heuristic.lexical import CodeLine

MODULE_OPEN_RE = re.compile(r"^\s*(fmod|fth|mod|smod|th|view)\s+([^\s{]+)(.*?)\bis\b")
MODULE_CLOSE_RE = re.compile(r"^\s*(endfm|endfth|endm|endsm|endv|endth)\b")
INLINE_CLOSE_RE = re.compile(r"\b(?:endfm|endfth|endm|endsm|endv|endth)\b")
SORT_STATEMENT_START_RE = re.compile(r"^\s*sorts?\s+")
# A sort name as Maude writes them: an identifier (`?` is identifier material, per the
# probes), optionally parameterized.
SORT_NAME_RE = re.compile(r"^[A-Za-z_$][\w'\-?]*(?:\{[^}]*\})?$")
# Theory modules declare interface sorts that user modules are expected to redeclare
# when they instantiate the theory, so they are not shadowed prelude sorts (review D6).
THEORY_KINDS = frozenset({"fth", "th"})
# Maude's placeholder in module expressions (`sorts none .` inside `(sth ... endsth)`);
# never a real sort declaration.
PLACEHOLDER_NAMES = frozenset({"none"})


@dataclass(frozen=True, slots=True)
class SortDeclaration:
    """A `sort`/`sorts` declaration found in Maude source text."""

    name: str
    """The declared name as written, e.g. `List{X}` or `Type?`."""

    line: int
    """1-based line of the name."""

    column: int
    """1-based column of the name."""

    module: str | None
    """Enclosing module name, or `None` when the file declares none."""


def _declared_names(statement_lines: Sequence[tuple[int, str, int]]) -> list[tuple[str, int, int]]:
    """Extract `(name, line, column)` from the lines of one complete `sorts` statement.

    Each entry is `(line number, code, offset)` where `offset` is the index in `code`
    at which the names start, so columns stay exact across continuation lines.
    """
    names: list[tuple[str, int, int]] = []
    last = len(statement_lines) - 1
    for index, (number, code, offset) in enumerate(statement_lines):
        segment = code[offset:]
        if index == last:
            stripped = segment.rstrip()
            segment = stripped[:-1] if stripped.endswith(".") else stripped
        for match in re.finditer(r"\S+", segment):
            names.append((match.group(0), number, offset + match.start() + 1))
    return names


def _declarations_for_statement(
    statement: Sequence[tuple[int, str, int]],
    module: tuple[str, str] | None,
    excluded: Counter[str] | None,
) -> Iterator[SortDeclaration]:
    """Yield the declarations of one complete `sorts` statement.

    Excluded, in this order: declarations outside a module, declarations in `view`
    bodies and in theory modules (`fth`/`th`), renaming mappings (`sort X to Y`, i.e.
    any statement containing the `to` token) and the `none` placeholder. Names that do
    not match Maude's sort-name shape are dropped token by token (the
    `(sth ... sorts none . ... endsth)` meta-term leaves such junk).

    `excluded` accumulates the per-reason counts of dropped names, for the snapshot CLI's
    report.
    """
    names = _declared_names(statement)
    if module is None:
        _count(excluded, "outside a module", len(names))
        return
    if module[0] == "view":
        _count(excluded, "view body (sort mapping)", len(names))
        return
    if module[0] in THEORY_KINDS:
        _count(excluded, "theory body (interface sort)", len(names))
        return
    if any(name == "to" for name, _, _ in names):
        _count(excluded, "renaming instantiation (sort mapping)", len(names))
        return
    for name, line, column in names:
        if name in PLACEHOLDER_NAMES:
            _count(excluded, "placeholder (none)")
            continue
        if not SORT_NAME_RE.match(name):
            _count(excluded, "not a sort name")
            continue
        yield SortDeclaration(name=name, line=line, column=column, module=module[1])


def _count(excluded: Counter[str] | None, reason: str, count: int = 1) -> None:
    if excluded is not None:
        excluded[reason] += count


def iter_sort_declarations(
    lines: Sequence[CodeLine],
    excluded: Counter[str] | None = None,
) -> Iterator[SortDeclaration]:
    """Yield the real sort declarations, skipping mappings and placeholders."""
    module: tuple[str, str] | None = None  # (kind, name)
    pending: list[tuple[int, str, int]] = []
    for line in lines:
        code = line.code
        opening = MODULE_OPEN_RE.match(code)
        if opening:
            # A module opened and closed on the same line opens nothing.
            inline_close = INLINE_CLOSE_RE.search(code[opening.end() :])
            module = None if inline_close else (opening.group(1), opening.group(2))
            pending = []
            continue
        if MODULE_CLOSE_RE.match(code):
            module = None
            pending = []
            continue
        start = SORT_STATEMENT_START_RE.match(code)
        if start is not None:
            pending.append((line.number, code, start.end()))
        elif pending:
            pending.append((line.number, code, 0))
        if pending and code.rstrip().endswith("."):
            yield from _declarations_for_statement(pending, module, excluded)
            pending = []
