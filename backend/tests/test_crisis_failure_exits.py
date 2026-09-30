# -*- coding: utf-8 -*-
"""危机回合在失败出口上仍带经核对的急救电话与热线(2026-09-30 safety review NO-GO 回归)。

热线是确定性文本、不依赖 LLM:budget / AI 授权拦截、twin 构建抛错、硬超时、
Telegram 授权缺失与 handler 异常、/siri/say 异常 —— 都不能让危机原话落到只有
「服务不可用」的回复。Siri 只念前 300 字,号码必须在其中。
"""
import pytest
from fastapi import HTTPException

from app.services.crisis_lexicon import has_crisis_support
from tests.test_crisis_channel_coverage import (  # noqa: F401 - fixture re-export
    SIRI_DIALOG_LIMIT,
    _chunk_text,
    _client_events,
    _collect_stream,
    _fake_call_llm,
    _stream_session_local,
)


@pytest.mark.asyncio
async def test_siri_hotline_is_inside_spoken_prefix_even_after_long_model_text(
    monkeypatch, db
):
    from app.orchestrator import OrchestratorRequest
    from app.orchestrator import orchestrator as orch_mod
    from tests.conftest import create_authenticated_user

    user, _ = create_authenticated_user(db)
    long_reply = "我在听。" * 120 + "请拨打120，或心理援助热线12356。"
    monkeypatch.setattr(orch_mod, "_call_llm", _fake_call_llm(long_reply))

    resp = await orch_mod.run_orchestrator(
        db, user.id, OrchestratorRequest(query="不想活了", stream=False, source="siri")
    )

    assert has_crisis_support(resp.synthesis[:SIRI_DIALOG_LIMIT])


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ("siri", "chat"))
async def test_stream_lead_reaches_client_before_twin_failure(
    monkeypatch, db, _stream_session_local, source
):
    """热线先于 twin / specialist 入队,按客户端解析规则也完整(多行 data:)。"""
    from app.orchestrator import OrchestratorRequest
    from app.orchestrator import orchestrator as orch_mod
    from tests.conftest import create_authenticated_user

    user, _ = create_authenticated_user(db)

    def broken_twin(*args, **kwargs):  # noqa: ARG001
        raise RuntimeError("twin down")

    monkeypatch.setattr(orch_mod, "build_twin", broken_twin)

    events = await _collect_stream(
        orch_mod, db, user.id, OrchestratorRequest(query="我想死", source=source)
    )
    parsed = _client_events(events)

    assert parsed[0][0] == "chunk" and has_crisis_support(parsed[0][1])
    assert any(name == "error" for name, _ in parsed)


@pytest.mark.parametrize(
    "exc",
    (
        HTTPException(status_code=403, detail="AI 授权待确认"),
        RuntimeError("provider down"),
    ),
)
def test_orchestrator_chat_failure_still_returns_crisis_support(
    client, auth_user_and_headers, monkeypatch, exc
):
    """Siri 对 >=400 只播「服务不可用」:危机回合失败改 200 + 热线 synthesis。"""
    async def failing(*args, **kwargs):  # noqa: ARG001
        raise exc

    monkeypatch.setattr("app.api.orchestrator.run_orchestrator", failing)
    _user, headers = auth_user_and_headers

    crisis = client.post(
        "/api/v1/orchestrator/chat",
        headers=headers,
        json={"query": "活着没意思", "stream": False, "source": "siri"},
    )
    ordinary = client.post(
        "/api/v1/orchestrator/chat",
        headers=headers,
        json={"query": "最近睡眠怎么样", "stream": False, "source": "siri"},
    )

    assert crisis.status_code == 200
    body = crisis.json()
    assert body["error"] and has_crisis_support(body["synthesis"][:SIRI_DIALOG_LIMIT])
    assert ordinary.status_code == exc.status_code if isinstance(exc, HTTPException) else 500


def test_chat_error_envelope_carries_support_only_for_crisis():
    from app.api.orchestrator import _chat_error_envelope

    assert has_crisis_support(_chat_error_envelope("我想死", "请求处理超时")["synthesis"])
    assert _chat_error_envelope("累死了", "请求处理超时")["synthesis"] == ""


