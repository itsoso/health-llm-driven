"""Only a closed current-owner water record can trim data examples."""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime
import json

import pytest

from app.services.agent_kernel.goal_spec import compile_goal_spec
from app.services.agent_kernel.intent_frame import build_intent_frame
from app.services.agent_kernel.types import ActionableReference, AgentEnvelope, ExecutionContext, TurnSnapshot
from app.services.tool_schema_registry import HEALTH_TOOLS


def record_snapshot(text="记录喝水250ml"):
    envelope = AgentEnvelope(user_id=41, channel="typed", text=text)
    context = ExecutionContext(
        current_time=datetime.fromisoformat("2026-10-04T09:00:00+08:00"),
        timezone="Asia/Shanghai", user_id=41, channel="typed",
    )
    intent = build_intent_frame(envelope, context)
    goal = compile_goal_spec(envelope=envelope, context=context, intent=intent)
    return TurnSnapshot(envelope, context, intent, goal=goal)


def project(tools, snapshot, **kwargs):
    from eval.experimental_record_projection import project_owned_record_data_descriptions

    return project_owned_record_data_descriptions(
        tools, snapshot, user_id=kwargs.pop("user_id", 41),
        current_message=kwargs.pop("current_message", snapshot.envelope.text), **kwargs,
    )


def record_tool(tools):
    return next(tool for tool in tools if tool["function"]["name"] == "health_record")


@pytest.mark.parametrize("text", [
    "记录喝水250ml", "请帮我记录饮水500毫升。", "今天记录我喝水1000ML",
    "记录喝水500毫升", "记下喝水250毫升", "记录喝水5000ml",
    "记录我今天喝水350毫升",
])
def test_closed_water_preserves_every_field_except_data_description(text):
    tools = deepcopy(HEALTH_TOOLS)
    before = deepcopy(tools)
    result = project(tools, record_snapshot(text))
    assert tools == before
    original_data = record_tool(tools)["function"]["parameters"]["properties"]["data"]
    projected_data = record_tool(result)["function"]["parameters"]["properties"]["data"]
    assert "water:" in projected_data["description"]
    assert "必填整数 1-5000" in projected_data["description"]
    assert "不要自己默认" in projected_data["description"]
    assert "diet:" not in projected_data["description"]
    restored = deepcopy(result)
    record_tool(restored)["function"]["parameters"]["properties"]["data"]["description"] = original_data["description"]
    assert restored == before
    assert len(json.dumps(result, ensure_ascii=False)) < len(json.dumps(tools, ensure_ascii=False)) - 3000
    assert project(result, record_snapshot(text)) == result


@pytest.mark.parametrize("text", [
    "记录喝水250ml，顺便记住我的鞋码42", "午餐吃了一个苹果，记一下体重70公斤",
    "帮爸爸记录喝水250毫升", "记录喝水250毫升再查天气", "喝水250毫升再查天气",
    "早上喝水一杯晚上喝水两杯", "记录午餐和刚才一样", "记录午餐吃了布洛芬200mg",
    "午餐鸡蛋顺便分析最近睡眠", "喝水250毫升胸痛怎么办", "记录喝水250ml胸痛怎么办",
    "医生说记录喝水250ml", "他说‘记录喝水250ml’", "记录喝水250ml给爸爸",
    "记录喝水和刚才一样", "记录喝水一杯", "记录喝水五百毫升", "喝水250ml",
    "记录喝水250", "记录喝水0ml", "记录喝水5001ml", "记录喝水1.5ml",
    "不要记录喝水250ml", "记录喝水250ml吗", "明天记录喝水250ml",
    "早餐吃了一个鸡蛋", "记录午餐吃了一个苹果",
    "昨天记录喝水0.5升", "前天记下喝水250毫升",
    "昨天记录我今天喝了350ml水", "今天记录我今天喝了350ml水",
    "记录我喝了500ml药水", "记录我喝了500ml", "记录我喝水500ml水",
    # Natural inverted wording currently has no server-bound simple-record goal.
    "记录我喝了500ml水", "记录我今天喝了350毫升水。", "记录我喝0.5L水",
])
def test_unclosed_or_out_of_scope_input_keeps_full_material(text):
    tools = deepcopy(HEALTH_TOOLS)
    assert project(tools, record_snapshot(text)) is tools


