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
    _build_deterministic_diet_correction_tool_call,
    _build_deterministic_goal_lookup_tool_call,
    _build_goal_verification_tool_call,
    _ground_query_response_date_labels,
    _goal_target_record_ids,
    _goal_lookup_resolution_prompt,
    _is_explicit_latest_diet_delete,
    _model_tool_result_content,
    _parse_explicit_diet_correction,
    _normalize_relative_date,
    _normalize_goal_guarded_tool_calls,
    _tool_call_is_read_only,
)
from app.services.agent_kernel.types import GoalSpec
from app.services.internal_diet_correction import (
    INTERNAL_DIET_PORTION_SIGNATURE_HEADER,
    verify_internal_diet_portion_signature,
)

BJ = timezone(timedelta(hours=8))


def _diet_recalculate_goal() -> GoalSpec:
    return GoalSpec(
        kind="diet_recalculate_update",
        domain="diet",
        operation="update",
        target_date="2026-07-24",
        target_meal_types=("breakfast", "lunch"),
        reference_foods=(
            ("breakfast", "豆腐脑约1碗 + 小笼包1个"),
            ("lunch", "三文鱼约1块 + 藜麦约半碗"),
        ),
        requires_lookup=True,
        requires_verification=True,
        prohibited_operations=("create", "delete"),
        postconditions=("existing_records_only", "read_back_verified"),
    )


def test_recalculate_goal_starts_with_one_deterministic_database_lookup():
    call = _build_deterministic_goal_lookup_tool_call(
        _diet_recalculate_goal(),
        write_receipts=[],
    )

    assert call is not None
    assert call["function"]["name"] == "health_manage"
    assert json.loads(call["function"]["arguments"]) == {
        "record_type": "diet",
        "operation": "list",
        "date": "2026-07-24",
        "limit": 20,
    }


def test_recalculate_goal_never_allows_model_to_create_duplicate_diet_record():
    call = {
        "id": "unsafe-create",
        "type": "function",
        "function": {
            "name": "health_record",
            "arguments": json.dumps({
                "record_type": "diet",
                "data": {
                    "meal_type": "breakfast",
                    "food_items": "豆腐脑约1碗 + 小笼包1个",
                },
            }),
        },
    }

    normalized = _normalize_goal_guarded_tool_calls(
        [call],
        _diet_recalculate_goal(),
    )

    assert normalized[0]["function"]["name"] == "health_manage"
    assert json.loads(normalized[0]["function"]["arguments"]) == {
        "record_type": "diet",
        "operation": "list",
        "date": "2026-07-24",
        "limit": 20,
    }


def test_recalculate_goal_never_allows_model_to_delete_existing_diet_record():
    call = {
        "id": "unsafe-delete",
        "type": "function",
        "function": {
            "name": "health_manage",
            "arguments": json.dumps({
                "record_type": "diet",
                "operation": "delete",
                "record_id": 101,
            }),
        },
    }

    normalized = _normalize_goal_guarded_tool_calls(
        [call],
        _diet_recalculate_goal(),
        lookup_completed=True,
        allowed_record_ids={"101", "102"},
    )

    assert normalized == []


def test_recalculate_goal_only_updates_ids_resolved_from_target_meals():
    wrong_record = {
        "id": "wrong-record",
        "type": "function",
        "function": {
            "name": "health_manage",
            "arguments": json.dumps({
                "record_type": "diet",
                "operation": "update",
                "record_id": 303,
                "data": {"meal_type": "breakfast", "calories": 410},
            }),
        },
    }

    normalized = _normalize_goal_guarded_tool_calls(
        [wrong_record],
        _diet_recalculate_goal(),
        lookup_completed=True,
        allowed_record_ids={"101", "102"},
    )

    assert normalized[0]["function"]["name"] == "health_manage"
    assert json.loads(normalized[0]["function"]["arguments"])["operation"] == "list"


def test_recalculate_goal_allows_only_a_resolved_target_record_update():
    target_record = {
        "id": "target-record",
        "type": "function",
        "function": {
            "name": "health_manage",
            "arguments": json.dumps({
                "record_type": "diet",
                "operation": "update",
                "record_id": 101,
                "data": {"meal_type": "breakfast", "calories": 410},
            }),
        },
    }

    normalized = _normalize_goal_guarded_tool_calls(
        [target_record],
        _diet_recalculate_goal(),
        lookup_completed=True,
        allowed_record_ids={"101", "102"},
    )

    assert normalized == [target_record]


