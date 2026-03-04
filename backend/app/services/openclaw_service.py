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
