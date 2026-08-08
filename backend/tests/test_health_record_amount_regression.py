"""Regression: symptom 记录不应触发 'amount' KeyError.

根因 (2026-05-11): _exec_health_record 里 record_map 是 dict 字面量, eager 求值.
即使 rtype='symptom' 后面有早返, dict 里 'amount': data['amount'] 也会先炸.
修法: 把 data['amount'] 改成 data.get('amount').
"""
import json
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest


def _semantic_health_record_turn(args_raw):
    """Describe the same target as the model payload for adapter-only tests."""
    if isinstance(args_raw, str):
        try:
            args = json.loads(args_raw)
        except json.JSONDecodeError:
            return "记录健康数据"
    else:
        args = dict(args_raw or {})
    data = args.get("data") if isinstance(args.get("data"), dict) else {}
    record_type = str(args.get("record_type") or "").strip().lower()
    record_date = str(data.get("record_date") or "")[:10]
    date_prefix = (
        f"{record_date[:4]}年{int(record_date[5:7])}月{int(record_date[8:10])}日"
        if len(record_date) == 10
        else ""
    )
    if record_type == "water":
        amount = data.get("amount") or data.get("amount_ml")
        return f"记录{date_prefix}喝水{amount}ml" if amount else "记录喝水"
    if record_type == "diet":
        meal = {
            "breakfast": "早餐",
            "lunch": "午餐",
            "dinner": "晚餐",
            "snack": "加餐",
        }.get(str(data.get("meal_type") or "").lower(), "这餐")
        food = str(data.get("food_items") or "").strip()
        return f"记录{date_prefix}{meal}吃了{food}" if food else f"记录{meal}"
    if record_type == "mood":
        mood = {"calm": "平静"}.get(str(data.get("mood") or ""), data.get("mood"))
        return f"记录心情{mood}" if mood else "记录心情"
    if record_type == "reminder":
        title = str(data.get("title") or "提醒事项")
        start = data.get("start_time")
        end = data.get("end_time")
        clock = data.get("time") or data.get("remind_at")
        if start and end:
            return f"设置每天{start}到{end}{title}提醒"
        return f"设置每天{clock}{title}提醒" if clock else f"设置{title}提醒"
    if record_type == "waist":
        return f"记录{date_prefix}腰围{data.get('waist_cm')}cm"
    if record_type == "sleep":
        bedtime = str(data.get("bedtime") or "")
        wake_time = str(data.get("wake_time") or "")
        if bedtime and wake_time:
            return (
                f"记录{date_prefix}{bedtime[11:16]}入睡"
                f"{wake_time[11:16]}起床睡眠质量{data.get('sleep_quality')}分"
            )
        return "记录睡眠"
    if record_type == "excretion":
        kind = {
            "bowel": "排便",
            "constipation": "便秘",
            "diarrhea": "腹泻",
        }.get(str(data.get("type") or ""), "排便")
        return f"记录{date_prefix}{kind}"
    if record_type == "illness":
        return f"记录{data.get('name') or data.get('illness_name') or '疾病'}"
    if record_type == "medication":
        name = data.get("medication_name") or data.get("name") or "药"
        dosage = data.get("actual_dosage") or data.get("dosage") or ""
        return f"记录我吃了{name}{dosage}"
    if record_type == "supplement":
        return f"记录{data.get('supplement_name') or data.get('name') or '补剂'}"
    return "记录健康数据"


@pytest.fixture(autouse=True)
def _declare_explicit_turn_for_raw_record_handler_contracts(monkeypatch):
    """These legacy handler tests exercise transport/normalization, not intent."""
    from app.services.agent_executor import AgentExecutor

    original = AgentExecutor._execute_tool

    async def with_explicit_test_turn(self, tool_name, args_raw, user_token):
        self._current_user_id = self._current_user_id or 1
        if not getattr(self, "_current_turn_user_message", ""):
            self._current_turn_user_message = _semantic_health_record_turn(args_raw)
        if getattr(self, "_diet_photo_auto_save", False):
            self._current_turn_has_attachment = True
        return await original(self, tool_name, args_raw, user_token)

    monkeypatch.setattr(AgentExecutor, "_execute_tool", with_explicit_test_turn)


