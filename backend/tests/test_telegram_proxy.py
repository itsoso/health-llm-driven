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
            def json(self): return {"ok": True}

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


@pytest.mark.asyncio
@pytest.mark.parametrize('status,body,expected', [
    (200, {'ok': True, 'result': {'message_id': 1}}, True),
    (200, {'ok': False, 'description': 'private upstream detail'}, False),
    (429, {'ok': False, 'description': 'private upstream detail'}, False),
])
async def test_telegram_checks_api_success_without_exposing_credentials(monkeypatch, caplog, status, body, expected):
    import httpx
    import logging
    token = 'synthetic-bot-secret'
    monkeypatch.setattr('app.services.notification.telegram_push.settings.telegram_bot_token', token)
    monkeypatch.setattr('app.services.notification.telegram_push.settings.telegram_alert_chat_id', 'synthetic-admin')
    monkeypatch.setattr('app.services.notification.telegram_push.settings.telegram_api_base', 'https://api.telegram.org')
    monkeypatch.setattr('app.services.notification.telegram_push.settings.telegram_proxy_url', None)
    original = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(status, json=body))
    monkeypatch.setattr('app.services.notification.telegram_push.httpx.AsyncClient', lambda **kwargs: original(transport=transport, **kwargs))
    with caplog.at_level(logging.INFO):
        result = await TelegramPushService().send_message('synthetic registration', parse_mode=None)
    assert result['success'] is expected
    assert token not in caplog.text
    assert 'private upstream detail' not in caplog.text
    assert 'private upstream detail' not in str(result)


