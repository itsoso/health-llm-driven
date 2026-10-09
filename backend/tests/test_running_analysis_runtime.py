"""Actual Pi/gateway/DB reads; only model and public weather are synthetic."""
import json
from uuid import uuid4

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
from tests.test_agent_read_repair_round_budget import batch_trace


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


@pytest.mark.asyncio
@pytest.mark.parametrize("panel", [False, True])
@pytest.mark.parametrize("single_domain", [False, True])
@pytest.mark.parametrize("reply", [
    "你的恢复状态良好，可以跑步5公里。",
    "你的蛋白质摄入不足。",
    "这些饮食和睡眠记录是模板占位数据。",
    "<p>你的蛋白质摄入<strong>不足</strong>。</p>",
    "<p>你的蛋白质摄入<span>&#19981;&#36275;</span>。</p>",
    "<p>你的恢复状态<strong>良好</strong>，可以跑步<b>5</b>公里。</p>",
    "<p>这些饮食和睡眠记录是模<strong>板</strong>占<span>位</span>数据。</p>",
    '<p style="display:none; display:block">你的蛋白质摄入不足。</p>',
    '<p style="visibility:hidden"><span style="visibility:visible">你的蛋白质摄入不足。</span></p>',
    '<head><title>报告</title><body>你的蛋白质摄入不足。</body>',
    '<p style="display:none-block">你的蛋白质摄入不足。</p>',
    '<p>你的蛋白质摄入<br>不足。</p>',
    '<div>你的蛋白质摄入</div><div>不足。</div>',
    '<p>这些饮食和睡眠记录是模<br>板占位数据。</p>',
])
async def test_composite_retains_health_evidence_guards_before_stream_and_save(
    db, owned_data, monkeypatch, panel, single_domain, reply,
):
    query = REQUEST.replace("饮食睡眠", "饮食") if single_domain else REQUEST
    queries = [{"dimension": "diet"}] if single_domain else [{"dimension": "diet"}, {"dimension": "sleep"}]
    trace = batch_trace(db, monkeypatch, [
        [("health_query_batch", {"queries": queries})],
        [("environment_check", {"check_type": "weather", "city": "杭州"})],
        reply,
    ])

    async def weather(*_args):
        return json.dumps({"weather": {"available": True, "city": "杭州", "weather": "小雨"}})

    monkeypatch.setattr(trace.executor, "_exec_environment", weather)
    class PanelProvider:
        async def chat(self, **_kwargs):
            return {"content": reply, "finish_reason": "stop"}

    monkeypatch.setattr("app.services.llm.factory.create_provider_for_model_id", lambda *a, **k: PanelProvider())
    events = [event async for event in trace.executor.run_stream(
        owned_data.id, query, client_turn_id=str(uuid4()),
        extra_context=json.dumps({"multi_model": panel}),
    )]
    done = next(e["data"] for e in reversed(events) if e.get("event") == "done")
    saved = db.get(AgentMessage, done["message_id"])
    public = "".join(e["data"].get("content", "") for e in events if e.get("event") == "token")
    assert reply not in saved.content and reply not in public
    assert reply not in json.dumps(events, ensure_ascii=False)
    assert public == saved.content
    assert any(r.tool_name == "environment_check" for r in trace.dispatches)
    assert not done["write_receipts"]
