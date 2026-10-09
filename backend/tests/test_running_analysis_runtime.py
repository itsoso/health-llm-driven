"""Actual Pi/gateway/DB reads; only model and public weather are synthetic."""
import json

import pytest

from app.models.agent_conversation import AgentMessage
from tests.test_agent_coherence_pi_trajectories import (
    _isolate_twin_cache as _isolate_twin_cache,
    clock as clock,
    owned_data as owned_data,
    run,
    script_executor,
)
from tests.test_running_analysis_read_scope import REQUEST


@pytest.mark.asyncio
@pytest.mark.parametrize("weather_failed", [False, True])
async def test_running_analysis_keeps_weather_tools_and_original_question(
    db, owned_data, monkeypatch, weather_failed,
):
    trace = script_executor(db, monkeypatch, [
        ("health_query_batch", {"queries": [{"dimension": "diet"}, {"dimension": "sleep"}]}),
        ("environment_check", {"check_type": "weather", "city": "杭州"}),
        ("已查到部分饮食和睡眠记录，天气查询失败。不能据此判断运动条件；本轮未生成 HTML 页面。"
         if weather_failed else
         "已查到部分饮食和睡眠记录，当前天气返回小雨。不能仅凭这些信息确认运动安全；本轮未生成 HTML 页面。"),
    ])
    weather_calls = []

    async def weather(_base, _headers, args):
        weather_calls.append(args)
        if weather_failed:
            return json.dumps({"error": "weather_unavailable"})
        return json.dumps({"weather": {"available": True, "city": "杭州", "weather": "小雨"}})

    monkeypatch.setattr(trace.executor, "_exec_environment", weather)
    done, saved = await run(db, trace, owned_data, REQUEST)
    if weather_failed:
        assert done["turn_outcome"]["status"] != "complete"
    assert [r.tool_name for r in trace.dispatches] == ["health_query_batch", "environment_check"]
    assert weather_calls == [{"check_type": "weather", "city": "杭州"}]
    # A pure-health synthesis used to discard the tool transcript and disable
    # all tools before the weather step, even though only history was complete.
    assert any(t["function"]["name"] == "environment_check" for t in trace.calls[1][1])
    assert any(m.get("role") == "tool" for m in trace.calls[1][0])
    assert any(REQUEST in str(m.get("content", "")) for m in trace.calls[-1][0])
    assert "范围限制尚不能完整解析" not in saved.content
    assert "未生成 HTML" in saved.content
    source = db.query(AgentMessage).filter_by(conversation_id=saved.conversation_id, role="user").one()
    assert source.content == REQUEST
    assert trace.executor._composed_read_completion().complete
    sleep = next(q for q in trace.executor._composed_read_completion().verified_evidence["queries"]
                 if q["query"]["dimension"] == "sleep")
    assert [row["known_fields"]["sleep_score"] for row in sleep["records"]] == [80]
