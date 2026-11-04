"""Everyday admission must change the actual provider payload, not only routing."""
import json
from copy import deepcopy

import pytest

from app.models.agent_conversation import AgentMessage
from app.services import agent_executor as ae
from app.services.agent_conversation_service import AgentConversationService
from app.services.tool_schema_registry import get_health_tools
from tests.test_agent_executor_fast_routing import _wire_common

pytestmark = pytest.mark.usefixtures("consenting_agent_user", "isolated_agent_protocol_transport")


class Provider:
    model = "deepseek-v4.1-flash"

    def __init__(self):
        self.calls = []

    async def chat_stream(self, **kwargs):
        self.calls.append(deepcopy(kwargs))
        yield {"type": "content", "text": "小熊折好纸船，让它载着星光漂向远方。"}
        yield {"type": "finish", "finish_reason": "stop"}

    async def chat(self, **kwargs):
        self.calls.append(deepcopy(kwargs))
        return {"content": "小熊折好纸船，让它载着星光漂向远方。", "finish_reason": "stop"}


@pytest.mark.asyncio
@pytest.mark.parametrize("selected", [False, True])
@pytest.mark.parametrize("history", [False, "greeting", "correction"])
async def test_everyday_payload_is_small_and_retains_original_history(
    db, auth_user_and_headers, monkeypatch, selected, history,
):
    user, _ = auth_user_and_headers
    user.is_admin = True
    db.commit()
    executor = ae.AgentExecutor(db)
    provider = Provider()
    _wire_common(executor, monkeypatch, lambda _: provider)
    monkeypatch.setattr("app.services.llm.factory.create_provider_for_user", lambda *a, **k: provider)
    monkeypatch.setattr(ae, "get_health_tools", get_health_tools)
    monkeypatch.setattr(ae.settings, "domain_prompt_optimization", True)
    monkeypatch.setattr(ae.settings, "decision_mode", "off")
    monkeypatch.setattr(executor, "_build_system_prompt", lambda *a, **k: "FULL_HEALTH_CONTEXT" * 1000)
    monkeypatch.setattr(executor, "_build_system_knowledge_prompt_context", lambda *a: "PRIVATE_KB_SENTINEL")
    svc = AgentConversationService(db)
    conv = svc.get_or_create_conversation(user.id, None, title="synthetic everyday") if history else None
    prior = [("user", "你好"), ("assistant", "你好！")]
    if history == "correction":
        from tests.test_agent_everyday_prompt import PICKUP, PICKUP_REPLY
        prior = [("user", PICKUP), ("assistant", PICKUP_REPLY),
                 ("user", "不是10号门，是11号门。"),
                 ("assistant", "收到，是11号门，不是10号门。")]
    if conv:
        for role, content in prior:
            svc.save_message(conv.id, role, content, meta={
                "client_turn_finalized": True, "completion_status": "complete",
                "turn_outcome": {"status": "complete", "confirmation_required": False,
                                 "verified_receipt_count": 0, "actions": [], "goals": []},
            } if role == "assistant" else None)
    events = [event async for event in executor.run_stream(
        user_id=user.id, message="讲一个很短的故事", user_auth_token="test-token",
        conversation_id=conv.id if conv else None,
        extra_context=json.dumps({"model_id": provider.model}) if selected else None,
    )]
    assert len(provider.calls) == 1
    call = provider.calls[0]
    assert not call.get("tools")
    payload = json.dumps(call["messages"], ensure_ascii=False)
    assert "FULL_HEALTH_CONTEXT" not in payload
    assert "PRIVATE_KB_SENTINEL" not in payload
    assert len(payload) < 6000
    if history:
        assert all(content in payload for _, content in prior)
        assert "历史用户消息" in payload
    done = events[-1]["data"]
    assert done["turn_outcome"]["status"] == "complete"
    saved = db.get(AgentMessage, done["message_id"]).content
    streamed = "".join(e["data"].get("content", "") for e in events if e.get("event") == "token")
    assert saved == streamed == "小熊折好纸船，让它载着星光漂向远方。"
    if selected:
        assert executor._request_model_id == provider.model


def test_admission_reads_entire_owned_small_conversation(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    executor = ae.AgentExecutor(db)
    svc = AgentConversationService(db)
    conv = svc.get_or_create_conversation(user.id, None, title="pending task")
    svc.save_message(conv.id, "user", "请删除这条记录")
    svc.save_message(conv.id, "assistant", "确认删除吗？", meta={"pending_choice": {"required": True}})
    for _ in range(8):
        svc.save_message(conv.id, "user", "你好")
        svc.save_message(conv.id, "assistant", "你好！")
    assert executor._admit_everyday_task("讲一个很短的故事", user.id, conv.id) is None
    assert executor._admit_everyday_task("讲一个很短的故事", user.id + 1, conv.id) is None
    assert executor._admit_everyday_task("讲一个很短的故事", user.id, conv.id + 100) is None
    assert executor._admit_everyday_task("查我的睡眠", user.id, None) is None


def test_send_meta_keeps_payload_coverage():
    from app.services.agent_send_meta import _build_usage

    usage = _build_usage({"calls": 21, "prompt_tokens": 700,
                          "captured_items": 20, "omitted_items": 1,
                          "prompt_payload_calls": 21, "prompt_payload_items": 20})
    assert usage["captured_items"] == 20
    assert usage["omitted_items"] == 1
    assert usage["prompt_payload_calls"] == 21
    assert usage["prompt_payload_items"] == 20
