"""Composite running advice binds history, not weather or answer formatting."""
from dataclasses import replace

import pytest

from app.services.agent_kernel.read_task_scope import resolve_owned_read_scope
from tests.test_longitudinal_read_scope_policy import decide, snapshot


REQUEST = (
    "基于我的身体状况，以及最近的饮食睡眠，我还有现在的杭州的天气，"
    "分析是否适合跑步以及跑多远，怎么跑，注意事项。给我详细的分析，"
    "最终生成一个 HTML 页面。"
)


@pytest.mark.parametrize("text,days", [
    (REQUEST, 7),
    (REQUEST.replace("最近的", "近3天的"), 3),
    (REQUEST.replace("饮食睡眠", "睡眠和饮食"), 7),
    (REQUEST.replace("我还有现在的杭州的天气", "以及今天的上海天气"), 7),
    (REQUEST.replace("，最终生成一个 HTML 页面", ""), 7),
])
def test_running_question_binds_only_requested_owned_history(text, days):
    turn = snapshot(text)
    scope = resolve_owned_read_scope(turn)
    assert scope is not None
    assert {q["dimension"] for q in scope.queries} == {"diet", "sleep"}
    assert all(q["days"] == days and q["end_date"] == "2026-09-13" for q in scope.queries)
    assert ("default_recent_7_days" in scope.limitations) == (days == 7)
    for dimension in ("diet", "sleep"):
        result = decide({"dimension": dimension}, text=text)
        assert result.action == "allow", result.reason
        assert result.normalized_args == scope.query(dimension)
    assert turn.envelope.text == text  # Weather and HTML remain model-visible.


@pytest.mark.parametrize("text", [
    REQUEST.replace("我的身体", "妈妈的身体"),
    REQUEST.replace("最近的饮食", "最近小王的饮食"),
    REQUEST.replace("饮食睡眠", "饮食和妈妈的睡眠"),
    REQUEST.replace("最近的", "近32天的"),
    REQUEST.replace("最近的", "最近7天到昨天的"),
    REQUEST.replace("最近的", "昨天下午的"),
    REQUEST + "只看上午。",
    REQUEST + "只分析睡眠。",
    REQUEST + "不要查询我的记录。",
    REQUEST + "删除昨天的记录。",
    REQUEST + "只查2020-01-01。",
    "如果可以，" + REQUEST,
    "解释例句：“" + REQUEST + "”",
    "    " + REQUEST,
    "```\n" + REQUEST + "\n```",
    REQUEST.replace("我的身体状况", "我的身体状况和朋友的病史"),
    REQUEST.replace("HTML 页面", "HTML 页面并查询基因"),
    REQUEST.replace("杭州的天气", "杭州的天气仅查询上午"),
    REQUEST.replace("杭州的天气", "杭州只查上午的天气"),
])
def test_composite_question_never_erases_unknown_or_restrictive_clauses(text):
    assert resolve_owned_read_scope(snapshot(text)) is None
    assert decide({"dimension": "sleep", "days": 7}, text=text).action == "block"


@pytest.mark.parametrize("args", [
    {"dimension": "workout"}, {"dimension": "illness"},
    {"dimension": "supplements"}, {"dimension": "genetic"},
    {"dimension": "sleep", "days": 30},
    {"dimension": "sleep", "user_id": 42},
    {"dimension": "sleep", "start_date": "2020-01-01"},
    {"dimension": "sleep", "timezone": "UTC"},
])
def test_running_advice_does_not_expand_history_authority(args):
    assert decide(args, text=REQUEST).action == "block"


def test_composite_owner_must_match_authenticated_context_and_cannot_write():
    turn = snapshot(REQUEST)
    assert resolve_owned_read_scope(replace(turn, context=replace(turn.context, user_id=42))) is None
    assert decide({"record_type": "workout", "data": {"duration": 30}},
                  text=REQUEST, tool="health_record").action == "block"


def test_explicit_public_weather_is_scoped_separately_from_health_history():
    from app.services.agent_input_tool_scope import scope_tools_for_owned_read

    tools = [{"function": {"name": name}} for name in (
        "health_query_batch", "environment_check", "health_record", "health_analysis")]
    scoped = scope_tools_for_owned_read(tools, resolve_owned_read_scope(snapshot(REQUEST)))
    assert [t["function"]["name"] for t in scoped] == ["health_query_batch", "environment_check"]
    assert scope_tools_for_owned_read([], resolve_owned_read_scope(snapshot(REQUEST))) == []
    result = decide({}, text=REQUEST, tool="environment_check")
    assert result.action == "allow"
    assert result.normalized_args == {"city": "杭州", "check_type": "weather"}
    for args in ({"city": "北京"}, {"check_type": "forecast"}, {"days": 30}, {"user_id": 42}):
        assert decide(args, text=REQUEST, tool="environment_check").action == "block"
    pure = "查询我最近的饮食和睡眠并分析"
    assert decide({}, text=pure, tool="environment_check").action == "block"


@pytest.mark.parametrize("domains", ["睡眠", "饮食", "睡眠和睡眠"])
@pytest.mark.parametrize("has_weather", [False, True])
def test_single_domain_composite_cannot_use_broad_analysis(domains, has_weather):
    from app.services.agent_input_tool_scope import scope_tools_for_owned_read

    text = REQUEST.replace("饮食睡眠", domains)
    if not has_weather:
        text = text.replace("我还有现在的杭州的天气，", "")
    scope = resolve_owned_read_scope(snapshot(text))
    assert scope is not None and len(scope.queries) == 1
    tools = [{"function": {"name": name}} for name in (
        "health_query", "environment_check", "health_record", "health_analysis")]
    expected = ["health_query", "environment_check"] if has_weather else ["health_query"]
    assert [t["function"]["name"] for t in scope_tools_for_owned_read(tools, scope)] == expected
    assert decide({"analysis_type": "comprehensive", "days": 30},
                  text=text, tool="health_analysis").action == "block"
