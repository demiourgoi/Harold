"""Unit tests for the shared tool-tag vocabulary (`harold_mcp.server.tags`)."""

from harold_mcp.server import tags


def test_harold_tags_always_includes_domain_tags() -> None:
    assert tags.harold_tags() == {tags.MAUDE, tags.PROGRAMMING}


def test_harold_tags_adds_requested_tags() -> None:
    assert tags.harold_tags(tags.DIAGNOSTICS) == {tags.MAUDE, tags.PROGRAMMING, tags.DIAGNOSTICS}


def test_tag_values_are_stable_strings() -> None:
    """Tag strings are part of the client-visible interface; keep them stable."""
    assert tags.MAUDE == "maude"
    assert tags.PROGRAMMING == "programming"
    assert tags.DIAGNOSTICS == "diagnostics"
    assert tags.INTERPRETER == "interpreter"
    assert tags.DOCS == "docs"