@pytest.mark.asyncio
async def test_telegram_timeout_returns_safe_retry_reason(monkeypatch, caplog):
    import httpx
    import logging
    monkeypatch.setattr('app.services.notification.telegram_push.settings.telegram_bot_token', 'synthetic-timeout-secret')
    monkeypatch.setattr('app.services.notification.telegram_push.settings.telegram_alert_chat_id', 'synthetic-admin')
    monkeypatch.setattr('app.services.notification.telegram_push.settings.telegram_proxy_url', None)
    original = httpx.AsyncClient
    def timeout(request):
        raise httpx.ReadTimeout('private-token-and-payload', request=request)
    monkeypatch.setattr('app.services.notification.telegram_push.httpx.AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(timeout), **kwargs))
    with caplog.at_level(logging.INFO):
        result = await TelegramPushService().send_message('synthetic')
    assert result == {'success': False, 'reason': 'transport_error'}
    assert 'private-token-and-payload' not in caplog.text
    assert 'synthetic-timeout-secret' not in caplog.text


# ─────────────── 健康告警格式:severity emoji + 旧 Markdown 转义 ───────────────

def _parse_legacy_markdown(text: str) -> str:
    """Telegram 旧 Markdown(parse_mode="Markdown")解析模型,对齐 TDLib parse_markdown:
    实体外 `\\` 只转义 _ * ` [;_ * ` 开实体并找同字符闭合,[ 找 ];实体内一律字面。
    返回可见文本;实体未闭合 → ValueError(= Telegram 400,整条告警被拒收)。"""
    out, i = [], 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and text[i + 1:i + 2] in ("_", "*", "`", "["):
            out.append(text[i + 1])
            i += 2
        elif ch in "_*`[":
            end = text.find("]" if ch == "[" else ch, i + 1)
            if end == -1:
                raise ValueError(f"Can't find end of the entity starting at offset {i}")
            out.append(text[i + 1:end])
            i = end + 1
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _capture_send_message(monkeypatch):
    sent = []

    async def fake(self, text, chat_id=None, parse_mode="Markdown"):
        sent.append({"text": text, "parse_mode": parse_mode})
        return {"success": True}

    monkeypatch.setattr(TelegramPushService, "send_message", fake)
    return sent


@pytest.mark.asyncio
@pytest.mark.parametrize("severity,emoji", [
    ("critical", "🔴"), ("high", "🟠"), ("HIGH", "🟠"), ("medium", "🟡"),
    ("warning", "🟡"), ("low", "🔵"), ("info", "🔵"), ("bogus", "⚪"),
])
async def test_health_alert_severity_emoji_covers_push_vocabulary(monkeypatch, severity, emoji):
    sent = _capture_send_message(monkeypatch)
    await TelegramPushService().send_health_alert("标题", "正文", severity=severity)
    assert sent[0]["text"].startswith(f"{emoji} ")


@pytest.mark.asyncio
@pytest.mark.parametrize("title", [
    "健康预警：spo2_avg",     # 下划线在粗体实体内是字面量
    "⚠️ 2*2 [x] `y`",         # 粗体内的 * 会提前闭合实体 → 400
    "Eval Golden Set",
])
async def test_health_alert_title_survives_legacy_markdown(monkeypatch, title):
    sent = _capture_send_message(monkeypatch)
    await TelegramPushService().send_health_alert(title, "正文", severity="warning")
    assert sent[0]["parse_mode"] == "Markdown"
    assert _parse_legacy_markdown(sent[0]["text"]) == f"🟡 {title}\n\n正文"


@pytest.mark.asyncio
async def test_health_alert_message_keeps_markdown_for_formatted_callers(monkeypatch):
    """eval_runner 传入带 *粗体* / `code` 的 Markdown 正文,格式须保留(转义只在纯文本出口做)。"""
    sent = _capture_send_message(monkeypatch)
    body = "*Eval Weekly*\n✅ `safety`: 3/3"
    await TelegramPushService().send_health_alert("Eval Golden Set", body, severity="warning")
    assert sent[0]["text"].endswith(body)


@pytest.mark.asyncio
@pytest.mark.parametrize("content", [
    "静息心率异常偏高：当前 72 bpm，7天均值 61.4 bpm，偏高 17.2%",
    "rule_id=anomaly.spo2_low 触发",     # 落单 `_`:旧实现 400 拒收整条
    "a*b `c [d] e_f \\_g",               # 四个特殊字符 + 文本里原有的反斜杠
])
async def test_push_telegram_fallback_plain_text_shows_verbatim(db, monkeypatch, content):
    from app.services.notification.push_service import PushService

    sent = _capture_send_message(monkeypatch)
    result = await PushService(db)._send_telegram(
        1, "health_alert", "⚠️ 标题_x", content, {"severity": "warning"}, "info"
    )
    assert result == {"success": True}
    assert _parse_legacy_markdown(sent[0]["text"]) == f"🟡 ⚠️ 标题_x\n\n{content}"


@pytest.mark.asyncio
@pytest.mark.parametrize("data,severity,emoji", [
    ({}, "high", "🟠"),                       # Safety Guardian:data 无 severity,只有推送档位
    ({"severity": "critical"}, "info", "🔴"),  # 生产者显式标注优先(delayed 回放同理)
])
async def test_push_telegram_fallback_severity_source(db, monkeypatch, data, severity, emoji):
    from app.services.notification.push_service import PushService

    sent = _capture_send_message(monkeypatch)
    await PushService(db)._send_telegram(1, "health_alert", "标题", "正文", data, severity)
    assert sent[0]["text"].startswith(f"{emoji} ")


@pytest.mark.asyncio
async def test_safety_guardian_high_push_renders_high_on_telegram(db, monkeypatch):
    """真实 send_notification 调用形态(notifications.py Safety Guardian):原先 HIGH 被渲染成 🔵 info。"""
    from datetime import datetime

    from app.models.notification import UserNotificationSetting
    from app.models.user import User
    from app.services.notification.push_service import PushService

    user = User(username="tg_fallback", email="tg_fallback@test.local", name="tg", hashed_password="x")
    db.add(user)
    db.commit()
    db.refresh(user)
    db.add(UserNotificationSetting(user_id=user.id, enabled=True, health_alert_enabled=True))
    db.commit()
    sent = _capture_send_message(monkeypatch)
    with patch("app.services.notification.push_service.get_china_now",
               return_value=datetime(2026, 3, 1, 14, 0)):
        result = await PushService(db).send_notification(
            user_id=user.id, notification_type="health_alert",
            title="⚠️ 血压 185/125 达到急症阈值", content="收缩压 185 mmHg,建议立即就医。",
            data={"screen": "alerts", "rule_id": "vitals.bp_critical"},
            severity="high", channels=["telegram"],
        )
    assert result["success"] is True
    assert sent[0]["text"].startswith("🟠 ")
