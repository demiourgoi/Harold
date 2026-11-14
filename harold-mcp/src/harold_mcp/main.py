from importlib.metadata import version
from pathlib import Path
from typing import Annotated

from cyclopts import App, Parameter

from harold_mcp.server import run as run_server
from harold_mcp.skill_install import install_skill

app = App(name="harold-mcp", help="An MCP server for AI-assisted Maude programming.")
_ = app.command(serve := App(name="serve"))


@app.default
@serve.default
def run() -> None:
    """Run the MCP server."""
    run_server()


@app.command
def setup(
    directory: Annotated[Path, Parameter(help="Skills directory to install into (ignored with --global).")] = Path(
        ".agents"
    )
    / "skills",
    global_: Annotated[bool, Parameter(["--global", "-g"], help="Install into ~/.agents/skills instead.")] = False,
) -> None:
    """Install the bundled maude-manual skill for coding agents."""
    base = Path.home() / ".agents" / "skills" if global_ else directory
    installed = install_skill(base)
    print(f"Installed the {installed.name} skill at {installed} (harold-mcp {version('harold-mcp')}).")


if __name__ == "__main__":  # pragma: no cover
    app()
