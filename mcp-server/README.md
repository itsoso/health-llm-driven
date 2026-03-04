# Health MCP Server

A Model Context Protocol (MCP) server that exposes health management capabilities to any AI client.

## Quick Start

### Local (stdio mode)
```bash
export HEALTH_API_URL=https://your-health-api.com/api/v1
export HEALTH_API_TOKEN=your-jwt-token
pip install -r requirements.txt
python server.py
```

### Remote (SSE mode)
```bash
export MCP_TRANSPORT=sse
export MCP_SSE_PORT=8808
python server.py
```

### Docker
```bash
docker compose up mcp-server
```

## Available Tools

### Query Tools (10)
- `get_health_summary` - Health overview (steps, heart rate, sleep)
- `get_weight_history` - Weight records
- `get_blood_pressure_history` - Blood pressure records
- `get_water_intake` - Water intake
- `get_sleep_data` - Sleep analysis
- `get_heart_rate` - Heart rate & HRV
- `get_workout_history` - Workout records
- `get_diet_records` - Diet records
- `get_checkin_status` - Checkin status
- `get_achievements` - Badges & achievements

### Record Tools (5)
- `record_water` - Log water intake
- `record_weight` - Log weight
- `record_blood_pressure` - Log blood pressure
- `record_checkin` - Quick checkin
- `record_diet` - Log diet

### Analysis Tools (3)
- `get_health_analysis` - AI health analysis
- `get_daily_recommendation` - Daily health tips
- `get_health_trends` - Health trend predictions

## Claude Desktop Configuration

Add to `~/.claude/claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "health": {
      "command": "python",
      "args": ["path/to/mcp-server/server.py"],
      "env": {
        "HEALTH_API_URL": "https://your-health-api.com/api/v1",
        "HEALTH_API_TOKEN": "your-jwt-token"
      }
    }
  }
}
```

## Testing

```bash
python -m pytest tests/ -v
```
