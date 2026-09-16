"""Unit tests for the heuristic linter provider (`HeuristicLinterProvider`)."""

from pathlib import Path

from harold_mcp.diagnostics import Severity, SourceFile
from harold_mcp.heuristic import HeuristicLinterProvider
from harold_mcp.heuristic.lexical import SourceView
from harold_mcp.heuristic.rules import Rule, RuleFinding

APOSTROPHE = "\u2019"


def _source(text: str) -> SourceFile:
    """A source whose path does not exist: the provider must run on the text alone."""
    return SourceFile(path=Path("not-on-disk.maude"), text=text)


def _rule(code: str, severity: Severity, message: str = "found") -> Rule:
    def detect(view: SourceView) -> list[RuleFinding]:
        assert view.lines  # the rule receives the built view
        return [RuleFinding(message=message, line=1, column=1, end_column=2)]

    return Rule(code=code, severity=severity, detect=detect)


def test_provider_stamps_rule_metadata_on_every_finding() -> None:
    rules = (_rule("demo-info", "info", "an observation"), _rule("demo-warning", "warning", "a suspicion"))
    provider = HeuristicLinterProvider(rules)

    diagnostics = provider.diagnose(_source("fmod T is endfm\n"))

    assert [(d.source, d.code, d.severity, d.message, d.line, d.column, d.end_column) for d in diagnostics] == [
        ("heuristic-linter", "demo-info", "info", "an observation", 1, 1, 2),
        ("heuristic-linter", "demo-warning", "warning", "a suspicion", 1, 1, 2),
    ]


def test_provider_accepts_a_rule_subset() -> None:
    provider = HeuristicLinterProvider((_rule("only-rule", "warning"),))

    diagnostics = provider.diagnose(_source(f"op L{APOSTROPHE} : -> Nat .\n"))

    assert [d.code for d in diagnostics] == ["only-rule"]  # the default registry is not consulted


def test_provider_runs_the_full_registry_by_default() -> None:
    provider = HeuristicLinterProvider()

    diagnostics = provider.diagnose(_source(f"op L{APOSTROPHE} : -> Nat .\n"))

    assert [d.code for d in diagnostics] == ["non-ascii-character"]
    assert diagnostics[0].severity == "info"
    assert diagnostics[0].fix is not None


def test_provider_is_idempotent_over_the_same_text() -> None:
    provider = HeuristicLinterProvider()
    text = f"fmod T is\n    op L{APOSTROPHE} : -> Nat .\nendfm\n"

    assert provider.diagnose(_source(text)) == provider.diagnose(_source(text))


def test_provider_returns_no_findings_for_clean_text() -> None:
    assert HeuristicLinterProvider().diagnose(_source("fmod T is endfm\n")) == []
