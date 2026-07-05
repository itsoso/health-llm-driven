"""Conversation persistence for the first-party health Agent."""
from __future__ import annotations

import uuid
from typing import Dict, List, Optional

from sqlalchemy.orm import Session, joinedload

from app.models.agent_conversation import AgentConversation, AgentMessage


class AgentConversationService:
    """CRUD wrapper for first-party Agent conversations and messages."""

    def __init__(self, db: Session):
        self.db = db

    def get_or_create_conversation(
        self,
        user_id: int,
        conversation_id: Optional[int],
        title: str = "新对话",
    ) -> AgentConversation:
        if conversation_id:
            conv = (
                self.db.query(AgentConversation)
                .filter(
                    AgentConversation.id == conversation_id,
                    AgentConversation.user_id == user_id,
                )
                .first()
            )
            if not conv:
                raise ValueError("对话不存在")
            return conv

        conv = AgentConversation(
            user_id=user_id,
            title=(title or "新对话")[:50],
            session_key=f"agent-{user_id}-{uuid.uuid4().hex[:12]}",
        )
        self.db.add(conv)
        self.db.commit()
        self.db.refresh(conv)
        return conv

    def get_conversations(
        self,
        user_id: int,
        limit: int = 20,
        title_like: Optional[str] = None,
        offset: int = 0,
    ) -> List[AgentConversation]:
        q = self.db.query(AgentConversation).filter(AgentConversation.user_id == user_id)
        if title_like:
            q = q.filter(AgentConversation.title.ilike(f"%{title_like}%"))
        return q.order_by(AgentConversation.updated_at.desc()).offset(offset).limit(limit).all()

    def count_conversations(self, user_id: int, title_like: Optional[str] = None) -> int:
        q = self.db.query(AgentConversation).filter(AgentConversation.user_id == user_id)
        if title_like:
            q = q.filter(AgentConversation.title.ilike(f"%{title_like}%"))
        return q.count()

    def get_conversation_detail(self, user_id: int, conversation_id: int) -> Optional[AgentConversation]:
        return (
            self.db.query(AgentConversation)
            .options(joinedload(AgentConversation.messages))
            .filter(
                AgentConversation.id == conversation_id,
                AgentConversation.user_id == user_id,
            )
            .first()
        )

    def delete_conversation(self, user_id: int, conversation_id: int) -> bool:
        conv = (
            self.db.query(AgentConversation)
            .filter(
                AgentConversation.id == conversation_id,
                AgentConversation.user_id == user_id,
            )
            .first()
        )
        if not conv:
            return False
        self.db.delete(conv)
        self.db.commit()
        return True

    def update_conversation_title(
        self,
        user_id: int,
        conversation_id: int,
        title: str,
    ) -> Optional[AgentConversation]:
        normalized = (title or "").strip()
        if not normalized:
            raise ValueError("标题不能为空")
        conv = (
            self.db.query(AgentConversation)
            .filter(
                AgentConversation.id == conversation_id,
                AgentConversation.user_id == user_id,
            )
            .first()
        )
        if not conv:
            return None
        conv.title = normalized[:120]
        self.db.commit()
        self.db.refresh(conv)
        return conv

    def save_message(
        self,
        conversation_id: int,
        role: str,
        content: str,
        image_url: str | None = None,
    ) -> AgentMessage:
        msg = AgentMessage(
            conversation_id=conversation_id,
            role=role,
            content=content,
            image_url=image_url,
        )
        self.db.add(msg)
        self.db.commit()
        self.db.refresh(msg)
        return msg

    def build_messages(self, conversation_id: int, limit: int = 20) -> List[Dict[str, str]]:
        history = (
            self.db.query(AgentMessage)
            .filter(AgentMessage.conversation_id == conversation_id)
            # id 决胜: created_at 同刻(时钟回拨/同毫秒并写)时 user/assistant 顺序
            # 不能翻转,否则多轮历史喂给 LLM 时轮次错位。
            .order_by(AgentMessage.created_at.asc(), AgentMessage.id.asc())
            .all()
        )
        recent = history[-limit:] if len(history) > limit else history
        return [{"role": m.role, "content": m.content} for m in recent]

    @staticmethod
    def compress_image_base64(
        base64_data: str,
        image_type: str = "jpeg",
        max_size: int = 1024,
        quality: int = 75,
    ) -> str:
        from app.services.chat_utils import compress_image_base64

        return compress_image_base64(base64_data, image_type, max_size, quality)