def test_mobile_meal_photo_context_enables_auto_save_intent():
    from app.services.agent_executor import _is_diet_photo_auto_save_turn

    context = json.dumps({
        "source": "mobile_chat_meal_photo",
        "intent": "diet_photo_record",
    })
    assert _is_diet_photo_auto_save_turn(context, has_images=True) is True
    assert _is_diet_photo_auto_save_turn(context, has_images=False) is False


@pytest.mark.asyncio
async def test_initial_meal_photo_turn_writes_without_a_second_confirmation(db):
    """拍照记餐是用户明确动作：识别后直接写 DietRecord，不再卡在确认前置。"""
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._diet_photo_auto_save = True

    with patch.object(
        executor,
        "_api_post",
        new=AsyncMock(return_value=json.dumps({"id": 123, "meal_type": "lunch"})),
    ) as post:
        result = await executor._execute_tool(
            tool_name="health_record",
            args_raw=json.dumps({
                "record_type": "diet",
                "data": {
                    "meal_type": "lunch",
                    "food_items": "米饭 1 碗",
                    "calories": 250,
                    "protein": 6,
                    "carbs": 55,
                    "fat": 1,
                    "fiber": 1,
                },
            }),
            user_token=None,
        )

    assert "NEEDS_CONFIRMATION" not in str(result)
    post.assert_awaited_once()


@pytest.mark.asyncio
async def test_meal_photo_auto_save_failure_cannot_write_incomplete_fallback(db):
    """图片预写失败后，模型 fallback 仍必须提供完整营养，不能降级成空壳。"""
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = "记录这餐"
    executor._current_turn_has_attachment = True
    executor._diet_photo_auto_save = True
    executor._turn_contextual_diet_record_id = None

    with patch.object(executor, "_api_post", new=AsyncMock()) as post:
        result = await executor._execute_tool(
            tool_name="health_record",
            args_raw=json.dumps({
                "record_type": "diet",
                "data": {
                    "meal_type": "lunch",
                    "food_items": "米饭和鸡肉",
                    "source": "manual",
                },
            }),
            user_token=None,
        )

    payload = json.loads(result)
    assert payload["status"] == "rejected"
    assert payload["error_code"] == "diet_nutrition_incomplete"
    post.assert_not_awaited()


@pytest.mark.asyncio
async def test_meal_photo_auto_save_success_replays_before_nutrition_validation(db):
    """图片已经写入时，模型的冗余不完整调用应复用回执，不能误报校验失败。"""
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = "记录这餐"
    executor._current_turn_has_attachment = True
    executor._diet_photo_auto_save = True
    executor._turn_contextual_diet_record_id = 123
    replay = json.dumps({
        "id": 123,
        "record_id": 123,
        "resource_type": "diet_record",
        "operation_id": "contextual_meal_photo:123",
        "status": "recorded",
        "replayed": True,
    })

    with (
        patch.object(
            executor,
            "_contextual_diet_replay_result",
            return_value=replay,
        ) as replay_result,
        patch.object(executor, "_api_post", new=AsyncMock()) as post,
    ):
        result = await executor._execute_tool(
            tool_name="health_record",
            args_raw=json.dumps({
                "record_type": "diet",
                "data": {
                    "meal_type": "lunch",
                    "food_items": "米饭和鸡肉",
                    "source": "agent_text",
                },
            }),
            user_token=None,
        )

    assert json.loads(result)["record_id"] == 123
    replay_result.assert_called_once_with()
    post.assert_not_awaited()


