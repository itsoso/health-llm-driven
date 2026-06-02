"""多模型综合分析 (商用三强 panel) — 单元 + 编排集成测试。

验证: lead 带工具只执行一次 (不重复写库)、GPT/Gemini 并发独立分析、
Claude 综合, 单条 assistant 消息落库, done 事件 mode=multi_model。
"""
import json

import pytest

from app.services.agent_executor import (
    AgentExecutor,
    _build_multi_model_synthesis_prompt,
    _extract_multi_model_flag,
    _gathered_data_context,
)


def test_extract_multi_model_flag():
    assert _extract_multi_model_flag('{"multi_model": true}') is True
    assert _extract_multi_model_flag('{"multi_model": false}') is False
    assert _extract_multi_model_flag('{"model_id": "gpt-5.5"}') is False
    assert _extract_multi_model_flag(None) is False
    assert _extract_multi_model_flag("not json") is False


def test_gathered_data_context_extracts_tool_results_only():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "1"}]},
        {"role": "tool", "tool_call_id": "1", "content": "睡眠评分 79"},
        {"role": "tool", "tool_call_id": "2", "content": "HRV 56ms"},
    ]
    ctx = _gathered_data_context(messages)
    assert "睡眠评分 79" in ctx
    assert "HRV 56ms" in ctx
    assert "sys" not in ctx and "q" not in ctx


def test_synthesis_prompt_includes_question_and_all_analyses():
    prompt = _build_multi_model_synthesis_prompt(
        "我最近睡眠怎么样",
        [("Claude Opus 4.7", "A 分析"), ("GPT-5.5", "B 分析"), ("Gemini 3.1 Pro", "C 分析")],
    )
    assert "我最近睡眠怎么样" in prompt
    for label in ("Claude Opus 4.7", "GPT-5.5", "Gemini 3.1 Pro"):
        assert label in prompt
    assert "A 分析" in prompt and "B 分析" in prompt and "C 分析" in prompt
    assert "共识结论" in prompt and "分歧" in prompt


@pytest.mark.asyncio
async def test_multi_model_stream_lead_tools_once_then_synthesizes(db, auth_user_and_headers, monkeypatch):
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)

    monkeypatch.setattr(executor, "_build_system_prompt", lambda *a, **k: "SYS")
    monkeypatch.setattr("app.services.agent_executor.get_health_tools", lambda: [])

    # Lead loop: round 1 → one tool call; round 2 → final analysis text.
    lead_calls = {"n": 0}

    async def fake_call_llm(messages, tools):
        lead_calls["n"] += 1
        if lead_calls["n"] == 1:
            return {
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [{
                    "id": "c1", "type": "function",
                    "function": {"name": "health_query", "arguments": json.dumps({"metric": "sleep"})},
                }],
            }
        return {"content": "LEAD ANALYSIS", "finish_reason": "stop"}

    tool_runs = []

    async def fake_execute_tool(name, args, token):
        tool_runs.append(name)
        return "睡眠评分 79，HRV 56ms"

    monkeypatch.setattr(executor, "_call_llm", fake_call_llm)
    monkeypatch.setattr(executor, "_execute_tool", fake_execute_tool)

    synth_user_prompts = []

    class FakeProvider:
        def __init__(self, model_id):
            self.model = model_id

        async def chat(self, **kwargs):
            messages = kwargs["messages"]
            system = messages[0]["content"]
            user_msg = messages[-1]["content"]
            if "综合专家" in system:  # synthesis call
                synth_user_prompts.append(user_msg)
                return {"content": "SYNTHESIS REPORT", "finish_reason": "stop"}
            return {"content": f"PERSP[{self.model}]", "finish_reason": "stop"}

    monkeypatch.setattr(
        "app.services.llm.factory.create_provider_for_model_id",
        lambda model_id: FakeProvider(model_id),
    )

    events = []
    async for ev in executor._run_multi_model_stream(
        user.id, "我最近睡眠怎么样", None, None, '{"multi_model": true}'
    ):
        events.append(ev)

    kinds = [e["event"] for e in events]
    assert kinds[0] == "agent_start"
    assert "token" in kinds and kinds[-1] == "done"

    # lead tool executed exactly once (panel must NOT triplicate writes)
    assert tool_runs == ["health_query"]

    # streamed answer is the synthesis
    streamed = "".join(e["data"]["content"] for e in events if e["event"] == "token")
    assert streamed == "SYNTHESIS REPORT"

    # synthesis saw lead + both perspectives
    assert len(synth_user_prompts) == 1
    sp = synth_user_prompts[0]
    assert "LEAD ANALYSIS" in sp
    assert "PERSP[gpt-5.5]" in sp
    assert "PERSP[gemini-3.1-pro]" in sp

    # done event carries multi_model mode + the saved message persisted the synthesis
    done = events[-1]["data"]
    assert done["mode"] == "multi_model"
    assert "Claude Opus 4.7" in done["model"] and "GPT-5.5" in done["model"]

    from app.services.openclaw_service import OpenClawService
    conv = OpenClawService(db).get_conversation_detail(user.id, done["conversation_id"])
    assistant_msgs = [m for m in conv.messages if m.role == "assistant"]
    assert len(assistant_msgs) == 1  # exactly one synthesis message, not one per panel model
    assert "SYNTHESIS REPORT" in (assistant_msgs[0].content or "")
