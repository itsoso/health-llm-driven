"""Spoken portion corrections preserve explicit ratios and write boundaries."""
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import urlsplit

import pytest
from app.models.daily_health import DietRecord
from app.models.user import User

from app.services.agent_executor import (
    AgentExecutor, _SimpleRecordTerminal, _parse_explicit_diet_correction,
    _build_deterministic_diet_correction_tool_call, _contextual_meal_consumed_fraction,
)

NOW = datetime(2026, 9, 11, 21, 9, tzinfo=timezone(timedelta(hours=8)))
MESSAGE = "我吃了二分之一，其实是三人份，重新修改晚餐的热量和分量。"


@pytest.mark.parametrize("message", [
    MESSAGE,
    "我吃了1/2，其实是3人份，重新修改晚餐的热量和份量。",
    "我吃了一半，修改晚餐记录",
    "晚餐只吃了二分之一，修改记录",
])
def test_spoken_half_correction_has_one_absolute_ratio_and_named_meal(message):
    correction = _parse_explicit_diet_correction(message, reference_now=NOW)
    assert correction is not None
    assert correction["consumed_fraction"] == 0.5
    assert correction["meal_type"] == "dinner"
    assert correction["date"] == "2026-09-11"
    assert "food_items" not in correction
    call = _build_deterministic_diet_correction_tool_call(message, write_receipts=[], reference_now=NOW)
    assert call and json.loads(call["function"]["arguments"])["operation"] == "list"


@pytest.mark.parametrize("message", [
    "我吃了二分之一还是三分之一，修改晚餐记录",
    "我没吃二分之一，修改晚餐记录",
    "我可能吃了二分之一，修改晚餐记录",
    "我吃了二分之一，其实是三人份，取消修改晚餐记录",
    "我吃了二分之一，其实是三人份，重新修改晚餐的热量和分量吗？",
    "我吃了二分之一，其实是三分之一，修改晚餐记录",
    "我吃了二分之一的烤鸭，修改晚餐记录",
    "他吃了二分之一，修改晚餐记录",
    "我吃了二分之一，其实是三人份，重新修改晚餐的热量和分量。不要修改",
    "我吃了二分之一，其实是三人份",
])
def test_ambiguous_cancelled_or_item_level_spoken_portions_do_not_write(message):
    assert _parse_explicit_diet_correction(message, reference_now=NOW) is None
    assert _build_deterministic_diet_correction_tool_call(message, write_receipts=[], reference_now=NOW) is None


def test_chinese_half_is_consistent_for_whole_meal_photos():
    assert _contextual_meal_consumed_fraction("这餐吃了二分之一") == (0.5, "二分之一")
    assert _contextual_meal_consumed_fraction(MESSAGE) is None


def model_call():
    return {"id": "synthetic", "type": "function", "function": {
        "name": "health_record", "arguments": json.dumps({
            "record_type": "diet", "data": {"food_items": "model must not create another meal"},
        }),
    }}


@pytest.mark.asyncio
async def test_shared_meal_scales_once_not_by_diner_count_and_retries_are_absolute():
    executor = AgentExecutor(MagicMock())
    executor._current_turn_user_message = MESSAGE
    executor._agent_kernel_reference_now = lambda: NOW
    record = {"id": 1040, "meal_type": "dinner", "food_items": "合成餐", "calories": 900,
              "protein": 42, "carbs": 78, "fat": 43, "fiber": 6}
    executor._api_get_json = AsyncMock(return_value=([record], None))
    for _ in range(2):
        calls = await executor._normalize_explicit_diet_update_tool_calls([model_call()], "owner-token")
        args = json.loads(calls[0]["function"]["arguments"])
        assert calls[0]["function"]["name"] == "health_manage"
        assert args["operation"] == "update" and args["record_id"] == 1040
        data = args["data"]
        assert data["calories"] == 450
        assert data["protein"] == 21 and data["carbs"] == 39
        assert data["fat"] == 21.5 and data["fiber"] == 3
        assert data["food_items"] == "合成餐（按实际食用二分之一计）"
        executor._api_get_json.return_value = ([{**record, **data}], None)


