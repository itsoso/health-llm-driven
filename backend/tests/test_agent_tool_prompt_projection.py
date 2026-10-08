"""Provider descriptions may shrink; schemas and read authority cannot change."""

from copy import deepcopy
from datetime import datetime
import json

import pytest

from app.services.agent_kernel.intent_frame import build_intent_frame
from app.services.agent_kernel.read_task_scope import OwnedReadScope, resolve_owned_read_scope
from app.services.agent_kernel.types import AgentEnvelope, ExecutionContext, TurnSnapshot
from app.services.tool_schema_registry import HEALTH_TOOLS


def read_scope(text="分析我最近7天的睡眠血氧"):
    env = AgentEnvelope(user_id=41, channel="typed", text=text)
    context = ExecutionContext(
        current_time=datetime.fromisoformat("2026-10-04T09:00:00+08:00"),
        timezone="Asia/Shanghai", user_id=41, channel="typed",
    )
    scope = resolve_owned_read_scope(TurnSnapshot(env, context, build_intent_frame(env, context)))
    assert scope is not None
    return scope


def read_tools():
    return deepcopy([tool for tool in HEALTH_TOOLS if tool["function"]["name"] in {
        "health_query", "health_query_batch", "knowledge_search",
    }])


def test_real_scope_shortens_descriptions_without_mutating_authorized_schema():
    from app.services.agent_tool_prompt_projection import project_owned_read_tool_descriptions

    tools = read_tools()
    before = deepcopy(tools)
    result = project_owned_read_tool_descriptions(tools, read_scope())
    assert tools == before
    assert [t["function"]["name"] for t in result] == [t["function"]["name"] for t in tools]
    for old, new in zip(tools, result):
        assert old["function"]["parameters"] == new["function"]["parameters"]
    assert len(json.dumps(result, ensure_ascii=False)) < len(json.dumps(tools, ensure_ascii=False)) * 0.8
    query = result[0]["function"]["description"]
    assert "sleep" in query and "spo2" in query
    assert "基因位点" not in query
    assert "手动录入" not in query
    assert "未验证睡眠期/连续监测" in query
    assert "不推算 ODI" in query and "不把无数据当正常" in query
    assert "来源和覆盖情况" in query
    assert "昨晚睡眠按醒来归属日读取" in query
    assert "不能使用旧记录替代" in query


@pytest.mark.parametrize("text,kept,dropped", [
    ("分析我昨天的饮食", "今日饮食记录", "夜间血氧逐分钟"),
    ("分析我最近7天的运动", "结构化运动", "用户**手动录入**"),
    ("分析我最近7天的补剂", "补剂服用依从率", "基因位点"),
    ("分析我昨晚睡眠", "睡眠评分", "OSAHS"),
])
def test_only_bound_dimension_entries_are_included(text, kept, dropped):
    from app.services.agent_tool_prompt_projection import project_owned_read_tool_descriptions

    result = project_owned_read_tool_descriptions(read_tools(), read_scope(text))
    for tool in result[:2]:
        description = tool["function"]["description"]
        assert kept in description
        assert dropped not in description


def test_batch_keeps_calendar_aggregation_units_unknown_value_and_spo2_constraints():
    from app.services.agent_tool_prompt_projection import project_owned_read_tool_descriptions

    batch = project_owned_read_tool_descriptions(read_tools(), read_scope())[1]["function"]
    description = batch["description"]
    for fragment in (
        "1-6 条子查询", "日历查询不支持 agg/compare", "不得用 days 代替昨天或昨晚",
        "trend = 首尾差", "数值聚合仅对可穿戴日指标有效", "其他维度 agg 会被忽略",
        "diff=a-b, ratio=a/b", "value, unit, n", "未知 dimension / 未知 agg / 超过 6 条",
        "来源和覆盖情况", "不推算 ODI", "不把无数据当正常", "不确诊",
    ):
        assert fragment in description
    assert "完整示例" not in description


@pytest.mark.parametrize("scope", [
    None, object(), OwnedReadScope(()), OwnedReadScope(({},)),
    OwnedReadScope(({"dimension": "unknown"},)),
    OwnedReadScope(({"dimension": "sleep"}, {"dimension": "genetic"})),
    OwnedReadScope(({"dimension": ["sleep"]},)),
])
def test_unknown_scope_is_unchanged(scope):
    from app.services.agent_tool_prompt_projection import project_owned_read_tool_descriptions

    tools = read_tools()
    assert project_owned_read_tool_descriptions(tools, scope) is tools


@pytest.mark.parametrize("change", ["description", "parameters", "type"])
def test_specialized_or_sealed_contract_is_not_projected(change):
    from app.services.agent_tool_prompt_projection import project_owned_read_tool_descriptions

    tools = read_tools()
    if change == "description":
        tools[0]["function"]["description"] += "\n专科封闭任务：只查询已选指标。"
    elif change == "parameters":
        tools[0]["function"]["parameters"]["properties"]["dimension"]["enum"] = ["sleep"]
    else:
        tools[0]["type"] = "specialized"
    original = deepcopy(tools[0])
    result = project_owned_read_tool_descriptions(tools, read_scope())
    assert result[0] is tools[0]
    assert result[0] == original


def test_never_adds_missing_tool_and_preserves_extension_fields_and_idempotency():
    from app.services.agent_tool_prompt_projection import project_owned_read_tool_descriptions

    tools = read_tools()[1:]
    tools[0]["cache_control"] = {"type": "ephemeral"}
    tools[0]["function"]["strict"] = True
    result = project_owned_read_tool_descriptions(tools, read_scope())
    assert [t["function"]["name"] for t in result] == ["health_query_batch", "knowledge_search"]
    assert result[0]["cache_control"] == {"type": "ephemeral"}
    assert result[0]["function"]["strict"] is True
    assert result[1] is tools[1]
    assert project_owned_read_tool_descriptions(result, read_scope()) == result
    result[0]["function"]["parameters"]["required"].append("changed_by_provider")
    assert tools[0]["function"]["parameters"]["required"] == ["queries"]


def test_unknown_query_guide_format_falls_back_to_full_registry(monkeypatch):
    from app.services import agent_tool_prompt_projection as projection

    changed = deepcopy(HEALTH_TOOLS)
    changed[0]["function"]["description"] = "新版结构，尚未支持安全投影"
    monkeypatch.setattr(projection, "HEALTH_TOOLS", changed)
    tools = deepcopy(changed[:2])
    assert projection.project_owned_read_tool_descriptions(tools, read_scope()) is tools


def test_unknown_batch_guide_format_keeps_full_batch(monkeypatch):
    from app.services import agent_tool_prompt_projection as projection

    changed = deepcopy(HEALTH_TOOLS)
    changed[1]["function"]["description"] = "新版批查询结构，尚未支持安全投影"
    monkeypatch.setattr(projection, "HEALTH_TOOLS", changed)
    tools = deepcopy(changed[:2])
    result = projection.project_owned_read_tool_descriptions(tools, read_scope())
    assert result[1] is tools[1]


def test_registry_updates_to_relevant_safety_prose_are_reused(monkeypatch):
    from app.services import agent_tool_prompt_projection as projection

    changed = deepcopy(HEALTH_TOOLS)
    description = changed[0]["function"]["description"]
    changed[0]["function"]["description"] = description.replace(
        "不确诊。", "不确诊。新增经过审核的限制。",
    )
    monkeypatch.setattr(projection, "HEALTH_TOOLS", changed)
    tools = deepcopy(changed[:2])
    result = projection.project_owned_read_tool_descriptions(tools, read_scope())
    assert all("新增经过审核的限制" in t["function"]["description"] for t in result)
