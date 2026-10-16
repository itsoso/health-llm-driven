"""Named-food followups must never halve unrelated foods in a saved meal."""

from dataclasses import replace
from unittest.mock import AsyncMock
import json
import pytest

from tests.test_diet_spoken_fraction_correction import (
    meal_receipt_context,
    model_call,
    NOW,
)
from app.services.agent_diet_continuation import (
    is_bare_portion_correction,
    load_diet_portion_reference,
)
from app.services.agent_executor import _SimpleRecordTerminal


def configure(db, context, message, foods):
    executor, user, conv, target, answer, current = context
    current.content = message
    target.food_items = foods
    db.flush()
    executor._current_turn_user_message = message
    executor._agent_kernel_snapshot = replace(
        executor._agent_kernel_snapshot,
        envelope=replace(executor._agent_kernel_snapshot.envelope, text=message),
    )
    executor._bind_read_task_reference(user.id, conv.id)
    executor._api_get_json = AsyncMock(
        return_value=(
            [
                {
                    "id": target.id,
                    "record_date": NOW.date().isoformat(),
                    "meal_type": "lunch",
                    "food_items": foods,
                    "calories": 900,
                    "protein": 30,
                    "carbs": 90,
                    "fat": 40,
                    "fiber": 8,
                }
            ],
            None,
        )
    )
    return executor


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message", ["水饺吃了一半", "饺子吃了一半", "我水饺只吃了一半。"]
)
async def test_named_dumpling_followup_updates_same_single_food_record(
    db, meal_receipt_context, message
):
    executor = configure(db, meal_receipt_context, message, "水饺 约1盘")
    calls = await executor._normalize_explicit_diet_update_tool_calls(
        [model_call()], "owner-token"
    )
    args = json.loads(calls[0]["function"]["arguments"])
    assert args["operation"] == "update"
    assert args["record_id"] == meal_receipt_context[3].id
    assert args["data"]["calories"] == 450
    assert args["data"]["fiber"] == 4
    assert "水饺" in args["data"]["food_items"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "foods",
    ["水饺 约1盘，米饭1碗", "煎饺 1盘", "水饺、蒸饺", "水饺或米饭", "水饺（含米饭）"],
)
async def test_mixed_or_different_food_requires_component_clarification(
    db, meal_receipt_context, foods
):
    executor = configure(db, meal_receipt_context, "水饺吃了一半", foods)
    with pytest.raises(_SimpleRecordTerminal, match="水饺|单项"):
        await executor._normalize_explicit_diet_update_tool_calls(
            [model_call()], "owner-token"
        )
    assert meal_receipt_context[3].calories == 900


@pytest.mark.parametrize(
    "message",
    [
        "他水饺吃了一半",
        "水饺没吃一半",
        "水饺吃了一半吗",
        "水饺可能吃了一半",
        "“水饺吃了一半”",
        "水饺吃了一半，米饭也一半",
        "水饺吃了一半，取消修改",
    ],
)
def test_named_food_closed_grammar_rejects_unsafe_utterances(message):
    assert not is_bare_portion_correction(message)


@pytest.mark.parametrize("damage", ["expired", "foreign_owner", "unfinalized"])
def test_named_followup_keeps_owned_fresh_finalized_receipt_gate(
    db, meal_receipt_context, damage
):
    from datetime import timedelta
    from app.models.user import User

    executor = configure(db, meal_receipt_context, "水饺吃了一半", "水饺1盘")
    _, user, conv, target, answer, _ = meal_receipt_context
    if damage == "expired":
        answer.meta = {
            **answer.meta,
            "write_receipts": [
                {
                    **answer.meta["write_receipts"][0],
                    "completed_at": (NOW - timedelta(days=2)).isoformat(),
                }
            ],
        }
    elif damage == "foreign_owner":
        other = User(name="Synthetic", email="named-portion@example.invalid")
        db.add(other)
        db.flush()
        target.user_id = other.id
    else:
        answer.meta = {**answer.meta, "client_turn_finalized": False}
    db.flush()
    assert (
        load_diet_portion_reference(
            db, user.id, conv.id, executor._agent_kernel_snapshot
        )
        is None
    )


