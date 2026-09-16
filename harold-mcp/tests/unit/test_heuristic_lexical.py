"""Unit tests for the heuristic linter's lexical layer (`code_view`)."""

import pytest

from harold_mcp.heuristic.lexical import (
    CodeLine,
    SourceView,
    code_view,
    declaration_index,
    is_identifier_char,
)


def _masked_lines(text: str) -> tuple[str, ...]:
    """Mask `text` and assert every masked line keeps the source line's length."""
    view = code_view(text)
    for source_line, code_line in zip(text.split("\n"), view, strict=True):
        assert len(code_line.code) == len(source_line)
    return tuple(code_line.code for code_line in view)


def _masked(line: str) -> str:
    return _masked_lines(line)[0]


def test_code_view_numbers_lines_from_one() -> None:
    view = code_view("a\nb\n")

    assert view == (CodeLine(number=1, code="a"), CodeLine(number=2, code="b"), CodeLine(number=3, code=""))
    assert [line.number for line in view] == [1, 2, 3]


def test_is_identifier_char_matches_maude_identifier_material() -> None:
    assert all(is_identifier_char(ch) for ch in "aZ0_'-?$")
    assert is_identifier_char("é")
    assert is_identifier_char("\u2019")  # typographic apostrophe (RUF001-safe escape)
    assert not any(is_identifier_char(ch) for ch in ' ()[]{}.,;:="')


@pytest.mark.parametrize("marker", ["***", "---"])
def test_comment_markers_blank_the_rest_of_the_line(marker: str) -> None:
    line = f"eq f = 1 . {marker} trailing comment"

    masked = _masked(line)

    assert masked == "eq f = 1 . ".ljust(len(line))
    assert "trailing" not in masked


@pytest.mark.parametrize("marker", ["***", "---"])
def test_whole_line_comment_is_fully_blanked(marker: str) -> None:
    line = f"{marker} whole-line comment"

    assert _masked(line) == " " * len(line)


def test_double_dash_is_not_a_comment() -> None:
    line = "eq f = 1 . -- not a Maude comment"

    assert _masked(line) == line  # only *** and --- start comments; -- is a real error


def test_comment_markers_inside_a_string_are_literal() -> None:
    literal = '"a *** b --- c -- d"'
    line = f"eq s = {literal} ."

    assert _masked(line) == f"eq s = {' ' * len(literal)} ."


def test_string_literal_content_is_blanked_but_the_code_after_it_is_not() -> None:
    literal = '"when -- = café"'
    line = f"eq s = {literal} ."

    assert _masked(line) == f"eq s = {' ' * len(literal)} ."


def test_unterminated_string_blanks_the_delimiters_and_the_rest_of_the_line() -> None:
    line = 'eq s = "no closing quote'

    assert _masked(line) == "eq s = " + " " * len('"no closing quote')


def test_quote_after_identifier_material_does_not_open_a_string() -> None:
    line = 'op f" : -> Nat .'

    assert _masked(line) == line  # the " belongs to the identifier token, not a string


def test_masking_composes_on_a_realistic_line() -> None:
    text = 'fmod T is\n    eq s = "when -- = café" . *** c\nendfm\n'

    masked = _masked_lines(text)

    assert masked[0] == "fmod T is"
    assert masked[1] == f"    eq s = {' ' * len('"when -- = café"')} ." + " " * len(" *** c")
    assert masked[2] == "endfm"


@pytest.mark.parametrize("quoted", ["'when", "'--", "'a"])
def test_quoted_identifier_masking(quoted: str) -> None:
    line = f"eq q = {quoted} b ."

    assert _masked(line) == "eq q = " + " " * len(quoted) + " b ."


def test_apostrophe_inside_an_identifier_is_identifier_material() -> None:
    for line in ("eq f(A') = A' .", "eq f(A'b) = A'b ."):
        assert _masked(line) == line


def test_quoted_identifier_ends_at_whitespace() -> None:
    assert _masked("eq q = 'a b .") == "eq q = " + " " * 2 + " b ."


@pytest.mark.parametrize("statement", ["eq", "ceq", "rl", "crl"])
def test_statement_label_masking(statement: str) -> None:
    line = f"{statement} [Rewrite] : f(X) = X ."

    assert _masked(line) == f"{statement} " + " " * len("[Rewrite]") + " : f(X) = X ."


def test_masked_label_leaves_no_capitalized_token_behind() -> None:
    masked = _masked("    eq [Rewrite] : f(X) = X .")

    assert "Rewrite" not in masked
    assert masked.endswith(": f(X) = X .")


def test_brackets_outside_a_statement_position_are_not_labels() -> None:
    line = "    op f : Nat -> Nat [ctor] ."

    assert _masked(line) == line  # operator attributes are not labels


def test_unterminated_label_blanks_the_rest_of_the_line() -> None:
    line = "rl [rule : f(X) => X ."

    assert _masked(line) == "rl " + " " * (len(line) - 3)


def test_declaration_index_collects_vars_operators_and_sort_references() -> None:
    text = (
        "    vars X Y : Float .\n    var N : Nat .\n    ops f g : Nat Nat -> Nat .\n    eq normalize(V:Vector) = V .\n"
    )

    declarations = declaration_index(code_view(text))

    assert declarations.variables == frozenset({"X", "Y", "N", "V"})
    assert declarations.operators == frozenset({"f", "g"})
    assert declarations.sort_references == frozenset({"Float", "Nat", "Vector"})


def test_declaration_index_ignores_commented_declarations() -> None:
    declarations = declaration_index(code_view("    vars X : Nat . *** var Y : Nat .\n"))

    assert declarations.variables == frozenset({"X"})


def test_source_view_builds_lines_declarations_and_sort_bases() -> None:
    text = "fmod T is\n    sorts List{X} Map{X,Y} Nat .\n    var H : Nat .\nendfm\n"

    view = SourceView.from_text(text)

    assert [line.code for line in view.lines][:2] == ["fmod T is", "    sorts List{X} Map{X,Y} Nat ."]
    assert [declaration.name for declaration in view.sort_declarations] == ["List{X}", "Map{X,Y}", "Nat"]
    assert view.declarations.variables == frozenset({"H"})
    assert view.sort_bases == frozenset({"List", "Map", "Nat"})
