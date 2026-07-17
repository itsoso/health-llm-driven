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
    _ground_query_response_date_labels,
    _is_explicit_latest_diet_delete,
    _model_tool_result_content,
    _parse_explicit_diet_correction,
    _normalize_relative_date,
    _tool_call_is_read_only,
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


@pytest.mark.parametrize(
    ("message", "meal_type", "food_items"),
    [
        ("修改早餐：一碗小米粥 一个蔬菜饼", "breakfast", "一碗小米粥 一个蔬菜饼"),
        ("午餐改成 牛肉面一碗", "lunch", "牛肉面一碗"),
        ("把昨天晚餐修改为清蒸鱼和米饭", "dinner", "清蒸鱼和米饭"),
        ("把早餐从西米露改成小米粥", "breakfast", "小米粥"),
    ],
)
def test_parse_explicit_diet_correction(message, meal_type, food_items):
    parsed = _parse_explicit_diet_correction(message)

    assert parsed is not None
    assert parsed["meal_type"] == meal_type
    assert parsed["food_items"] == food_items


@pytest.mark.parametrize(
    "message",
    [
        "怎么修改早餐？",
        "先别修改早餐：一碗粥",
        "早餐吃了一碗粥",
        "修改一下饮食",
        "修改早餐热量为400卡",
        "把早餐时间调整为8点",
    ],
)
def test_diet_correction_requires_unambiguous_write_intent(message):
    assert _parse_explicit_diet_correction(message) is None


@pytest.mark.asyncio
async def test_explicit_diet_correction_resolves_list_to_one_verified_update():
    executor = AgentExecutor(MagicMock())
    executor._current_turn_user_message = "修改早餐：一碗小米粥 一个蔬菜饼"
    executor._api_get_json = AsyncMock(return_value=([{
        "id": 821,
        "meal_type": "breakfast",
        "food_items": "西米露 约1碗 + 炒饭 约1份",
    }], None))

    calls = await executor._normalize_explicit_diet_update_tool_calls([{
        "id": "call-1",
        "type": "function",
        "function": {
            "name": "health_manage",
            "arguments": json.dumps({
                "record_type": "diet",
                "operation": "list",
                "date": "2026-07-10",
                "meal_type": "breakfast",
            }),
        },
    }], "test-token")

    args = json.loads(calls[0]["function"]["arguments"])
    assert args == {
        "record_type": "diet",
        "operation": "update",
        "record_id": 821,
        "data": {
            "meal_type": "breakfast",
            "food_items": "一碗小米粥 一个蔬菜饼",
        },
    }
    request_url = executor._api_get_json.await_args.args[0]
    assert f"start_date={datetime.now(BJ).date().isoformat()}" in request_url
    assert "2026-07-10" not in request_url


@pytest.mark.asyncio
async def test_explicit_diet_correction_stays_read_only_when_target_is_ambiguous():
    executor = AgentExecutor(MagicMock())
    executor._current_turn_user_message = "修改早餐：一碗小米粥 一个蔬菜饼"
    executor._api_get_json = AsyncMock(return_value=([
        {"id": 821, "meal_type": "breakfast"},
        {"id": 820, "meal_type": "breakfast"},
    ], None))
    original_args = {
        "record_type": "diet",
        "operation": "list",
        "date": "today",
        "meal_type": "breakfast",
    }

    calls = await executor._normalize_explicit_diet_update_tool_calls([{
        "id": "call-1",
        "type": "function",
        "function": {
            "name": "health_manage",
            "arguments": json.dumps(original_args),
        },
    }], "test-token")

    assert json.loads(calls[0]["function"]["arguments"]) == {
        "record_type": "diet",
        "operation": "list",
        "date": datetime.now(BJ).date().isoformat(),
        "meal_type": "breakfast",
        "limit": 20,
    }


@pytest.mark.asyncio
async def test_explicit_diet_correction_never_creates_a_duplicate_record():
    executor = AgentExecutor(MagicMock())
    executor._current_turn_user_message = "修改早餐：一碗小米粥 一个蔬菜饼"
    executor._api_get_json = AsyncMock(return_value=([{"id": 821}], None))

    calls = await executor._normalize_explicit_diet_update_tool_calls([{
        "id": "call-1",
        "type": "function",
        "function": {
            "name": "health_record",
            "arguments": json.dumps({
                "record_type": "diet",
                "data": {
                    "meal_type": "breakfast",
                    "food_items": "一碗小米粥 一个蔬菜饼",
                },
            }),
        },
    }], "test-token")

    assert calls[0]["function"]["name"] == "health_manage"
    args = json.loads(calls[0]["function"]["arguments"])
    assert args["operation"] == "update"
    assert args["record_id"] == 821


