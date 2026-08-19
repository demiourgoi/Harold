from fastmcp.utilities.logging import get_logger

from harold_mcp.server import mcp

_LOG = get_logger(__name__)


def run() -> None:
    """Run the MCP server."""
    _LOG.info("Launching Harold...")
    mcp.run()


if __name__ == "__main__":  # pragma: no cover
    run()
