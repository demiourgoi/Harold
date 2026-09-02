from cyclopts import App

from harold_mcp.server import run as run_server

app = App(name="harold-mcp", help="An MCP server for AI-assisted Maude programming.")
_ = app.command(serve := App(name="serve"))


@app.default
@serve.default
def run() -> None:
    """Run the MCP server."""
    run_server()


if __name__ == "__main__":  # pragma: no cover
    app()
