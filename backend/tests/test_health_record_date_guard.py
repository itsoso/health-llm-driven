"""LLM 日期幻觉守门 — 防止 GPT-4o-mini 把今天的记录写到 2023/2024.

走真实链路 _execute_tool (prelude 里的 validate_tool_call 会先 coerce 日期),
而不是直接打 _exec_health_record, 以免绕过守门.
"""
import json
from datetime import datetime, date, timedelta
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def _declare_explicit_turn_for_raw_date_guard_contracts(monkeypatch):
    from app.services.agent_executor import AgentExecutor

    original = AgentExecutor._execute_tool

    async def with_explicit_test_turn(self, tool_name, args_raw, user_token):
        self._current_user_id = self._current_user_id or 1
        if not getattr(self, "_current_turn_user_message", ""):
            self._current_turn_user_message = "记录测试饮食"
        return await original(self, tool_name, args_raw, user_token)

    monkeypatch.setattr(AgentExecutor, "_execute_tool", with_explicit_test_turn)


@pytest.mark.asyncio
async def test_overrides_record_date_when_far_past(db):
    """LLM 给 record_date=2023-10-09, 应覆盖为今天."""
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 1

    captured_data = {}
    async def fake_post(url, headers, payload):
        captured_data.update(payload)
        return '{"id": 1, "ok": true}'

    with patch.object(executor, '_api_post', new=AsyncMock(side_effect=fake_post)):
        await executor._execute_tool(
            tool_name="health_record",
            args_raw=json.dumps({
                "record_type": "diet",
                "data": {
                    "meal_type": "dinner",
                    "food_items": "半份牛肉面",
                    "calories": 350,
                    "record_date": "2023-10-09",  # LLM 幻觉
                },
            }),
            user_token=None,
        )

    expected_today = date.today()
    actual_dates = {(expected_today - timedelta(days=1)).isoformat(),
                    expected_today.isoformat(),
                    (expected_today + timedelta(days=1)).isoformat()}
    assert captured_data.get("record_date") in actual_dates, \
        f"应覆盖为今天附近, 实际 {captured_data.get('record_date')}"
    assert "2023" not in captured_data.get("record_date", "")


@pytest.mark.asyncio
async def test_keeps_recent_date(db):
    """LLM 给 record_date=昨天, 在 7 天容忍内, 不覆盖."""
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 1

    yesterday = (date.today() - timedelta(days=1)).isoformat()
    captured = {}
    async def fake_post(url, headers, payload):
        captured.update(payload)
        return '{"id": 1}'

    with patch.object(executor, '_api_post', new=AsyncMock(side_effect=fake_post)):
        await executor._execute_tool(
            tool_name="health_record",
            args_raw=json.dumps({
                "record_type": "diet",
                "data": {
                    "meal_type": "lunch", "food_items": "三明治",
                    "record_date": yesterday,
                },
            }),
            user_token=None,
        )

    assert captured.get("record_date") == yesterday


@pytest.mark.asyncio
async def test_overrides_invalid_format(db):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 1

    captured = {}
    async def fake_post(url, headers, payload):
        captured.update(payload)
        return '{"id": 1}'

    with patch.object(executor, '_api_post', new=AsyncMock(side_effect=fake_post)):
        await executor._execute_tool(
            tool_name="health_record",
            args_raw=json.dumps({
                "record_type": "diet",
                "data": {
                    "meal_type": "lunch", "food_items": "三明治",
                    "record_date": "Tuesday",  # 不合法
                },
            }),
            user_token=None,
        )

    # 应该被改成有效的 YYYY-MM-DD
    assert captured.get("record_date") and "-" in captured["record_date"]
    assert captured["record_date"] != "Tuesday"
