import json
from unittest.mock import AsyncMock

import pytest

from app.services.agent_executor import AgentExecutor


def _visible_text(events: list[dict]) -> str:
    return "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )


async def _run_unresolved_correction(
    db,
    user_id: int,
    *,
    lookup_rows,
    lookup_error: str | None = None,
):
    executor = AgentExecutor(db)
    executor._api_get_json = AsyncMock(
        return_value=(lookup_rows, lookup_error)
    )
    execute_tool = AsyncMock(return_value=json.dumps(lookup_rows, ensure_ascii=False))
    executor._execute_tool = execute_tool
    model_rounds: list[int] = []

    async def fake_call_llm_stream(messages, tools):
        model_rounds.append(len(model_rounds) + 1)
        if len(model_rounds) == 1:
            yield {
                "type": "tool_calls",
                "tool_calls": [{
                    "id": "diet-correction-list",
                    "type": "function",
                    "function": {
                        "name": "health_manage",
                        "arguments": json.dumps({
                            "record_type": "diet",
                            "operation": "list",
                            "date": "today",
                            "meal_type": "dinner",
                        }),
                    },
                }],
            }
            yield {"type": "finish", "finish_reason": "tool_calls"}
            return
        yield {"type": "content", "text": "不应进入第二轮模型。"}
        yield {"type": "finish", "finish_reason": "stop"}

    executor._call_llm_stream = fake_call_llm_stream
    events = [
        event
        async for event in executor.run_stream(
            user_id=user_id,
            message="晚餐只吃了 1/2 修改记录",
            user_auth_token="test-token",
        )
    ]
    return events, model_rounds, execute_tool


@pytest.mark.asyncio
async def test_ambiguous_diet_correction_stops_after_owner_scoped_lookup(
    db,
    auth_user_and_headers,
):
    user, _headers = auth_user_and_headers
    events, model_rounds, execute_tool = await _run_unresolved_correction(
        db,
        user.id,
        lookup_rows=[
            {"id": 821, "meal_type": "dinner", "food_items": "第一条"},
            {"id": 822, "meal_type": "dinner", "food_items": "第二条"},
        ],
    )

    text = _visible_text(events)
    assert len(model_rounds) == 1
    execute_tool.assert_not_awaited()
    assert "找到多条" in text
    assert "暂时没有修改" in text
    assert "不应进入第二轮模型" not in text
    assert events[-1]["event"] == "done"
    assert events[-1]["data"]["completion_status"] == "error"
    assert not events[-1]["data"].get("write_receipts")


@pytest.mark.asyncio
async def test_missing_diet_correction_target_stops_without_a_write_claim(
    db,
    auth_user_and_headers,
):
    user, _headers = auth_user_and_headers
    events, model_rounds, execute_tool = await _run_unresolved_correction(
        db,
        user.id,
        lookup_rows=[],
    )

    text = _visible_text(events)
    assert len(model_rounds) == 1
    execute_tool.assert_not_awaited()
    assert "没有找到" in text
    assert "没有修改" in text
    assert "已修改" not in text
    assert events[-1]["data"]["completion_status"] == "error"


@pytest.mark.asyncio
async def test_failed_diet_correction_lookup_stops_with_a_retryable_message(
    db,
    auth_user_and_headers,
):
    user, _headers = auth_user_and_headers
    events, model_rounds, execute_tool = await _run_unresolved_correction(
        db,
        user.id,
        lookup_rows=None,
        lookup_error="upstream unavailable",
    )

    text = _visible_text(events)
    assert len(model_rounds) == 1
    execute_tool.assert_not_awaited()
    assert "暂时无法核对" in text
    assert "稍后重试" in text
    assert "已修改" not in text
    assert events[-1]["data"]["completion_status"] == "error"
