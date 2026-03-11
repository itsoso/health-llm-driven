"""智能助理专用 OpenClaw 对话代理服务"""
import logging
import uuid
from datetime import datetime
from typing import AsyncGenerator, Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.assistant_openclaw import (
    AssistantOpenClawConversation,
    AssistantOpenClawMessage,
)
from app.services.assistant_openclaw_gateway_client import (
    AssistantOpenClawGatewayAuthError,
    AssistantOpenClawGatewayClient,
    AssistantOpenClawGatewayError,
)
from app.services.assistant_openclaw_binding_service import AssistantOpenClawBindingService

logger = logging.getLogger(__name__)


class AssistantOpenClawService:
    """智能助理专用 OpenClaw 对话代理"""

    def __init__(self, db: Session):
        self.db = db
        self.binding_service = AssistantOpenClawBindingService(db)

    @staticmethod
    def build_user_session_key(user_id: int) -> str:
        """为智能助理专用 OpenClaw 生成用户级固定 session key"""
        return f"assistant-openclaw-user-{user_id}"

    @staticmethod
    def _matches_fixed_session(current_session_key: Optional[str], fixed_session_key: str) -> bool:
        if not current_session_key:
            return False
        return current_session_key == fixed_session_key or current_session_key.endswith(f":{fixed_session_key}")

    def get_or_create_conversation(
        self, user_id: int, conversation_id: Optional[int], title: str = "新对话"
    ) -> AssistantOpenClawConversation:
        fixed_session_key = self.build_user_session_key(user_id)
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
            if not self._matches_fixed_session(conv.session_key, fixed_session_key):
                conv.session_key = fixed_session_key
                self.db.commit()
                self.db.refresh(conv)
            return conv

        conv = AssistantOpenClawConversation(
            user_id=user_id,
            title=title[:50],
            session_key=fixed_session_key,
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

        full_response = ""
        session_key = conv.session_key or f"assistant-openclaw-{user_id}"
        run_id = uuid.uuid4().hex

        def sync_session_key(resolved_session_key: str):
            if resolved_session_key and conv.session_key != resolved_session_key:
                conv.session_key = resolved_session_key

        async for token in self._call_gateway_stream(
            gateway_url=gateway_url,
            gateway_token=gateway_token,
            session_key=session_key,
            message=message,
            run_id=run_id,
            on_session_key=sync_session_key,
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
        session_key: str,
        message: str,
        run_id: str,
        on_session_key: Optional[Callable[[str], None]] = None,
    ) -> AsyncGenerator[str, None]:
        stream_text = ""

        try:
            async with AssistantOpenClawGatewayClient(gateway_url, gateway_token) as client:
                await client.send_chat(
                    session_key=session_key,
                    message=message,
                    idempotency_key=run_id,
                )

                async for payload in client.stream_chat(
                    session_key=session_key,
                    run_id=run_id,
                ):
                    resolved_session_key = payload.get("sessionKey")
                    if on_session_key and isinstance(resolved_session_key, str):
                        on_session_key(resolved_session_key)

                    state = payload.get("state")
                    message_text = self._extract_message_text(payload.get("message"))
                    if state == "delta":
                        delta = self._extract_delta(stream_text, message_text)
                        if delta:
                            stream_text += delta
                            yield delta
                    elif state == "final":
                        delta = self._extract_delta(stream_text, message_text)
                        if delta:
                            stream_text += delta
                            yield delta
                        break
                    elif state == "aborted":
                        if message_text:
                            delta = self._extract_delta(stream_text, message_text)
                            if delta:
                                stream_text += delta
                                yield delta
                        break
                    elif state == "error":
                        raise RuntimeError(payload.get("errorMessage") or "Gateway 对话失败")
        except AssistantOpenClawGatewayAuthError as exc:
            logger.warning("Assistant OpenClaw auth failed: %s", exc)
            raise ValueError("OpenClaw Token 无效，请前往设置页重新保存并测试连接") from exc
        except AssistantOpenClawGatewayError as exc:
            logger.warning("Assistant OpenClaw gateway failed: %s", exc)
            raise ValueError("OpenClaw Gateway 暂时不可用，请稍后重试") from exc

    @staticmethod
    def _extract_message_text(message: object) -> str:
        if isinstance(message, str):
            return message
        if not isinstance(message, dict):
            return ""

        text = message.get("text")
        if isinstance(text, str):
            return text

        content = message.get("content")
        if not isinstance(content, list):
            return ""

        parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text" and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts)

    @staticmethod
    def _extract_delta(current: str, incoming: str) -> str:
        if not incoming:
            return ""
        if not current:
            return incoming
        if incoming.startswith(current):
            return incoming[len(current):]
        return incoming
