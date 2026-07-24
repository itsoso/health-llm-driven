"""微信 Bot 消息路由 — first-party Agent

所有消息统一转发到小巴第一方 Agent：
- 文字 → Agent stream
- 图片 → Agent stream（带 image_base64）
- 语音 → 假设已转文字 → Agent stream
"""
import logging
from typing import Dict, Any

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _wechat_client_turn_id(msg: Dict[str, Any]) -> str:
    from app.services.agent_runtime_identity import external_client_turn_id

    return external_client_turn_id(
        "wechat",
        channel="wechat",
        user_id=msg.get("user_id") or "",
        conversation_id=msg.get("wechat_openid") or "",
        message_id=msg.get("msg_id") or msg.get("message_id"),
    )


class WeChatBotHandler:
    """微信消息处理器 — first-party Agent 模式"""

    def __init__(self, db: Session):
        self.db = db

    async def handle_message(self, msg: Dict[str, Any]) -> Dict[str, Any]:
        """
        统一消息入口 — 全部走第一方 Agent。

        Args:
            msg: {
                "msg_type": "text" | "image" | "voice",
                "content": str,  # 文字内容 / 图片 base64 / 语音识别文字
                "wechat_openid": str,
                "user_id": int | None,
            }

        Returns:
            {"reply": str, "action": dict | None}
        """
        msg_type = msg.get("msg_type", "text")
        content = msg.get("content", "")
        user_id = msg.get("user_id")

        if not user_id:
            return {"reply": "您好！请先让家人帮您绑定账号。", "action": None}

        if not content.strip():
            return {"reply": "请发送文字、照片或语音消息。", "action": None}

        # 所有消息类型统一走第一方 Agent
        image_base64 = None
        image_type = "jpeg"
        message = content.strip()

        if msg_type == "image":
            image_base64 = content
            message = "请识别这张图片，判断是体检报告、药品还是其他内容，并做出相应处理。"
        elif msg_type == "voice":
            # 企业微信通常已将语音转为文字
            message = content.strip()

        from app.services.agent_runtime_facade import (
            get_or_create_channel_conversation,
        )

        conversation_id = get_or_create_channel_conversation(
            self.db,
            user_id=user_id,
            channel="wechat",
            title="微信对话",
        )
        client_turn_id = _wechat_client_turn_id(msg)

        # 调用 Agent stream，收集完整回复
        reply = await self._call_agent(
            user_id,
            message,
            image_base64,
            image_type,
            conversation_id=conversation_id,
            client_turn_id=client_turn_id,
            channel="voice" if msg_type == "voice" else "typed",
        )

        return {
            "reply": reply,
            "action": {"type": "agent_reply"},
        }

    async def _call_agent(
        self,
        user_id: int,
        message: str,
        image_base64: str | None = None,
        image_type: str = "jpeg",
        *,
        conversation_id: int | None = None,
        client_turn_id: str | None = None,
        channel: str = "typed",
    ) -> str:
        """调用第一方 Agent stream 并收集完整回复"""
        try:
            from app.services.agent_runtime_facade import CloudAgentRuntimeFacade

            service = CloudAgentRuntimeFacade(self.db)

            full_reply = ""
            images = [{"base64": image_base64, "type": image_type}] if image_base64 else None
            async for event in service.run_stream(
                user_id=user_id,
                message=message,
                images=images,
                conversation_id=conversation_id,
                client_turn_id=client_turn_id,
                origin="wechat",
                channel=channel,
            ):
                if event.get("event") == "token":
                    full_reply += event.get("data", {}).get("content", "")

            return full_reply or "收到了，但暂时无法回复，请稍后再试。"

        except Exception as e:
            logger.error(f"Agent 调用失败: {e}", exc_info=True)
            return "抱歉，系统暂时繁忙，请稍后再试。"