@pytest.mark.asyncio
async def test_water_record_persists_exact_amount_with_verified_receipt(db):
    """The domain write must persist the exact amount and return its durable id."""
    from app.services.agent_executor import AgentExecutor
    from app.models.daily_health import WaterIntake

    executor = AgentExecutor(db)
    executor._current_user_id = 1

    result = await executor._execute_tool(
        tool_name="health_record",
        args_raw=json.dumps({
            "record_type": "water",
            "data": {"amount": 1000, "confirmed": True},
        }),
        user_token=None,
    )

    assert "Error" not in str(result)
    receipt = json.loads(result)
    record = db.query(WaterIntake).filter(WaterIntake.id == receipt["record_id"]).one()
    assert receipt["status"] == "verified"
    assert receipt["resource_type"] == "water_record"
    assert record.user_id == 1
    assert record.amount_ml == 1000


@pytest.mark.asyncio
async def test_water_record_persists_historical_date_with_verified_receipt(db):
    from app.services.agent_executor import (
        AgentExecutor,
        _write_receipt_from_tool_result,
    )
    from app.models.daily_health import WaterIntake

    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._agent_kernel_reference_now = lambda: datetime(
        2026,
        7,
        17,
        9,
        57,
        tzinfo=ZoneInfo("Asia/Shanghai"),
    )
    args = {
        "record_type": "water",
        "data": {
            "amount": 1200,
            "record_date": "2026-07-16",
            "confirmed": True,
        },
        "confirmed": True,
    }

    result = await executor._execute_tool(
        tool_name="health_record",
        args_raw=json.dumps(args),
        user_token=None,
    )

    payload = json.loads(result)
    record = db.query(WaterIntake).filter(WaterIntake.id == payload["record_id"]).one()
    receipt = _write_receipt_from_tool_result("health_record", args, result)
    assert record.record_date.isoformat() == "2026-07-16"
    assert payload["record_date"] == "2026-07-16"
    assert receipt is not None
    assert receipt["date"] == "2026-07-16"


@pytest.mark.asyncio
async def test_water_record_missing_amount_does_not_default_to_250(db):
    """Missing water amount must fail before API call instead of writing 250ml."""
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 1

    with patch.object(executor, "_api_post", new=AsyncMock()) as post:
        result = await executor._execute_tool(
            tool_name="health_record",
            args_raw=json.dumps({
                "record_type": "water",
                "data": {"confirmed": True},
            }),
            user_token=None,
        )

    rejection = json.loads(result)
    assert rejection["status"] == "rejected"
    assert rejection["dispatch_started"] is False
    assert rejection["error_code"] == "tool_validation_failed"
    assert "amount" in rejection["message"]
    post.assert_not_called()


@pytest.mark.asyncio
async def test_symptom_record_does_not_throw_on_missing_amount(db):
    """symptom 数据不带 amount, 应正常调 /symptoms 不抛 KeyError."""
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = "眼睛痒"

    captured = {}

    async def fake_post(url, headers, payload):
        captured["url"] = url
        captured["payload"] = payload
        return '{"id": 1, "ok": true}'

    with patch.object(executor, "_api_post", new=AsyncMock(side_effect=fake_post)):
        result = await executor._execute_tool(
            tool_name="health_record",
            args_raw=json.dumps({
                "record_type": "symptom",
                "data": {
                    "body_part": "eye",
                    "description": "眼睛痒",
                    "severity": 2,
                },
            }),
            user_token=None,
        )

    # 不应是 Error: amount 也不应是异常字符串
    assert "amount" not in str(result).lower() or "Error" not in str(result)
    assert "/symptoms" in captured.get("url", "")
    assert captured["payload"]["body_part"] == "eye"
    assert captured["payload"]["description"] == "眼睛痒"


