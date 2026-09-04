"""Shared vocabulary of MCP tool tags.

FastMCP uses tags to categorize tools and to drive server-side visibility
control: ``mcp.disable(tags=...)`` / ``mcp.enable(tags=..., only=True)`` (and
per-session ``ctx.enable_components``) match any tool carrying one of the
given tags. With mcp SDK 1.29 (spec 2025-06-18) tags are not serialized to
clients; the docs note clients can use them "in some cases", i.e. on newer
protocol revisions.

All Harold tools must build their tag sets from the constants below, so the
vocabulary stays consistent as more tools are added. Each tool carries:

- the two **domain** tags (``MAUDE`` and ``PROGRAMMING``, added automatically
  by :func:`harold_tags`): the specific Maude domain plus the general
  programming domain, so clients that know nothing about Maude can still
  group Harold with their other programming tools;
- one **functional-category** tag describing what the tool does.

Effect/safety metadata belongs in ``ToolAnnotations`` (``readOnlyHint``,
``destructiveHint``, ...) — the standard, client-consumed place for it — so
it is deliberately not duplicated as tags.
"""

# Domain: every Harold tool is about programming in the Maude language.
MAUDE = "maude"
PROGRAMMING = "programming"

DIAGNOSTICS = "diagnostics"  # static analysis of Maude programs (maude_program_diagnostics)
INTERPRETER = "interpreter"  # running Maude programs in the interpreter (planned)
DOCS = "docs"  # Maude documentation search/RAG (planned)


def harold_tags(*tags: str) -> set[str]:
    """Build the tag set for a Harold tool; the domain tags are always included."""
    return {MAUDE, PROGRAMMING, *tags}
