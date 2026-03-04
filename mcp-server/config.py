"""Health MCP Server 配置"""
import os


class Config:
    HEALTH_API_URL = os.environ.get("HEALTH_API_URL", "http://localhost:8000/api/v1")
    HEALTH_API_TOKEN = os.environ.get("HEALTH_API_TOKEN", "")
    MCP_TRANSPORT = os.environ.get("MCP_TRANSPORT", "stdio")
    MCP_SSE_PORT = int(os.environ.get("MCP_SSE_PORT", "8808"))