def test_symptom_body_part_is_inferred_from_explicit_chinese_location():
    """腰疼等明确部位不能因弱模型漏传 body_part 而被误报成未写入。"""
    from app.services.agent_executor import _prepare_health_record_args_for_validation

    args = {
        "record_type": "symptom",
        "data": {"description": "还是有腰疼的症状"},
    }

    normalized = _prepare_health_record_args_for_validation("health_record", args)

    assert normalized["data"]["body_part"] == "musculoskeletal"


@pytest.mark.asyncio
async def test_symptom_with_explicit_location_reaches_api_without_body_part(db):
    """模型漏传 body_part 时，明确的中文部位仍应真正写入并拿到 API 回执。"""
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = "记录还是有腰疼的症状"
    captured = {}

    async def fake_post(url, headers, payload):
        captured["url"] = url
        captured["payload"] = payload
        return '{"id": 42, "body_part": "musculoskeletal", "description": "还是有腰疼的症状"}'

    with patch.object(executor, "_api_post", new=AsyncMock(side_effect=fake_post)):
        result = await executor._execute_tool(
            tool_name="health_record",
            args_raw=json.dumps({
                "record_type": "symptom",
                "data": {"description": "还是有腰疼的症状"},
            }),
            user_token=None,
        )

    assert "Error" not in str(result)
    assert captured["payload"]["body_part"] == "musculoskeletal"


@pytest.mark.asyncio
async def test_voice_symptom_recovers_truncated_tool_args_and_writes(db):
    """清晰语音症状陈述不应被模型多出的右大括号和内核歧义门一起吞掉。"""
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._turn_channel = "voice"
    executor._current_turn_user_message = "还是有腰疼的症状。"
    captured = {}

    async def fake_post(url, headers, payload):
        captured["url"] = url
        captured["payload"] = payload
        return '{"id": 43, "body_part": "musculoskeletal", "description": "还是有腰疼的症状"}'

    with patch.object(executor, "_api_post", new=AsyncMock(side_effect=fake_post)):
        result = await executor._execute_tool(
            tool_name="health_record",
            args_raw='{"record_type": "symptom"}}',
            user_token=None,
        )

    assert "Error" not in str(result)
    assert captured["url"].endswith("/symptoms")
    assert captured["payload"]["body_part"] == "musculoskeletal"
    assert captured["payload"]["description"] == "还是有腰疼的症状"


@pytest.mark.asyncio
async def test_mood_record_does_not_throw_on_missing_amount(db):
    """mood 走 record_map 路径, 数据不带 amount, 应正常发 /mood/records."""
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 1

    captured = {}

    async def fake_post(url, headers, payload):
        captured["url"] = url
        captured["payload"] = payload
        return '{"id": 1, "ok": true}'

    with patch.object(executor, "_api_post", new=AsyncMock(side_effect=fake_post)):
        await executor._execute_tool(
            tool_name="health_record",
            args_raw=json.dumps({
                "record_type": "mood",
                "data": {"mood": "calm", "note": "睡前"},
            }),
            user_token=None,
        )

    assert "/mood/records" in captured.get("url", "")
    assert captured["payload"]["mood"] == "calm"


@pytest.mark.asyncio
async def test_garmin_sync_does_not_throw_on_missing_amount(db):
    """garmin_sync 不带 data, record_map 仍 eager 构造 — 不能炸."""
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 1

    async def fake_post(url, headers, payload):
        return '{"ok": true}'

    with patch.object(executor, "_api_post", new=AsyncMock(side_effect=fake_post)):
        result = await executor._execute_tool(
            tool_name="health_record",
            args_raw=json.dumps({
                "record_type": "garmin_sync",
                "data": {},
            }),
            user_token=None,
        )

    assert "Error" not in str(result)


