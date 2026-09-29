"""Missing meal evidence/targets cannot become a successful or guessed write."""
import json
from datetime import date

import pytest

from app.models.agent_conversation import AgentMessage
from app.models.daily_health import DietRecord
from app.services.agent_executor import AgentExecutor


@pytest.fixture(autouse=True)
def _isolated_transport(isolated_agent_protocol_transport):
    """Keep real entrypoint/transport while refusing any external connection."""


@pytest.mark.asyncio
@pytest.mark.parametrize("panel", [False, True])
@pytest.mark.parametrize("query,reason", [
    ("根据图片记录晚餐", "meal_image_required"),
    ("记录图片里的晚餐", "meal_image_required"),
    ("其实只吃了一半", "meal_correction_target_required"),
    ("不是午餐，是晚餐", "meal_correction_target_required"),
])
async def test_missing_meal_input_waits_without_dispatch(db, auth_user_and_headers, monkeypatch, panel, query, reason):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    provider_calls = []
    dispatched = []

    async def provider(messages, tools):
        provider_calls.append("ordinary_or_lead")
        yield {"type": "content", "text": "这轮尚未记录或修改，请补充图片或目标餐。"}
        yield {"type": "finish", "finish_reason": "stop"}

    class PanelProvider:
        async def chat(self, **kwargs):
            provider_calls.append("panel")
            return {"content": "这轮尚未记录或修改，请补充图片或目标餐。", "finish_reason": "stop"}

    async def dispatch(request, token):
        dispatched.append(request)
        return '{"records": []}'

    monkeypatch.setattr(executor, "_build_system_prompt", lambda *a, **k: "Use the scripted response.")
    monkeypatch.setattr(executor, "_call_llm_stream", provider)
    monkeypatch.setattr(executor, "_dispatch_tool_request", dispatch)
    monkeypatch.setattr("app.services.llm.factory.create_provider_for_model_id", lambda *a, **k: PanelProvider())
    events = [event async for event in executor.run_stream(
        user.id, query, extra_context=json.dumps({"multi_model": panel}),
        client_turn_id=f"missing-meal-{panel}-{reason}-{query}",
    )]
    done = events[-1]["data"]
    assert done["turn_outcome"]["status"] == "waiting_for_user"
    assert done["turn_outcome"]["reason_code"] == reason
    assert done["turn_outcome"]["dispatch_started"] is False
    assert done["turn_outcome"]["verified_receipt_count"] == 0
    assert done["turn_outcome"]["confirmation_required"] is True
    assert not dispatched and not provider_calls
    assert db.query(DietRecord).filter_by(user_id=user.id).count() == 0
    saved = db.get(AgentMessage, done["message_id"])
    assert saved.meta["turn_outcome"] == done["turn_outcome"]
    assert saved.meta["completion_status"] == done["completion_status"]
    public = "".join(event.get("data", {}).get("content", "") for event in events if event.get("event") == "token")
    assert public == saved.content
    assert "未" in public
    assert ("图片" if reason == "meal_image_required" else "哪") in public


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["其实只吃了一半", "不是午餐，是晚餐"])
async def test_unbound_followup_does_not_select_existing_meal_and_replay_stays_waiting(
    db, auth_user_and_headers, monkeypatch, query,
):
    user, _ = auth_user_and_headers
    existing = DietRecord(user_id=user.id, record_date=date(2026, 9, 28),
                          meal_type="lunch", food_items="合成测试餐", calories=800)
    db.add(existing)
    db.commit()
    executor = AgentExecutor(db)

    async def forbidden(*args, **kwargs):
        pytest.fail("An unbound correction cannot query or mutate a guessed target")

    monkeypatch.setattr(executor, "_api_get_json", forbidden)
    monkeypatch.setattr(executor, "_dispatch_tool_request", forbidden)
    monkeypatch.setattr(executor, "_call_llm", forbidden)
    monkeypatch.setattr(executor, "_call_llm_stream", forbidden)
    for _ in range(2):
        events = [event async for event in executor.run_stream(
            user.id, query, client_turn_id="unbound-followup-replay",
        )]
        done = events[-1]["data"]
        assert done["turn_outcome"]["status"] == "waiting_for_user"
        assert not done.get("write_receipts")
        db.refresh(existing)
        assert existing.meal_type == "lunch" and existing.calories == 800
        assert db.query(DietRecord).filter_by(user_id=user.id).count() == 1


@pytest.mark.parametrize("query,reason", [
    ("请帮我根据照片记录今天晚餐。", "meal_image_required"),
    ("保存照片中的午餐", "meal_image_required"),
    ("我只吃了1/2", "meal_correction_target_required"),
    ("实际上只吃了二分之一。", "meal_correction_target_required"),
    ("不是早餐,是午餐", "meal_correction_target_required"),
])
def test_complete_known_frames_only_request_missing_input(query, reason):
    from app.services.agent_meal_input_clarification import resolve_meal_input_clarification
    result = resolve_meal_input_clarification(query, has_attachment=False)
    assert result is not None and result.reason_code == reason


@pytest.mark.parametrize("query", [
    "根据图片记录晚餐", "记录图片里的晚餐", "其实只吃了一半", "不是午餐，是晚餐",
])
def test_current_attachment_keeps_existing_media_path(query):
    from app.services.agent_meal_input_clarification import resolve_meal_input_clarification
    assert resolve_meal_input_clarification(query, has_attachment=True) is None


@pytest.mark.parametrize("query", [
    "不要根据图片记录晚餐", "如果根据图片记录晚餐", "解释例句：根据图片记录晚餐",
    "“根据图片记录晚餐”", "`根据图片记录晚餐`", "根据图片记录妈妈的晚餐",
    "根据图片记录晚餐和午餐", "根据图片记录晚餐，再删除午餐",
    "不是妈妈的午餐，是晚餐", "不是午餐，是晚餐，删除之前的记录",
    "其实妈妈只吃了一半", "其实只吃了一半的蛋糕", "其实只吃了一半吗？",
    "其实只吃了一半，不要修改", "其实只吃了一半，然后记录喝水500ml",
    "修正上一餐吃了1/3", "晚餐我吃了1/2，请修改记录", "记录晚餐，吃了一半",
    "记录今天晚餐：白米饭100克、鸡蛋1个", "不是午餐，是午餐",
])
def test_clarification_frame_never_erases_other_authority_or_known_targets(query):
    from app.services.agent_meal_input_clarification import resolve_meal_input_clarification
    assert resolve_meal_input_clarification(query, has_attachment=False) is None
