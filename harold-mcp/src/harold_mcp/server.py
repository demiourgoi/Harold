from fastmcp import FastMCP

mcp = FastMCP("Maude programming assistant")


@mcp.tool
def greet(name: str) -> str:
    return f"Hello, {name}!"
