import maude
from fastmcp import FastMCP

maude.init()

mcp = FastMCP("Maude programming tools")


@mcp.tool
def greet(name: str) -> str:
    m = maude.getModule("NAT")
    t = m.parseTerm("2 * 3")
    t.reduce()
    return f"Result = {t}"
