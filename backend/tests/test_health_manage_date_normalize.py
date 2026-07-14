"""health_manage 的 date 参数归一化 — 修「修改早餐」传字面 'today' → 422 的 bug。

founder 实测: health_manage(record_type='diet', operation='list', date='today') → 端点
把 'today' 当 start_date 解析 → 422 date_from_datetime_parsing → 修改失败。
"""
from datetime import date, datetime, timedelta, timezone
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.agent_executor import (
    AgentExecutor,
    _is_explicit_latest_diet_delete,
    _normalize_relative_date,
)

BJ = timezone(timedelta(hours=8))


def test_today_resolves_to_iso_date():
    today = datetime.now(BJ).date()
    assert _normalize_relative_date("today") == today.isoformat()
    assert _normalize_relative_date("今天") == today.isoformat()
    assert _normalize_relative_date("今日") == today.isoformat()


def test_relative_words():
    today = datetime.now(BJ).date()
    assert _normalize_relative_date("昨天") == (today - timedelta(days=1)).isoformat()
    assert _normalize_relative_date("yesterday") == (today - timedelta(days=1)).isoformat()
    assert _normalize_relative_date("前天") == (today - timedelta(days=2)).isoformat()
    assert _normalize_relative_date("明天") == (today + timedelta(days=1)).isoformat()


def test_iso_date_passthrough():
    assert _normalize_relative_date("2026-07-13") == "2026-07-13"
    # 带时间的 ISO → 取日期部分
    assert _normalize_relative_date("2026-07-13T10:30:00") == "2026-07-13"


def test_date_and_datetime_objects():
    assert _normalize_relative_date(date(2026, 7, 13)) == "2026-07-13"
    assert _normalize_relative_date(datetime(2026, 7, 13, 8, 0)) == "2026-07-13"


def test_unparseable_returns_none_not_garbage():
    # 解析不出 → None (调用方不带日期过滤, 列近期; 绝不把垃圾当 start_date 发 → 避免 422)
    assert _normalize_relative_date("someday") is None
    assert _normalize_relative_date("") is None
    assert _normalize_relative_date(None) is None
    assert _normalize_relative_date("2026-13-99") is None  # 非法日期


@pytest.mark.asyncio
async def test_latest_meal_is_resolved_before_the_write_state_machine():
    executor = AgentExecutor(MagicMock())
    executor._current_turn_user_message = "删除最后一餐，重复记录了"
    executor._api_get_json = AsyncMock(return_value=([
        {"id": 805, "meal_type": "dinner"},
        {"id": 804, "meal_type": "dinner"},
    ], None))

    calls = await executor._normalize_latest_diet_delete_tool_calls([{
        "id": "call-1",
        "type": "function",
        "function": {
            "name": "health_manage",
            "arguments": json.dumps({"record_type": "diet", "operation": "delete"}),
        },
    }], "test-token")

    args = json.loads(calls[0]["function"]["arguments"])
    assert args == {"record_type": "diet", "operation": "delete", "record_id": 805}
    executor._api_get_json.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_without_record_id_stays_fail_closed_when_latest_is_not_explicit():
    executor = AgentExecutor(MagicMock())
    executor._current_turn_user_message = "删除一条饮食记录"
    executor._api_get = AsyncMock()
    executor._api_delete = AsyncMock()

    result = await executor._exec_health_manage(
        "https://example.test/api/v1",
        {},
        {"record_type": "diet", "operation": "delete"},
    )

    assert result.startswith("Error:")
    executor._api_get.assert_not_awaited()
    executor._api_delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_call_never_implicitly_deletes_even_with_latest_delete_intent():
    executor = AgentExecutor(MagicMock())
    executor._current_turn_user_message = "删除最新一餐，刚才重复记了"
    executor._api_get = AsyncMock(return_value=json.dumps([{"id": 902}]))
    executor._api_delete = AsyncMock()

    result = await executor._exec_health_manage(
        "https://example.test/api/v1",
        {},
        {"record_type": "diet", "operation": "list", "limit": 2},
    )

    assert json.loads(result) == [{"id": 902}]
    executor._api_delete.assert_not_awaited()


@pytest.mark.parametrize("message", [
    "不要删除最后一餐",
    "先别删掉最新一餐",
    "如何删除最后一餐？",
    "是否删除最后一餐？",
])
def test_latest_delete_intent_rejects_negation_and_how_to_questions(message):
    assert _is_explicit_latest_diet_delete(message) is False
