"""Relative meal corrections use an authenticated lookup, never model IDs."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import urlsplit

import pytest
from app.models.daily_health import DietRecord
from app.models.user import User
from app.services.agent_executor import (
    AgentExecutor,
    _build_deterministic_diet_correction_tool_call,
    _contextual_meal_consumed_fraction,
    _parse_explicit_diet_correction,
    _SimpleRecordTerminal,
)
from app.services.utterance_intent_classifier import classify_agent_utterance

NOW = datetime(2026, 9, 8, 18, 54, tzinfo=timezone(timedelta(hours=8)))
MESSAGE = "修正上一餐吃了1/3"


def meal(record_id=101, *, day="2026-09-08", at="2026-09-08T12:00:00+08:00", **values):
    return {
        "id": record_id, "record_date": day, "created_at": at,
        "meal_type": "lunch", "food_items": "合成测试餐",
        "calories": 900.0, "protein": 60.0, "carbs": 90.0,
        "fat": 30.0, "fiber": 9.0, **values,
    }


def tool_call(name="health_record"):
    return {
        "id": "model-call", "type": "function",
        "function": {"name": name, "arguments": json.dumps({
            "record_type": "diet", "operation": "update", "record_id": 999,
            "data": {"meal_type": "breakfast", "calories": 1},
        })},
    }


@pytest.mark.parametrize("message", [MESSAGE, "修正上一顿吃了1／3", "修改刚才那餐只吃了三分之一"])
def test_relative_fraction_correction_is_typed_and_has_a_deterministic_lookup(message):
    intent = classify_agent_utterance(message, reference_now=NOW)
    assert intent.is_write and intent.domain == "diet" and intent.operation == "update"
    parsed = _parse_explicit_diet_correction(message, reference_now=NOW)
    assert parsed and parsed["target"] == "latest"
    assert parsed["consumed_fraction"] == pytest.approx(1 / 3)
    call = _build_deterministic_diet_correction_tool_call(message, write_receipts=[], reference_now=NOW)
    assert call and call["function"]["name"] == "health_manage"
    args = json.loads(call["function"]["arguments"])
    assert args["operation"] == "list" and "meal_type" not in args


@pytest.mark.parametrize("message", [
    "不要修正上一餐吃了1/3", "怎么修正上一餐吃了1/3？", "修正上一餐吃了1/3还是1/2",
    "修正上一餐吃了1/0", "修正上一餐吃了2/1", "修正上一餐吃了-1/3",
    "修正上一餐吃了大概1/3", "修正上一餐吃了1/3，算了不要改", "修正上一餐蛋糕吃了1/3",
])
def test_relative_correction_never_accepts_ambiguous_or_cancelled_fractions(message):
    assert _parse_explicit_diet_correction(message, reference_now=NOW) is None


def test_previous_meal_correction_is_not_a_new_photo_consumption_statement():
    assert _contextual_meal_consumed_fraction("修正上一餐只吃了1/3") is None


@pytest.mark.asyncio
async def test_latest_correction_updates_only_authoritative_latest_record_and_is_absolute():
    executor = AgentExecutor(MagicMock())
    executor._current_turn_user_message = MESSAGE
    executor._agent_kernel_reference_now = lambda: NOW
    executor._api_get_json = AsyncMock(return_value=([
        meal(), meal(100, at="2026-09-08T08:00:00+08:00", meal_type="breakfast"),
    ], None))
    calls = await executor._normalize_explicit_diet_update_tool_calls([tool_call()], "owner-token")
    args = json.loads(calls[0]["function"]["arguments"])
    assert calls[0]["function"]["name"] == "health_manage"
    assert args["operation"] == "update" and args["record_id"] == 101
    assert args["data"]["meal_type"] == "lunch"
    assert args["data"]["calories"] == 300 and args["data"]["protein"] == 20
    url, headers = executor._api_get_json.await_args.args
    assert "/diet/records/me?" in url and "limit=2" in url
    assert "start_date=2026-09-07" in url and "end_date=2026-09-08" in url
    assert "meal_type=" not in url and headers == {"Authorization": "Bearer owner-token"}
    executor._api_get_json.return_value = ([meal(**args["data"])], None)
    repeated = await executor._normalize_explicit_diet_update_tool_calls([tool_call()], "owner-token")
    assert json.loads(repeated[0]["function"]["arguments"])["data"]["calories"] == 300


@pytest.mark.asyncio
async def test_previous_meal_can_be_yesterday_after_midnight():
    executor = AgentExecutor(MagicMock())
    executor._current_turn_user_message = MESSAGE
    executor._agent_kernel_reference_now = lambda: NOW.replace(hour=0, minute=5)
    executor._api_get_json = AsyncMock(return_value=([
        meal(day="2026-09-07", at="2026-09-07T19:00:00+08:00", meal_type="dinner"),
    ], None))
    calls = await executor._normalize_explicit_diet_update_tool_calls([tool_call()], "owner-token")
    assert json.loads(calls[0]["function"]["arguments"])["data"]["meal_type"] == "dinner"


@pytest.mark.parametrize("rows,error", [
    ([], None), (None, "upstream unavailable"), ([meal(), meal(102)], None),
    ([meal(created_at=None)], None), ([meal(day="2026-09-01")], None),
    ([meal(at="2026-09-09T12:00:00+08:00")], None),
    ([meal(), {"id": 102}], None),
])
@pytest.mark.asyncio
async def test_latest_lookup_must_be_recent_complete_unique_and_successful(rows, error):
    executor = AgentExecutor(MagicMock())
    executor._current_turn_user_message = MESSAGE
    executor._agent_kernel_reference_now = lambda: NOW
    executor._api_get_json = AsyncMock(return_value=(rows, error))
    with pytest.raises(_SimpleRecordTerminal):
        await executor._normalize_explicit_diet_update_tool_calls([tool_call()], "owner-token")
    assert not executor._trusted_diet_portion_update_keys
    if rows and not error:
        assert executor._turn_diet_correction_unresolved_reason == "latest_target_unverified"


@pytest.mark.asyncio
async def test_pi_stream_binds_previous_meal_proposal_before_dispatch(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    executor._agent_kernel_reference_now = lambda: NOW
    executor._api_get_json = AsyncMock(return_value=([meal()], None))
    calls = []

    async def execute(name, arguments, token):
        args = json.loads(arguments) if isinstance(arguments, str) else arguments
        calls.append((name, args))
        return json.dumps({"id": 101, "resource_type": "diet_record", "message": "已更新午餐记录"})

    async def model(messages, tools):
        if not calls:
            yield {"type": "tool_calls", "tool_calls": [tool_call()]}
            yield {"type": "finish", "finish_reason": "tool_calls"}
            return
        assert any(m.get("role") == "tool" for m in messages)
        yield {"type": "content", "text": "已按实际食用1/3修正上一餐。"}
        yield {"type": "finish", "finish_reason": "stop"}

    executor._execute_tool = execute
    executor._call_llm_stream = model
    events = [event async for event in executor.run_stream(user_id=user.id, message=MESSAGE, user_auth_token="owner-token")]
    assert len(calls) == 1 and calls[0][1]["operation"] == "update"
    assert calls[0][1]["record_id"] == 101 and calls[0][1]["data"]["calories"] == 300
    assert all(args.get("record_id") != 999 for _, args in calls)
    assert events[-1]["data"].get("write_receipts")
    assert events[-1]["data"]["completion_status"] == "complete"


@pytest.mark.asyncio
async def test_real_lookup_and_update_preserve_owner_identity_and_record_count(db, client, auth_user_and_headers):
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("owner/date/update semantics require PostgreSQL")
    user, headers = auth_user_and_headers
    other = User(name="Other synthetic user", email="meal-other@example.invalid")
    db.add(other)
    db.flush()
    first = DietRecord(user_id=user.id, record_date=NOW.date(), meal_type="breakfast",
        food_items="测试早餐", calories=400, created_at=NOW.replace(hour=8))
    target = DietRecord(user_id=user.id, record_date=NOW.date(), meal_type="lunch",
        food_items="测试午餐", calories=900, protein=60, carbs=90, fat=30, fiber=9,
        created_at=NOW.replace(hour=12))
    foreign = DietRecord(user_id=other.id, record_date=NOW.date(), meal_type="dinner",
        food_items="另一账号的合成餐", calories=1200, created_at=NOW.replace(hour=18))
    db.add_all([first, target, foreign])
    db.commit()
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    executor._current_turn_user_message = MESSAGE
    executor._agent_kernel_reference_now = lambda: NOW

    async def get_json(url, request_headers):
        parsed = urlsplit(url)
        response = client.get(parsed.path + "?" + parsed.query, headers=request_headers)
        return (response.json(), None) if response.status_code == 200 else (None, "lookup failed")

    async def put(url, request_headers, data):
        response = client.put(urlsplit(url).path, headers=request_headers, json=data)
        assert response.status_code == 200, response.text
        return response.text

    executor._api_get_json = get_json
    executor._api_put = put
    executor._invalidate_twin_after_mutation = lambda: None
    token = headers["Authorization"].split(" ", 1)[1]
    for _ in range(2):
        calls = await executor._normalize_explicit_diet_update_tool_calls([tool_call()], token)
        args = json.loads(calls[0]["function"]["arguments"])
        assert args["record_id"] == target.id
        await executor._exec_health_manage("http://testserver/api/v1", headers, args)
        db.expire_all()
        assert db.get(DietRecord, target.id).calories == 300
    assert db.query(DietRecord).count() == 3
    assert db.get(DietRecord, foreign.id).calories == 1200
    assert db.get(DietRecord, first.id).calories == 400
    assert client.put(f"/api/v1/diet/records/{foreign.id}", headers=headers, json={"calories": 1}).status_code == 403
