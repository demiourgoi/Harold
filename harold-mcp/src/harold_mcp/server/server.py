"""Harold MCP server: the FastMCP instance and its lifecycle.

Importing this module builds the `mcp` instance but does **not** initialize
Maude: the interpreter lives in a worker process managed by the server
lifespan (see `harold_mcp.maude`).
"""

from fastmcp import FastMCP

from harold_mcp.logging import get_logger
from harold_mcp.resources import HAROLD_ICON

_LOG = get_logger(__name__)


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


def run() -> None:
    """Run the MCP server over stdio."""
    _LOG.info("Initializing Harold...")
    mcp.run()
