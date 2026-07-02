"""Regression: symptom 记录不应触发 'amount' KeyError.

根因 (2026-05-11): _exec_health_record 里 record_map 是 dict 字面量, eager 求值.
即使 rtype='symptom' 后面有早返, dict 里 'amount': data['amount'] 也会先炸.
修法: 把 data['amount'] 改成 data.get('amount').
"""
import json
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_water_record_posts_amount_as_query_param(db):
    """water quick endpoint requires amount in query string, not JSON body."""
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 1

    captured = {}

    async def fake_post(url, headers, payload):
        captured["url"] = url
        captured["payload"] = payload
        return '{"id": 1, "amount": 1000, "drink_type": "水"}'

    with patch.object(executor, "_api_post", new=AsyncMock(side_effect=fake_post)):
        result = await executor._execute_tool(
            tool_name="health_record",
            args_raw=json.dumps({
                "record_type": "water",
                "data": {"amount": 1000, "confirmed": True},
            }),
            user_token=None,
        )

    assert "Error" not in str(result)
    assert captured["url"].endswith("/water/records/quick?amount=1000")
    assert captured["payload"] == {}


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

    assert "Error" in str(result)
    assert "amount" in str(result)
    post.assert_not_called()


@pytest.mark.asyncio
async def test_symptom_record_does_not_throw_on_missing_amount(db):
    """symptom 数据不带 amount, 应正常调 /symptoms 不抛 KeyError."""
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 1

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
    assert captured["payload"]["priority"] == "normal"
    assert captured["payload"]["remind_at"].endswith("+08:00")
    assert "T10:30:00" in captured["payload"]["remind_at"]


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

    class FakeOpenClawService:
        def __init__(self, db):
            self.db = db

        def get_or_create_conversation(self, user_id, conversation_id=None, title=None):
            return type("Conversation", (), {"id": 123})()

        def save_message(self, *args, **kwargs):
            return None

        def build_messages(self, conv_id, limit=15):
            return [{"role": "user", "content": "今天怎么安排"}]

    with patch("app.services.openclaw_service.OpenClawService", FakeOpenClawService), \
         patch.object(executor, "_build_system_prompt", return_value="system"), \
         patch("app.services.agent_executor._inspect_user_data_sources", return_value=["twin"]):
        stream = executor.run_stream(
            user_id=1,
            message="今天怎么安排",
            extra_context='{"from":"today"}',
        )
        first = await anext(stream)
        await stream.aclose()

    assert first["event"] == "agent_start"


# === Regression (2026-06): _api_get 字符截断损坏 JSON → 用药/补剂查找崩溃并把原始错误泄漏给用户 ===
# 截图复现: 大响应被 _api_get 截到 3000 字符切断 'null'→'nul', 调用方 json.loads 抛
# 'Invalid control character' / 'Extra data', 然后 'Error: 用药记录失败: ...' 直接进了用户回复。
# 修复: 内部 ID 查找改走 _api_get_json (不截断), 失败给友好兜底文案。

@pytest.mark.asyncio
async def test_medication_lookup_corrupt_json_no_raw_error_leak(db):
    """药物列表响应损坏时, 给用户友好兜底, 不泄漏 'Invalid control character'/原始 JSON。"""
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
    # medication 恒确认前置(2026-07-02):带 confirmed=true 越过确认闸,
    # 本测试专测确认后的 lookup 损坏兜底路径。
    result = await executor._execute_tool(
        tool_name="health_record",
        args_raw=json.dumps({
            "record_type": "medication",
            "confirmed": True,
            "data": {"medication_name": "二甲双胍", "confirmed": True},
        }),
        user_token="t",
    )
    s = str(result)
    # 不得泄漏 python json 异常 / 原始 JSON / "Error:" 机器文案
    assert "Invalid control character" not in s
    assert "Extra data" not in s
    assert "用药记录失败" not in s
    assert '"is_active"' not in s  # 不回吐原始 JSON
    # 应是友好中文兜底
    assert "用药记录" in s and ("稍后再试" in s or "没成功" in s)


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
