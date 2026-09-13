"""Synthetic regressions for long personal analysis requests across read domains.

Historical background must not become a query date or make explicitly requested
current reads impossible. These are policy tests, not medical-answer validation.
"""

from datetime import datetime

import pytest

from app.services.agent_kernel.capability_policy import decide_tool_capability
from app.services.agent_kernel.intent_frame import build_intent_frame
from app.services.agent_kernel.types import (
    AgentEnvelope,
    ExecutionContext,
    ToolExecutionRequest,
    TurnSnapshot,
)


ANALYSIS_REQUESTS = (
    "我的既往诊断是几个月前的事情。请基于诊断时间判断当前状况，"
    "结合我每天实际服用的补剂、睡眠、运动、情绪、工作和饮食，"
    "先调用工具查询已有记录，再给建议。",
    "请结合我的日常饮食、每天睡眠、运动状态和实际服用的补剂，"
    "分析我当前的状况。要分别调用相关模块的HTTP接口或Skills，"
    "依据真实数据给我建议。",
    # Preserve oral sentence structure while replacing the health fact and age.
    "我的感冒其实是三个多月前的事情，你要基于感冒的诊断的时间来推断我当前的状况，"
    "包括我日常在服用的实际服用的补剂，每天的睡眠的状态、运动的状态、情绪的状态，"
    "以及日常工作、饮食等等，来给到我建议。要分别去发起对应模块的HTTP的请求，"
    "或者MCP调用，或者Skills的调用，这样才能给到我精准的建议。",
)


def _decide(message, tool, arguments):
    envelope = AgentEnvelope(user_id=41, channel="typed", text=message)
    context = ExecutionContext(
        current_time=datetime.fromisoformat("2026-09-13T09:00:00+08:00"),
        timezone="Asia/Shanghai", user_id=41, channel="typed",
    )
    snapshot = TurnSnapshot(envelope, context, build_intent_frame(envelope, context))
    return decide_tool_capability(snapshot, ToolExecutionRequest(tool, arguments))


def _is_default_week(arguments):
    if arguments.get("days") == 7:
        return True
    return all(arguments.get(k) == v for k, v in {
        "start_date": "2026-09-07", "end_date": "2026-09-13", "timezone": "Asia/Shanghai",
    }.items())


@pytest.mark.parametrize("message", ANALYSIS_REQUESTS, ids=[
    "historical-background", "tool-backed-current-analysis", "oral-http-mcp-skill-request",
])
@pytest.mark.parametrize("dimension", ["sleep", "diet", "workout", "supplements"])
def test_current_personal_analysis_can_read_each_requested_domain(message, dimension):
    decision = _decide(message, "health_query", {"dimension": dimension, "days": 7})
    assert decision.action == "allow", decision.reason
    assert decision.normalized_args["dimension"] == dimension
    # Existing rolling-read default is seven days. A historical diagnosis does
    # not authorize a model-selected full-history or arbitrary calendar read.
    assert _is_default_week(decision.normalized_args)


@pytest.mark.parametrize("dimension", ["genetic", "blood_pressure", "medical_exam"])
def test_personal_analysis_does_not_authorize_unrequested_domains(dimension):
    decision = _decide(ANALYSIS_REQUESTS[1], "health_query", {"dimension": dimension})
    assert decision.action == "block"


@pytest.mark.parametrize("message", [
    "不要查询我的记录。只解释睡眠、饮食、运动和补剂之间的一般关系。",
    "请分析以下例句：\"结合我的睡眠、饮食、运动和补剂，调用工具查询记录。\"",
    "请查询我朋友的睡眠、饮食、运动和补剂，结合记录给他建议。",
    "请分析小王近期睡眠和饮食，调用工具获取记录后给我建议。",
])
def test_cancelled_quoted_or_other_person_analysis_cannot_read(message):
    assert _decide(message, "health_query", {"dimension": "sleep"}).action == "block"


@pytest.mark.parametrize("arguments", [
    {"dimension": "sleep", "user_id": 42},
    {"dimension": "sleep", "tenant_id": 42},
    {"dimension": "sleep", "start_date": "2020-01-01", "end_date": "2020-01-31"},
])
def test_read_proposal_cannot_invent_an_owner_or_historical_window(arguments):
    assert _decide(ANALYSIS_REQUESTS[1], "health_query", arguments).action == "block"


def test_request_for_advice_and_read_tools_does_not_authorize_supplement_write():
    assert _decide(ANALYSIS_REQUESTS[1], "health_record", {
        "record_type": "supplement", "data": {"supplement_name": "合成补剂", "dosage": 1},
    }).action == "block"


