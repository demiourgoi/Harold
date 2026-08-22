"""Integration tests for `harold_mcp.maude` against the real Maude interpreter."""

from pathlib import Path

from harold_mcp.maude import MaudeRuntime, init_maude

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_get_module_supports_parse_reduce_flow() -> None:
    init_maude()
    module = MaudeRuntime().get_module("NAT")
    term = module.parseTerm("2 * 3")
    term.reduce()
    assert f"Result = {term}" == "Result = 6"


def test_load_module_picks_up_redefined_module() -> None:
    """Loading an edited program redefines its modules, so fresh wrappers see the new definition.

    `hello.maude` and `hello2.maude` both define `HELLO-WORLD` with `f = 1 * 2`
    and `f = 1 + 2` respectively, simulating an edit to the same source file.
    """
    runtime = MaudeRuntime()

    hello = runtime.load_module(FIXTURES_DIR / "hello.maude", "HELLO-WORLD")
    term = hello.parseTerm("f")
    term.reduce()
    assert str(term) == "2"

    hello2 = runtime.load_module(FIXTURES_DIR / "hello2.maude", "HELLO-WORLD")
    term2 = hello2.parseTerm("f")
    term2.reduce()
    assert str(term2) == "3"
