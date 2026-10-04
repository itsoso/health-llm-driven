"""Equivalent retrospective verbs preserve exact owned read authority."""
from dataclasses import replace

import pytest

from app.services.agent_kernel.capability_policy import decide_tool_capability
from app.services.agent_kernel.read_task_scope import resolve_owned_read_scope
from app.services.agent_kernel.types import ToolExecutionRequest
from tests.test_longitudinal_read_scope_policy import snapshot


@pytest.mark.parametrize("verb", ["分析", "洞察", "复盘", "总结"])
@pytest.mark.parametrize("dimensions", [("sleep", "diet"), ("diet", "sleep")])
def test_retrospective_verbs_bind_same_owned_window(verb, dimensions):
    turn = snapshot(f"{verb}我最近7天的睡眠和饮食记录。")
    scope = resolve_owned_read_scope(turn)
    assert scope is not None
    expected = [{"dimension": d, "days": 7, "start_date": "2026-09-07",
                 "end_date": "2026-09-13", "timezone": "Asia/Shanghai"}
                for d in dimensions]
    decision = decide_tool_capability(turn, ToolExecutionRequest("health_query_batch", {
        "queries": [{"dimension": d, "days": 7} for d in dimensions],
    }))
    assert decision.action == "allow", decision.reason
    assert decision.normalized_args == {"queries": expected}


@pytest.mark.parametrize("verb", ["复盘", "总结"])
@pytest.mark.parametrize("text", [
    "{verb}我朋友最近7天的睡眠和饮食记录。",
    "{verb}小王最近7天的睡眠和饮食记录，给我建议。",
    "{verb}我最近7天的睡眠和小王的饮食记录。",
    "不要{verb}我最近7天的睡眠和饮食记录。",
    "假设{verb}我最近7天的睡眠和饮食记录。",
    "解释这句话：“{verb}我最近7天的睡眠和饮食记录。”",
    "{verb}我最近7天的睡眠和饮食记录，只看午睡前。",
    "{verb}我最近7天到昨天的睡眠和饮食记录。",
    "{verb}我最近32天的睡眠和饮食记录。",
    "{verb}我最近7天的睡眠和饮食记录，并删除饮食。",
])
def test_retrospective_verb_does_not_erase_owner_or_restrictions(verb, text):
    turn = snapshot(text.format(verb=verb))
    assert resolve_owned_read_scope(turn) is None
    decision = decide_tool_capability(turn, ToolExecutionRequest("health_query_batch", {
        "queries": [{"dimension": "sleep", "days": 7}, {"dimension": "diet", "days": 7}],
    }))
    assert decision.action == "block"


@pytest.mark.parametrize("changes", [
    {"dimension": "genetic"}, {"days": 30}, {"days": True},
    {"start_date": "2026-09-01"}, {"end_date": "2026-09-14"},
    {"timezone": "UTC"}, {"user_id": 42}, {"owner_id": 42}, {"tenant_id": 42},
])
def test_retrospective_read_rejects_model_expansion(changes):
    turn = snapshot("复盘我最近7天的睡眠和饮食记录。")
    decision = decide_tool_capability(turn, ToolExecutionRequest("health_query", {
        "dimension": "sleep", "days": 7, **changes,
    }))
    assert decision.action == "block"


def test_retrospective_read_requires_authenticated_owner_match():
    turn = snapshot("复盘我最近7天的睡眠和饮食记录。")
    assert resolve_owned_read_scope(replace(turn, context=replace(turn.context, user_id=42))) is None


@pytest.mark.parametrize("alias", [{"dimension": "food"}, {"dimension": "饮食"},
                                  {"dimension": " diet "}, {"type": "diet"}])
def test_batch_uses_same_registered_dimension_aliases_as_single(alias):
    turn = snapshot("分析我最近7天的睡眠和饮食记录。")
    decision = decide_tool_capability(turn, ToolExecutionRequest("health_query_batch", {
        "queries": [{**alias, "days": 7}, {"dimension": "sleep", "days": 7}],
    }))
    assert decision.action == "allow", decision.reason
    assert [q["dimension"] for q in decision.normalized_args["queries"]] == ["diet", "sleep"]
    assert all(q["start_date"] == "2026-09-07" and q["end_date"] == "2026-09-13"
               for q in decision.normalized_args["queries"])


@pytest.mark.parametrize("changes", [{"user_id": 42}, {"owner_id": 42}, {"tenant_id": 42},
    {"days": 30}, {"days": True}, {"start_date": "2026-09-01"},
    {"end_date": "2026-09-14"}, {"timezone": "UTC"}, {"period": "night"}])
def test_dimension_alias_never_discards_original_owner_or_window_fields(changes):
    turn = snapshot("分析我最近7天的睡眠和饮食记录。")
    decision = decide_tool_capability(turn, ToolExecutionRequest("health_query_batch", {
        "queries": [{"dimension": "food", "days": 7, **changes}, {"dimension": "sleep", "days": 7}],
    }))
    assert decision.action == "block"


def test_alias_does_not_allow_duplicate_or_extra_dimension():
    turn = snapshot("分析我最近7天的睡眠和饮食记录。")
    for dimensions in (("food", "diet"), ("food", "sleep", "heart_rate"), ("food", "gene")):
        decision = decide_tool_capability(turn, ToolExecutionRequest("health_query_batch", {
            "queries": [{"dimension": d, "days": 7} for d in dimensions],
        }))
        assert decision.action == "block"
