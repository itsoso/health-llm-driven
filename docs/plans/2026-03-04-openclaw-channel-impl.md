# OpenClaw Channel 代理集成 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在 AI 助手页面新增 OpenClaw tab，后端代理连接 OpenClaw Gateway `/v1/chat/completions`，实现独立的 OpenClaw 对话通道。

**Architecture:** 后端新建独立的 `openclaw` router + service + model，通过 httpx 流式调用 OpenClaw Gateway，SSE 转发给前端。前端在 AI 助手页面复用 tab 切换，OpenClaw 模式走完全独立的 API 路径。

**Tech Stack:** FastAPI, SQLAlchemy, httpx (async streaming), SSE, Next.js/React

---

### Task 1: Backend Model — OpenClaw 数据模型

**Files:**
- Create: `backend/app/models/openclaw.py`
- Modify: `backend/app/models/__init__.py`

**Step 1: Create the model file**

```python
# backend/app/models/openclaw.py
"""OpenClaw Channel 对话模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Index
from sqlalchemy.orm import relationship
from app.database import Base


class OpenClawConversation(Base):
    """OpenClaw 对话会话"""
    __tablename__ = "openclaw_conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(200), default="新对话")
    session_key = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    messages = relationship(
        "OpenClawMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="OpenClawMessage.created_at",
    )

    __table_args__ = (
        Index("ix_openclaw_conv_user_updated", "user_id", "updated_at"),
    )


class OpenClawMessage(Base):
    """OpenClaw 对话消息"""
    __tablename__ = "openclaw_messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(
        Integer,
        ForeignKey("openclaw_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String(20), nullable=False)  # user / assistant
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("OpenClawConversation", back_populates="messages")
```

**Step 2: Register models in `__init__.py`**

在 `backend/app/models/__init__.py` 末尾添加：

```python
# OpenClaw Channel
from app.models.openclaw import OpenClawConversation, OpenClawMessage
```

并在 `__all__` 列表中添加 `"OpenClawConversation"`, `"OpenClawMessage"`。

**Step 3: Commit**

```bash
git add backend/app/models/openclaw.py backend/app/models/__init__.py
git commit -m "feat: add OpenClaw conversation & message models"
```

---

### Task 2: Backend Config — 添加 OpenClaw Gateway 配置

**Files:**
- Modify: `backend/app/config.py`

**Step 1: 在 Settings 类中添加配置项**

在 `backend/app/config.py` 的 `Settings` 类中添加：

```python
    # OpenClaw Gateway
    openclaw_gateway_url: str = ""  # e.g. http://47.237.191.17:3000
    openclaw_api_key: str = ""
```

**Step 2: Commit**

```bash
git add backend/app/config.py
git commit -m "feat: add OpenClaw Gateway config (url + api key)"
```

---

### Task 3: Backend Service — OpenClaw 对话服务

**Files:**
- Create: `backend/app/services/openclaw_service.py`

**Step 1: Create the service file**