@pytest.mark.asyncio
async def test_reminder_record_normalizes_daily_time_without_extra_confirmation(db):
    """明确设置提醒 + 给出 10:30 时, Agent 应直接创建每日 SmartReminder payload."""
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 1

    captured = {}

    async def fake_post(url, headers, payload):
        captured["url"] = url
        captured["payload"] = payload
        return json.dumps({"id": 7, "title": payload["title"], "status": "pending"}, ensure_ascii=False)

    with patch.object(executor, "_api_post", new=AsyncMock(side_effect=fake_post)):
        result = await executor._execute_tool(
            tool_name="health_record",
            args_raw=json.dumps({
                "record_type": "reminder",
                "data": {
                    "title": "臀中肌训练",
                    "message": "蚌式开合、侧卧抬腿、臀桥",
                    "time": "10:30",
                    "recurrence": "daily",
                },
            }, ensure_ascii=False),
            user_token="test-token",
        )

    assert "[NEEDS_CONFIRMATION]" not in str(result)
    assert "Error" not in str(result)
    assert captured["url"].endswith("/reminders/me")
    assert captured["payload"]["title"] == "臀中肌训练"
    assert captured["payload"]["message"] == "蚌式开合、侧卧抬腿、臀桥"
    assert captured["payload"]["recurrence"] == "daily"


@pytest.mark.asyncio
async def test_reminder_record_routes_interval_window_as_one_atomic_write(db):
    """A follow-up time range must preserve the promised interval schedule."""
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 1
    captured = {}

    async def fake_post(url, headers, payload):
        captured["url"] = url
        captured["payload"] = payload
        return json.dumps({
            "id": 150,
            "record_ids": list(range(150, 158)),
            "resource_type": "smart_reminder",
            "status": "scheduled",
            "created_count": 8,
        })

    with patch.object(executor, "_api_post", new=AsyncMock(side_effect=fake_post)):
        result = await executor._execute_tool(
            tool_name="health_record",
            args_raw=json.dumps({
                "record_type": "reminder",
                "data": {
                    "title": "定时饮水提醒",
                    "message": "少量多次饮水",
                    "start_time": "9点",
                    "end_time": "20点",
                    "interval_hours": 1.5,
                    "recurrence": "daily",
                },
            }, ensure_ascii=False),
            user_token="test-token",
        )

    assert "Error" not in str(result)
    assert captured["url"].endswith("/reminders/me/window")
    assert captured["payload"]["start_time"] == "09:00"
    assert captured["payload"]["end_time"] == "20:00"
    assert captured["payload"]["interval_minutes"] == 90


@pytest.mark.asyncio
async def test_reminder_follow_up_recovers_explicit_window_and_prior_interval(db):
    """Production regression: '9点到20点' must not collapse to one 09:00 reminder."""
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = "9点到20点”"
    executor._current_turn_recent_messages = [
        {
            "role": "assistant",
            "content": "我会为你生成每天每 1.5 小时一次的循环饮水提醒。请告诉我开始和结束时间。",
        },
        {"role": "user", "content": "9点到20点”"},
    ]
    captured = {}

    async def fake_post(url, headers, payload):
        captured["url"] = url
        captured["payload"] = payload
        return json.dumps({
            "id": 150,
            "record_ids": list(range(150, 158)),
            "resource_type": "smart_reminder",
            "status": "scheduled",
        })

    with patch.object(executor, "_api_post", new=AsyncMock(side_effect=fake_post)):
        result = await executor._execute_tool(
            tool_name="health_record",
            args_raw=json.dumps({
                "record_type": "reminder",
                "data": {
                    "title": "定时饮水提醒",
                    "message": "少量多次饮水",
                    "remind_at": "2026-07-15T09:00:00+08:00",
                    "recurrence": "daily",
                },
            }, ensure_ascii=False),
            user_token="test-token",
        )

    assert "Error" not in str(result)
    assert captured["url"].endswith("/reminders/me/window")
    assert captured["payload"]["start_time"] == "09:00"
    assert captured["payload"]["end_time"] == "20:00"
    assert captured["payload"]["interval_minutes"] == 90
    assert "remind_at" not in captured["payload"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("record_type", "payload", "path", "expected_key"),
    [
        ("waist", {"waist_cm": 88.5, "record_date": date.today().isoformat()}, "/waist/records", "waist_cm"),
        (
            "sleep",
            {
                "record_date": date.today().isoformat(),
                "bedtime": f"{date.today() - timedelta(days=1)}T23:00:00+08:00",
                "wake_time": f"{date.today()}T07:00:00+08:00",
                "sleep_quality": 4,
            },
            "/sleep/records",
            "sleep_quality",
        ),
        ("excretion", {"record_date": date.today().isoformat(), "type": "bowel", "stool_type": 4}, "/excretion/records", "type"),
    ],
)
async def test_agent_health_record_posts_manual_body_records(db, record_type, payload, path, expected_key):
    """Agent 操作面补洞:腰围/睡眠/排泄可经 health_record 真正写入对应 API。"""
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 1
    captured = {}

    async def fake_post(url, headers, body):
        captured["url"] = url
        captured["payload"] = body
        return json.dumps({"id": 9, **body}, ensure_ascii=False)

    with patch.object(executor, "_api_post", new=AsyncMock(side_effect=fake_post)):
        result = await executor._execute_tool(
            tool_name="health_record",
            args_raw=json.dumps({"record_type": record_type, "data": payload}, ensure_ascii=False),
            user_token=None,
        )

    assert captured["url"].endswith(path)
    assert captured["payload"][expected_key] == payload[expected_key]
    assert json.loads(result)["id"] == 9