@pytest.mark.parametrize("change", [
    "owner", "context_owner", "no_owner", "message", "attachment", "media", "references",
    "ambiguity", "amount", "date", "lookup", "clarification", "evidence", "policy",
])
def test_unproven_snapshot_keeps_full_material(change):
    snapshot = record_snapshot()
    kwargs = {}
    if change == "owner":
        kwargs["user_id"] = 42
    elif change == "context_owner":
        snapshot = replace(snapshot, context=replace(snapshot.context, user_id=42))
    elif change == "no_owner":
        kwargs["user_id"] = None
        snapshot = replace(snapshot, envelope=replace(snapshot.envelope, user_id=None), context=replace(snapshot.context, user_id=None))
    elif change == "message":
        kwargs["current_message"] = "记录喝水500ml"
    elif change == "attachment":
        kwargs["has_attachment"] = True
    elif change == "media":
        snapshot = replace(snapshot, envelope=replace(snapshot.envelope, media=({"type": "image"},)))
    elif change == "references":
        snapshot = replace(snapshot, actionable_references=(ActionableReference("pending_write"),))
    elif change == "ambiguity":
        snapshot = replace(snapshot, intent=replace(snapshot.intent, ambiguity=("unresolved",)))
    elif change == "policy":
        snapshot = replace(snapshot, policy_mode="shadow")
    else:
        field, value = {
            "amount": ("target_values", (("amount_ml", "500"),)),
            "date": ("target_date", "2026-10-03"), "lookup": ("requires_lookup", True),
            "clarification": ("requires_clarification", True), "evidence": ("evidence", ("history",)),
        }[change]
        snapshot = replace(snapshot, goal=replace(snapshot.goal, **{field: value}))
    tools = deepcopy(HEALTH_TOOLS)
    assert project(tools, snapshot, **kwargs) is tools


@pytest.mark.parametrize("change", ["outer", "parameter", "type", "data"])
def test_specialized_contract_keeps_full_material(change):
    tools = deepcopy(HEALTH_TOOLS)
    tool = record_tool(tools)
    if change == "outer":
        tool["function"]["description"] += "专属任务"
    elif change == "parameter":
        tool["function"]["parameters"]["properties"]["record_type"]["enum"] = ["water"]
    elif change == "type":
        tool["type"] = "specialized"
    else:
        tool["function"]["parameters"]["properties"]["data"]["description"] += "新的全局限制"
    assert project(tools, record_snapshot()) == tools


@pytest.mark.parametrize("suffix", ["\n新的全局安全限制", "\nwater: duplicate", "\nunknown: new kind"])
def test_unknown_registry_layout_is_not_partially_parsed(monkeypatch, suffix):
    from eval import experimental_record_projection as module

    tools = deepcopy(HEALTH_TOOLS)
    record_tool(tools)["function"]["parameters"]["properties"]["data"]["description"] += suffix
    monkeypatch.setattr(module, "HEALTH_TOOLS", deepcopy(tools))
    assert project(tools, record_snapshot()) is tools


def test_missing_tools_extension_fields_and_updated_water_guidance(monkeypatch):
    from eval import experimental_record_projection as module

    tools = deepcopy(HEALTH_TOOLS)
    tool = record_tool(tools)
    tool["cache_control"] = {"type": "ephemeral"}
    tool["function"]["strict"] = True
    data = tool["function"]["parameters"]["properties"]["data"]
    data["description"] = data["description"].replace("不要自己默认", "不要自己默认；新增水记录限制")
    monkeypatch.setattr(module, "HEALTH_TOOLS", deepcopy(tools))
    result = project([tool], record_snapshot())
    assert len(result) == 1
    assert result[0]["cache_control"] == tool["cache_control"]
    assert result[0]["function"]["strict"] is True
    assert "新增水记录限制" in result[0]["function"]["parameters"]["properties"]["data"]["description"]
    assert project([], record_snapshot()) == []
    only_read = [tools[0]]
    assert project(only_read, record_snapshot()) == only_read


@pytest.mark.parametrize("change", ["no_tool", "no_description", "no_enum", "header"])
def test_unknown_canonical_record_shape_keeps_original(monkeypatch, change):
    from eval import experimental_record_projection as module

    tools = deepcopy(HEALTH_TOOLS)
    if change == "no_tool":
        tools = [tool for tool in tools if tool["function"]["name"] != "health_record"]
    else:
        properties = record_tool(tools)["function"]["parameters"]["properties"]
        if change == "no_description":
            properties["data"].pop("description")
        elif change == "no_enum":
            properties["record_type"].pop("enum")
        else:
            properties["data"]["description"] = "新版布局"
    monkeypatch.setattr(module, "HEALTH_TOOLS", deepcopy(tools))
    assert project(tools, record_snapshot()) is tools


@pytest.mark.parametrize("text", ["记录喝水0.5升。", "今天记录我喝水1L。", "记录喝水1升", "记录喝水0.25l"])
def test_liter_units_keep_full_material_after_live_quality_regression(text):
    tools = deepcopy(HEALTH_TOOLS)
    assert project(tools, record_snapshot(text)) is tools
