"""LLM 日期幻觉守门 — 防止模型把今天的记录写到错误日期.

走真实链路 _execute_tool (prelude 里的 validate_tool_call 会校验日期),
而不是直接打 _exec_health_record, 以免绕过守门.
"""
import json
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def _declare_explicit_turn_for_raw_date_guard_contracts(monkeypatch):
    from app.services.agent_executor import AgentExecutor

    original = AgentExecutor._execute_tool

    async def with_explicit_test_turn(self, tool_name, args_raw, user_token):
        self._current_user_id = self._current_user_id or 1
        if not getattr(self, "_current_turn_user_message", ""):
            args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
            data = args.get("data") if isinstance(args.get("data"), dict) else {}
            record_date = str(data.get("record_date") or "")
            if len(record_date) == 10 and record_date[4] == "-":
                date_prefix = (
                    f"{record_date[:4]}年{int(record_date[5:7])}月"
                    f"{int(record_date[8:10])}日"
                )
            else:
                date_prefix = ""
            meal = {
                "breakfast": "早餐",
                "lunch": "午餐",
                "dinner": "晚餐",
                "snack": "加餐",
            }.get(str(data.get("meal_type") or ""), "这餐")
            self._current_turn_user_message = (
                f"记录{date_prefix}{meal}吃了{data.get('food_items') or ''}"
            )
        return await original(self, tool_name, args_raw, user_token)

    monkeypatch.setattr(AgentExecutor, "_execute_tool", with_explicit_test_turn)


@pytest.mark.asyncio
async def test_rejects_record_date_when_far_past(db):
    """LLM 给 record_date=2023-10-09, 应拒绝而不是静默改成今天."""
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 1

    captured_data = {}
    async def fake_post(url, headers, payload):
        captured_data.update(payload)
        return '{"id": 1, "ok": true}'

    with patch.object(executor, '_api_post', new=AsyncMock(side_effect=fake_post)):
        result = await executor._execute_tool(
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

    assert captured_data == {}
    assert "超出可直接记录的日期范围" in result


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
                    "meal_type": "lunch",
                    "food_items": "三明治",
                    "calories": 320,
                    "protein": 15,
                    "carbs": 38,
                    "fat": 12,
                    "fiber": 4,
                    "record_date": yesterday,
                },
            }),
            user_token=None,
        )

    assert captured.get("record_date") == yesterday


@pytest.mark.asyncio
async def test_rejects_invalid_format(db):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 1

    captured = {}
    async def fake_post(url, headers, payload):
        captured.update(payload)
        return '{"id": 1}'

    with patch.object(executor, '_api_post', new=AsyncMock(side_effect=fake_post)):
        result = await executor._execute_tool(
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

    assert captured == {}
    assert "不是合法日期" in result