@pytest.mark.asyncio
async def test_agent_health_record_sleep_missing_times_fails_loud(db):
    """睡眠补录不能编造入睡/醒来时间;缺字段时必须让模型追问。"""
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 1

    with patch.object(executor, "_api_post", new=AsyncMock()) as post:
        result = await executor._exec_health_record(
            "http://test",
            {},
            {"record_type": "sleep", "data": {"sleep_quality": 4}},
        )

    rejection = json.loads(result)
    assert rejection["status"] == "rejected"
    assert rejection["dispatch_started"] is False
    assert rejection["error_code"] == "sleep_fields_missing"
    assert "bedtime" in rejection["message"]
    post.assert_not_called()


@pytest.mark.asyncio
async def test_agent_health_record_sleep_start_intent_records_life_event(db):
    """“准备开始睡觉”是开始事件,不是事后完整睡眠补录;应写 life_event 且给可验证回执。"""
    from app.services.agent_executor import (
        AgentExecutor,
        _write_receipt_from_tool_result,
    )

    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = "准备开始睡觉了。"
    captured = {}

    async def fake_post(url, headers, body):
        captured["url"] = url
        captured["payload"] = body
        return json.dumps({
            "id": 42,
            "title": "准备开始睡觉",
            "occurred_at": "2026-07-17T14:57:00+00:00",
            "occurred_precision": "exact",
            "occurred_display": "今天 22:57",
        }, ensure_ascii=False)

    with patch.object(executor, "_api_post", new=AsyncMock(side_effect=fake_post)):
        result = await executor._execute_tool(
            tool_name="health_record",
            args_raw=json.dumps({
                "record_type": "sleep",
                "data": {"bedtime": "2026-07-17T22:57:00+08:00"},
            }, ensure_ascii=False),
            user_token=None,
        )

    assert "Error" not in str(result)
    assert captured["url"].endswith("/episodes/life-event")
    assert captured["payload"]["title"] == "准备开始睡觉"
    assert captured["payload"]["occurred_at"] == "2026-07-17T22:57:00+08:00"
    receipt = _write_receipt_from_tool_result("health_record", "sleep", result)
    assert receipt is not None
    assert receipt["resource_type"] == "health_episode"
    assert receipt["resource_id"] == "42"


