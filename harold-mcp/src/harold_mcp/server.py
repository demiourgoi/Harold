import maude
from fastmcp import FastMCP

from harold_mcp.resources import HAROLD_ICON

maude.init()

mcp = FastMCP("Maude programming tools", icons=[HAROLD_ICON])


@mcp.tool
def greet(name: str) -> str:
    m = maude.getModule("NAT")
    t = m.parseTerm("2 * 3")
    t.reduce()
    return f"Result = {t}"