def test_health_manage_list_is_read_only_but_update_is_not():
    assert _tool_call_is_read_only("health_manage", {
        "record_type": "diet",
        "operation": "list",
    }) is True
    assert _tool_call_is_read_only("health_manage", {
        "record_type": "diet",
        "operation": "update",
    }) is False


def test_query_only_diet_turn_downgrades_model_update_to_beijing_today_list():
    executor = AgentExecutor(MagicMock())
    executor._current_turn_user_message = "晚餐是昨天的晚餐，按北京时间重新列出今天吃的东西"

    calls = executor._normalize_query_only_health_manage_tool_calls([{
        "id": "call-1",
        "type": "function",
        "function": {
            "name": "health_manage",
            "arguments": json.dumps({
                "id": "825",
                "record_type": "diet",
                "operation": "update",
                "data": {"record_date": "2026-07-15"},
            }),
        },
    }])

    args = json.loads(calls[0]["function"]["arguments"])
    assert args == {
        "record_type": "diet",
        "operation": "list",
        "date": datetime.now(BJ).date().isoformat(),
    }


def test_query_only_diet_turn_overrides_stale_model_date_with_beijing_today():
    executor = AgentExecutor(MagicMock())
    executor._current_turn_user_message = "列出我今天的饮食，按照北京时间"

    calls = executor._normalize_query_only_health_manage_tool_calls([{
        "id": "call-1",
        "type": "function",
        "function": {
            "name": "health_manage",
            "arguments": json.dumps({
                "record_type": "diet",
                "operation": "list",
                "date": "2026-07-14",
                "limit": 20,
            }),
        },
    }])

    args = json.loads(calls[0]["function"]["arguments"])
    assert args == {
        "record_type": "diet",
        "operation": "list",
        "date": datetime.now(BJ).date().isoformat(),
        "limit": 20,
    }


def test_explicit_diet_update_is_not_downgraded_by_query_only_guard():
    executor = AgentExecutor(MagicMock())
    executor._current_turn_user_message = "把晚餐改到昨天，再列出今天吃的东西"
    original = [{
        "id": "call-1",
        "type": "function",
        "function": {
            "name": "health_manage",
            "arguments": json.dumps({
                "record_type": "diet",
                "operation": "update",
                "record_id": 825,
                "data": {"record_date": "2026-07-15"},
            }),
        },
    }]

    assert executor._normalize_query_only_health_manage_tool_calls(original) is original


def test_diet_record_used_as_query_noun_still_uses_beijing_today():
    executor = AgentExecutor(MagicMock())
    executor._current_turn_user_message = "查询我今天的饮食记录"

    calls = executor._normalize_query_only_health_manage_tool_calls([{
        "id": "call-1",
        "type": "function",
        "function": {
            "name": "health_manage",
            "arguments": json.dumps({
                "record_type": "diet",
                "operation": "list",
                "date": "2026-07-14",
            }),
        },
    }])

    assert json.loads(calls[0]["function"]["arguments"])["date"] == (
        datetime.now(BJ).date().isoformat()
    )


def test_diet_query_tool_result_tells_synthesis_exact_beijing_date():
    today = datetime.now(BJ).date().isoformat()

    content = _model_tool_result_content(
        "health_manage",
        {"record_type": "diet", "operation": "list", "date": today},
        '[{"id": 1, "record_date": "' + today + '"}]',
    )

    assert f"查询日期: {today}" in content
    assert "时区: Asia/Shanghai" in content
    assert content.endswith('}]')


def test_reminder_tool_result_tells_synthesis_not_to_claim_watch_delivery():
    content = _model_tool_result_content(
        "health_record",
        {"record_type": "reminder"},
        json.dumps({
            "id": 7,
            "title": "喝水提醒",
            "recurrence": "daily",
            "delivery_status": {
                "agent_claim": "created_not_device_delivered",
                "iphone_notification": {"status": "will_attempt_when_due"},
                "watch": {
                    "route": "watch_summary_due_item",
                    "delivery_confirmed": False,
                },
            },
        }, ensure_ascii=False),
    )

    assert "不得说已发送到手表" in content
    assert "手表刷新今日摘要后可执行" in content
    assert "created_not_device_delivered" in content


def test_stale_beijing_date_in_query_response_is_grounded_before_streaming():
    today = datetime.now(BJ).date()
    stale_day = 14 if today.day != 14 else 13
    text = f"# 今日饮食汇总（北京时间 7月{stale_day}日）\n\n早餐……"

    grounded = _ground_query_response_date_labels(
        text,
        "列出我今天的饮食，按照北京时间",
    )

    assert f"北京时间 {today.month}月{today.day}日" in grounded
    assert f"北京时间 7月{stale_day}日" not in grounded


def test_explicit_diet_update_response_date_is_not_rewritten():
    original = "已把 7月14日 的晚餐改到北京时间 7月15日"

    assert _ground_query_response_date_labels(
        original,
        "把晚餐改到昨天，再列出今天吃的东西",
    ) == original


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