def test_recalculate_goal_resolves_ids_only_when_every_target_meal_is_unique():
    result = json.dumps([
        {"id": 101, "meal_type": "breakfast"},
        {"id": 102, "meal_type": "lunch"},
        {"id": 103, "meal_type": "dinner"},
    ])

    assert _goal_target_record_ids(_diet_recalculate_goal(), result) == {"101", "102"}


def test_recalculate_goal_rejects_the_whole_batch_when_a_target_is_ambiguous():
    result = json.dumps([
        {"id": 101, "meal_type": "breakfast"},
        {"id": 111, "meal_type": "breakfast"},
        {"id": 102, "meal_type": "lunch"},
    ])

    assert _goal_target_record_ids(_diet_recalculate_goal(), result) == set()


def test_recalculate_goal_rejects_the_whole_batch_when_a_target_is_missing():
    result = json.dumps([
        {"id": 101, "meal_type": "breakfast"},
        {"id": 103, "meal_type": "dinner"},
    ])

    assert _goal_target_record_ids(_diet_recalculate_goal(), result) == set()


def test_recalculate_goal_explains_ambiguous_targets_without_allowing_a_write():
    result = json.dumps([
        {"id": 101, "meal_type": "breakfast"},
        {"id": 111, "meal_type": "breakfast"},
        {"id": 102, "meal_type": "lunch"},
    ])

    prompt = _goal_lookup_resolution_prompt(_diet_recalculate_goal(), result)

    assert "存在多条早餐" in prompt
    assert "禁止继续写入或宣称完成" in prompt
    assert "午餐" not in prompt


def test_recalculate_goal_explains_missing_targets_without_generic_failure():
    result = json.dumps([
        {"id": 101, "meal_type": "breakfast"},
    ])

    prompt = _goal_lookup_resolution_prompt(_diet_recalculate_goal(), result)

    assert "未找到午餐" in prompt
    assert "请用户选择或补充" in prompt


def test_recalculate_goal_adds_no_resolution_prompt_for_unique_targets():
    result = json.dumps([
        {"id": 101, "meal_type": "breakfast"},
        {"id": 102, "meal_type": "lunch"},
    ])

    assert _goal_lookup_resolution_prompt(_diet_recalculate_goal(), result) == ""


def test_recalculate_goal_does_not_mislabel_a_tool_error_as_missing_records():
    assert _goal_lookup_resolution_prompt(
        _diet_recalculate_goal(),
        "Error: database unavailable",
    ) == ""


def test_recalculate_goal_reads_back_after_all_target_updates_have_receipts():
    goal = _diet_recalculate_goal()
    call = _build_goal_verification_tool_call(
        goal,
        write_receipts=[
            {"resource_type": "diet", "resource_id": 101},
            {"resource_type": "diet", "resource_id": 102},
        ],
        already_attempted=False,
    )

    assert call is not None
    assert json.loads(call["function"]["arguments"]) == {
        "record_type": "diet",
        "operation": "list",
        "date": "2026-07-24",
        "limit": 20,
    }
    assert _build_goal_verification_tool_call(
        goal,
        write_receipts=[{"resource_type": "diet", "resource_id": 101}],
        already_attempted=False,
    ) is None


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


@pytest.mark.parametrize(
    ("message", "meal_type", "consumed_fraction"),
    [
        (
            "今天我没吃那么多，晚餐的两千大卡只有吃了四分之一",
            "dinner",
            0.25,
        ),
        ("晚饭实际只吃了一半，帮我按实际摄入修正", "dinner", 0.5),
        ("午餐没有全吃完，只吃了三分之一", "lunch", 1 / 3),
    ],
)
def test_parse_partial_meal_correction(message, meal_type, consumed_fraction):
    parsed = _parse_explicit_diet_correction(message)

    assert parsed is not None
    assert parsed["meal_type"] == meal_type
    assert parsed["consumed_fraction"] == pytest.approx(consumed_fraction)
    assert "food_items" not in parsed


