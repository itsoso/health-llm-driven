"""Telegram webhook → directive 解析端到端."""
import pytest

from app.models.user_directive import UserDirective


@pytest.fixture(autouse=True)
def _patch_settings(monkeypatch):
    """配置模拟的 advisor chat."""
    from app.config import settings
    monkeypatch.setattr(settings, "telegram_advisor_chat_id", "12345")
    monkeypatch.setattr(settings, "telegram_advisor_user_id", 7)
    monkeypatch.setattr(settings, "telegram_doctor_chat_id", None)
    monkeypatch.setattr(settings, "telegram_doctor_user_id", None)
    monkeypatch.setattr(settings, "telegram_webhook_secret", "test-secret")


@pytest.fixture(autouse=True)
def _no_telegram_send(monkeypatch):
    """默认不真发 Telegram 回复."""
    async def _fake_reply(chat_id, text, reply_to_message_id=None):
        return None
    from app.api import telegram_webhook
    monkeypatch.setattr(telegram_webhook, "_reply_to_telegram", _fake_reply)


@pytest.fixture
def _force_fallback_parser(monkeypatch):
    """LLM mock 失败强制走 fallback 关键词."""
    from app.services import directive_parser
    monkeypatch.setattr(directive_parser, "_parse_with_llm", lambda text: [])


class TestSecretAuth:
    def test_no_secret_rejected(self, client):
        r = client.post("/api/v1/telegram/webhook", json={"message": {"text": "x"}})
        assert r.status_code == 403

    def test_wrong_secret_rejected(self, client):
        r = client.post("/api/v1/telegram/webhook?secret=wrong",
                       json={"message": {"text": "x"}})
        assert r.status_code == 403

    def test_correct_secret_passes(self, client):
        r = client.post("/api/v1/telegram/webhook?secret=test-secret",
                       json={"message": {"chat": {"id": 99999}, "text": "hi"}})
        assert r.status_code == 200
        assert r.json()["ignored"] == "not_advisor_chat"


class TestNonDoctorChat:
    def test_other_chat_ignored(self, client, db, _force_fallback_parser):
        r = client.post("/api/v1/telegram/webhook?secret=test-secret",
                       json={"message": {"chat": {"id": 99999}, "text": "LDL < 2.6 严格戒酒"}})
        assert r.status_code == 200
        assert r.json()["ignored"] == "not_advisor_chat"
        # 没创建 directive
        assert db.query(UserDirective).count() == 0


class TestDoctorReply:
    def test_command_ignored(self, client, db):
        r = client.post("/api/v1/telegram/webhook?secret=test-secret",
                       json={"message": {"chat": {"id": 12345}, "text": "/start"}})
        assert r.status_code == 200
        assert r.json()["ignored"] == "command"

    def test_short_text_ignored(self, client, db):
        # 03f96231 把阈值放宽到 len < 2 (允许 "嗯"/"好" 等短回复进 LLM); 用 1 字测试
        r = client.post("/api/v1/telegram/webhook?secret=test-secret",
                       json={"message": {"chat": {"id": 12345}, "text": "x"}})
        assert r.status_code == 200
        assert r.json()["ignored"] == "text_too_short"

    def test_creates_directive_from_text(self, client, db, _force_fallback_parser):
        r = client.post("/api/v1/telegram/webhook?secret=test-secret",
                       json={
                           "message": {
                               "chat": {"id": 12345},
                               "text": "LDL 控制在 2.6 以下",
                               "message_id": 100,
                           }
                       })
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        # 03f96231 后响应改为 {"ok": True, "reply": "✅ 已录入 N 条指令:..."}
        assert "已录入" in body["reply"]

        rows = db.query(UserDirective).filter(UserDirective.user_id == 7).all()
        assert len(rows) >= 1
        assert rows[0].source == "external_telegram"
        assert rows[0].source_message_id.startswith("telegram-")
        assert rows[0].source_message_id != "100"

    def test_no_recognizable_pattern(self, client, db, _force_fallback_parser):
        r = client.post("/api/v1/telegram/webhook?secret=test-secret",
                       json={"message": {"chat": {"id": 12345},
                                         "text": "今天天气真好谢谢",
                                         "message_id": 101}})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        # query/chat intent 不创建 directive
        assert db.query(UserDirective).count() == 0

    def test_missing_provider_message_id_fails_closed(
        self, client, db, caplog
    ):
        with caplog.at_level("WARNING"):
            r = client.post(
                "/api/v1/telegram/webhook?secret=test-secret",
                json={
                    "message": {
                        "chat": {"id": 12345},
                        "text": "记录饮水500ml",
                    }
                },
            )

        assert r.status_code == 200
        assert r.json() == {"ok": False, "reason": "missing_message_id"}
        assert db.query(UserDirective).count() == 0
        assert "12345" not in caplog.text
        assert "missing provider message_id" in caplog.text


class TestDoctorNotConfigured:
    def test_advisor_chat_not_set_ignores_all(self, client, db, monkeypatch):
        from app.config import settings
        monkeypatch.setattr(settings, "telegram_advisor_chat_id", None)
        monkeypatch.setattr(settings, "telegram_doctor_chat_id", None)
        r = client.post("/api/v1/telegram/webhook?secret=test-secret",
                       json={"message": {"chat": {"id": 12345}, "text": "LDL < 2.6"}})
        assert r.status_code == 200
        assert r.json()["ignored"] == "advisor_not_configured"


class TestWebhookSecretRequired:
    def test_no_secret_in_settings_returns_503(self, client, monkeypatch):
        from app.config import settings
        monkeypatch.setattr(settings, "telegram_webhook_secret", None)
        r = client.post("/api/v1/telegram/webhook?secret=anything", json={})
        assert r.status_code == 503
