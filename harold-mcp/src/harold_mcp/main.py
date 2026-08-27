import argparse
from importlib.metadata import version

from harold_mcp.server import run as run_server

PACKAGE_NAME = "harold-mcp"


def run() -> None:
    """Run the MCP server, printing the version instead when -v/--version is given."""
    parser = argparse.ArgumentParser(
        prog=PACKAGE_NAME,
        description="An MCP server for AI-assisted Maude programming.",
        add_help=False,
    )
    _ = parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"{PACKAGE_NAME} {version(PACKAGE_NAME)}",
    )
    _ = parser.parse_known_args()
    run_server()


if __name__ == "__main__":  # pragma: no cover
    run()