@pytest.mark.parametrize(
    ("message", "label"),
    [
        ("晚餐只吃了 1/2 修改记录", "1/2"),
        ("晚餐只吃了 1 / 2，按实际摄入修正", "1/2"),
        ("晚餐只吃了 1／2 修改记录", "1/2"),
    ],
)
def test_parse_numeric_partial_meal_correction(message, label):
    parsed = _parse_explicit_diet_correction(message)

    assert parsed is not None
    assert parsed["meal_type"] == "dinner"
    assert parsed["consumed_fraction"] == pytest.approx(0.5)
    assert parsed["consumed_fraction_label"] == label
    assert "food_items" not in parsed


@pytest.mark.parametrize(
    "message",
    [
        "晚餐只吃了 0/2 修改记录",
        "晚餐只吃了 2/1 修改记录",
        "晚餐只吃了 1/0 修改记录",
        "晚餐只吃了 -1/2 修改记录",
        "晚餐只吃了 1/-2 修改记录",
        "晚餐只吃了 1//2 修改记录",
        "晚餐只吃了 1.5/2 修改记录",
        "晚餐只吃了 1/2.5 修改记录",
        "晚餐只吃了 −1/2 修改记录",
        "晚餐只吃了 1/−2 修改记录",
    ],
)
def test_invalid_numeric_partial_meal_fraction_is_not_a_food_replacement(message):
    assert _parse_explicit_diet_correction(message) is None


def test_partial_meal_advice_question_is_not_parsed_as_a_correction():
    assert _parse_explicit_diet_correction("晚餐只吃四分之一会不会饿？") is None


def test_fraction_before_the_correction_clause_is_not_used_as_consumed_amount():
    assert _parse_explicit_diet_correction(
        "晚餐四分之一是肉，我没吃那么多，只吃了蔬菜"
    ) is None


def test_partial_meal_correction_builds_a_deterministic_lookup_tool_call():
    call = _build_deterministic_diet_correction_tool_call(
        "今天我没吃那么多，晚餐的两千大卡只有吃了四分之一",
        write_receipts=[],
    )

    assert call is not None
    assert call["function"]["name"] == "health_manage"
    assert json.loads(call["function"]["arguments"]) == {
        "record_type": "diet",
        "operation": "list",
        "date": datetime.now(BJ).date().isoformat(),
        "meal_type": "dinner",
        "limit": 20,
    }