def test_agent_system_prompt_teaches_reminder_write_flow(db):
    """共享对话失败点: 不应说接口限制;应调用 health_record(reminder)."""
    from app.services.agent_executor import AgentExecutor

    prompt = AgentExecutor(db)._build_system_prompt(
        user_id=1,
        conv_id=1,
        user_auth_token="token",
    )

    assert "record_type=reminder" in prompt
    assert "recurrence=daily" in prompt
    assert "不能回复“系统接口限制”" in prompt


def test_agent_system_prompt_teaches_sleep_start_event_flow(db):
    """提示词要区分开始睡觉事件与事后完整睡眠补录。"""
    from app.services.agent_executor import AgentExecutor

    prompt = AgentExecutor(db)._build_system_prompt(
        user_id=1,
        conv_id=1,
        user_auth_token="token",
    )

    assert "准备开始睡觉" in prompt
    assert "record_type=event" in prompt
    assert "record_type=sleep" in prompt


def test_reminder_fast_record_is_auto_confirmed():
    """明确提醒写入是低风险记录,流式工具循环不应再二次确认。"""
    from app.services.agent_executor import _auto_confirm_fast_record_args

    args = _auto_confirm_fast_record_args(
        "health_record",
        {
            "record_type": "reminder",
            "data": {"title": "臀中肌训练", "time": "10:30", "recurrence": "daily"},
        },
    )

    assert args["record_type"] == "reminder"
    assert args["confirmed"] is True
    assert args["data"]["confirmed"] is True
    assert "_fast_record_requires_confirmation" not in args


@pytest.mark.asyncio
async def test_illness_record_accepts_name_payload(db):
    """illness schema 使用 name 字段, 执行器应兼容并写入 illness episodes."""
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 1

    captured = {}

    async def fake_post(url, headers, payload):
        captured["url"] = url
        captured["payload"] = payload
        return '{"id": 1, "name": "感冒"}'

    with patch.object(executor, "_api_post", new=AsyncMock(side_effect=fake_post)):
        result = await executor._execute_tool(
            tool_name="health_record",
            args_raw=json.dumps({
                "record_type": "illness",
                "data": {
                    "name": "感冒",
                    "severity": 4,
                    "status": "active",
                    "confirmed": True,
                },
            }),
            user_token=None,
        )

    assert "Error" not in str(result)
    assert "/illness/episodes" in captured.get("url", "")
    assert captured["payload"]["name"] == "感冒"
    assert captured["payload"]["severity"] == 4


@pytest.mark.asyncio
async def test_run_stream_with_extra_context_does_not_crash_before_first_event(db):
    """Regression: sources_used must be initialized before data-source inspection.

    The bug surfaced only on the streaming path before the first SSE event, so this
    exercises run_stream rather than private helpers.
    """
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)

    class FakeAgentConversationService:
        def __init__(self, db):
            self.db = db

        def get_or_create_conversation(self, user_id, conversation_id=None, title=None):
            from app.models.agent_conversation import AgentConversation

            conversation = AgentConversation(user_id=user_id, title=title)
            self.db.add(conversation)
            self.db.commit()
            self.db.refresh(conversation)
            return conversation

        def save_message(self, *args, **kwargs):
            return None

        def save_user_message_once(self, conv_id, user_id, content, **kwargs):
            from app.models.agent_conversation import AgentMessage

            message = AgentMessage(
                conversation_id=conv_id,
                role="user",
                content=content,
                image_url=kwargs.get("image_url"),
                meta=kwargs.get("meta") or {},
            )
            self.db.add(message)
            self.db.commit()
            self.db.refresh(message)
            return message, True

        def build_messages(self, conv_id, limit=15):
            return [{"role": "user", "content": "今天怎么安排"}]

    with patch("app.services.agent_conversation_service.AgentConversationService", FakeAgentConversationService), \
         patch.object(executor, "_build_system_prompt", return_value="system"), \
         patch("app.services.agent_executor._inspect_user_data_sources", return_value=["twin"]):
        stream = executor.run_stream(
            user_id=1,
            message="今天怎么安排",
            extra_context='{"from":"today"}',
        )
        first = await anext(stream)
        second = await anext(stream)
        third = await anext(stream)
        await stream.aclose()

    # P0-1 契约: accepted 恒为首事件;持久化 ACK 必须先于模型工作状态。
    assert first == {"type": "status", "stage": "accepted"}
    assert second["event"] == "request_persisted"
    assert third["event"] == "agent_start"


