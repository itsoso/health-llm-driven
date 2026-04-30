"""Telegram 代理支持单元测试."""
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.services.notification.telegram_push import TelegramPushService


class TestApiBaseCustomization:
    def test_default_api_base(self, monkeypatch):
        monkeypatch.setattr("app.services.notification.telegram_push.settings.telegram_api_base", None)
        svc = TelegramPushService()
        assert svc.api_base == "https://api.telegram.org"

    def test_custom_api_base_strips_trailing_slash(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.notification.telegram_push.settings.telegram_api_base",
            "https://bot.executor.life/telegram-api/",
        )
        svc = TelegramPushService()
        assert svc.api_base == "https://bot.executor.life/telegram-api"


class TestProxySupport:
    def test_no_proxy_kwargs_clean(self, monkeypatch):
        monkeypatch.setattr("app.services.notification.telegram_push.settings.telegram_proxy_url", None)
        svc = TelegramPushService()
        kwargs = svc._client_kwargs()
        assert kwargs == {"timeout": 10}
        assert "proxy" not in kwargs

    def test_http_proxy_in_kwargs(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.notification.telegram_push.settings.telegram_proxy_url",
            "http://127.0.0.1:7890",
        )
        svc = TelegramPushService()
        kwargs = svc._client_kwargs()
        assert kwargs.get("proxy") == "http://127.0.0.1:7890"

    def test_socks5_proxy_in_kwargs(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.notification.telegram_push.settings.telegram_proxy_url",
            "socks5://user:pass@proxy.test:1080",
        )
        svc = TelegramPushService()
        kwargs = svc._client_kwargs()
        assert kwargs.get("proxy") == "socks5://user:pass@proxy.test:1080"


class TestSendMessageRoutes:
    @pytest.mark.asyncio
    async def test_send_uses_custom_base(self, monkeypatch):
        """发送时 URL 走 custom api_base."""
        monkeypatch.setattr(
            "app.services.notification.telegram_push.settings.telegram_bot_token",
            "fake_token",
        )
        monkeypatch.setattr(
            "app.services.notification.telegram_push.settings.telegram_alert_chat_id",
            "12345",
        )
        monkeypatch.setattr(
            "app.services.notification.telegram_push.settings.telegram_api_base",
            "https://bot.executor.life/telegram-api",
        )
        svc = TelegramPushService()

        captured_urls = []
        class MockResp:
            status_code = 200
            text = ""

        class MockClient:
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return None
            async def post(self, url, **kw):
                captured_urls.append(url)
                return MockResp()

        with patch("app.services.notification.telegram_push.httpx.AsyncClient",
                   return_value=MockClient()):
            result = await svc.send_message("hello")
        assert result["success"] is True
        # URL 必须走自定义 base
        assert "bot.executor.life/telegram-api/bot" in captured_urls[0]
        assert "api.telegram.org" not in captured_urls[0]

    @pytest.mark.asyncio
    async def test_unconfigured_returns_not_configured(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.notification.telegram_push.settings.telegram_bot_token", None,
        )
        svc = TelegramPushService()
        result = await svc.send_message("hello")
        assert result["success"] is False
        assert result["reason"] == "not_configured"