def test_deterministic_partial_meal_lookup_is_not_repeated_after_a_write_receipt():
    assert _build_deterministic_diet_correction_tool_call(
        "晚饭实际只吃了一半，帮我按实际摄入修正",
        write_receipts=[{"operation_id": "existing"}],
    ) is None


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
async def test_partial_meal_correction_scales_the_unique_existing_record():
    executor = AgentExecutor(MagicMock())
    executor._current_turn_user_message = (
        "今天我没吃那么多，晚餐的两千大卡只有吃了四分之一"
    )
    executor._api_get_json = AsyncMock(return_value=([{
        "id": 829,
        "meal_type": "dinner",
        "food_items": "三文鱼 + 黎麦沙拉 + 羊乳酪",
        "calories": 2000,
        "protein": 80,
        "carbs": 120,
        "fat": 100,
        "fiber": 16,
        "alcohol_units": 2,
    }], None))

    calls = await executor._normalize_explicit_diet_update_tool_calls([{
        "id": "call-1",
        "type": "function",
        "function": {
            "name": "health_record",
            "arguments": json.dumps({
                "record_type": "diet",
                "data": {
                    "meal_type": "dinner",
                    "food_items": "晚餐只吃了四分之一",
                },
            }),
        },
    }], "test-token")

    assert calls[0]["function"]["name"] == "health_manage"
    assert json.loads(calls[0]["function"]["arguments"]) == {
        "record_type": "diet",
        "operation": "update",
        "record_id": 829,
        "data": {
            "meal_type": "dinner",
            "food_items": "三文鱼 + 黎麦沙拉 + 羊乳酪（按实际食用四分之一计）",
            "calories": 500.0,
            "protein": 20.0,
            "carbs": 30.0,
            "fat": 25.0,
            "fiber": 4.0,
            "alcohol_units": 0.5,
        },
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "expected_label", "expected_calories", "expected_protein"),
    [
        ("晚餐只吃了 1／2 修改记录", "1/2", 500.0, 50.0),
        ("晚餐只吃了 1/3 修改记录", "1/3", 1000 / 3, 100 / 3),
        ("晚餐只吃了 1/1 修改记录", "1/1", 1000.0, 100.0),
    ],
)
async def test_partial_meal_correction_replaces_the_previous_nutrition_fraction(
    message,
    expected_label,
    expected_calories,
    expected_protein,
):
    executor = AgentExecutor(MagicMock())
    executor._current_turn_user_message = message
    executor._api_get_json = AsyncMock(return_value=([{
        "id": 832,
        "meal_type": "dinner",
        "food_items": "牛肉面（按实际食用1/2计）",
        "calories": 500,
        "protein": 50,
    }], None))

    calls = await executor._normalize_explicit_diet_update_tool_calls([{
        "id": "call-1",
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
    }], "test-token")

    args = json.loads(calls[0]["function"]["arguments"])
    assert args["operation"] == "update"
    assert args["record_id"] == 832
    assert args["data"]["food_items"] == f"牛肉面（按实际食用{expected_label}计）"
    assert args["data"]["calories"] == pytest.approx(expected_calories)
    assert args["data"]["protein"] == pytest.approx(expected_protein)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    [
        "晚餐只吃了 −1/2 修改记录",
        "晚餐只吃了 1/−2 修改记录",
        "晚餐只吃了 1／／2 修改记录",
        "晚餐只吃了 50% 修改记录",
        "晚餐只吃了 50％ 修改记录",
        "晚餐只吃了 0.5 修改记录",
        "晚餐只吃了 ½ 修改记录",
        "晚餐只吃了 二分之一 修改记录",
        "晚餐只吃一半好吗",
        "晚餐是不是只吃一半",
        "晚餐不是只吃了1/2，修改记录",
        "晚餐不是只吃了1/2，是只吃了1/3，修改记录",
        "晚餐只吃了1/2还是1/3？",
        "晚餐只吃了1/2，实际是1/3，修改记录",
        "晚餐只吃了1/2，应该改成1/3，修改记录",
        "晚餐只吃了1/2么 修改记录",
        "晚餐只吃了1/2呢 修改记录",
        "晚餐没只吃1/2，修改记录",
        "晚餐未只吃1/2，修改记录",
        "晚餐并没有只吃1/2，修改记录",
        "晚餐1/3，本来只吃了1/2，修改记录",
        "晚餐只吃了1/2吗修改记录",
        "晚餐只吃了1/2这个说法不对，修改记录",
        "晚餐只吃了 1e-1 修改记录",
        "晚餐只吃了1/2吗帮我修改记录",
        "晚餐只吃了1/2，不要修改记录",
        "晚餐只吃了1/2，取消修改",
        "晚餐只吃了1/2，暂时别改",
    ],
)
async def test_unsafe_unsupported_or_invalid_fraction_cannot_reach_a_diet_write(message):
    executor = AgentExecutor(MagicMock())
    executor._current_turn_user_message = message
    executor._api_get_json = AsyncMock()

    with pytest.raises(RuntimeError, match="无法确认.*没有修改"):
        await executor._normalize_explicit_diet_update_tool_calls([{
            "id": "call-1",
            "type": "function",
            "function": {
                "name": "health_record",
                "arguments": json.dumps({
                    "record_type": "diet",
                    "data": {
                        "meal_type": "dinner",
                        "food_items": message,
                    },
                }),
            },
        }], "test-token")

    executor._api_get_json.assert_not_awaited()


@pytest.mark.asyncio
async def test_partial_meal_correction_preserves_food_without_inventing_nutrition():
    executor = AgentExecutor(MagicMock())
    executor._current_turn_user_message = "午餐没有全吃完，只吃了三分之一"
    executor._api_get_json = AsyncMock(return_value=([{
        "id": 830,
        "meal_type": "lunch",
        "food_items": "牛肉面",
    }], None))

    calls = await executor._normalize_explicit_diet_update_tool_calls([{
        "id": "call-1",
        "type": "function",
        "function": {
            "name": "health_manage",
            "arguments": json.dumps({
                "record_type": "diet",
                "operation": "list",
                "date": "today",
                "meal_type": "lunch",
            }),
        },
    }], "test-token")

    args = json.loads(calls[0]["function"]["arguments"])
    assert args == {
        "record_type": "diet",
        "operation": "update",
        "record_id": 830,
        "data": {
            "meal_type": "lunch",
            "food_items": "牛肉面（按实际食用三分之一计）",
        },
    }
    assert not any(
        field in args["data"]
        for field in ("calories", "protein", "carbs", "fat", "fiber")
    )


