"""Health MCP Server 入口"""
from fastmcp import FastMCP

from config import Config

mcp = FastMCP(
    "Health Management",
    description="AI-powered health management system - query health data, record measurements, and get health analysis",
)


if __name__ == "__main__":
    transport = Config.MCP_TRANSPORT
    if transport == "sse":
        mcp.run(transport="sse", port=Config.MCP_SSE_PORT)
    else:
        mcp.run(transport="stdio")
