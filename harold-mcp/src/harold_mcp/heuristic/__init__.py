"""Harold's heuristic linter for Maude programs: report-only pattern checks.

The linter runs in the MCP server process, pure text in and diagnostics out: it never
imports the `maude` bindings and never depends on the worker. It is a complement to the
interpreter, not a replacement — its findings are heuristics that may be false
positives, which is why they are reported as `info`/`warning` and carry a message that
explains how to write the construct in Maude.
"""

from harold_mcp.heuristic.provider import HeuristicLinterProvider

__all__ = ["HeuristicLinterProvider"]
