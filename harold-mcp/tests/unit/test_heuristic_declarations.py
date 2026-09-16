"""Unit tests for the sort declaration reader (`harold_mcp.heuristic.declarations`)."""

from harold_mcp.heuristic.declarations import SortDeclaration, iter_sort_declarations
from harold_mcp.heuristic.lexical import code_view


def _declarations(text: str) -> list[SortDeclaration]:
    return list(iter_sort_declarations(code_view(text)))


def _names(text: str) -> list[str]:
    return [declaration.name for declaration in _declarations(text)]


def test_declaration_records_name_line_column_and_module() -> None:
    text = "fmod MY-MOD is\n    sort Nat' .\nendfm\n"

    assert _declarations(text) == [SortDeclaration(name="Nat'", line=2, column=10, module="MY-MOD")]


def test_parameterised_module_headers_yield_the_plain_module_name() -> None:
    text = (
        "fmod LIST{X :: TRIV} is\n"
        "    sort List{X} .\n"
        "endfm\n"
        "fmod MAP{X :: TRIV, Y :: TRIV} is\n"
        "    sort Map{X,Y} .\n"
        "endfm\n"
    )

    assert _declarations(text) == [
        SortDeclaration(name="List{X}", line=2, column=10, module="LIST"),
        SortDeclaration(name="Map{X,Y}", line=5, column=10, module="MAP"),
    ]


def test_multiline_sorts_statement_reports_each_name_on_its_own_line() -> None:
    text = "fmod T is\n    sorts A B\n          C .\nendfm\n"

    assert _declarations(text) == [
        SortDeclaration(name="A", line=2, column=11, module="T"),
        SortDeclaration(name="B", line=2, column=13, module="T"),
        SortDeclaration(name="C", line=3, column=11, module="T"),
    ]


def test_view_declared_and_closed_on_one_line_opens_nothing() -> None:
    text = "view TRIV from TRIV to TRIV is endv\nfmod T is\n    sort A .\nendfm\n"

    assert _names(text) == ["A"]


def test_view_bodies_are_excluded() -> None:
    text = "view V from TRIV to NAT is\n    sort Elt to Nat .\nendv\n"

    assert _names(text) == []


def test_renaming_mappings_are_excluded() -> None:
    text = "fmod T is\n    sort A to B .\n    sort C .\nendfm\n"

    assert _names(text) == ["C"]


def test_theory_module_sorts_are_excluded() -> None:
    """Review D6: `Elt` (declared by `fth TRIV`) is not a shadowed prelude sort."""
    text = "fth TRIV is\n    sort Elt .\nendfth\nth ORDER is\n    sort Order .\nendth\nmod T is\n    sort A .\nendm\n"

    assert _names(text) == ["A"]


def test_the_meta_term_junk_is_excluded() -> None:
    """The `(sth ... sorts none . ... endsth)` expression leaves only junk tokens."""
    text = (
        "mod T is\n"
        "    eq [Q:Qid] = (sth Q:Qid is including Q:Qid .\n"
        "    sorts none . none none none\n"
        "    endsth) .\n"
        "    sort A .\n"
        "endm\n"
    )

    assert _names(text) == ["A"]


def test_placeholder_and_non_name_tokens_are_dropped() -> None:
    text = "fmod T is\n    sorts none . endsth) A .\nendfm\n"

    assert _names(text) == ["A"]


def test_question_mark_sort_names_are_accepted() -> None:
    text = "fmod T is\n    sorts Type? MatchPair? .\n    sort ?A .\nendfm\n"

    assert _names(text) == ["Type?", "MatchPair?"]


def test_declarations_outside_a_module_are_ignored() -> None:
    text = "sort Loose .\nfmod T is\n    sort A .\nendfm\nsort AlsoLoose .\n"

    assert _names(text) == ["A"]


def test_module_body_of_object_and_system_modules_is_tracked() -> None:
    text = "mod CONFIG is\n    sort Attribute .\nendm\nsmod SYSTEM is\n    sort State .\nendsm\n"

    assert _declarations(text) == [
        SortDeclaration(name="Attribute", line=2, column=10, module="CONFIG"),
        SortDeclaration(name="State", line=5, column=10, module="SYSTEM"),
    ]


def test_comments_cannot_be_mistaken_for_declarations() -> None:
    text = "fmod T is\n    *** sort Commented .\n    sort A .\nendfm\n"

    assert _names(text) == ["A"]
