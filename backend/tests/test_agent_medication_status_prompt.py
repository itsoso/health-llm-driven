"""Intent guidance is shared; it grants no clinical or write authority."""
import pytest

from app.services.agent_executor import AgentExecutor, _build_compact_empty_retry_messages
from app.services.guidance_validator import enforce_medical_evidence_boundaries


@pytest.mark.parametrize("kwargs", [
    {"lite": True}, {"lite": False}, {"static_rules_only": True},
    {"health_evidence_runtime": True},
])
def test_medication_status_guidance_present_in_shared_prompt(db, auth_user_and_headers, kwargs):
    user, _ = auth_user_and_headers
    prompt = AgentExecutor(db)._build_system_prompt(user.id, 0, None, **kwargs)
    assert "## 健康近况与用药意图" in prompt
    for rule in ("用户自述", "记录或提醒", "不代表治愈", "急症", "未完成的确认"):
        assert rule in prompt


def test_compact_retry_keeps_status_and_safety_rules_even_with_large_context():
    messages = [
        {"role": "system", "content": "## 用户健康档案\n" + "历史资料" * 1000},
        {"role": "user", "content": "我感觉好些了，好像不用吃药了。"},
    ]
    result = _build_compact_empty_retry_messages(messages)
    for rule in ("## 健康近况与用药意图", "用户自述", "不代表治愈", "急症", "未完成的确认"):
        assert rule in result[0]["content"]
    assert result[-1]["content"] == messages[-1]["content"]


def test_compact_retry_preserves_previous_health_context_budget():
    context = "## 用户健康档案\n" + "资料" * 230 + "CLINICAL_CONTEXT_END"
    result = _build_compact_empty_retry_messages([
        {"role": "system", "content": context},
        {"role": "user", "content": "我现在感觉好些了。"},
    ])
    assert "CLINICAL_CONTEXT_END" in result[0]["content"]


def test_acknowledgement_does_not_need_medical_evidence_but_stop_advice_does():
    safe = "了解，你说胃部情况已经好转。你是告诉我近况，还是希望修改用药记录或提醒？目前我没有更改任何记录或提醒。"
    assert not enforce_medical_evidence_boundaries(safe).violations
    assert "unverified_dose_action" in enforce_medical_evidence_boundaries(
        "胃病已经好了，可以停药。"
    ).violations


@pytest.mark.parametrize("text", [
    "是否停药，请由医生确认，不要自行停。",
    "能否停药，请由医生判断。",
    "是否可以停药，需由药师评估。",
])
def test_explicit_clinician_referral_is_not_discontinuation_advice(text):
    result = enforce_medical_evidence_boundaries(text)
    assert not result.violations
    assert text in result.text


@pytest.mark.parametrize("tail", [
    "，但你现在可以停药。", "，明天服用两片。", "，药物服用时间改为睡前。",
    "，疗程缩短到三天。", "，停药即可。", "，你应该每天吃两片药。",
    "，确认前先断药。", "，今晚先停一晚。",
])
def test_referral_cannot_hide_appended_regimen_action(tail):
    result = enforce_medical_evidence_boundaries("是否停药建议先跟开药的医生确认" + tail)
    assert "unverified_dose_action" in result.violations


@pytest.mark.parametrize("text", [
    "是否停药（现在可以停药）建议先跟医生确认。",
    "是否停药建议先跟医生确认可以停药。",
    "是否停药建议先跟医生确认并每天服用两片。",
    "医生确认可以停药。",
    "是否停药需要向药师咨询，得到答复之前先停药。",
])
def test_clinician_mention_or_inserted_action_is_not_an_exemption(text):
    assert "unverified_dose_action" in enforce_medical_evidence_boundaries(text).violations


@pytest.mark.asyncio
async def test_panel_synthesis_keeps_intent_boundary(db, auth_user_and_headers, monkeypatch):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    monkeypatch.setattr("app.services.agent_executor.get_health_tools", lambda **kwargs: [])
    captured = []

    async def lead(messages, tools):
        captured.append(messages[0]["content"])
        return {"content": "你是在告知近况，还是想修改用药记录或提醒？", "finish_reason": "stop"}

    class Provider:
        async def chat(self, **kwargs):
            captured.append(kwargs["messages"][0]["content"])
            return {"content": "你是在告知近况，还是想修改用药记录或提醒？", "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_call_llm", lead)
    monkeypatch.setattr("app.services.llm.factory.create_provider_for_model_id", lambda *_: Provider())
    events = [event async for event in executor._run_multi_model_stream(
        user.id, "我感觉好些了，好像不用吃药了。", None, None, '{"multi_model":true}',
    )]
    assert events[-1]["event"] == "done"
    assert len(captured) == 4
    assert all("## 健康近况与用药意图" in prompt for prompt in captured)


@pytest.mark.asyncio
async def test_ordinary_clarification_is_persisted_and_replayed_without_write(db, auth_user_and_headers, monkeypatch):
    from app.models.agent_conversation import AgentMessage
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    calls = []
    reply = "了解，你说现在感觉好些了。你是告诉我近况，还是想修改用药记录或提醒？"

    async def answer(messages, tools):
        calls.append(messages)
        assert "## 健康近况与用药意图" in messages[0]["content"]
        yield {"type": "content", "text": reply}
        yield {"type": "finish", "finish_reason": "stop"}

    async def forbidden_tool(*args, **kwargs):
        pytest.fail("Clarification must not dispatch a tool")

    monkeypatch.setattr(executor, "_call_llm_stream", answer)
    monkeypatch.setattr(executor, "_execute_tool", forbidden_tool)
    kwargs = dict(user_id=user.id, message="我感觉好些了，好像不用吃药了。",
                  client_turn_id="synthetic-medication-clarification")
    events = [e async for e in executor.run_stream(**kwargs)]
    done = next(e["data"] for e in events if e.get("event") == "done")
    saved = db.get(AgentMessage, done["message_id"])
    streamed = "".join(e["data"]["content"] for e in events if e.get("event") == "token")
    assert streamed == saved.content
    assert reply in saved.content
    assert not saved.meta.get("medical_boundary_flags")
    assert not done.get("write_receipts")
    assert done["turn_outcome"]["status"] == "complete"
    replay = [e async for e in executor.run_stream(**kwargs, conversation_id=done["conversation_id"])]
    assert next(e["data"]["message_id"] for e in replay if e.get("event") == "done") == saved.id
    assert len(calls) == 1
