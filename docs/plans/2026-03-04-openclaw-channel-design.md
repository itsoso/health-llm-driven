# OpenClaw Channel 代理集成设计

## 目标

将健康管理系统作为 OpenClaw 的一个 Channel（类似飞书/钉钉集成），在 AI 助手页面新增 OpenClaw tab，前端通过后端代理连接 OpenClaw Gateway 的 `/v1/chat/completions` 接口，OpenClaw Agent 通过 Skills 自主调用 Health API。

## 架构

```
┌──────────────────────────────────────────────────┐
│ 前端 /ai-assistant (OpenClaw tab)                 │
│  POST /api/v1/openclaw/stream  ──SSE──→ 渲染对话  │
│  GET  /api/v1/openclaw/conversations   历史列表    │
│  GET  /api/v1/openclaw/conversations/:id 详情     │
│  DELETE /api/v1/openclaw/conversations/:id 删除   │
└──────────────┬───────────────────────────────────┘
               │
┌──────────────▼───────────────────────────────────┐
│ 后端 FastAPI (39.98.206.178)                      │
│  openclaw.py (router) + openclaw_service.py       │
│  - 验证用户 token                                  │
│  - 管理会话 & 消息 (独立表)                         │
│  - 转发到 OpenClaw Gateway (stream)                │
│  - SSE 流式返回前端                                 │
└──────────────┬───────────────────────────────────┘
               │ HTTP POST (stream)
┌──────────────▼───────────────────────────────────┐
│ OpenClaw Gateway (47.237.191.17:18789)             │
│  Nginx SSL → bot.executor.life                    │
│  /v1/chat/completions (Token Auth)                │
│  Agent → Skills → curl Health API                 │
└──────────────┬───────────────────────────────────┘
               │ curl (由 Skills 发起)
┌──────────────▼───────────────────────────────────┐
│ Health API (39.98.206.178/api/v1/*)               │
│  garmin-analysis, weight, water, checkin, etc.    │
└──────────────────────────────────────────────────┘
```

**选择方案 B（后端代理）的理由：**
1. Gateway 无需对外暴露端口
2. 消息实时存储不丢失
3. 统一鉴权
4. 和现有 SSE 架构一致

## 数据模型

### openclaw_conversations

| 列 | 类型 | 说明 |
|----|------|------|
| id | Integer PK | 自增 ID |
| user_id | Integer FK(users.id) | 用户 ID，有索引 |
| title | String(200) | 对话标题，默认"新对话" |
| session_key | String(100) | OpenClaw Gateway 侧会话 key |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

### openclaw_messages

| 列 | 类型 | 说明 |
|----|------|------|
| id | Integer PK | 自增 ID |
| conversation_id | Integer FK | 关联会话 |
| role | String(20) | "user" / "assistant" |
| content | Text | 消息内容 |
| created_at | DateTime | 创建时间 |

**设计要点：**
- 独立于 chat_conversations/chat_messages，避免和健康助理数据混杂
- session_key 传给 OpenClaw 的 `user` 字段维持会话
- 不存 system 消息（由 OpenClaw 自管）

## 后端 API

### 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/openclaw/stream` | POST | 流式对话 (SSE) |
| `/openclaw/conversations` | GET | 对话列表 |
| `/openclaw/conversations/{id}` | GET | 对话详情 + 消息 |
| `/openclaw/conversations/{id}` | DELETE | 删除对话 |

### 流式对话流程

```python
async def send_message_stream(user_id, conversation_id, content):
    # 1. 获取或创建会话
    conv = get_or_create_conversation(user_id, conversation_id)
    # 2. 保存用户消息
    save_message(conv.id, "user", content)
    # 3. 构建 messages 列表（最近 20 条历史）
    messages = build_messages_from_history(conv.id, limit=20)
    # 4. 流式调用 Gateway /v1/chat/completions
    full_reply = ""
    async for chunk in call_gateway_stream(messages, conv.session_key):
        token = extract_delta_content(chunk)
        if token:
            full_reply += token
            yield {"event": "token", "data": {"content": token}}
    # 5. 保存 AI 回复
    msg = save_message(conv.id, "assistant", full_reply)
    # 6. 首次消息自动生成标题
    if is_first_message(conv):
        conv.title = content[:50]
    # 7. done 事件
    yield {"event": "done", "data": {"conversation_id": conv.id, "message_id": msg.id}}
```

