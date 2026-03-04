"""Health MCP Server 入口"""
from fastmcp import FastMCP

from config import Config
from tools.query import (
    get_achievements,
    get_blood_pressure_history,
    get_checkin_status,
    get_diet_records,
    get_health_summary,
    get_heart_rate,
    get_sleep_data,
    get_water_intake,
    get_weight_history,
    get_workout_history,
)
from tools.record import (
    record_blood_pressure,
    record_checkin,
    record_diet,
    record_water,
    record_weight,
)
from tools.analysis import (
    get_daily_recommendation,
    get_health_analysis,
    get_health_trends,
)

mcp = FastMCP(
    "Health Management",
    description="AI-powered health management system - query health data, record measurements, and get health analysis",
)

# ---- 查询工具 (10) ----
mcp.tool()(get_health_summary)
mcp.tool()(get_weight_history)
mcp.tool()(get_blood_pressure_history)
mcp.tool()(get_water_intake)
mcp.tool()(get_sleep_data)
mcp.tool()(get_heart_rate)
mcp.tool()(get_workout_history)
mcp.tool()(get_diet_records)
mcp.tool()(get_checkin_status)
mcp.tool()(get_achievements)

# ---- 记录工具 (5) ----
mcp.tool()(record_water)
mcp.tool()(record_weight)
mcp.tool()(record_blood_pressure)
mcp.tool()(record_checkin)
mcp.tool()(record_diet)

# ---- 分析工具 (3) ----
mcp.tool()(get_health_analysis)
mcp.tool()(get_daily_recommendation)
mcp.tool()(get_health_trends)


if __name__ == "__main__":
    transport = Config.MCP_TRANSPORT
    if transport == "sse":
        mcp.run(transport="sse", port=Config.MCP_SSE_PORT)
    else:
        mcp.run(transport="stdio")
