"""Harold MCP server package: the FastMCP instance, its lifecycle, and its tools."""

from harold_mcp.server import tools  # noqa: F401  (registers the tools on mcp)
from harold_mcp.server.server import mcp, run

__all__ = ["mcp", "run"]
