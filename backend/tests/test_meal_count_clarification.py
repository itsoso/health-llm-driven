"""Meal counts and duplicate-record clarifications are not food intake payloads."""
from dataclasses import replace

import pytest
from app.services.agent_kernel.capability_policy import decide_tool_capability
from app.services.agent_kernel.goal_spec import compile_goal_spec
from app.services.agent_kernel.intent_frame import build_intent_frame
from app.services.agent_kernel.types import (
    AgentEnvelope,
    ExecutionContext,
    ToolExecutionRequest,
    TurnSnapshot,
)
from app.services.utterance_intent_classifier import classify_agent_utterance

from tests.test_agent_coherence_pi_trajectories import (
    _isolate_twin_cache as _isolate_twin_cache,
)
from tests.test_agent_coherence_pi_trajectories import (
    clock as clock,
)
from tests.test_agent_coherence_pi_trajectories import (
    owned_data as owned_data,
)
from tests.test_agent_coherence_pi_trajectories import (
    script_executor,
)

COUNT_CONTEXT = [
    "中午是吃了两顿 没有重复", "中午吃了两顿，没有重复记录。",
    "午餐确实吃了两顿，不是重复记录", "我吃了两顿饭，没有重复",
    "两顿没有重复", "中午吃了两顿", "记录午餐吃了两顿饭",
]


@pytest.mark.parametrize("message", COUNT_CONTEXT)
@pytest.mark.parametrize("has_image", [False, True])
def test_meal_count_cannot_authorize_invented_food_or_mutation(message, has_image):
    intent = classify_agent_utterance(message)
    assert not intent.is_write
    context = ExecutionContext.for_test(user_id=1, channel="typed")
    envelope = AgentEnvelope(user_id=1, channel="typed", text=message,
                             media=({"kind": "image"},) if has_image else ())
    snapshot = TurnSnapshot(envelope=envelope, context=context,
                            intent=build_intent_frame(envelope, context))
    snapshot = replace(snapshot, goal=compile_goal_spec(
        envelope=envelope, context=context, intent=snapshot.intent))
    for tool, arguments in [
        ("health_record", {"record_type": "diet", "data": {
            "meal_type": "snack", "food_items": "两顿没有重复",
            "calories": 480, "protein": 20, "carbs": 40, "fat": 20, "fiber": 3}}),
        ("health_manage", {"record_type": "diet", "action": "delete", "record_id": 1}),
        ("health_manage", {"record_type": "diet", "action": "update", "record_id": 1,
                           "data": {"calories": 0}}),
    ]:
        request = ToolExecutionRequest(tool_name=tool, arguments=arguments, tool_call_id="count-only")
        assert decide_tool_capability(snapshot, request).action == "block"


@pytest.mark.asyncio
@pytest.mark.parametrize("history", [False, True])
async def test_duplicate_clarification_preserves_both_meals_and_never_estimates(
    db, monkeypatch, owned_data, clock, client, auth_user_and_headers, history,
):
    from app.config import settings
    from app.models.agent_conversation import AgentConversation, AgentMessage
    from app.models.daily_health import DietRecord
    from app.models.user import User

    monkeypatch.setattr(settings, "domain_prompt_optimization", True)
    user = owned_data
    other = db.query(User).filter(User.id != user.id).first()
    rows = [DietRecord(user_id=owner, record_date=clock[0].date(), meal_type="lunch",
                       food_items=food, calories=calories)
            for owner, food, calories in [(user.id, "合成午餐甲", 170),
                                          (user.id, "合成午餐乙", 230),
                                          (other.id, "其他用户测试餐", 310)]]
    db.add_all(rows)
    conversation_id = None
    if history:
        conv = AgentConversation(user_id=user.id, title="合成餐次澄清")
        db.add(conv)
        db.flush()
        conversation_id = conv.id
        db.add_all([
            AgentMessage(conversation_id=conv.id, role="user", content="中午吃过两顿饭。"),
            AgentMessage(conversation_id=conv.id, role="assistant", content="这两条午餐是否重复？"),
        ])
    db.commit()
    before = [(r.id, r.user_id, r.food_items, r.calories) for r in db.query(DietRecord).all()]
    trace = script_executor(db, monkeypatch, [
        ("health_record", {"record_type": "diet", "data": {
            "meal_type": "snack", "food_items": "两顿没有重复",
            "record_date": str(clock[0].date()),
            "calories": 480, "protein": 20, "carbs": 40, "fat": 20, "fiber": 3}}),
        "已记录加餐。",
    ])
    estimates, dispatched = [], []

    async def estimate(food):
        estimates.append(food)
        return {"calories": 480, "protein": 20, "carbs": 40, "fat": 20, "fiber": 3}

    async def dispatch(request, token):
        dispatched.append(request)
        assert request.tool_name == "health_record"
        response = client.post("/api/v1/diet/records", json=request.arguments["data"],
                               headers=auth_user_and_headers[1])
        assert response.status_code == 200
        return response.text

    monkeypatch.setattr("app.services.agent_executor._estimate_simple_diet_nutrition", estimate)
    monkeypatch.setattr(trace.executor, "_dispatch_tool_request", dispatch)
    for _ in range(2):
        events = [e async for e in trace.executor.run_stream(
            user.id, "中午是吃了两顿 没有重复", channel="typed",
            conversation_id=conversation_id, client_turn_id="synthetic-meal-count-clarification")]
        done = next(e["data"] for e in reversed(events) if e.get("event") == "done")
        db.expire_all()
        assert [(r.id, r.user_id, r.food_items, r.calories) for r in db.query(DietRecord).all()] == before
        assert not estimates and not dispatched and not trace.calls
        assert not done.get("write_receipts")
        assert done["turn_outcome"]["status"] == "complete"
        assert done["turn_outcome"]["confirmation_required"] is False
        saved = db.get(AgentMessage, done["message_id"])
        public = "".join(e["data"].get("content", "") for e in events if e.get("event") == "token")
        assert saved.content == public
        assert "新增" in public and "重复" in public
        assert "kcal" not in public and "480" not in public
        assert saved.meta["turn_outcome"] == done["turn_outcome"]


