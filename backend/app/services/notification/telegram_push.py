"""
Telegram Bot 推送服务。

Agent Native 告警通道：当 iOS APNs 不可用时（App 未构建），
通过 Telegram Bot API 直接发送健康告警到用户的 Telegram。

配置：
  TELEGRAM_BOT_TOKEN — Bot 的 API token（从 @BotFather 获取）
  TELEGRAM_ALERT_CHAT_ID — 默认告警推送的 chat_id

国内服务器连不到 api.telegram.org 时两选一 (都可选, 填一个就行):
  TELEGRAM_API_BASE — 反代 URL, 如 https://bot.executor.life/telegram-api
                      (默认 https://api.telegram.org)
  TELEGRAM_PROXY_URL — HTTP/SOCKS5 代理, 如 http://127.0.0.1:7890 或
                       socks5://user:pass@proxy.host:1080
"""

import logging
import re
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class _TelegramURLRedactor(logging.Filter):
    """httpx INFO logs include the bot token in Telegram's required URL path."""

    def filter(self, record: logging.LogRecord) -> bool:
        rendered = record.getMessage()
        if re.search(r"/bot[^/\s]+/", rendered):
            record.msg = re.sub(r"/bot[^/\s]+/", "/bot[REDACTED]/", rendered)
            record.args = ()
        return True


logging.getLogger("httpx").addFilter(_TelegramURLRedactor())


class TelegramPushService:
    """Telegram Bot 推送"""

    def __init__(self):
        self.token = settings.telegram_bot_token
        self.default_chat_id = settings.telegram_alert_chat_id
        # 支持反代 URL (国内出站不通时的轻量方案)
        self.api_base = (
            getattr(settings, "telegram_api_base", None)
            or "https://api.telegram.org"
        ).rstrip("/")
        # HTTP/SOCKS5 代理 (和 api_base 二选一, 如果用户偏好走代理)
        self.proxy_url = getattr(settings, "telegram_proxy_url", None) or None

    @property
    def configured(self) -> bool:
        return bool(self.token and self.default_chat_id)

    def _client_kwargs(self) -> dict:
        """构造 httpx.AsyncClient 的 kwargs, 按需附加 proxy."""
        kwargs = {"timeout": 10}
        if self.proxy_url:
            # httpx 新版用 `proxy=` 旧版用 `proxies=`, 这里统一新版
            try:
                import httpx as _hx
                # 检测 httpx >= 0.26 支持 proxy=
                kwargs["proxy"] = self.proxy_url
            except Exception:
                kwargs["proxies"] = self.proxy_url
        return kwargs

    async def send_message(
        self,
        text: str,
        chat_id: Optional[str] = None,
        parse_mode: Optional[str] = "Markdown",
    ) -> dict:
        """发送文本消息. parse_mode=None 则纯文本 (Telegram API 不接受 null 值, 不加字段)."""
        if not self.token:
            logger.debug("[telegram] 未配置 bot token，跳过")
            return {"success": False, "reason": "not_configured"}

        target = chat_id or self.default_chat_id
        if not target:
            return {"success": False, "reason": "no_chat_id"}

        url = f"{self.api_base}/bot{self.token}/sendMessage"
        payload: dict = {
            "chat_id": target,
            "text": text,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode

        try:
            async with httpx.AsyncClient(**self._client_kwargs()) as client:
                resp = await client.post(url, json=payload)
                try:
                    body = resp.json()
                except ValueError:
                    logger.warning("[telegram] invalid response status=%s", resp.status_code)
                    return {"success": False, "reason": "invalid_response"}
                if resp.status_code == 200 and isinstance(body, dict) and body.get("ok") is True:
                    logger.info("[telegram] message accepted")
                    return {"success": True}
                logger.warning("[telegram] request rejected status=%s", resp.status_code)
                return {"success": False, "reason": "telegram_rejected", "status": resp.status_code}
        except (httpx.HTTPError, OSError):
            logger.warning("[telegram] transport failure")
            return {"success": False, "reason": "transport_error"}

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