@pytest.mark.asyncio
async def test_spoken_correction_still_requires_one_verified_target():
    executor = AgentExecutor(MagicMock())
    executor._current_turn_user_message = MESSAGE
    executor._agent_kernel_reference_now = lambda: NOW
    executor._api_get_json = AsyncMock(return_value=([
        {"id": 1, "meal_type": "dinner"}, {"id": 2, "meal_type": "dinner"},
    ], None))
    with pytest.raises(_SimpleRecordTerminal):
        await executor._normalize_explicit_diet_update_tool_calls([model_call()], "owner-token")


@pytest.mark.asyncio
async def test_spoken_correction_stream_finishes_with_receipt_instead_of_failure(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    executor._agent_kernel_reference_now = lambda: NOW
    executor._api_get_json = AsyncMock(return_value=([{
        "id": 1040, "meal_type": "dinner", "food_items": "合成餐", "calories": 900,
    }], None))
    calls = []

    async def execute(name, arguments, token):
        args = json.loads(arguments) if isinstance(arguments, str) else arguments
        calls.append((name, args))
        return json.dumps({"id": 1040, "resource_type": "diet_record", "message": "已更新晚餐记录"})

    async def model(messages, tools):
        if not calls:
            yield {"type": "tool_calls", "tool_calls": [model_call()]}
            yield {"type": "finish", "finish_reason": "tool_calls"}
            return
        yield {"type": "content", "text": "已按整餐的二分之一修正晚餐。"}
        yield {"type": "finish", "finish_reason": "stop"}

    executor._execute_tool = execute
    executor._call_llm_stream = model
    events = [event async for event in executor.run_stream(user_id=user.id, message=MESSAGE, user_auth_token="owner-token")]
    assert len(calls) == 1 and calls[0][1]["operation"] == "update"
    assert calls[0][1]["data"]["calories"] == 450
    assert events[-1]["data"]["completion_status"] == "complete"
    assert events[-1]["data"]["write_receipts"]


@pytest.mark.asyncio
async def test_spoken_correction_postgres_updates_owned_meal_once(db, client, auth_user_and_headers):
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("real meal update and owner isolation require PostgreSQL")
    user, headers = auth_user_and_headers
    other = User(name="Synthetic other", email="fraction-other@example.invalid")
    db.add(other)
    db.flush()
    target = DietRecord(user_id=user.id, record_date=NOW.date(), meal_type="dinner",
        food_items="合成餐", calories=900, protein=42, carbs=78, fat=43, fiber=6)
    foreign = DietRecord(user_id=other.id, record_date=NOW.date(), meal_type="dinner",
        food_items="另一账号的合成餐", calories=1200)
    db.add_all([target, foreign])
    db.commit()
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    executor._current_turn_user_message = MESSAGE
    executor._agent_kernel_reference_now = lambda: NOW

    async def get_json(url, request_headers):
        parsed = urlsplit(url)
        response = client.get(parsed.path + "?" + parsed.query, headers=request_headers)
        assert response.status_code == 200
        return response.json(), None

    async def put(url, request_headers, data):
        response = client.put(urlsplit(url).path, headers=request_headers, json=data)
        assert response.status_code == 200
        return response.text

    executor._api_get_json = get_json
    executor._api_put = put
    executor._invalidate_twin_after_mutation = lambda: None
    token = headers["Authorization"].split(" ", 1)[1]
    for _ in range(2):
        calls = await executor._normalize_explicit_diet_update_tool_calls([model_call()], token)
        args = json.loads(calls[0]["function"]["arguments"])
        assert args["record_id"] == target.id
        await executor._exec_health_manage("http://testserver/api/v1", headers, args)
        db.expire_all()
        saved = db.get(DietRecord, target.id)
        assert (saved.calories, saved.protein, saved.carbs, saved.fat, saved.fiber) == (450, 21, 39, 21.5, 3)
        assert saved.food_items == "合成餐（按实际食用二分之一计）"
    assert db.query(DietRecord).count() == 2
    assert db.get(DietRecord, foreign.id).calories == 1200


@pytest.mark.parametrize("message", [
    "修改午餐记录，我只吃了其中的五分之一。修改今天的午餐记录。",
    "修改今天的午餐记录，我只吃了五分之一。",
    "刚才午餐吃了五分之一",
])
def test_production_command_first_portions_resolve_named_meal(message):
    correction = _parse_explicit_diet_correction(message, reference_now=NOW)
    assert correction is not None
    assert correction["consumed_fraction"] == 0.2
    assert correction["meal_type"] == "lunch"
    assert correction["date"] == "2026-09-11"


@pytest.mark.parametrize("message", [
    "修改午餐记录，我只吃了其中的五分之一。修改昨天的晚餐记录。",
    "修改今天午餐记录，我只吃了五分之一。修改昨天午餐记录。",
    "修改午餐记录，他只吃了五分之一",
    "修改午餐记录，我只吃了五分之一的米饭",
    "修改午餐记录，我只吃了五分之一。不要修改",
])
def test_command_first_conflicting_or_cancelled_portions_never_write(message):
    assert _parse_explicit_diet_correction(message, reference_now=NOW) is None


@pytest.mark.asyncio
async def test_ambiguous_meals_offer_bounded_commands_and_selection_is_reverified():
    executor = AgentExecutor(MagicMock())
    executor._current_turn_user_message = "午餐只吃了五分之一"
    executor._agent_kernel_reference_now = lambda: NOW
    rows = [{"id": record_id, "meal_type": "lunch", "food_items": "合成餐", "calories": 900}
            for record_id in (11, 12)]
    executor._api_get_json = AsyncMock(return_value=(rows, None))
    with pytest.raises(_SimpleRecordTerminal) as stopped:
        await executor._normalize_explicit_diet_update_tool_calls([model_call()], "owner-token")
    assert "记录 #11" in stopped.value.message
    assert "记录 #12" in stopped.value.message
    assert "修改2026-09-11午餐记录#11，我只吃了五分之一" in stopped.value.message
    executor._current_turn_user_message = "修改2026-09-11午餐记录#11，我只吃了五分之一"
    calls = await executor._normalize_explicit_diet_update_tool_calls([model_call()], "owner-token")
    args = json.loads(calls[0]["function"]["arguments"])
    assert args["record_id"] == 11 and args["data"]["calories"] == 180
    # A user/model supplied ID outside the authenticated query result cannot be edited.
    executor._current_turn_user_message = "修改2026-09-11午餐记录#99，我只吃了五分之一"
    with pytest.raises(_SimpleRecordTerminal):
        await executor._normalize_explicit_diet_update_tool_calls([model_call()], "owner-token")


@pytest.mark.asyncio
async def test_multiple_model_tools_only_produce_one_diet_update():
    executor = AgentExecutor(MagicMock())
    executor._current_turn_user_message = MESSAGE
    executor._agent_kernel_reference_now = lambda: NOW
    executor._api_get_json = AsyncMock(return_value=([{
        "id": 1040, "meal_type": "dinner", "food_items": "合成餐", "calories": 900,
    }], None))
    calls = await executor._normalize_explicit_diet_update_tool_calls([model_call(), model_call()], "owner-token")
    assert len(calls) == 1


@pytest.fixture
def meal_receipt_context(db, auth_user_and_headers):
    from app.models.agent_conversation import AgentConversation, AgentMessage
    user, _ = auth_user_and_headers
    conv = AgentConversation(user_id=user.id)
    db.add(conv); db.flush()
    target = DietRecord(user_id=user.id, record_date=NOW.date(), meal_type="lunch",
                        food_items="合成餐", calories=900)
    db.add(target); db.flush()
    receipt = {"verified": True, "status": "verified", "resource_type": "diet_record",
               "resource_id": str(target.id), "action": "create", "completed_at": NOW.isoformat()}
    answer = AgentMessage(conversation_id=conv.id, role="assistant", content="已保存午餐",
                          created_at=NOW.astimezone(timezone.utc), meta={"client_turn_finalized": True, "write_receipts": [receipt]})
    db.add(answer); db.flush()
    current = AgentMessage(conversation_id=conv.id, role="user", content="我只吃了三分之一", created_at=NOW)
    db.add(current); db.commit()
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    executor._current_turn_user_message = current.content
    executor._start_agent_kernel_turn(user_id=user.id, message=current.content, channel="chat",
        client_time_context={"current_time": NOW.isoformat(), "timezone": "Asia/Shanghai"})
    # Freeze the authoritative server clock for the synthetic receipt.
    from dataclasses import replace
    executor._agent_kernel_snapshot = replace(executor._agent_kernel_snapshot,
        context=replace(executor._agent_kernel_snapshot.context, current_time=NOW))
    executor._bind_agent_kernel_source_message(current.id)
    return executor, user, conv, target, answer, current


@pytest.mark.asyncio
async def test_short_followup_binds_owned_receipt_and_normalizes_to_same_record(db, meal_receipt_context):
    executor, user, conv, target, _, current = meal_receipt_context
    executor._bind_read_task_reference(user.id, conv.id)
    assert executor._agent_kernel_snapshot.intent.domain == "diet"
    assert executor._agent_kernel_snapshot.intent.operation == "update"
    executor._current_turn_user_message = current.content
    executor._api_get_json = AsyncMock(return_value=([{
        "id": target.id, "record_date": NOW.date().isoformat(), "meal_type": "lunch",
        "food_items": "合成餐", "calories": 900,
    }], None))
    calls = await executor._normalize_explicit_diet_update_tool_calls([model_call()], "owner-token")
    args = json.loads(calls[0]["function"]["arguments"])
    assert args["operation"] == "update" and args["record_id"] == target.id
    assert args["data"]["calories"] == 300


@pytest.mark.parametrize("damage", ["draft", "multiple_receipts", "foreign_owner", "foreign_conversation", "expired", "unfinalized", "unrelated_turn", "cancelled"])
def test_bare_portion_never_inherits_unverified_or_stale_context(db, meal_receipt_context, damage):
    from app.models.agent_conversation import AgentConversation, AgentMessage
    from app.services.agent_diet_continuation import load_diet_portion_reference
    from dataclasses import replace
    executor, user, conv, target, answer, current = meal_receipt_context
    if damage == "draft": answer.meta = {**answer.meta, "write_receipts": [], "cards": [{"type": "diet_draft"}]}
    elif damage == "multiple_receipts": answer.meta = {**answer.meta, "write_receipts": answer.meta["write_receipts"] * 2}
    elif damage == "foreign_owner":
        other = User(name="Other", email="meal-continuation@example.invalid"); db.add(other); db.flush()
        target.user_id = other.id
    elif damage == "foreign_conversation":
        other_conv = AgentConversation(user_id=user.id); db.add(other_conv); db.flush()
        current.conversation_id = other_conv.id
    elif damage == "expired": answer.meta = {**answer.meta, "write_receipts": [
        {**answer.meta["write_receipts"][0], "completed_at": (NOW - timedelta(days=2)).isoformat()}]}
    elif damage == "unfinalized": answer.meta = {**answer.meta, "client_turn_finalized": False}
    elif damage == "unrelated_turn": answer.role = "user"
    elif damage == "cancelled":
        current.content += "，取消修改"
        executor._agent_kernel_snapshot = replace(executor._agent_kernel_snapshot,
            envelope=replace(executor._agent_kernel_snapshot.envelope, text=current.content))
    db.flush()
    assert load_diet_portion_reference(db, user.id, conv.id, executor._agent_kernel_snapshot) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("message", [
    "修改午餐记录，我只吃了其中的五分之一。修改今天的午餐记录。",
    "刚才午餐吃了三分之一",
    "我只吃了三分之一",
])
async def test_real_pi_gateway_executes_exact_correction_without_model_tool_call(
        db, auth_user_and_headers, monkeypatch, isolated_agent_protocol_transport, message):
    from app.twin.schema import HealthTwin, TwinMeta
    user, _ = auth_user_and_headers
    monkeypatch.setattr("app.twin.builder.build_twin", lambda _db, user_id, **kwargs:
                        HealthTwin(meta=TwinMeta(user_id=user_id, generated_at=NOW)))
    executor = AgentExecutor(db)
    monkeypatch.setattr(executor, "_build_system_prompt", lambda *a, **k: "Use authorized tools.")
    conversation_id = None
    if message == "我只吃了三分之一":
        from app.models.agent_conversation import AgentConversation, AgentMessage
        now = datetime.now(timezone.utc)
        conv = AgentConversation(user_id=user.id)
        db.add(conv); db.flush()
        conversation_id = conv.id
        db.add(DietRecord(id=42, user_id=user.id, record_date=now.astimezone(NOW.tzinfo).date(),
                          meal_type="lunch", food_items="合成餐", calories=900))
        db.add(AgentMessage(conversation_id=conv.id, role="assistant", content="已保存午餐",
            created_at=now, meta={"client_turn_finalized": True, "write_receipts": [{
                "verified": True, "status": "verified", "resource_type": "diet_record",
                "resource_id": "42", "action": "create", "completed_at": now.isoformat(),
            }]}))
        db.commit()
    calls = []
    async def provider(messages, tools):
        yield {"type": "content", "text": "已按要求修正。"}
        yield {"type": "finish", "finish_reason": "stop"}
    async def get_records(url, headers):
        # The runtime owns the current date; the row reflects its exact query.
        from urllib.parse import parse_qs
        day = parse_qs(urlsplit(url).query)["start_date"][0]
        return [{"id": 42, "record_date": day, "meal_type": "lunch",
                 "food_items": "合成餐", "calories": 900}], None
    async def dispatch(request, token):
        calls.append(request)
        return json.dumps({"id": 42, "resource_type": "diet_record", "status": "verified"})
    monkeypatch.setattr(executor, "_api_get_json", get_records)
    monkeypatch.setattr(executor, "_call_llm_stream", provider)
    monkeypatch.setattr(executor, "_dispatch_tool_request", dispatch)
    events = [event async for event in executor.run_stream(user_id=user.id, message=message,
                        conversation_id=conversation_id, user_auth_token="test-token")]
    done = events[-1]["data"]
    assert len(calls) == 1, done
    assert calls[0].arguments["operation"] == "update"
    assert calls[0].arguments["record_id"] == 42
    expected = 180 if "五分之一" in message else 300
    assert calls[0].arguments["data"]["calories"] == expected
    assert done["completion_status"] == "complete"
    assert done["write_receipts"][0]["resource_id"] == "42"


@pytest.mark.asyncio
async def test_pending_draft_followup_blocks_model_create_instead_of_scaling_saved_meal(db, meal_receipt_context):
    executor, user, conv, target, answer, _ = meal_receipt_context
    answer.meta = {"client_turn_finalized": True, "write_receipts": [],
                   "cards": [{"type": "diet_draft", "data": {"photo_draft_token": "pending-synthetic"}}]}
    db.flush()
    executor._bind_read_task_reference(user.id, conv.id)
    assert not executor._agent_kernel_snapshot.intent.is_write
    executor._api_get_json = AsyncMock()
    with pytest.raises(_SimpleRecordTerminal, match="草稿"):
        await executor._normalize_explicit_diet_update_tool_calls([model_call()], "owner-token")
    executor._api_get_json.assert_not_awaited()
    assert target.calories == 900
