# OpenClaw 深度集成设计文档

> **目标**：双向集成健康系统与 OpenClaw，通过 MCP Server + OpenClaw Skills 让健康数据在任意 AI 客户端和渠道可用。

**日期**：2026-03-04

---

## 1. 概览

### 1.1 目标

- 将健康系统的数据查询、记录写入、分析报告能力通过标准化接口暴露
- OpenClaw 用户可在 Telegram/Discord/微信/Web 等任意渠道操作健康数据
- 任何支持 MCP 的 AI 客户端（Claude Desktop、Cursor 等）也能使用

### 1.2 方案

**双轨方案**：MCP Server（核心，行业标准）+ OpenClaw Skill（薄包装层，原生体验）

### 1.3 核心决策

| 决策项 | 选择 |
|--------|------|
| 核心协议 | MCP（Model Context Protocol） |
| MCP 框架 | FastMCP（Python） |
| 传输模式 | stdio（本地）+ SSE（远程） |
| OpenClaw 集成 | Skills（SKILL.md） |
| 认证方式 | Bearer Token（复用 JWT） |
| 前端改造 | Function Calling 替代 <<<ACTIONS: 正则 |

---

## 2. MCP Server

### 2.1 Tools 清单

#### 数据查询类（只读）

| Tool | 描述 | 参数 |
|------|------|------|
| `get_health_summary` | 今日/本周健康概览 | `period: today\|week\|month` |
| `get_weight_history` | 体重历史 | `days: int` |
| `get_blood_pressure_history` | 血压历史 | `days: int` |
| `get_water_intake` | 饮水记录 | `date?: string` |
| `get_sleep_data` | 睡眠数据 | `days: int` |
| `get_heart_rate` | 心率数据 | `days: int` |
| `get_workout_history` | 运动记录 | `days: int, type?: string` |
| `get_diet_records` | 饮食记录 | `days: int` |
| `get_checkin_status` | 打卡状态 | `date?: string` |
| `get_achievements` | 成就徽章 | 无 |

#### 记录写入类（写操作）

| Tool | 描述 | 参数 |
|------|------|------|
| `record_water` | 记录饮水 | `amount_ml: int` |
| `record_weight` | 记录体重 | `weight_kg: float` |
| `record_blood_pressure` | 记录血压 | `systolic: int, diastolic: int, heart_rate?: int` |
| `record_checkin` | 快速打卡 | `template_name: string, value?: float` |
| `record_diet` | 记录饮食 | `meal_type: string, foods: string, calories?: int` |

#### 分析报告类

| Tool | 描述 | 参数 |
|------|------|------|
| `get_health_analysis` | AI 健康分析 | `question?: string` |
| `get_daily_recommendation` | 今日推荐 | 无 |
| `get_health_trends` | 健康趋势预测 | `dimension: weight\|sleep\|exercise\|overall` |

### 2.2 技术架构

```
Claude Desktop / Cursor / OpenClaw / 任何 MCP Client
        ↓ MCP 协议 (stdio 或 SSE)
Health MCP Server (Python, FastMCP)
        ↓ HTTP (Bearer Token)
健康系统后端 API (health-api.executor.life)
```

### 2.3 目录结构

```
mcp-server/
├── server.py              # MCP Server 入口
├── tools/
│   ├── query.py           # 数据查询类 Tools
│   ├── record.py          # 记录写入类 Tools
│   └── analysis.py        # 分析报告类 Tools
├── client.py              # 健康 API HTTP 客户端
├── config.py              # 配置（API URL, Token）
├── requirements.txt
└── README.md
```

### 2.4 配置

```env
HEALTH_API_URL=https://health-api.executor.life/api/v1
HEALTH_API_TOKEN=<user-jwt-token>
MCP_TRANSPORT=stdio    # stdio | sse
MCP_SSE_PORT=8808      # SSE 模式端口
```

### 2.5 Docker Compose 集成

在现有 `docker-compose.yml` 中增加 `mcp-server` service：

