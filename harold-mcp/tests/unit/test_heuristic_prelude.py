"""Unit tests for the prelude sort snapshot and its extractor."""

import re

from harold_mcp.heuristic.prelude_extract import extract_prelude_sorts
from harold_mcp.heuristic.prelude_sorts import PRELUDE_SORT_BASES, PRELUDE_SORTS

SAMPLE_PRELUDE = """
*** Sort, kind and type sets.
fmod TRUTH-VALUE is
    sort Bool .
endfm

fmod NAT is
    sorts Zero NzNat Nat .
endfm

fth TRIV is
    sort Elt .
endfth

view TRIV from TRIV to TRIV is endv

view Nat from TRIV to NAT is
    sort Elt to Nat .
endv

fmod LIST{X :: TRIV} is
    sorts NeList{X}
          List{X} .
endfm

fmod MAPPING-SAMPLE is
    protecting LIST{Nat} *
        (sort NeList{Nat} to NeNatList) .
    sort NeNatList to NatList .
    sort Local .
endfm

mod META-SAMPLE is
    eq [Q:Qid] = (sth Q:Qid is including Q:Qid .
    sorts none . none none none
    endsth) .
    sort State .
endm

sorts OutsideAModule .
"""


def test_extract_prelude_sorts_keeps_real_declarations() -> None:
    sorts = extract_prelude_sorts(SAMPLE_PRELUDE)

    assert sorts == {
        "Bool": "TRUTH-VALUE",
        "Zero": "NAT",
        "NzNat": "NAT",
        "Nat": "NAT",
        "NeList{X}": "LIST",
        "List{X}": "LIST",
        "Local": "MAPPING-SAMPLE",
        "State": "META-SAMPLE",
    }


def test_extract_prelude_sorts_excludes_mappings_theories_views_and_junk() -> None:
    sorts = extract_prelude_sorts(SAMPLE_PRELUDE)

    assert "Elt" not in sorts  # theory interface sort (review D6)
    assert "none" not in sorts  # placeholder inside the `(sth ...)` meta-term
    assert "NeNatList" not in sorts  # renaming mapping
    assert "NatList" not in sorts
    assert "OutsideAModule" not in sorts  # not inside a module


def test_extract_prelude_sorts_reports_exclusion_counts() -> None:
    from collections import Counter

    excluded: Counter[str] = Counter()
    _ = extract_prelude_sorts(SAMPLE_PRELUDE, excluded)

    assert excluded["view body (sort mapping)"] == 3  # `sort Elt to Nat .` in the view
    assert excluded["theory body (interface sort)"] == 1
    assert excluded["renaming instantiation (sort mapping)"] == 3  # `sort NeNatList to NatList .`
    assert excluded["placeholder (none)"] == 4
    assert excluded["not a sort name"] == 2  # `endsth)` and `.`
    assert excluded["outside a module"] == 1


def test_snapshot_holds_the_prelude_sorts() -> None:
    assert PRELUDE_SORTS["Qid"] == "QID"
    assert PRELUDE_SORTS["Bool"] == "TRUTH-VALUE"
    assert PRELUDE_SORTS["Nat"] == "NAT"
    assert PRELUDE_SORTS["List{X}"] == "LIST"
    assert PRELUDE_SORTS["Set{X}"] == "SET"
    assert PRELUDE_SORTS["Map{X,Y}"] == "MAP"
    assert PRELUDE_SORTS["State"] == "LOOP-MODE"
    assert PRELUDE_SORTS["Configuration"] == "CONFIGURATION"


def test_snapshot_excludes_theory_sorts() -> None:
    """`Elt` (declared by `fth TRIV`) must not be reported (review D6)."""
    assert "Elt" not in PRELUDE_SORTS
    assert "Elt" not in PRELUDE_SORT_BASES


def test_snapshot_has_no_junk_names() -> None:
    assert len(PRELUDE_SORTS) > 100
    assert "none" not in PRELUDE_SORTS
    assert "NatList" not in PRELUDE_SORTS  # a renamed instance, not a declaration
    assert "." not in PRELUDE_SORTS
    for name in PRELUDE_SORTS:
        assert re.fullmatch(r"[A-Za-z_$][\w'\-?]*(\{[^}]*\})?", name), name
        assert name.isascii()
        assert name.strip() == name


def test_snapshot_bases_are_the_names_without_parameters() -> None:
    assert frozenset(name.split("{", 1)[0] for name in PRELUDE_SORTS) == PRELUDE_SORT_BASES
    assert {"Bool", "Nat", "Int", "Float", "String", "Qid", "List", "Set", "Map", "$Split"} <= PRELUDE_SORT_BASES
    assert not PRELUDE_SORT_BASES & {"none", "Elt", "NatList", "QidList"}


def test_snapshot_module_records_more_than_twenty_modules() -> None:
    assert len(set(PRELUDE_SORTS.values())) > 20
    assert PRELUDE_SORTS["Term"] == "META-TERM"
    assert PRELUDE_SORTS["$Split{X}"] == "WEAKLY-SORTABLE-LIST"