@pytest.mark.asyncio
async def test_partial_meal_correction_replaces_a_generated_portion_suffix():
    executor = AgentExecutor(MagicMock())
    executor._current_turn_user_message = "晚餐只吃了 1/2 修改记录"
    executor._api_get_json = AsyncMock(return_value=([{
        "id": 831,
        "meal_type": "dinner",
        "food_items": "牛肉面（按实际食用三分之一计）",
    }], None))

    calls = await executor._normalize_explicit_diet_update_tool_calls([{
        "id": "call-1",
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
    }], "test-token")

    args = json.loads(calls[0]["function"]["arguments"])
    assert args["operation"] == "update"
    assert args["record_id"] == 831
    assert args["data"] == {
        "meal_type": "dinner",
        "food_items": "牛肉面（按实际食用1/2计）",
    }


@pytest.mark.asyncio
async def test_deterministic_portion_execution_signs_the_exact_internal_update():
    executor = AgentExecutor(MagicMock())
    executor._current_user_id = 7
    executor._current_turn_user_message = "晚餐只吃了 1/1 修改记录"
    executor._api_get_json = AsyncMock(return_value=([{
        "id": 833,
        "meal_type": "dinner",
        "food_items": "牛肉面",
        "calories": 500,
        "fiber": 0,
    }], None))

    calls = await executor._normalize_explicit_diet_update_tool_calls([{
        "id": "call-1",
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
    }], "test-token")
    args = json.loads(calls[0]["function"]["arguments"])
    executor._api_put = AsyncMock(return_value=json.dumps({
        "id": 833,
        "meal_type": "dinner",
        "food_items": args["data"]["food_items"],
    }))
    executor._invalidate_twin_after_mutation = MagicMock()

    await executor._exec_health_manage(
        "http://internal.test/api/v1",
        {"Authorization": "Bearer test-token"},
        args,
    )

    put_headers = executor._api_put.await_args.args[1]
    signature = put_headers[INTERNAL_DIET_PORTION_SIGNATURE_HEADER]
    assert verify_internal_diet_portion_signature(
        signature,
        7,
        833,
        args["data"],
    )
    assert "source" not in args["data"]


@pytest.mark.asyncio
async def test_explicit_diet_correction_terminates_when_target_is_ambiguous():
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

    with pytest.raises(RuntimeError, match="找到多条.*暂时没有修改"):
        await executor._normalize_explicit_diet_update_tool_calls([{
            "id": "call-1",
            "type": "function",
            "function": {
                "name": "health_manage",
                "arguments": json.dumps(original_args),
            },
        }], "test-token")

    assert executor._turn_diet_correction_unresolved_reason == "ambiguous_target"


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


def test_query_only_diet_turn_downgrades_model_health_record_to_list():
    executor = AgentExecutor(MagicMock())
    executor._current_turn_user_message = "今天我的饮食的记录，帮我列个表格出来。"

    calls = executor._normalize_query_only_health_manage_tool_calls([{
        "id": "call-1",
        "type": "function",
        "function": {
            "name": "health_record",
            "arguments": json.dumps({
                "record_type": "reminder",
                "data": {
                    "title": "请记录今天的饮食",
                    "message": "包括早餐、午餐、晚餐和加餐",
                },
            }, ensure_ascii=False),
        },
    }])

    assert calls[0]["function"]["name"] == "health_manage"
    assert json.loads(calls[0]["function"]["arguments"]) == {
        "record_type": "diet",
        "operation": "list",
        "date": datetime.now(BJ).date().isoformat(),
    }


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

    rejection = json.loads(result)
    assert rejection == {
        "status": "rejected",
        "success": False,
        "dispatch_started": False,
        "error_code": "record_id_missing",
        "message": "修改或删除缺少记录 ID。",
        "recovery_guidance": "请先查询候选记录并确认要操作的记录。",
    }
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
