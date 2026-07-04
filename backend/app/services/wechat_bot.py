"""微信 Bot 消息路由 — first-party Agent

所有消息统一转发到阿衡第一方 Agent：
- 文字 → Agent stream
- 图片 → Agent stream（带 image_base64）
- 语音 → 假设已转文字 → Agent stream
"""
import logging
from typing import Dict, Any

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


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

        # 调用 Agent stream，收集完整回复
        reply = await self._call_agent(user_id, message, image_base64, image_type)

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
    ) -> str:
        """调用第一方 Agent stream 并收集完整回复"""
        try:
            from app.services.agent_executor import AgentExecutor

            service = AgentExecutor(self.db)

            full_reply = ""
            images = [{"base64": image_base64, "type": image_type}] if image_base64 else None
            async for event in service.run_stream(
                user_id=user_id,
                message=message,
                images=images,
            ):
                if event.get("event") == "token":
                    full_reply += event.get("data", {}).get("content", "")

            return full_reply or "收到了，但暂时无法回复，请稍后再试。"

        except Exception as e:
            logger.error(f"Agent 调用失败: {e}", exc_info=True)
            return "抱歉，系统暂时繁忙，请稍后再试。"
