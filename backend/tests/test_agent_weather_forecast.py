"""Agent weather queries must preserve forecast scope and explicit city."""

from unittest.mock import MagicMock

import pytest

from app.services.agent_executor import AgentExecutor
from app.services.llm.tool_validator import validate_tool_call
from app.services.tool_schema_registry import get_health_tools


def _environment_schema() -> dict:
    return next(
        tool["function"]
        for tool in get_health_tools()
        if tool["function"]["name"] == "environment_check"
    )


def test_environment_tool_can_express_beijing_forecast_query():
    schema = _environment_schema()
    properties = schema["parameters"]["properties"]

    assert "forecast" in properties["check_type"]["enum"]
    assert properties["city"]["type"] == "string"
    assert properties["days"]["minimum"] == 1
    assert properties["days"]["maximum"] == 7

    validated = validate_tool_call(
        "environment_check",
        {"check_type": "forecast", "city": " 北京 ", "days": "3"},
    )
    assert validated["error"] is None
    assert validated["warnings"] == []
    assert validated["data"] == {
        "check_type": "forecast",
        "city": "北京",
        "days": 3,
    }


@pytest.mark.asyncio
async def test_environment_executor_forwards_encoded_city_and_days():
    executor = AgentExecutor(MagicMock())
    requested = []

    async def fake_api_get(url, headers):
        requested.append((url, headers))
        return '{"available": true}'

    executor._api_get = fake_api_get

    result = await executor._exec_environment(
        "http://health.test/api/v1",
        {"Authorization": "Bearer test"},
        {"check_type": "forecast", "city": "北京", "days": 3},
    )

    assert result == '{"available": true}'
    assert requested == [
        (
            "http://health.test/api/v1/environment/weather/forecast?city=%E5%8C%97%E4%BA%AC&days=3",
            {"Authorization": "Bearer test"},
        )
    ]


@pytest.mark.asyncio
async def test_current_weather_executor_forwards_explicit_city():
    executor = AgentExecutor(MagicMock())
    requested = []

    async def fake_api_get(url, headers):
        requested.append(url)
        return '{}'

    executor._api_get = fake_api_get

    await executor._exec_environment(
        "http://health.test/api/v1",
        {},
        {"check_type": "weather", "city": "北京市"},
    )

    assert requested == [
        "http://health.test/api/v1/environment/weather?city=%E5%8C%97%E4%BA%AC%E5%B8%82"
    ]
