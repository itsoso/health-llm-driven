"""Agent weather queries must preserve forecast scope and explicit city."""

import json
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
async def test_environment_executor_forwards_encoded_city_and_days(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "reads_in_process", False, raising=False)
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
async def test_current_weather_executor_forwards_explicit_city(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "reads_in_process", False, raising=False)
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


@pytest.mark.asyncio
async def test_environment_check_without_bearer_reads_in_process(monkeypatch):
    """Web cookie sessions never forward Authorization; weather still must succeed."""
    from app.config import settings

    monkeypatch.setattr(settings, "reads_in_process", True, raising=False)
    executor = AgentExecutor(MagicMock())
    executor._current_user_id = 3

    async def boom(*_args, **_kwargs):
        raise AssertionError("cookie sessions must not loop back through HTTP")

    executor._api_get = boom

    async def fake_weather(city=None, lat=None, lon=None):
        assert city == "成都"
        return {"available": True, "city": city, "source": "qweather"}

    from app.services.environment import weather_service

    monkeypatch.setattr(weather_service, "get_current_weather", fake_weather)
    monkeypatch.setattr(
        weather_service,
        "get_exercise_advice",
        lambda weather: {"suitable": True, "advices": []},
    )

    result = await executor._exec_environment(
        "http://health.test/api/v1",
        {},
        {"check_type": "weather", "city": "成都"},
    )

    payload = json.loads(result)
    assert payload["weather"]["available"] is True
    assert payload["weather"]["city"] == "成都"


@pytest.mark.asyncio
async def test_environment_check_killswitch_still_uses_http(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "reads_in_process", False, raising=False)
    executor = AgentExecutor(MagicMock())
    requested = []

    async def fake_api_get(url, headers):
        requested.append((url, headers))
        return '{"available": true}'

    executor._api_get = fake_api_get

    result = await executor._exec_environment(
        "http://health.test/api/v1",
        {},
        {"check_type": "weather", "city": "成都"},
    )

    assert result == '{"available": true}'
    assert requested == [
        ("http://health.test/api/v1/environment/weather?city=%E6%88%90%E9%83%BD", {})
    ]
