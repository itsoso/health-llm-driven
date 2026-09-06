"""Verified Telegram identity must reach AI gates without trusting payload IDs."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import sessionmaker

from tests.conftest import create_authenticated_user


@pytest.fixture
def telegram_consent(db, monkeypatch):
    from app.config import settings
    from app.api import telegram_webhook
    from app.services import ai_consent
    user, _ = create_authenticated_user(db)
    monkeypatch.setattr(settings, "telegram_webhook_secret", "consent-test-secret")
    monkeypatch.setattr(settings, "telegram_advisor_chat_id", "9001")
    monkeypatch.setattr(settings, "telegram_advisor_user_id", user.id)
    monkeypatch.setattr(ai_consent, "SessionLocal", sessionmaker(bind=db.get_bind()))
    replies = []
    async def reply(chat_id, text, **kwargs):
        replies.append(text)
    monkeypatch.setattr(telegram_webhook, "_reply_to_telegram", reply)
    ai_consent.update_ai_consent(db, user.id, True, ai_consent.POLICY_VERSION)
    return user, replies


@pytest.mark.parametrize("kind", ["text", "voice"])
def test_verified_telegram_user_can_use_ai_and_revocation_is_explicit(client, db, monkeypatch, telegram_consent, kind):
    from app.services import ai_consent, speech_transcription, telegram_inbound
    user, replies = telegram_consent
    seen = []
    def transcribe(audio, audio_format):
        ai_consent.require_ai_consent(destination="https://dashscope.aliyuncs.com/api/v1")
        seen.append("voice")
        return SimpleNamespace(text="记录饮水300ml")
    async def download(file_id):
        return b"synthetic-audio"
    async def handle(db, user_id, text, **kwargs):
        ai_consent.require_ai_consent()
        assert user_id == user.id
        seen.append("text")
        return "已完成"
    monkeypatch.setattr(speech_transcription, "transcribe_audio_bytes", transcribe)
    monkeypatch.setattr(telegram_inbound, "download_telegram_file", download)
    monkeypatch.setattr(telegram_inbound, "handle_inbound_text", handle)
    message = {"chat": {"id": 9001}, "message_id": 11, "user_id": 999999}
    message.update({"voice": {"file_id": "test-file"}} if kind == "voice" else {"text": "记录饮水300ml"})
    response = client.post("/api/v1/telegram/webhook?secret=consent-test-secret", json={"message": message})
    assert response.json()["ok"] is True
    assert seen == (["voice", "text"] if kind == "voice" else ["text"])
    ai_consent.update_ai_consent(db, user.id, False, ai_consent.POLICY_VERSION)
    response = client.post("/api/v1/telegram/webhook?secret=consent-test-secret", json={"message": message})
    assert response.json()["reason"] == "ai_consent_required"
    assert "授权" in replies[-1]
    assert "识别失败" not in replies[-1]


def test_unverified_chat_cannot_borrow_configured_users_consent(client, monkeypatch, telegram_consent):
    from app.services import telegram_inbound
    async def forbidden(*args, **kwargs):
        pytest.fail("unverified chat reached AI handler")
    monkeypatch.setattr(telegram_inbound, "handle_inbound_text", forbidden)
    response = client.post("/api/v1/telegram/webhook?secret=consent-test-secret", json={
        "message": {"chat": {"id": 123}, "message_id": 1, "text": "记录饮水", "user_id": telegram_consent[0].id},
    })
    assert response.json()["ignored"] == "not_advisor_chat"


@pytest.mark.asyncio
async def test_record_extraction_never_disguises_consent_denial_as_no_record(monkeypatch):
    from app.services.ai_consent import ai_user_scope
    from app.services.llm.providers.openai_provider import OpenAIProvider
    from app.services.telegram_inbound import llm_extract_record
    provider = OpenAIProvider(api_key="test-only", base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
    monkeypatch.setattr("app.services.llm.factory.get_llm_provider", lambda: provider)
    with ai_user_scope(None), pytest.raises(HTTPException) as denied:
        await llm_extract_record("记录饮水300ml")
    assert denied.value.detail["code"] == "ai_consent_required"


def test_wechat_reports_consent_before_agent_instead_of_system_busy(client, db, monkeypatch):
    from app.services import ai_consent
    user, token = create_authenticated_user(db)
    headers = {"Authorization": f"Bearer {token}"}
    monkeypatch.setattr(ai_consent, "SessionLocal", sessionmaker(bind=db.get_bind()))
    called = []
    async def handle(self, msg):
        called.append(msg["user_id"])
        return {"reply": "done", "action": None}
    monkeypatch.setattr("app.services.wechat_bot.WeChatBotHandler.handle_message", handle)
    payload = {"msg_type": "text", "content": "记录饮水300ml", "msg_id": "synthetic-1", "user_id": 99999}
    path = "/api/v1/family-health/wechat-bot/message"
    denied = client.post(path, headers=headers, json=payload)
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "ai_consent_required"
    assert called == []
    ai_consent.update_ai_consent(db, user.id, True, ai_consent.POLICY_VERSION)
    assert client.post(path, headers=headers, json=payload).status_code == 200
    assert called == [user.id]
    ai_consent.update_ai_consent(db, user.id, False, ai_consent.POLICY_VERSION)
    assert client.post(path, headers=headers, json=payload).status_code == 403