@pytest.mark.asyncio
async def test_named_dumpling_postgres_owned_update_absolute_retry(
    db, client, auth_user_and_headers, meal_receipt_context
):
    from urllib.parse import urlsplit
    from app.models.daily_health import DietRecord
    from app.models.user import User

    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("write and CAS evidence require PostgreSQL")
    executor = configure(db, meal_receipt_context, "水饺吃了一半", "水饺1盘")
    user, headers = auth_user_and_headers
    target = meal_receipt_context[3]
    other = User(name="Synthetic other", email="other-dumpling@example.invalid")
    db.add(other)
    db.flush()
    foreign = DietRecord(
        user_id=other.id,
        record_date=NOW.date(),
        meal_type="lunch",
        food_items="水饺1盘",
        calories=1200,
    )
    db.add(foreign)
    db.commit()

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
        calls = await executor._normalize_explicit_diet_update_tool_calls(
            [model_call()], token
        )
        args = json.loads(calls[0]["function"]["arguments"])
        assert args["record_id"] == target.id
        await executor._exec_health_manage("http://testserver/api/v1", headers, args)
        db.expire_all()
        assert db.get(DietRecord, target.id).calories == 450
    assert db.query(DietRecord).count() == 2
    assert db.get(DietRecord, foreign.id).calories == 1200


@pytest.mark.asyncio
@pytest.mark.parametrize("message", ["水饺吃了一半", "饺子吃了一半"])
async def test_mixed_food_stream_persists_specific_clarification_without_write(
    db,
    meal_receipt_context,
    monkeypatch,
    isolated_agent_protocol_transport,
    message,
):
    from datetime import datetime, timedelta, timezone
    from app.models.agent_conversation import AgentMessage
    from app.twin.schema import HealthTwin, TwinMeta

    executor, user, conv, target, answer, current = meal_receipt_context
    now = datetime.now(timezone.utc)
    target.record_date = now.astimezone(NOW.tzinfo).date()
    target.food_items = "水饺1盘，米饭1碗"
    answer.created_at = (now - timedelta(minutes=1)).replace(tzinfo=None)
    answer.meta = {
        **answer.meta,
        "write_receipts": [
            {**answer.meta["write_receipts"][0], "completed_at": now.isoformat()}
        ],
    }
    db.delete(current)
    db.commit()
    monkeypatch.setattr(
        "app.twin.builder.build_twin",
        lambda _db, user_id, **kwargs: HealthTwin(
            meta=TwinMeta(user_id=user_id, generated_at=now)
        ),
    )
    monkeypatch.setattr(
        executor, "_build_system_prompt", lambda *a, **k: "Use authorized tools."
    )

    async def provider(messages, tools):
        yield {"type": "content", "text": "已按要求修正。"}
        yield {"type": "finish", "finish_reason": "stop"}

    executor._call_llm_stream = provider
    executor._api_get_json = AsyncMock(
        return_value=(
            [
                {
                    "id": target.id,
                    "record_date": target.record_date.isoformat(),
                    "meal_type": "lunch",
                    "food_items": target.food_items,
                    "calories": 900,
                }
            ],
            None,
        )
    )
    executor._dispatch_tool_request = AsyncMock()
    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message=message,
            conversation_id=conv.id,
            user_auth_token="test-token",
        )
    ]
    done = events[-1]["data"]
    reply = db.get(AgentMessage, done["message_id"]).content
    assert "不能把整餐热量减半" in reply
    assert "继续修正本餐" in reply
    assert "你可以重试" not in reply
    assert done["record_intent_no_tool"] is False
    assert not done["write_receipts"]
    executor._dispatch_tool_request.assert_not_awaited()
    db.refresh(target)
    assert target.calories == 900
    assert target.food_items == "水饺1盘，米饭1碗"