```python
# backend/app/services/openclaw_service.py
"""OpenClaw Channel 对话服务 — 代理连接 OpenClaw Gateway"""
import json
import logging
import uuid
from datetime import datetime
from typing import AsyncGenerator, Dict, List, Optional

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models.openclaw import OpenClawConversation, OpenClawMessage

logger = logging.getLogger(__name__)


class OpenClawService:
    """OpenClaw Channel 服务"""

    def __init__(self, db: Session):
        self.db = db

    # ── 会话管理 ──────────────────────────────────────────

    def get_or_create_conversation(
        self, user_id: int, conversation_id: Optional[int], title: str = "新对话"
    ) -> OpenClawConversation:
        if conversation_id:
            conv = (
                self.db.query(OpenClawConversation)
                .filter(
                    OpenClawConversation.id == conversation_id,
                    OpenClawConversation.user_id == user_id,
                )
                .first()
            )
            if not conv:
                raise ValueError("对话不存在")
            return conv

        conv = OpenClawConversation(
            user_id=user_id,
            title=title[:50],
            session_key=f"health-{user_id}-{uuid.uuid4().hex[:12]}",
        )
        self.db.add(conv)
        self.db.commit()
        self.db.refresh(conv)
        return conv

    def get_conversations(self, user_id: int, limit: int = 20) -> List[OpenClawConversation]:
        return (
            self.db.query(OpenClawConversation)
            .filter(OpenClawConversation.user_id == user_id)
            .order_by(OpenClawConversation.updated_at.desc())
            .limit(limit)
            .all()
        )

    def get_conversation_detail(
        self, user_id: int, conversation_id: int
    ) -> Optional[OpenClawConversation]:
        return (
            self.db.query(OpenClawConversation)
            .filter(
                OpenClawConversation.id == conversation_id,
                OpenClawConversation.user_id == user_id,
            )
            .first()
        )

    def delete_conversation(self, user_id: int, conversation_id: int) -> bool:
        conv = (
            self.db.query(OpenClawConversation)
            .filter(
                OpenClawConversation.id == conversation_id,
                OpenClawConversation.user_id == user_id,
            )
            .first()
        )
        if not conv:
            return False
        self.db.delete(conv)
        self.db.commit()
        return True

    # ── 消息管理 ──────────────────────────────────────────

    def save_message(self, conversation_id: int, role: str, content: str) -> OpenClawMessage:
        msg = OpenClawMessage(conversation_id=conversation_id, role=role, content=content)
        self.db.add(msg)
        self.db.commit()
        self.db.refresh(msg)
        return msg

    def build_messages(self, conversation_id: int, limit: int = 20) -> List[Dict[str, str]]:
        """从 DB 取最近 N 条历史，构建 OpenAI 格式 messages 列表"""
        history = (
            self.db.query(OpenClawMessage)
            .filter(OpenClawMessage.conversation_id == conversation_id)
            .order_by(OpenClawMessage.created_at.asc())
            .all()
        )
        recent = history[-limit:] if len(history) > limit else history
        return [{"role": m.role, "content": m.content} for m in recent]

    # ── Gateway 流式调用 ──────────────────────────────────

    async def _call_gateway_stream(
        self, messages: List[Dict], session_key: str
    ) -> AsyncGenerator[str, None]:
        """流式调用 OpenClaw Gateway /v1/chat/completions"""
        gateway_url = settings.openclaw_gateway_url.rstrip("/")
        if not gateway_url:
            raise ValueError("OPENCLAW_GATEWAY_URL 未配置")

        url = f"{gateway_url}/v1/chat/completions"
        headers = {}
        if settings.openclaw_api_key:
            headers["Authorization"] = f"Bearer {settings.openclaw_api_key}"

        payload = {
            "model": "default",
            "messages": messages,
            "stream": True,
            "user": session_key,
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    logger.error(f"OpenClaw Gateway error {resp.status_code}: {body[:500]}")
                    raise RuntimeError(f"Gateway returned {resp.status_code}")

                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content")
                        if content:
                            yield content
                    except (json.JSONDecodeError, IndexError, KeyError):
                        continue

    # ── 主流程 ────────────────────────────────────────────

    async def send_message_stream(
        self,
        user_id: int,
        message: str,
        conversation_id: Optional[int] = None,
    ) -> AsyncGenerator[Dict, None]:
        """流式发送消息到 OpenClaw Gateway 并实时转发"""

        # 1. 获取或创建会话
        conv = self.get_or_create_conversation(user_id, conversation_id, title=message)

        # 2. 保存用户消息
        self.save_message(conv.id, "user", message)

        # 3. 构建 messages 列表
        messages = self.build_messages(conv.id, limit=20)

        # 4. 流式调用 Gateway
        full_reply = ""
        try:
            async for token in self._call_gateway_stream(messages, conv.session_key):
                full_reply += token
                yield {"event": "token", "data": {"content": token}}
        except Exception as e:
            logger.error(f"OpenClaw Gateway 调用失败: {type(e).__name__}: {e}")
            full_reply = "抱歉，OpenClaw 暂时无法响应，请稍后再试。"
            yield {"event": "token", "data": {"content": full_reply}}

        # 5. 保存 AI 回复
        ai_msg = self.save_message(conv.id, "assistant", full_reply)

        # 6. 更新会话时间
        conv.updated_at = datetime.utcnow()
        self.db.commit()

        # 7. done 事件
        yield {
            "event": "done",
            "data": {
                "conversation_id": conv.id,
                "message_id": ai_msg.id,
            },
        }
```

**Step 2: Commit**

```bash
git add backend/app/services/openclaw_service.py
git commit -m "feat: add OpenClaw Channel service with Gateway streaming"
```

---

### Task 4: Backend API — OpenClaw 路由

**Files:**
- Create: `backend/app/api/openclaw.py`

**Step 1: Create the router file**

