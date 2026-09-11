"""Cross-turn medical output regression using the real executor streaming loop.

Only model I/O and unrelated prompt retrieval are replaced; conversation history,
user ownership, final sanitation, persistence, and emitted events stay real.
"""

import pytest

from app.config import settings
from app.models.agent_conversation import AgentMessage
from app.services.agent_conversation_service import AgentConversationService
from app.services.agent_executor import AgentExecutor
from app.services.health_evidence import classify_health_intent
from tests.conftest import create_authenticated_user


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["应该怎么补", "给我建议"])
async def test_medical_followup_cannot_stream_advice_before_boundary_check(
    db, auth_user_and_headers, monkeypatch, query,
):
    user, _headers = auth_user_and_headers
    prior = "我想核对正在使用的鱼油补剂，不确定当前剂量是否合适。"
    service = AgentConversationService(db)
    conversation = service.get_or_create_conversation(user.id, None, title="合成安全回归")
    service.save_message(conversation.id, "user", prior)
    service.save_message(conversation.id, "assistant", "请先核对产品名称与已有医嘱。")
    db.commit()

    monkeypatch.setattr(settings, "health_evidence_runtime_enabled", True)
    # Current sealed-evidence intent slice does not own this terse follow-up.
    assert not classify_health_intent(query).requires_authority
    executor = AgentExecutor(db)
    monkeypatch.setattr(executor, "_build_system_prompt", lambda *_a, **_k: "健康记录助手。")
    monkeypatch.setattr(executor, "_build_system_knowledge_prompt_context", lambda *_a, **_k: "")
    captured = []

    async def fake_stream(messages, tools):
        captured.append(messages)
        yield {"type": "content", "text": "建议把鱼油"}
        yield {"type": "content", "text": "增加到每天四粒。"}
        yield {"type": "finish", "finish_reason": "stop"}

    async def fake_completion(messages, tools):
        return {"content": "建议把鱼油增加到每天四粒。", "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_call_llm_stream", fake_stream)
    monkeypatch.setattr(executor, "_call_llm", fake_completion)
    events = [
        event async for event in executor.run_stream(
            user_id=user.id,
            message=query,
            conversation_id=conversation.id,
            channel="typed",
        )
    ]

    assert captured, "The test must reach the actual model-stream seam."
    assert any(
        item.get("role") == "user" and prior in str(item.get("content", ""))
        for messages in captured for item in messages
    ), "The model must actually receive this user's same-conversation medical history."
    done = next(event["data"] for event in reversed(events) if event["event"] == "done")
    saved = db.get(AgentMessage, done["message_id"])
    assert saved is not None
    assert "增加到每天四粒" not in saved.content
    streamed = "".join(
        str(event.get("data", {}).get("content", ""))
        for event in events if event.get("event") == "token"
    )
    # Inspect every token, not only done/persisted text: final replacement cannot
    # retract a dose instruction already spoken or displayed by the client.
    assert "增加到每天四粒" not in streamed
    assert "核验" in streamed


@pytest.mark.asyncio
async def test_medical_followup_rejects_foreign_conversation_before_history_read(
    db, auth_user_and_headers, monkeypatch,
):
    user, _headers = auth_user_and_headers
    other_user, _token = create_authenticated_user(db)
    service = AgentConversationService(db)
    foreign = service.get_or_create_conversation(other_user.id, None, title="其他用户")
    service.save_message(foreign.id, "user", "合成私密上下文：鱼油补剂。")
    db.commit()
    history_reads = []
    original_build = AgentConversationService.build_messages

    def traced_build(self, conversation_id, **kwargs):
        history_reads.append(conversation_id)
        return original_build(self, conversation_id, **kwargs)

    monkeypatch.setattr(AgentConversationService, "build_messages", traced_build)
    executor = AgentExecutor(db)

    async def no_model(*_args, **_kwargs):
        pytest.fail("An unauthorized conversation must never reach the model.")
        yield

    monkeypatch.setattr(executor, "_call_llm_stream", no_model)
    with pytest.raises(ValueError, match="对话不存在"):
        _events = [
            event async for event in executor.run_stream(
                user_id=user.id,
                message="给我建议",
                conversation_id=foreign.id,
                channel="typed",
            )
        ]
    assert history_reads == []
