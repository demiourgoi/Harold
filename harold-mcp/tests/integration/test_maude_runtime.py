"""Integration tests for `harold_mcp.maude` against the real Maude interpreter."""

from harold_mcp.maude import MaudeRuntime, init_maude


def test_get_module_supports_parse_reduce_flow() -> None:
    init_maude()
    module = MaudeRuntime().get_module("NAT")
    term = module.parseTerm("2 * 3")
    term.reduce()
    assert f"Result = {term}" == "Result = 6"
