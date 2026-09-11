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