```python
# backend/app/api/openclaw.py
"""OpenClaw Channel API — 独立于健康助理的 OpenClaw 对话通道"""
import json
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.services.openclaw_service import OpenClawService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/openclaw", tags=["openclaw"])


# ── Schemas ───────────────────────────────────────────────

class OpenClawSendRequest(BaseModel):
    message: str
    conversation_id: int | None = None


class OpenClawConversationResponse(BaseModel):
    id: int
    title: str
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class OpenClawMessageResponse(BaseModel):
    id: int
    role: str
    content: str
    created_at: str

    class Config:
        from_attributes = True


class OpenClawConversationDetailResponse(BaseModel):
    id: int
    title: str
    messages: List[OpenClawMessageResponse]

    class Config:
        from_attributes = True


# ── Endpoints ─────────────────────────────────────────────

@router.post("/stream", summary="OpenClaw 流式对话")
async def stream_message(
    request: Request,
    req: OpenClawSendRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """流式发送消息到 OpenClaw Gateway，SSE 实时返回"""
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="消息不能为空")

    service = OpenClawService(db)

    async def generate():
        try:
            async for event in service.send_message_stream(
                user_id=current_user.id,
                message=req.message.strip(),
                conversation_id=req.conversation_id,
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"OpenClaw 流式异常: {e}", exc_info=True)
            error_event = {"event": "error", "data": {"message": str(e)}}
            yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/conversations", summary="OpenClaw 对话列表")
async def list_conversations(
    limit: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    service = OpenClawService(db)
    convs = service.get_conversations(current_user.id, limit)
    return [
        {
            "id": c.id,
            "title": c.title,
            "created_at": str(c.created_at),
            "updated_at": str(c.updated_at),
        }
        for c in convs
    ]


@router.get("/conversations/{conversation_id}", summary="OpenClaw 对话详情")
async def get_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    service = OpenClawService(db)
    conv = service.get_conversation_detail(current_user.id, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")
    return {
        "id": conv.id,
        "title": conv.title,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "created_at": str(m.created_at),
            }
            for m in conv.messages
        ],
    }


@router.delete("/conversations/{conversation_id}", summary="删除 OpenClaw 对话")
async def delete_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    service = OpenClawService(db)
    ok = service.delete_conversation(current_user.id, conversation_id)
    if not ok:
        raise HTTPException(status_code=404, detail="对话不存在")
    return {"ok": True}
```

**Step 2: Commit**

```bash
git add backend/app/api/openclaw.py
git commit -m "feat: add OpenClaw Channel API endpoints"
```

---

### Task 5: Backend Main — 注册 OpenClaw 路由

**Files:**
- Modify: `backend/app/api/main.py`

**Step 1: 在 import 区域添加**

在 `backend/app/api/main.py` 的 import 块末尾（`health_trend` 之后）添加：

```python
    openclaw,  # OpenClaw Channel 代理
```

**Step 2: 在路由注册区域添加**

在文件末尾（`health_trend.router` 之后）添加：

```python
# OpenClaw Channel 代理
api_router.include_router(openclaw.router)  # prefix 已在 router 中定义
```

**Step 3: Commit**

```bash
git add backend/app/api/main.py
git commit -m "feat: register OpenClaw Channel router"
```

---

### Task 6: Frontend API — 添加 openclawApi

**Files:**
- Modify: `frontend/src/services/api.ts`

**Step 1: 在 `chatApi` 对象之后添加 `openclawApi`**

在 `frontend/src/services/api.ts` 中，找到 `chatApi` 对象的结束花括号 `};`，在其后添加：

```typescript
// OpenClaw Channel API
export const openclawApi = {
  getConversations: (limit: number = 20) =>
    api.get<Conversation[]>(`/openclaw/conversations?limit=${limit}`),

  getConversation: (conversationId: number) =>
    api.get<ConversationDetail>(`/openclaw/conversations/${conversationId}`),

  deleteConversation: (conversationId: number) =>
    api.delete(`/openclaw/conversations/${conversationId}`),

  streamMessage: async function* (message: string, conversationId?: number) {
    const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;
    const response = await fetch(`${API_BASE_URL}/openclaw/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        message,
        conversation_id: conversationId,
      }),
    });

    if (!response.ok) {
      throw new Error(`OpenClaw stream request failed: ${response.status}`);
    }

    const reader = response.body?.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (reader) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6));
            yield data;
          } catch {
            // skip malformed JSON
          }
        }
      }
    }
  },
};
```

**Step 2: Commit**

```bash
git add frontend/src/services/api.ts
git commit -m "feat: add openclawApi for OpenClaw Channel"
```

---

### Task 7: Frontend AI Assistant — OpenClaw tab 切换

**Files:**
- Modify: `frontend/src/app/ai-assistant/page.tsx`

**Step 1: Import openclawApi**

在文件顶部 import 区域，找到 `import { ... } from '@/services/api'`，添加 `openclawApi`：

```typescript
import { chatApi, openclawApi } from '@/services/api';
```

（如果原来是 `import { api, chatApi, ... }`，加上 `openclawApi`）

**Step 2: 修改 chatMode 类型**

将 `chatMode` state 从：
```typescript
const [chatMode, setChatMode] = useState<'health' | 'proxy'>('health');
```
改为：
```typescript
const [chatMode, setChatMode] = useState<'health' | 'openclaw'>('health');
```

**Step 3: 修改 loadConversations 函数**

找到 `loadConversations` 函数，修改为根据模式调用不同 API：

```typescript
const loadConversations = useCallback(async () => {
  try {
    const response = chatMode === 'openclaw'
      ? await openclawApi.getConversations()
      : await chatApi.getConversations();
    setConversations(response.data || []);
  } catch (e) {
    console.error('加载对话列表失败:', e);
  }
}, [chatMode]);
```

**Step 4: 修改 loadConversation 函数**

找到 `loadConversation` 函数，修改为：

```typescript
const loadConversation = useCallback(async (convId: number, convMode?: string) => {
  try {
    const isOpenClaw = convMode === 'openclaw' || chatMode === 'openclaw';
    const response = isOpenClaw
      ? await openclawApi.getConversation(convId)
      : await chatApi.getConversation(convId);
    setMessages(response.data.messages || []);
    setConversationId(convId);
    if (convMode === 'openclaw') setChatMode('openclaw');
  } catch (e) {
    console.error('加载对话失败:', e);
  }
}, [chatMode]);
```

**Step 5: 修改 handleSend 中的流式调用**

在 `handleSend` 函数中，找到流式调用部分。将 `chatApi.streamMessage(...)` 调用修改为根据 mode 切换：

```typescript
// 替换原来的 streamMessage 调用
const streamIterator = chatMode === 'openclaw'
  ? openclawApi.streamMessage(msg, conversationId)
  : chatApi.streamMessage(msg, conversationId, undefined, imageBase64, imageType);

