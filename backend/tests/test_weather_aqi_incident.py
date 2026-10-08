"""Synthetic reproduction of the compound public weather incident through Pi."""
import json
import pytest
from app.services.agent_executor import AgentExecutor

@pytest.mark.asyncio
@pytest.mark.parametrize("short_identity_key", [False, True])
async def test_weather_and_aqi_two_tools_complete(db, auth_user_and_headers, monkeypatch, isolated_agent_protocol_transport, short_identity_key):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    if short_identity_key:
        monkeypatch.setattr("app.services.agent_runtime_identity.settings.secret_key", "synthetic-short")
    calls, reads = [], []
    async def provider(messages, tools):
        calls.append(messages)
        if len(calls) == 1:
            yield {"type": "tool_calls", "tool_calls": [
                {"id": "weather-forecast", "type": "function", "function": {"name": "environment_check", "arguments": json.dumps({"check_type": "forecast", "city": "杭州", "days": 2})}},
                {"id": "weather-aqi", "type": "function", "function": {"name": "environment_check", "arguments": json.dumps({"check_type": "air_quality", "city": "杭州"})}},
            ]}
            yield {"type": "finish", "finish_reason": "tool_calls"}
        else:
            yield {"type": "content", "text": "杭州明天多云，18至24度。当前空气质量良；没有明天的空气质量预报。"}
            yield {"type": "finish", "finish_reason": "stop"}
    async def environment(check_type, *, city, days):
        reads.append((check_type, city, days))
        if check_type == "forecast":
            return {"available": True, "city": city, "forecasts": [{"date": "2026-10-09", "temp_min": 18, "temp_max": 24, "text_day": "多云"}]}
        assert check_type == "air_quality"
        return {"available": True, "city": city, "aqi": 51, "aqi_description": "良", "update_time": "2026-10-08T19:00:00+08:00"}
    def expose(error):
        raise error
    monkeypatch.setattr(executor, "_build_system_prompt", lambda *a, **k: "Use public environment tools only.")
    monkeypatch.setattr(executor, "_call_llm_stream", provider)
    monkeypatch.setattr(executor, "_read_environment_in_process", environment)
    monkeypatch.setattr("app.services.agent_executor.safe_llm_error_message", expose)
    async def run():
        return [e async for e in executor.run_stream(user.id, "杭州明天天气温度怎么样？空气质量。", client_turn_id="weather-aqi-incident")]
    if short_identity_key:
        with pytest.raises(RuntimeError, match="^agent_runtime_identity_key_unavailable$"):
            await run()
        assert len(calls) == 1
        assert reads == []
        return
    events = await run()
    assert events[-1]["data"]["completion_status"] == "complete"
    assert [r[0] for r in reads] == ["forecast", "air_quality"]
    assert len(calls) == 2
