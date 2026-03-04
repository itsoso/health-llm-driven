# Health MCP Server

基于 Model Context Protocol (MCP) 的健康数据管理服务，可将健康管理能力暴露给任意 AI 客户端（Claude Desktop、Cursor、自定义 Agent 等）。

## 快速开始

### 方式一：本地运行（stdio 模式）

适用于 Claude Desktop 等本地 AI 客户端直接调用。

```bash
cd mcp-server
pip install -r requirements.txt

export HEALTH_API_URL=https://health-api.executor.life/api/v1
export HEALTH_API_TOKEN=your-jwt-token
python server.py
```

### 方式二：远程运行（SSE 模式）

适用于远程客户端通过 HTTP SSE 连接。

```bash
export HEALTH_API_URL=https://health-api.executor.life/api/v1
export HEALTH_API_TOKEN=your-jwt-token
export MCP_TRANSPORT=sse
export MCP_SSE_PORT=8808
python server.py
```

### 方式三：Docker 部署（推荐生产环境）

#### 单独启动 MCP Server

```bash
cd mcp-server
docker build -t health-mcp-server .
docker run -d \
  --name health-mcp \
  -p 8808:8808 \
  -e HEALTH_API_URL=https://health-api.executor.life/api/v1 \
  -e HEALTH_API_TOKEN=your-jwt-token \
  -e MCP_TRANSPORT=sse \
  -e MCP_SSE_PORT=8808 \
  --restart unless-stopped \
  health-mcp-server
```

#### 配合 docker-compose 全栈启动

项目根目录的 `docker-compose.yml` 已包含 MCP Server 配置：

```bash
# 设置环境变量
export MCP_API_TOKEN=your-jwt-token

# 启动所有服务（含后端、MCP Server、Celery 等）
docker compose up -d

# 仅启动 MCP Server
docker compose up -d mcp-server

# 查看日志
docker compose logs -f mcp-server

# 重启
docker compose restart mcp-server
```

docker-compose 中 MCP Server 自动连接内部后端（`http://backend:8000/api/v1`），无需公网暴露后端接口。

#### Docker 环境变量

| 变量 | 必填 | 说明 | 默认值 |
|------|:---:|------|--------|
| `HEALTH_API_URL` | ✅ | 后端 API 地址 | - |
| `HEALTH_API_TOKEN` | ✅ | JWT 认证 Token | - |
| `MCP_TRANSPORT` | ❌ | 传输模式 `stdio` / `sse` | `stdio` |
| `MCP_SSE_PORT` | ❌ | SSE 模式监听端口 | `8808` |

#### 验证服务状态

```bash
# 检查容器运行状态
docker ps | grep mcp

# 测试 SSE 端点
curl -N http://localhost:8808/sse
```

## 可用工具（18 个）

### 查询工具（10 个）
| 工具 | 说明 |
|------|------|
| `get_health_summary` | 综合健康概览（步数、心率、睡眠） |
| `get_weight_history` | 体重记录 |
| `get_blood_pressure_history` | 血压记录 |
| `get_water_intake` | 饮水量 |
| `get_sleep_data` | 睡眠分析 |
| `get_heart_rate` | 心率 & HRV |
| `get_workout_history` | 运动记录 |
| `get_diet_records` | 饮食记录 |
| `get_checkin_status` | 打卡状态 |
| `get_achievements` | 成就徽章 |

### 记录工具（5 个）
| 工具 | 说明 |
|------|------|
| `record_water` | 记录饮水 |
| `record_weight` | 记录体重 |
| `record_blood_pressure` | 记录血压 |
| `record_checkin` | 快速打卡 |
| `record_diet` | 记录饮食 |

### 分析工具（3 个）
| 工具 | 说明 |
|------|------|
| `get_health_analysis` | AI 健康分析 |
| `get_daily_recommendation` | 每日健康建议 |
| `get_health_trends` | 健康趋势预测 |

## 客户端配置

### Claude Desktop

在 `~/.claude/claude_desktop_config.json` 中添加：

```json
{
  "mcpServers": {
    "health": {
      "command": "python",
      "args": ["/path/to/mcp-server/server.py"],
      "env": {
        "HEALTH_API_URL": "https://health-api.executor.life/api/v1",
        "HEALTH_API_TOKEN": "your-jwt-token"
      }
    }
  }
}
```

### Claude Code

在 `~/.claude/settings.json` 中添加：

```json
{
  "mcpServers": {
    "health": {
      "command": "python",
      "args": ["/path/to/mcp-server/server.py"],
      "env": {
        "HEALTH_API_URL": "https://health-api.executor.life/api/v1",
        "HEALTH_API_TOKEN": "your-jwt-token"
      }
    }
  }
}
```

### Cursor / 其他 SSE 客户端

先以 SSE 模式启动服务，然后在客户端配置远程 MCP 端点：

```
http://your-server:8808/sse
```

## 测试

```bash
cd mcp-server
pip install -r requirements.txt
python -m pytest tests/ -v
```