for await (const event of streamIterator) {
  // ... 保持原有的 token/done/error 处理逻辑不变
```

**Step 6: 修改对话删除**

找到删除对话的调用，修改为：

```typescript
const deleteApi = chatMode === 'openclaw' ? openclawApi : chatApi;
await deleteApi.deleteConversation(convId);
```

**Step 7: 修改 tab 切换 UI**

找到 tab 切换的 JSX（约 line 642-663），将 `'proxy'` 替换为 `'openclaw'`：

```typescript
<button
  onClick={() => { if (chatMode !== 'openclaw') { setChatMode('openclaw'); setMessages([]); setConversationId(undefined); } }}
  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
    chatMode === 'openclaw'
      ? 'bg-blue-600 text-white shadow-lg'
      : 'text-slate-300 hover:text-white'
  }`}
>
  OpenClaw
</button>
```

**Step 8: 修改快捷问题显示逻辑**

将所有 `chatMode === 'proxy'` 替换为 `chatMode === 'openclaw'`。快捷问题数组引用也从 `PROXY_QUICK_QUESTIONS` 改为使用：

```typescript
const currentQuickQuestions = chatMode === 'openclaw' ? PROXY_QUICK_QUESTIONS : QUICK_QUESTIONS;
```

**Step 9: OpenClaw 模式下禁用图片上传和语音**

在图片上传按钮和语音按钮的条件渲染中，添加 `chatMode !== 'openclaw'` 条件：

```typescript
{chatMode !== 'openclaw' && (
  <button onClick={...} title="拍照识别食物">📷</button>
)}
```

语音按钮同理。

**Step 10: 修改 loadConversations 的 useEffect 依赖**

确保切换 tab 时重新加载对话列表：

```typescript
useEffect(() => {
  loadConversations();
}, [loadConversations]); // loadConversations 已经依赖 chatMode
```

**Step 11: Commit**

```bash
git add frontend/src/app/ai-assistant/page.tsx
git commit -m "feat: AI assistant OpenClaw tab with independent API"
```

---

### Task 8: Database Migration — 生产环境建表

**Step 1: SSH 到服务器执行 SQL**

```bash
ssh root@39.98.206.178
```

连接 PostgreSQL 执行：

```sql
CREATE TABLE openclaw_conversations (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    title VARCHAR(200) DEFAULT '新对话',
    session_key VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX ix_openclaw_conv_user_updated ON openclaw_conversations(user_id, updated_at);

CREATE TABLE openclaw_messages (
    id SERIAL PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES openclaw_conversations(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX ix_openclaw_messages_conv ON openclaw_messages(conversation_id);
```

**Step 2: 添加 .env 配置**

在服务器 `/opt/health-app/backend/.env` 中添加：

```
OPENCLAW_GATEWAY_URL=http://47.237.191.17:PORT
OPENCLAW_API_KEY=xxx
```

（PORT 和 KEY 需要从 OpenClaw 服务器确认）

---

### Task 9: Deploy

**Step 1: Push 代码**

```bash
git push origin main
```

**Step 2: 部署前后端**

```bash
./deploy.sh -a
```

**Step 3: 验证**

1. 访问 AI 助手页面，确认看到 "健康助理" / "OpenClaw" 两个 tab
2. 切换到 OpenClaw tab，发送消息，确认流式响应正常
3. 切换回健康助理，确认原有功能不受影响
4. OpenClaw 对话列表与健康助理对话列表互相独立
5. 刷新页面后重新进入 OpenClaw 历史对话，确认消息加载正确
