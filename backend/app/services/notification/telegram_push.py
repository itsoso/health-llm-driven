"""
Telegram Bot 推送服务。

Agent Native 告警通道：当 iOS APNs 不可用时（App 未构建），
通过 Telegram Bot API 直接发送健康告警到用户的 Telegram。

配置：
  TELEGRAM_BOT_TOKEN — Bot 的 API token（从 @BotFather 获取）
  TELEGRAM_ALERT_CHAT_ID — 默认告警推送的 chat_id
"""

import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"


class TelegramPushService:
    """Telegram Bot 推送"""

    def __init__(self):
        self.token = settings.telegram_bot_token
        self.default_chat_id = settings.telegram_alert_chat_id

    @property
    def configured(self) -> bool:
        return bool(self.token and self.default_chat_id)

    async def send_message(
        self,
        text: str,
        chat_id: Optional[str] = None,
        parse_mode: str = "Markdown",
    ) -> dict:
        """发送文本消息"""
        if not self.token:
            logger.debug("[telegram] 未配置 bot token，跳过")
            return {"success": False, "reason": "not_configured"}

        target = chat_id or self.default_chat_id
        if not target:
            return {"success": False, "reason": "no_chat_id"}

        url = f"{TELEGRAM_API}/bot{self.token}/sendMessage"
        payload = {
            "chat_id": target,
            "text": text,
            "parse_mode": parse_mode,
        }

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    logger.info(f"[telegram] 消息已发送到 chat_id={target}")
                    return {"success": True}
                else:
                    body = resp.text[:200]
                    logger.warning(f"[telegram] 发送失败: {resp.status_code} {body}")
                    return {"success": False, "status": resp.status_code, "body": body}
        except Exception as e:
            logger.warning(f"[telegram] 发送异常: {e}")
            return {"success": False, "error": str(e)}

    async def send_health_alert(
        self,
        title: str,
        message: str,
        severity: str = "warning",
        chat_id: Optional[str] = None,
    ) -> dict:
        """发送格式化的健康告警"""
        severity_emoji = {
            "critical": "🔴",
            "warning": "🟡",
            "info": "🔵",
        }
        emoji = severity_emoji.get(severity, "⚪")

        text = f"{emoji} *{title}*\n\n{message}"
        return await self.send_message(text, chat_id=chat_id)
