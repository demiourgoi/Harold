from fastmcp import FastMCP

mcp = FastMCP("Maude programming tools")


@mcp.tool
def greet(name: str) -> str:
    return f"Hello, {name}!"