```yaml
mcp-server:
  build:
    context: ./mcp-server
    dockerfile: Dockerfile
  environment:
    HEALTH_API_URL: http://backend:8000/api/v1
    HEALTH_API_TOKEN: ${MCP_API_TOKEN}
    MCP_TRANSPORT: sse
    MCP_SSE_PORT: 8808
  ports:
    - "8808:8808"
  depends_on:
    backend:
      condition: service_healthy
```

---

## 3. OpenClaw Skills

### 3.1 Skill 清单

| Skill 目录 | 描述 | 触发示例 |
|------------|------|---------|
| `health-query/` | 查询健康数据 | "查一下我今天的步数"、"最近一周体重变化" |
| `health-record/` | 记录健康数据 | "记录喝水250ml"、"体重72公斤"、"血压120/80" |
| `health-analysis/` | 健康分析 | "分析我最近的睡眠趋势"、"给我今天的健康建议" |

### 3.2 Skill 格式示例

#### health-query/SKILL.md

```yaml
---
name: health-query
description: Query health data from the Health Management System - steps, heart rate, sleep, weight, blood pressure, workouts, diet, checkin status, and achievements.
requires:
  env:
    - HEALTH_API_URL
    - HEALTH_API_TOKEN
---

You have access to a Health Management System API. Use curl to query health data.

## API Base
URL: ${HEALTH_API_URL}
Auth Header: Authorization: Bearer ${HEALTH_API_TOKEN}

## Available Endpoints

### Garmin/运动健康数据
- GET /garmin/health-data?days=7 — 步数、心率、睡眠、压力、Body Battery

### 体重
- GET /weight/?days=7 — 体重历史记录

### 血压
- GET /blood-pressure/?days=7 — 血压历史记录

### 饮水
- GET /water/?date=YYYY-MM-DD — 指定日期饮水记录

### 打卡
- GET /checkin/templates — 打卡模板和今日状态
- GET /checkin/records?days=7 — 打卡历史

### 饮食
- GET /diet/?days=3 — 饮食记录

### 运动
- GET /workout/?days=7 — 运动记录

### 成就
- GET /achievements/me — 成就徽章和进度

## Response Format
Always format responses in readable Chinese with appropriate units and formatting.
```

#### health-record/SKILL.md

```yaml
---
name: health-record
description: Record health data - water intake, weight, blood pressure, checkins, and diet entries.
requires:
  env:
    - HEALTH_API_URL
    - HEALTH_API_TOKEN
---

You can record health data via the Health Management System API.

## API Base
URL: ${HEALTH_API_URL}
Auth Header: Authorization: Bearer ${HEALTH_API_TOKEN}

## Available Actions

### 记录饮水
POST /water/
Body: {"amount_ml": 250, "cup_type": "medium"}

### 记录体重
POST /weight/
Body: {"weight_kg": 72.5}

### 记录血压
POST /blood-pressure/
Body: {"systolic": 120, "diastolic": 80, "heart_rate": 72}

### 快速打卡
POST /checkin/quick
Body: {"template_name": "俯卧撑", "value": 30}

### 记录饮食
POST /diet/
Body: {"meal_type": "lunch", "description": "鸡胸肉沙拉", "estimated_calories": 400}

## Rules
- Confirm the action with the user before recording
- After successful recording, report what was saved
- Always respond in Chinese
```

#### health-analysis/SKILL.md

```yaml
---
name: health-analysis
description: Get AI health analysis, daily recommendations, and health trend predictions.
requires:
  env:
    - HEALTH_API_URL
    - HEALTH_API_TOKEN
---

You can request health analysis and recommendations.

## API Base
URL: ${HEALTH_API_URL}
Auth Header: Authorization: Bearer ${HEALTH_API_TOKEN}

## Available Endpoints

### 今日推荐
GET /daily-recommendation/

### 健康趋势分析
POST /health-trends/analyze
Body: {"dimension": "weight|sleep|exercise|overall"}

### AI 健康洞察
GET /ai-insights/

### 健康评分
GET /health-score/today

## Rules
- Present analysis results in a structured, readable format
- Highlight important trends and anomalies
- Always respond in Chinese
```

