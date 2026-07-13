import json
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_health_record_creates_waist_record_from_agent(db):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    captured = {}

    async def fake_post(url, headers, payload):
        captured["url"] = url
        captured["payload"] = payload
        return json.dumps({"id": 11, **payload}, ensure_ascii=False)

    with patch.object(executor, "_api_post", new=AsyncMock(side_effect=fake_post)):
        result = await executor._exec_health_record(
            "http://x",
            {},
            {"record_type": "waist", "data": {"waist": 82, "confirmed": True}},
        )

    assert captured["url"] == "http://x/waist/records"
    assert captured["payload"]["waist_cm"] == 82
    assert captured["payload"]["source"] == "agent"
    assert json.loads(result)["id"] == 11


@pytest.mark.asyncio
async def test_health_record_creates_sleep_record_from_duration(db):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    captured = {}

    async def fake_post(url, headers, payload):
        captured["url"] = url
        captured["payload"] = payload
        return json.dumps({"id": 12, **payload}, ensure_ascii=False)

    with patch.object(executor, "_api_post", new=AsyncMock(side_effect=fake_post)):
        result = await executor._exec_health_record(
            "http://x",
            {},
            {
                "record_type": "sleep",
                "data": {
                    "duration_hours": 7.5,
                    "wake_time": "2026-07-06T07:30:00+08:00",
                    "sleep_quality": 4,
                    "confirmed": True,
                },
            },
        )

    assert captured["url"] == "http://x/sleep/records"
    assert captured["payload"]["record_date"] == "2026-07-06"
    assert captured["payload"]["bedtime"] == "2026-07-06T00:00:00+08:00"
    assert captured["payload"]["wake_time"] == "2026-07-06T07:30:00+08:00"
    assert captured["payload"]["sleep_quality"] == 4
    assert json.loads(result)["id"] == 12


@pytest.mark.asyncio
async def test_health_record_creates_excretion_record_with_alias(db):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    captured = {}

    async def fake_post(url, headers, payload):
        captured["url"] = url
        captured["payload"] = payload
        return json.dumps({"id": 13, **payload}, ensure_ascii=False)

    with patch.object(executor, "_api_post", new=AsyncMock(side_effect=fake_post)):
        result = await executor._exec_health_record(
            "http://x",
            {},
            {"record_type": "excretion", "data": {"type": "大便", "stool_type": 4, "confirmed": True}},
        )

    assert captured["url"] == "http://x/excretion/records"
    assert captured["payload"]["type"] == "bowel"
    assert captured["payload"]["stool_type"] == 4
    assert json.loads(result)["id"] == 13


@pytest.mark.asyncio
async def test_health_record_creates_goal_from_agent(db):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    captured = {}

    async def fake_post(url, headers, payload):
        captured["url"] = url
        captured["payload"] = payload
        return json.dumps({"id": 14, **payload}, ensure_ascii=False)

    with patch.object(executor, "_api_post", new=AsyncMock(side_effect=fake_post)):
        result = await executor._exec_health_record(
            "http://x",
            {},
            {
                "record_type": "goal",
                "data": {
                    "goal_type": "exercise",
                    "goal_period": "daily",
                    "title": "每日运动40分钟",
                    "target_value": 40,
                    "target_unit": "分钟",
                    "start_date": "2026-07-06",
                    "confirmed": True,
                },
            },
        )

    assert captured["url"] == "http://x/goals/"
    assert captured["payload"]["goal_type"] == "exercise"
    assert captured["payload"]["goal_period"] == "daily"
    assert captured["payload"]["title"] == "每日运动40分钟"
    assert json.loads(result)["id"] == 14


def test_health_record_schema_exposes_new_agent_operable_record_types():
    from app.services.tool_schema_registry import HEALTH_TOOLS

    schemas = {tool["function"]["name"]: tool["function"]["parameters"]["properties"] for tool in HEALTH_TOOLS}
    record_types = set(schemas["health_record"]["record_type"]["enum"])

    assert {"waist", "sleep", "excretion", "goal"} <= record_types
