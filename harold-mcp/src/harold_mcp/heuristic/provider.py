"""The heuristic diagnostics provider: runs the rule registry over the source text.

Pure and hermetic: no filesystem, no interpreter, no global state, so running it twice
over the same text returns the same findings. Unlike the interpreter provider it does
not wrap its failures — a rule bug is already a diagnostics-subsystem failure, and the
aggregator's safety net reports it as `heuristic-linter (ValueError: ...)`.
"""

from collections.abc import Sequence

from harold_mcp.diagnostics import DiagnosticSource, ProviderDiagnostic, SourceFile
from harold_mcp.heuristic.lexical import SourceView
from harold_mcp.heuristic.rules import RULES, Rule


class HeuristicLinterProvider:
    """`DiagnosticProvider` running the heuristic rules over the source text."""

    name: DiagnosticSource = "heuristic-linter"

    def __init__(self, rules: Sequence[Rule] = RULES) -> None:
        """`rules` defaults to the full registry; tests and future tools may pass a subset."""
        self._rules = tuple(rules)

    def diagnose(self, source: SourceFile) -> list[ProviderDiagnostic]:
        """Build the code view of `source.text` and stamp every finding with its rule."""
        view = SourceView.from_text(source.text)
        return [
            ProviderDiagnostic(
                source=self.name,
                severity=rule.severity,
                code=rule.code,
                line=finding.line,
                column=finding.column,
                end_column=finding.end_column,
                message=finding.message,
                fix=finding.fix,
            )
            for rule in self._rules
            for finding in rule.detect(view)
        ]
