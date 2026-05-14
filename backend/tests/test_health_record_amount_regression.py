"""Regression: symptom 记录不应触发 'amount' KeyError.

根因 (2026-05-11): _exec_health_record 里 record_map 是 dict 字面量, eager 求值.
即使 rtype='symptom' 后面有早返, dict 里 'amount': data['amount'] 也会先炸.
修法: 把 data['amount'] 改成 data.get('amount').
"""
import json
from unittest.mock import AsyncMock, patch

import pytest


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
