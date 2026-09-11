"""All panel narrative is untrusted until the common output boundary passes."""
import pytest
from fastapi import HTTPException

from app.models.agent_conversation import AgentMessage
from app.services.agent_executor import AgentExecutor
from app.services.llm.usage_tracker import LLMBudgetExceeded


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["lead", "perspective", "synthesis"])
@pytest.mark.parametrize("candidate,forbidden,flag", [
    ("建议每天服用布洛芬两片。", "服用布洛芬两片", "medical_evidence_boundary"),
    ("<tool_response>PRIVATE_PROTOCOL</tool_response>", "PRIVATE_PROTOCOL", "protocol_leak"),
])
async def test_panel_output_is_guarded_before_downstream_or_user_release(
    db, auth_user_and_headers, monkeypatch, stage, candidate, forbidden, flag,
):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    monkeypatch.setattr(executor, "_build_system_prompt", lambda *_a, **_k: "SYS")
    monkeypatch.setattr("app.services.agent_executor.get_health_tools", lambda *a, **k: [])
    synthesis_inputs = []

    async def lead(messages, tools):
        return {"content": candidate if stage == "lead" else "合成数据尚不足以说明原因。",
                "finish_reason": "stop"}

    class Provider:
        async def chat(self, **kwargs):
            synthesizing = "综合专家" in kwargs["messages"][0]["content"]
            if synthesizing:
                synthesis_inputs.append(kwargs["messages"][1]["content"])
            selected = "synthesis" if synthesizing else "perspective"
            return {"content": candidate if stage == selected else "当前没有足够记录支持结论。",
                    "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_call_llm", lead)
    monkeypatch.setattr("app.services.llm.factory.create_provider_for_model_id", lambda *_: Provider())
    events = [event async for event in executor._run_multi_model_stream(
        user.id, "聊聊今天", None, None, '{"multi_model":true}',
    )]
    done = events[-1]["data"]
    saved = db.get(AgentMessage, done["message_id"])
    streamed = "".join(event["data"].get("content", "")
                       for event in events if event["event"] == "token")
    assert forbidden not in streamed
    assert forbidden not in saved.content
    assert all(forbidden not in value for value in synthesis_inputs)
    assert streamed == saved.content
    assert done["turn_outcome"]["status"] == ("failed" if flag == "protocol_leak" else "blocked")
    assert saved.meta["turn_outcome"] == done["turn_outcome"]
    if flag == "protocol_leak":
        assert done["completion_status"] == "error"
        assert "protocol_leak" in saved.meta["output_quality_flags"]
    else:
        assert saved.meta["medical_boundary_flags"]


@pytest.mark.asyncio
@pytest.mark.parametrize("context_error", [False, True])
async def test_panel_normal_text_is_released_once_and_remains_complete(db, auth_user_and_headers, monkeypatch, caplog, context_error):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    monkeypatch.setattr(executor, "_build_system_prompt", lambda *_a, **_k: "SYS")
    monkeypatch.setattr("app.services.agent_executor.get_health_tools", lambda *a, **k: [])
    if context_error:
        def unavailable_context(*_a, **_k):
            raise RuntimeError("PRIVATE_CONTEXT_SENTINEL")
        monkeypatch.setattr(
            "app.services.agent_conversation_service.AgentConversationService.build_actionable_references",
            unavailable_context,
        )
    async def lead(messages, tools):
        return {"content": "普通知识说明。", "finish_reason": "stop"}
    class Provider:
        async def chat(self, **kwargs):
            return {"content": "这是普通的说明内容。", "finish_reason": "stop"}
    monkeypatch.setattr(executor, "_call_llm", lead)
    monkeypatch.setattr("app.services.llm.factory.create_provider_for_model_id", lambda *_: Provider())
    events = [event async for event in executor._run_multi_model_stream(
        user.id, "聊聊今天", None, None, '{"multi_model":true}',
    )]
    done = events[-1]["data"]
    streamed = "".join(event["data"].get("content", "") for event in events if event["event"] == "token")
    assert streamed == "这是普通的说明内容。"
    assert db.get(AgentMessage, done["message_id"]).content == streamed
    assert done["completion_status"] == "complete"
    assert done["turn_outcome"]["status"] == "complete"
    assert "PRIVATE_CONTEXT_SENTINEL" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["lead", "perspective", "synthesis"])
@pytest.mark.parametrize("error,reason", [
    (HTTPException(503, detail={"code": "ai_consent_unavailable", "message": "PRIVATE_FAILURE_SENTINEL"}), "consent_unavailable"),
    (LLMBudgetExceeded(reason="user_monthly_token_limit"), "budget_exhausted"),
    (RuntimeError("503 PRIVATE_FAILURE_SENTINEL"), "provider_error"),
    (None, "unknown"),
])
async def test_panel_failure_stops_dependent_calls_with_honest_sanitized_status(
    db, auth_user_and_headers, monkeypatch, caplog, stage, error, reason,
):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    monkeypatch.setattr(executor, "_build_system_prompt", lambda *_a, **_k: "SYS")
    monkeypatch.setattr("app.services.agent_executor.get_health_tools", lambda *a, **k: [])
    calls = []
    async def lead(messages, tools):
        calls.append("lead")
        if stage == "lead":
            if error is None:
                return {"content": "", "finish_reason": "stop"}
            raise error
        return {"content": "LEAD_DRAFT_NOT_A_FINAL_ANSWER", "finish_reason": "stop"}
    class Provider:
        async def chat(self, **kwargs):
            current = "synthesis" if "综合专家" in kwargs["messages"][0]["content"] else "perspective"
            calls.append(current)
            if stage == current:
                if error is None:
                    return {"content": "", "finish_reason": "stop"}
                raise error
            return {"content": "MODEL_DRAFT", "finish_reason": "stop"}
    monkeypatch.setattr(executor, "_call_llm", lead)
    monkeypatch.setattr("app.services.llm.factory.create_provider_for_model_id", lambda *_: Provider())
    events = [event async for event in executor._run_multi_model_stream(
        user.id, "聊聊今天", None, None, '{"multi_model":true}',
    )]
    done = events[-1]["data"]
    saved = db.get(AgentMessage, done["message_id"])
    assert "PRIVATE_FAILURE_SENTINEL" not in caplog.text
    assert "PRIVATE_FAILURE_SENTINEL" not in saved.content
    assert "LEAD_DRAFT_NOT_A_FINAL_ANSWER" not in saved.content
    assert done["turn_outcome"]["status"] == ("failed" if reason in {"provider_error", "unknown"} else "blocked")
    assert done["turn_outcome"]["reason_code"] == reason
    assert saved.meta["turn_outcome"] == done["turn_outcome"]
    if stage == "lead":
        assert calls == ["lead"]
    elif stage == "perspective":
        assert "synthesis" not in calls