### 3.3 Gateway 配置

在 OpenClaw 的 `~/.openclaw/openclaw.json` 中注入 API 凭证：

```json
{
  "skills": {
    "entries": {
      "health-query": {
        "env": {
          "HEALTH_API_URL": "https://health-api.executor.life/api/v1",
          "HEALTH_API_TOKEN": "<jwt-token>"
        }
      },
      "health-record": {
        "env": {
          "HEALTH_API_URL": "https://health-api.executor.life/api/v1",
          "HEALTH_API_TOKEN": "<jwt-token>"
        }
      },
      "health-analysis": {
        "env": {
          "HEALTH_API_URL": "https://health-api.executor.life/api/v1",
          "HEALTH_API_TOKEN": "<jwt-token>"
        }
      }
    }
  }
}
```

---

## 4. 前端 Function Calling 迁移

### 4.1 现状

当前 `chat_service.py` 使用正则解析 `<<<ACTIONS:` 标记来执行动作（记录饮水、体重等）。这种方式不够可靠，且 LLM 输出格式不稳定。

### 4.2 迁移方案

在向 OpenClaw / LLM 发送 chat 请求时，携带 `tools` 参数（OpenAI 兼容格式）：

```python
tools = [
    {
        "type": "function",
        "function": {
            "name": "record_water",
            "description": "记录用户饮水量",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount_ml": {"type": "integer", "description": "饮水量(毫升)"}
                },
                "required": ["amount_ml"]
            }
        }
    },
    # ... 其他工具
]

response = await provider.chat(messages=messages, tools=tools)
```

当 LLM 返回 `tool_calls` 时，后端执行对应操作：

```python
if response.tool_calls:
    for tool_call in response.tool_calls:
        result = execute_tool(tool_call.function.name, tool_call.function.arguments)
        # 将结果反馈给 LLM 生成自然语言回复
```

### 4.3 LLM Provider 改动

在 `LLMProvider` 基类的 `chat()` 方法中增加 `tools` 参数支持：

```python
async def chat(self, messages, model=None, temperature=0.7,
               max_tokens=2000, stream=False, tools=None) -> str | AsyncIterator:
```

OpenClawProvider 和 OpenAIProvider 都支持将 tools 透传给 API。

---

## 5. 实施优先级

| 优先级 | 内容 | 估计工作量 | 依赖 |
|--------|------|-----------|------|
| P0 | MCP Server 核心（18 个 Tools） | 中 | 无 |
| P1 | OpenClaw Skills（3 个 SKILL.md） | 小 | 需要确认 API 端点路径 |
| P2 | LLM Provider tools 参数支持 | 小 | 无 |
| P3 | 前端 Function Calling 迁移 | 中 | P2 |
| P4 | Docker Compose 集成 MCP Server | 小 | P0 |

---

## 6. 数据流总览

### 6.1 OpenClaw 渠道 → 健康系统（通过 Skill）

```
用户 (Telegram) → "我今天走了多少步？"
→ OpenClaw Gateway
→ 匹配 health-query Skill
→ curl GET health-api.executor.life/api/v1/garmin/health-data?days=1
→ 返回 JSON
→ OpenClaw 格式化为中文
→ 用户看到 "今天步数 8,234 步，达标！"
```

### 6.2 MCP 客户端 → 健康系统

```
用户 (Claude Desktop) → "记录体重72公斤"
→ Claude 调用 MCP tool: record_weight(72.0)
→ Health MCP Server → POST health-api/weight/
→ 返回成功
→ Claude 回复 "已记录体重 72.0 kg"
```

### 6.3 健康前端 → Function Calling（迁移后）

```
用户 (健康 App) → "帮我记录喝水250ml"
→ 后端 chat_service → OpenClaw /v1/chat/completions (with tools)
→ OpenClaw 返回 tool_call: record_water(250)
→ 后端执行写入
→ 返回结果给 OpenClaw 生成回复
→ 用户看到 "已记录饮水 250ml，今日累计 1,500ml"
```