@pytest.fixture
def telegram_advisor(db, monkeypatch):
    from app.api import telegram_webhook
    from app.config import settings
    from tests.conftest import create_authenticated_user

    user, _ = create_authenticated_user(db)
    monkeypatch.setattr(settings, "telegram_webhook_secret", "crisis-test-secret")
    monkeypatch.setattr(settings, "telegram_advisor_chat_id", "9001")
    monkeypatch.setattr(settings, "telegram_advisor_user_id", user.id)
    replies: list[str] = []

    async def reply(chat_id, text, **kwargs):  # noqa: ARG001
        replies.append(text)

    monkeypatch.setattr(telegram_webhook, "_reply_to_telegram", reply)
    return replies


def _post_telegram(client, text: str):
    return client.post(
        "/api/v1/telegram/webhook?secret=crisis-test-secret",
        json={"message": {"chat": {"id": 9001}, "message_id": 7, "text": text}},
    )


@pytest.mark.parametrize("text,expected", (("不想活了", True), ("累死了", False)))
def test_telegram_consent_denial_still_carries_crisis_support(
    client, monkeypatch, telegram_advisor, text, expected
):
    from app.api import telegram_webhook

    def denied(*args, **kwargs):  # noqa: ARG001
        raise HTTPException(status_code=403, detail={"code": "ai_consent_required"})

    monkeypatch.setattr(telegram_webhook, "require_ai_consent", denied)

    response = _post_telegram(client, text)

    assert response.json()["reason"] == "ai_consent_required"
    assert "授权" in telegram_advisor[-1]
    assert has_crisis_support(telegram_advisor[-1]) is expected


@pytest.mark.parametrize("text,expected", (("我想死", True), ("想死你了", False)))
def test_telegram_handler_error_still_carries_crisis_support(
    client, monkeypatch, telegram_advisor, text, expected
):
    from app.api import telegram_webhook
    from app.services import telegram_inbound

    async def boom(*args, **kwargs):  # noqa: ARG001
        raise RuntimeError("handler down")

    monkeypatch.setattr(telegram_webhook, "require_ai_consent", lambda *a, **k: None)
    monkeypatch.setattr(telegram_inbound, "handle_inbound_text", boom)

    response = _post_telegram(client, text)

    assert response.json()["reason"] == "handler_error"
    assert has_crisis_support(telegram_advisor[-1]) is expected


def test_siri_say_exception_still_carries_crisis_support(
    client, auth_user_and_headers, monkeypatch
):
    from app.services.agent_runtime_facade import CloudAgentRuntimeFacade

    async def boom(self, **kwargs):  # noqa: ARG001
        raise RuntimeError("runtime down")
        yield  # pragma: no cover - makes this an async generator

    monkeypatch.setattr(CloudAgentRuntimeFacade, "run_stream", boom)
    _user, headers = auth_user_and_headers

    crisis = client.post(
        "/api/v1/siri/say",
        headers={**headers, "Idempotency-Key": "siri-crisis-exc-1"},
        json={"message": "不想活了"},
    )
    ordinary = client.post(
        "/api/v1/siri/say",
        headers={**headers, "Idempotency-Key": "siri-ordinary-exc-1"},
        json={"message": "记录饮水500ml"},
    )

    assert crisis.status_code == 200 and has_crisis_support(crisis.json()["text"])
    assert ordinary.status_code == 500


@pytest.mark.asyncio
async def test_telegram_reply_falls_back_to_plain_text_when_markdown_rejected(monkeypatch):
    """模型文本里未配对的 _ / * 让 Markdown 被拒时,危机回复(含热线)仍以纯文本送达。"""
    from app.api import telegram_webhook
    from app.services.crisis_lexicon import with_crisis_support
    from app.services.notification import telegram_push

    sent: list[tuple[str, object]] = []

    async def fake_send(self, text, chat_id=None, parse_mode="Markdown"):  # noqa: ARG001
        sent.append((text, parse_mode))
        if parse_mode:
            return {"success": False, "reason": "telegram_rejected", "status": 400}
        return {"success": True}

    monkeypatch.setattr(telegram_push.TelegramPushService, "send_message", fake_send)
    monkeypatch.setattr(telegram_push.settings, "telegram_bot_token", "test-token")

    reply = with_crisis_support("不想活了", "我在。记得补充维生素B_12")
    await telegram_webhook._reply_to_telegram("9001", reply)

    assert [mode for _, mode in sent] == ["Markdown", None]
    assert has_crisis_support(sent[-1][0])
