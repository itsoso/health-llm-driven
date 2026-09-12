"""Real Pi must not advertise personal-data tools for material-only analysis."""
import pytest

from app.services.agent_executor import AgentExecutor


@pytest.mark.asyncio
async def test_pure_material_analysis_exposes_only_reviewed_knowledge_to_pi(
    db, auth_user_and_headers, monkeypatch,
):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    seen = []

    async def provider(messages, tools):
        seen.append({tool["function"]["name"] for tool in tools})
        yield {"type": "content", "text": "这是一条通用出行建议，可以按个人需求评估。"}
        yield {"type": "finish", "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_build_system_prompt", lambda *a, **k: "Analyze the provided material.")
    monkeypatch.setattr(executor, "_call_llm_stream", provider)
    events = [event async for event in executor.run_stream(
        user.id, "分析以下建议：如果家里有的话不用再买。检查水杯和舒适的鞋。",
    )]
    assert seen and all(names == {"knowledge_search"} for names in seen)
    assert events[-1]["data"]["perf"]["agent_kernel"] == "pi"
    assert events[-1]["data"]["completion_status"] == "complete"


@pytest.mark.parametrize("message", [
    "分析以下建议：“不用再买。”；查询我今天吃了什么",
    "分析以下建议：“不要记录。”；记录晚餐吃了米饭",
    "请记录医生诊断：臀肌无力",
])
def test_explicit_outside_action_keeps_existing_tool_authority(message):
    from app.services.agent_input_tool_scope import scope_tools_for_analyzed_material

    tools = [{"function": {"name": name}} for name in ["health_query", "health_record", "knowledge_search"]]
    assert scope_tools_for_analyzed_material(tools, message) == tools


def test_material_scope_cannot_restore_tools_removed_by_other_guards():
    from app.services.agent_input_tool_scope import scope_tools_for_analyzed_material

    assert scope_tools_for_analyzed_material([], "分析以下建议：不要查记录。") == []


@pytest.mark.parametrize("body", [
    "请记录医生诊断：臀肌无力",
    "医生认为是臀肌无力，我应该怎么办？",
])
def test_direct_clinician_guard_cannot_promote_analyzed_material(body):
    from app.services.clinician_provenance_guard import classify_clinician_turn

    decision = classify_clinician_turn(f"分析以下建议：{body}")
    assert decision.kind == "none"
    assert decision.content_start is None


def test_clinician_feedback_spans_bind_only_outside_explicit_write():
    from datetime import datetime
    from app.services.agent_executor import _bind_doctor_feedback_args_to_turn
    from app.services.clinician_provenance_guard import classify_clinician_turn

    decision = classify_clinician_turn(
        "分析以下建议：“请记录医生诊断：引用中的膝盖疼痛。”；请记录医生诊断：臀肌无力"
    )
    assert decision.kind == "explicit_doctor_feedback_write"
    args = _bind_doctor_feedback_args_to_turn(decision, reference_now=datetime(2026, 9, 12))
    assert args["assessment"] == "臀肌无力"
    assert decision.raw[decision.content_start:decision.content_end] == "臀肌无力"


@pytest.mark.asyncio
async def test_quoted_clinician_statement_does_not_block_outside_query(
    db, auth_user_and_headers, monkeypatch,
):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    seen = []

    async def provider(messages, tools):
        seen.append({tool["function"]["name"] for tool in tools})
        yield {"type": "content", "text": "本次还没有查询结果。"}
        yield {"type": "finish", "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_build_system_prompt", lambda *a, **k: "Read user records.")
    monkeypatch.setattr(executor, "_call_llm_stream", provider)
    events = [event async for event in executor.run_stream(
        user.id, "分析以下建议：“医生说是臀肌无力。”；查询我今天吃了什么",
    )]
    assert seen and "health_query" in seen[0]
    assert events[-1]["data"]["perf"]["agent_kernel"] == "pi"
