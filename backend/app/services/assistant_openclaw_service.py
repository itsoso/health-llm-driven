"""智能助理专用 OpenClaw 对话代理服务"""
import json
import logging
import uuid
from datetime import datetime
from typing import AsyncGenerator, Dict, List, Optional

import httpx
from sqlalchemy.orm import Session

from app.models.assistant_openclaw import (
    AssistantOpenClawConversation,
    AssistantOpenClawMessage,
)
from app.services.assistant_openclaw_binding_service import AssistantOpenClawBindingService

logger = logging.getLogger(__name__)


class AssistantOpenClawService:
    """智能助理专用 OpenClaw 对话代理"""

    def __init__(self, db: Session):
        self.db = db
        self.binding_service = AssistantOpenClawBindingService(db)

    def get_or_create_conversation(
        self, user_id: int, conversation_id: Optional[int], title: str = "新对话"
    ) -> AssistantOpenClawConversation:
        if conversation_id:
            conv = (
                self.db.query(AssistantOpenClawConversation)
                .filter(
                    AssistantOpenClawConversation.id == conversation_id,
                    AssistantOpenClawConversation.user_id == user_id,
                )
                .first()
            )
            if not conv:
                raise ValueError("对话不存在")
            return conv

        conv = AssistantOpenClawConversation(
            user_id=user_id,
            title=title[:50],
            session_key=f"assistant-openclaw-{user_id}-{uuid.uuid4().hex[:12]}",
        )
        self.db.add(conv)
        self.db.commit()
        self.db.refresh(conv)
        return conv

    def get_conversations(
        self, user_id: int, limit: int = 20
    ) -> List[AssistantOpenClawConversation]:
        return (
            self.db.query(AssistantOpenClawConversation)
            .filter(AssistantOpenClawConversation.user_id == user_id)
            .order_by(AssistantOpenClawConversation.updated_at.desc())
            .limit(limit)
            .all()
        )

    def get_conversation_detail(
        self, user_id: int, conversation_id: int
    ) -> Optional[AssistantOpenClawConversation]:
        return (
            self.db.query(AssistantOpenClawConversation)
            .filter(
                AssistantOpenClawConversation.id == conversation_id,
                AssistantOpenClawConversation.user_id == user_id,
            )
            .first()
        )

    def delete_conversation(self, user_id: int, conversation_id: int) -> bool:
        conv = (
            self.db.query(AssistantOpenClawConversation)
            .filter(
                AssistantOpenClawConversation.id == conversation_id,
                AssistantOpenClawConversation.user_id == user_id,
            )
            .first()
        )
        if not conv:
            return False
        self.db.delete(conv)
        self.db.commit()
        return True

    def save_message(
        self, conversation_id: int, role: str, content: str
    ) -> AssistantOpenClawMessage:
        msg = AssistantOpenClawMessage(
            conversation_id=conversation_id,
            role=role,
            content=content,
        )
        self.db.add(msg)
        self.db.commit()
        self.db.refresh(msg)
        return msg

    def build_messages(self, conversation_id: int, limit: int = 20) -> List[Dict[str, str]]:
        history = (
            self.db.query(AssistantOpenClawMessage)
            .filter(AssistantOpenClawMessage.conversation_id == conversation_id)
            .order_by(AssistantOpenClawMessage.created_at.asc())
            .all()
        )
        recent = history[-limit:] if len(history) > limit else history
        return [{"role": m.role, "content": m.content} for m in recent]

    async def send_message_stream(
        self,
        user_id: int,
        message: str,
        conversation_id: Optional[int] = None,
    ) -> AsyncGenerator[dict, None]:
        gateway_url, gateway_token = self.binding_service.get_active_connection(user_id)

        conv = self.get_or_create_conversation(user_id, conversation_id, title=message)
        self.save_message(conv.id, "user", message)

        messages = self.build_messages(conv.id)
        full_response = ""

        async for token in self._call_gateway_stream(
            gateway_url=gateway_url,
            gateway_token=gateway_token,
            messages=messages,
            session_key=conv.session_key or f"assistant-openclaw-{user_id}",
        ):
            full_response += token
            yield {"event": "token", "data": {"content": token}}

        ai_msg = self.save_message(conv.id, "assistant", full_response)
        conv.updated_at = datetime.utcnow()
        self.db.commit()

        yield {
            "event": "done",
            "data": {
                "conversation_id": conv.id,
                "message_id": ai_msg.id,
            },
        }

    async def _call_gateway_stream(
        self,
        gateway_url: str,
        gateway_token: str,
        messages: List[Dict[str, str]],
        session_key: str,
    ) -> AsyncGenerator[str, None]:
        url = f"{gateway_url.rstrip('/')}/v1/chat/completions"
        headers = {"Authorization": f"Bearer {gateway_token}"}
        payload = {
            "model": "default",
            "messages": messages,
            "stream": True,
            "user": session_key,
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    logger.error(
                        "Assistant OpenClaw Gateway error %s: %s",
                        response.status_code,
                        body[:500],
                    )
                    raise RuntimeError(f"Gateway returned {response.status_code}")

                async for line in response.aiter_lines():
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