# === Regression (2026-06): _api_get 字符截断损坏 JSON → 用药/补剂查找崩溃并把原始错误泄漏给用户 ===
# 截图复现: 大响应被 _api_get 截到 3000 字符切断 'null'→'nul', 调用方 json.loads 抛
# 'Invalid control character' / 'Extra data', 然后 'Error: 用药记录失败: ...' 直接进了用户回复。
# 修复: 内部 ID 查找改走 _api_get_json (不截断), 失败给友好兜底文案。

@pytest.mark.asyncio
async def test_medication_lookup_corrupt_json_no_raw_error_leak(db):
    """模型确认不能触达旧查询路径，因此损坏上游数据也不会泄漏。"""
    from app.services.agent_executor import AgentExecutor
    executor = AgentExecutor(db)
    executor._current_user_id = 1

    class _Resp:
        status_code = 200
        # 模拟被截断的非法 JSON (含控制字符 + 截断的 token)
        text = '{"data":[{"id":1,"name":"二甲双胍","is_active":true,"note":"' + "x" * 3000 + '\x00...'
        def json(self):
            import json as _j
            return _j.loads(self.text)  # 必抛, 模拟真实损坏

    class _Client:
        async def get(self, url, headers=None): return _Resp()

    executor._http_client = _Client()
    # confirmed=true 是模型可控字段；现在恒被阻断，真正确认只消费服务端
    # source-bound WriteIntent，不再依赖这条 HTTP lookup/write 路径。
    result = await executor._execute_tool(
        tool_name="health_record",
        args_raw=json.dumps({
            "record_type": "medication",
            "confirmed": True,
            "data": {
                "medication_name": "二甲双胍",
                "actual_dosage": "1片",
                "confirmed": True,
            },
        }),
        user_token="t",
    )
    s = str(result)
    # 不得泄漏 Python JSON 异常、原始 JSON 或旧式 Error 机器文案。
    assert "Invalid control character" not in s
    assert "Extra data" not in s
    assert "用药记录失败" not in s
    assert '"is_active"' not in s  # 不回吐原始 JSON
    assert not s.startswith("Error:")
    payload = json.loads(s)
    assert payload["status"] == "rejected"
    assert payload["success"] is False
    assert payload["dispatch_started"] is False
    assert payload["error_code"] == "medication_plan_context_missing"
    assert "确认计划未能建立" in payload["message"]


@pytest.mark.asyncio
async def test_supplement_lookup_clean_json_matches(db):
    """补剂列表正常时, _api_get_json 拿干净数据并成功匹配打卡 (回归正路径)。"""
    from app.services.agent_executor import AgentExecutor
    executor = AgentExecutor(db)
    executor._current_user_id = 1

    class _Resp:
        status_code = 200
        def json(self):
            return [{"id": 7, "name": "甘氨酸镁", "is_active": True}]
    class _Client:
        async def get(self, url, headers=None): return _Resp()
    executor._http_client = _Client()

    captured = {}
    async def fake_post(url, headers, payload):
        captured["payload"] = payload
        return '{"ok": true}'

    with patch.object(executor, "_api_post", new=AsyncMock(side_effect=fake_post)):
        result = await executor._execute_tool(
            tool_name="health_record",
            args_raw=json.dumps({"record_type": "supplement", "data": {"supplement_name": "甘氨酸镁"}}),
            user_token="t",
        )
    assert captured.get("payload", {}).get("supplement_id") == 7
    assert "补剂查找失败" not in str(result)
