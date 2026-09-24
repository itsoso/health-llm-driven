"""UI-authored read-only follow-up text; no patient data or write authority."""
import json
from datetime import datetime, timezone

import pytest
from app.services.clinician_provenance_guard import classify_clinician_turn
from app.services.utterance_intent_classifier import classify_agent_utterance

EXAM_PROMPT = (
    "请基于这次体检异常解读，帮我按优先级梳理风险、行动、复查安排和需要向医生确认的问题。"
    "不要替代诊断或用药建议。"
)


@pytest.mark.parametrize("text", [
    EXAM_PROMPT,
    "请帮我整理向医生确认的问题。",
    "帮我列出需要跟医师沟通的问题，不要替代诊断。",
    "帮我准备与大夫讨论的问题。",
])
def test_clinician_question_preparation_is_read_only_advice(text):
    decision = classify_clinician_turn(text)
    assert decision.kind == "clinician_advice"
    intent = classify_agent_utterance(text)
    assert (intent.primary, intent.domain, intent.is_write) == (
        "advice", "clinical_context", False,
    )


@pytest.mark.parametrize("action", [
    "保存体检记录", "删除用药记录", "同步健康数据", "修改用药剂量",
    "创建复查提醒", "安排明天复查", "完成复查计划", "记录今天早餐",
])
@pytest.mark.parametrize("position", ["before", "after"])
def test_question_list_does_not_unblock_an_independent_action(action, position):
    text = action + "。" + EXAM_PROMPT if position == "before" else EXAM_PROMPT + action
    assert classify_clinician_turn(text).kind == "ambiguous_clinician_action"


@pytest.mark.parametrize("text", [
    "依据医生意见调整用药剂量",
    "帮我梳理向医生确认的问题，并依据医生意见修改用药记录",
    "请向医生确认后修改用药记录",
])
def test_clinician_basis_actions_stay_blocked(text):
    assert classify_clinician_turn(text).kind == "ambiguous_clinician_action"


def test_reported_clinician_context_still_denies_tools():
    from app.services.agent_executor import _clinician_turn_allows_tool

    decision = classify_clinician_turn(
        "医生说需要复查。帮我整理向医生确认的问题并保存记录"
    )
    # Existing report handling is zero-tool context rather than an action.
    assert decision.kind in {"clinician_context", "ambiguous_clinician_action"}
    assert not _clinician_turn_allows_tool(decision, "health_record")


@pytest.mark.parametrize("tool,args", [
    ("health_record", {"record_type": "medication", "data": {"name": "测试药物"}}),
    ("health_manage", {"record_type": "diet", "operation": "delete", "record_id": 1}),
    ("record_doctor_feedback", {"assessment": "测试意见"}),
])
def test_read_only_preparation_does_not_authorize_model_proposed_writes(tool, args):
    from tests.test_sleep_oxygen_read_scope import decide

    assert decide(args, EXAM_PROMPT, tool).action == "block"


async def test_real_stream_keeps_exam_context_and_does_not_replace_answer_with_action_refusal(
    db, auth_user_and_headers, isolated_agent_protocol_transport, monkeypatch,
):
    from app.services.agent_executor import AgentExecutor
    from app.twin.schema import HealthTwin, TwinMeta

    monkeypatch.setattr(
        "app.twin.builder.build_twin",
        lambda _db, user_id, **kwargs: HealthTwin(
            meta=TwinMeta(user_id=user_id, generated_at=datetime.now(timezone.utc)),
        ),
    )
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    seen_prompts = []
    reply = "可以带上报告，向医生确认异常指标的含义与复查时间。"

    async def fake_model(messages, tools):
        seen_prompts.append(str(messages))
        yield {"type": "content", "text": reply}
        yield {"type": "finish", "finish_reason": "stop"}

    executor._call_llm_stream = fake_model
    events = [event async for event in executor.run_stream(
        user_id=user.id, message=EXAM_PROMPT, user_auth_token="test-token",
        extra_context=json.dumps({
            "from": "exam-explain/7", "feedback_intent": "exam_abnormal_review",
            "exam": {"id": 7}, "abnormal_items": [],
        }),
    )]
    text = "".join(e["data"]["content"] for e in events if e.get("event") == "token")
    done = next(e["data"] for e in events if e.get("event") == "done")
    assert any("exam_abnormal_review" in prompt for prompt in seen_prompts)
    assert reply in text
    assert "去掉" not in text and "这一轮没有执行" not in text
    assert done["completion_status"] == "complete"
    assert done.get("write_receipts", []) == []
    assert done.get("tools_used", []) == []
    assert not [
        event for event in events
        if event.get("event") == "card"
        and event.get("data", {}).get("type") in {
            "medication", "medication_record", "medication_draft",
        }
    ]