### Gateway 调用

```python
async def call_gateway_stream(messages, session_key):
    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream("POST", f"{GATEWAY_URL}/v1/chat/completions",
            json={"model": "default", "messages": messages, "stream": True, "user": session_key},
            headers={"Authorization": f"Bearer {OPENCLAW_API_KEY}"}
        ) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    yield json.loads(data)
```

### 配置项 (.env)

```
# OpenClaw Gateway — 通过 Nginx SSL 代理访问，无需直连内网端口
OPENCLAW_GATEWAY_URL=https://bot.executor.life
OPENCLAW_API_KEY=e89ad0759bb523b9cc56dbd52fb7993f86f545f19d6d4273
OPENCLAW_MODEL=openclaw:main

# Gateway 实际部署: 47.237.191.17:18789 (loopback)
# Nginx SSL 代理: bot.executor.life → 127.0.0.1:18789
# Token 认证: Bearer {OPENCLAW_API_KEY}
```

### 已完成部署状态

| 组件 | 状态 | 说明 |
|------|------|------|
| 后端 models/service/api | 已部署 | 39.98.206.178 |
| 前端 OpenClaw tab | 已部署 | health.executor.life |
| DB 表 (openclaw_conversations/messages) | 已创建 | PostgreSQL |
| OPENCLAW_GATEWAY_URL | 已配置 | https://bot.executor.life |
| Gateway 连通性 | 已验证 | 后端可正常调用 Gateway API |

## 前端 UI

### AI 助手 tab 切换

在 `/ai-assistant` 页面，将现有 `chatMode` 从 `'health' | 'proxy'` 改为 `'health' | 'openclaw'`：

- **健康助理 tab** → 现有 `/chat/stream`，保留所有健康功能
- **OpenClaw tab** → 新的 `/openclaw/stream`，纯粹对话

### OpenClaw 模式差异

| 功能 | 健康助理 | OpenClaw |
|------|---------|----------|
| 消息发送 | `/chat/stream` | `/openclaw/stream` |
| 历史对话 | `/chat/conversations` | `/openclaw/conversations` |
| 快捷问题 | 健康相关 | 通用 |
| 图片上传 | 支持 | 不支持 |
| 语音输入 | 支持 | 不支持 |
| action 解析 | 支持 | 不支持 |
| 饮食/打卡通知 | 支持 | 不支持 |

### 快捷问题

```typescript
const openclawQuickQuestions = [
  "帮我查看最近7天的运动数据",
  "记录喝水250ml",
  "我的健康评分是多少？",
  "分析一下我的睡眠趋势",
];
```

### 前端 API (`api.ts`)

```typescript
export const openclawApi = {
  streamMessage: (conversationId, content) =>
    fetch(`${API}/v1/openclaw/stream`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ conversation_id: conversationId, content }),
    }),
  getConversations: () => api.get('/v1/openclaw/conversations'),
  getConversation: (id) => api.get(`/v1/openclaw/conversations/${id}`),
  deleteConversation: (id) => api.delete(`/v1/openclaw/conversations/${id}`),
};
```

## 新增文件

| 文件 | 说明 |
|------|------|
| `backend/app/models/openclaw.py` | OpenClawConversation + OpenClawMessage 模型 |
| `backend/app/api/openclaw.py` | 4 个 API 端点 |
| `backend/app/services/openclaw_service.py` | Gateway 调用 + 会话管理 |

## 修改文件

| 文件 | 改动 |
|------|------|
| `backend/app/api/main.py` | 注册 openclaw router |
| `backend/app/models/__init__.py` | 注册新模型 |
| `frontend/src/services/api.ts` | 新增 openclawApi |
| `frontend/src/app/ai-assistant/page.tsx` | tab 切换逻辑，OpenClaw 模式走独立 API |

## 数据库迁移

```sql
-- 生产环境执行
CREATE TABLE openclaw_conversations (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    title VARCHAR(200) DEFAULT '新对话',
    session_key VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_openclaw_conv_user ON openclaw_conversations(user_id);

CREATE TABLE openclaw_messages (
    id SERIAL PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES openclaw_conversations(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_openclaw_msg_conv ON openclaw_messages(conversation_id);
```