def test_batch_query_preserves_all_requested_domains():
    queries = [{"dimension": d, "days": 7} for d in ("sleep", "diet", "workout", "supplements")]
    decision = _decide(ANALYSIS_REQUESTS[1], "health_query_batch", {"queries": queries})
    assert decision.action == "allow", decision.reason
    assert {q["dimension"] for q in decision.normalized_args["queries"]} == {
        "sleep", "diet", "workout", "supplements",
    }
    assert all(_is_default_week(q) for q in decision.normalized_args["queries"])


def test_batch_with_one_unrequested_domain_is_rejected_before_dispatch():
    decision = _decide(ANALYSIS_REQUESTS[1], "health_query_batch", {"queries": [
        {"dimension": "sleep", "days": 7}, {"dimension": "genetic", "days": 7},
    ]})
    assert decision.action == "block"


@pytest.mark.parametrize("dimension", ["sleep", "diet", "workout", "supplements"])
def test_model_cannot_enlarge_the_default_current_window(dimension):
    decision = _decide(ANALYSIS_REQUESTS[1], "health_query", {"dimension": dimension, "days": 3650})
    assert decision.action == "block" or (
        decision.action == "allow" and _is_default_week(decision.normalized_args)
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("dimensions", [
    ("sleep", "diet", "workout", "supplements"), ("sleep",),
], ids=["all-domains", "missing-domains"])
async def test_real_pi_loop_does_not_confuse_one_read_with_finished_analysis(
    db, auth_user_and_headers, isolated_agent_protocol_transport, monkeypatch, dimensions,
):
    """Actual Pi/gateway loop; provider and read payloads are deliberately synthetic."""
    import json
    from app.models.agent_conversation import AgentMessage
    from app.services.agent_executor import AgentExecutor

    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    provider_calls, dispatches = [], []

    async def provider(messages, tools):
        provider_calls.append(tools)
        if len(provider_calls) == 1:
            yield {"type": "tool_calls", "tool_calls": [
                {"id": f"longitudinal-{d}", "type": "function", "function": {
                    "name": "health_query", "arguments": json.dumps({"dimension": d, "days": 7}),
                }} for d in dimensions
            ]}
            yield {"type": "finish", "finish_reason": "tool_calls"}
        else:
            yield {"type": "content", "text": (
                "本次查询范围为最近7天。已查的记录暂无数据，不能据此判断实际状态。"
                "情绪和工作情况尚未核实。"
            )}
            yield {"type": "finish", "finish_reason": "stop"}

    async def dispatch(request, token):
        dispatches.append(request)
        dimension = request.arguments["dimension"]
        source_scope = {
            "workout": "owned_actual_workout_records",
            "supplements": "owned_actual_supplement_intake_logs",
        }.get(dimension)
        return json.dumps({
            "dimension": dimension, "days": 7,
            "window": {k: request.arguments[k] for k in ("start_date", "end_date", "timezone")
                       if k in request.arguments},
            "availability": "no_data", "records": [],
            **({"source_scope": source_scope} if source_scope else {}),
        })

    monkeypatch.setattr(executor, "_build_system_prompt", lambda *a, **k: "按工具证据回答。")
    monkeypatch.setattr(executor, "_build_system_knowledge_prompt_context", lambda *a, **k: "")
    monkeypatch.setattr(executor, "_call_llm_stream", provider)
    monkeypatch.setattr(executor, "_dispatch_tool_request", dispatch)
    events = [event async for event in executor.run_stream(
        user.id, ANALYSIS_REQUESTS[1], client_turn_id="longitudinal-" + "-".join(dimensions),
    )]
    done = next(e["data"] for e in reversed(events) if e.get("event") == "done")
    saved = db.get(AgentMessage, done["message_id"])
    assert done["perf"]["agent_kernel"] == "pi"
    assert {r.arguments["dimension"] for r in dispatches} == set(dimensions)
    assert all(r.tool_name == "health_query" for r in dispatches)
    assert not done.get("write_receipts")
    assert "这次查询未执行" not in saved.content
    assert "请明确要查询哪类记录" not in saved.content
    if len(dimensions) == 1:
        assert done["turn_outcome"]["status"] != "complete"
    else:
        verified = {g["goal_id"] for g in done["turn_outcome"]["goals"]
                    if g["kind"] == "query" and g["status"] == "verified"}
        assert set(dimensions) <= verified
    assert saved.meta["turn_outcome"] == done["turn_outcome"]