@pytest.mark.parametrize("message", [
    "午餐吃了两份牛肉", "中午吃了两个鸡蛋", "记录晚餐吃了一碗米饭",
    "其实只吃了一半的蛋糕", "记录午餐 米饭100克，晚餐也吃了一顿牛肉",
])
def test_actual_food_intake_keeps_existing_write_authority(message):
    assert classify_agent_utterance(message).is_write


@pytest.mark.parametrize("message", [
    "妈妈中午吃了两顿，没有重复", "如果中午吃了两顿，没有重复",
    "“中午吃了两顿，没有重复”", "解释例句：中午吃了两顿，没有重复",
    "中午吃了两顿，没有重复吗？", "中午吃了两顿，没有重复，胃痛怎么办？",
    "中午吃了两顿，没有重复，然后删除午餐记录",
    "中午吃了两顿，没有重复，记录喝水200ml",
    "中午吃了两顿牛肉，没有重复", "我吃了两次阿司匹林",
])
def test_count_acknowledgement_never_swallows_other_questions_or_authority(message):
    from app.services.agent_meal_input_clarification import resolve_meal_count_input
    assert resolve_meal_count_input(message) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("panel", [False, True])
@pytest.mark.parametrize("image", [False, True])
@pytest.mark.parametrize("message,status", [
    ("中午是吃了两顿 没有重复", "complete"),
    ("记录午餐吃了两顿饭", "waiting_for_user"),
])
async def test_count_only_input_bypasses_models_even_with_image_or_panel(
    db, auth_user_and_headers, isolated_agent_protocol_transport, monkeypatch,
    message, status, panel, image,
):
    import base64
    import json
    from io import BytesIO

    from app.models.daily_health import DietRecord
    from app.services.agent_executor import AgentExecutor
    from PIL import Image

    executor = AgentExecutor(db)

    async def forbidden(*args, **kwargs):
        pytest.fail("meal-count context must not estimate, dispatch or call a model")

    def forbidden_provider(*args, **kwargs):
        pytest.fail("meal-count context must not instantiate a model provider")

    monkeypatch.setattr(executor, "_call_llm", forbidden)
    monkeypatch.setattr(executor, "_call_llm_stream", forbidden)
    monkeypatch.setattr(executor, "_dispatch_tool_request", forbidden)
    monkeypatch.setattr("app.services.agent_executor._estimate_simple_diet_nutrition", forbidden)
    monkeypatch.setattr("app.services.llm.factory.create_provider_for_model_id", forbidden_provider)
    kwargs = {}
    if image:
        from app.api.agent import AgentRequest, _validate_agent_attachments
        with BytesIO() as stream:
            Image.new("RGB", (8, 8), color="white").save(stream, format="PNG")
            request = AgentRequest(message=message, image_type="png",
                                   image_base64=base64.b64encode(stream.getvalue()).decode())
        kwargs["images"], _, _ = _validate_agent_attachments(request)
        assert kwargs["images"]
    events = [e async for e in executor.run_stream(
        auth_user_and_headers[0].id, message, channel="typed",
        extra_context=json.dumps({"multi_model": panel}), **kwargs)]
    done = next(e["data"] for e in reversed(events) if e.get("event") == "done")
    assert done["turn_outcome"]["status"] == status
    assert done["turn_outcome"]["dispatch_started"] is False
    assert not done.get("write_receipts")
    assert db.query(DietRecord).count() == 0
