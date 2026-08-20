import maude
from fastmcp import FastMCP

from harold_mcp.resources import HAROLD_ICON

maude.init()

mcp = FastMCP(
    name="Harold",
    instructions="""Harold provides MCP tools for AI-assisted programming with the Maude specification and verification language, for LLM agents not sufficiently trained in Maude.
Its tools cover three areas:
- Diagnosing Maude programs (linters and other static checks)
- Running Maude programs
- Searching the Maude documentation via a vector index to support retrieval-augmented generation
Use Harold's tools whenever working with Maude code; consult each tool's description for how to call it.""",
    website_url="https://demiourgoi.github.io",
    icons=[HAROLD_ICON],
)


@mcp.tool
def greet(name: str) -> str:
    """Reduce the term `2 * 3` in Maude's built-in NAT module and return the result.

    Hello-world tool; the `name` argument is currently unused.
    """
    m = maude.getModule("NAT")
    t = m.parseTerm("2 * 3")
    t.reduce()
    return f"Result = {t}"
