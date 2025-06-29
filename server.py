import logging

from mcp.server.fastmcp import FastMCP

# MCP server for testing purpose
mcp = FastMCP("Demo", host="127.0.0.1", port="48000")


@mcp.tool()
def toUpperCase(text: str) -> str:
    """Add two numbers"""
    return text.upper()


@mcp.tool(description="greetings service")
def get_greeting(name: str) -> str:
    """Get a personalized greeting"""
    return f"Hello, {name}!"


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    mcp.run(transport="sse")