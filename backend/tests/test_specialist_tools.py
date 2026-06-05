# -*- coding: utf-8 -*-
"""RFC 方向一 Phase A 回归:specialist 工具化 + 安全边界 + flag 门控。

钉住三件事:
1. flag 门控:默认关时工具列表不含 analyze_*;开时才出现(行为不破坏现状)
2. 安全边界:safety_guardian 永远不被暴露为 Agent 可自主调用的工具
3. 适配器:能把 specialist.run 的结构化输出序列化成给 LLM 的文本,失败给友好兜底(不泄漏原始异常)
"""
from unittest.mock import patch, MagicMock

import pytest


def test_safety_guardian_not_exposed_as_tool():
    """安全裁决永不交给 Agent 自主调用(RFC 不可动摇的边界)。"""
    from app.services.specialist_tools import SPECIALIST_TOOLS
    exposed = {v[0] for v in SPECIALIST_TOOLS.values()}
    assert "safety_guardian" not in exposed
    # 也不能有任何工具名带 safety
    assert not any("safety" in t for t in SPECIALIST_TOOLS)


def test_longevity_tool_exposed():
    """LongevitySpecialist 被暴露为 Agent 工具 analyze_longevity → 'longevity'。"""
    from app.services.specialist_tools import SPECIALIST_TOOLS, is_specialist_tool
    assert "analyze_longevity" in SPECIALIST_TOOLS
    assert SPECIALIST_TOOLS["analyze_longevity"][0] == "longevity"
    assert is_specialist_tool("analyze_longevity") is True
    # 仍守安全边界:工具名不含 safety
    assert "safety" not in "analyze_longevity"


def test_flag_gating_off_unchanged():
    """flag 默认关:工具列表不含 specialist 分析工具(现状不破坏)。"""
    from app.config import settings
    from app.services.tool_schema_registry import get_health_tools
    old = settings.agent_specialist_tools
    settings.agent_specialist_tools = False
    try:
        names = [t["function"]["name"] for t in get_health_tools()]
        assert not any(n.startswith("analyze_") for n in names)
    finally:
        settings.agent_specialist_tools = old


def test_flag_gating_on_adds_specialist_tools():
    """flag 开:追加 specialist 工具,且不与已有动作工具重名。"""
    from app.config import settings
    from app.services.tool_schema_registry import get_health_tools
    old = settings.agent_specialist_tools
    settings.agent_specialist_tools = True
    try:
        names = [t["function"]["name"] for t in get_health_tools()]
        assert "analyze_recovery" in names
        assert "health_query" in names  # 原有工具仍在
        assert len(names) == len(set(names))  # 无重名
    finally:
        settings.agent_specialist_tools = old


def test_run_specialist_tool_serializes_finding():
    """适配器:specialist.run 的 SpecialistFinding → 紧凑文本(不回吐原始 JSON)。"""
    from app.services import specialist_tools as st

    fake_finding = MagicMock()
    fake_finding.summary = "恢复就绪度偏低(58/100)"
    fake_finding.findings = [{"label": "HRV", "value": "偏低"}, {"label": "睡眠", "value": "6.1h"}]
    fake_finding.evidence_refs = ["guideline:hrv-2021"]
    fake_sp = MagicMock()
    fake_sp.run.return_value = fake_finding

    with patch("app.orchestrator.specialists.get_specialist", return_value=fake_sp), \
         patch("app.twin.builder.build_twin", return_value=MagicMock()):
        out = st.run_specialist_tool(db=MagicMock(), user_id=1, tool_name="analyze_recovery")

    assert "恢复就绪度偏低" in out
    assert "HRV" in out and "睡眠" in out
    assert "guideline:hrv-2021" in out
    assert "{" not in out  # 不回吐原始 JSON


def test_run_specialist_tool_failure_friendly():
    """specialist 抛异常 → 友好兜底,不泄漏原始异常文本。"""
    from app.services import specialist_tools as st
    fake_sp = MagicMock()
    fake_sp.run.side_effect = ValueError("internal boom xyz")
    with patch("app.orchestrator.specialists.get_specialist", return_value=fake_sp), \
         patch("app.twin.builder.build_twin", return_value=MagicMock()):
        out = st.run_specialist_tool(db=MagicMock(), user_id=1, tool_name="analyze_recovery")
    assert "boom xyz" not in out
    assert "稍后再试" in out or "没成功" in out


def test_run_specialist_tool_unknown_and_no_user():
    from app.services.specialist_tools import run_specialist_tool, is_specialist_tool
    assert is_specialist_tool("analyze_recovery") is True
    assert is_specialist_tool("health_query") is False
    assert "未知" in run_specialist_tool(db=MagicMock(), user_id=1, tool_name="analyze_nope")
    assert "用户" in run_specialist_tool(db=MagicMock(), user_id=None, tool_name="analyze_recovery")


@pytest.mark.asyncio
async def test_executor_dispatches_specialist_tool(db):
    """agent_executor._execute_tool 能 dispatch specialist 工具到适配器。"""
    from app.services.agent_executor import AgentExecutor
    from app.services import specialist_tools as st
    ex = AgentExecutor(db)
    ex._current_user_id = 1
    with patch.object(st, "run_specialist_tool", return_value="恢复分析结果X") as m:
        # 绕过 validate_tool_call(specialist 工具无参数), 直接验 dispatch
        out = await ex._execute_tool("analyze_recovery", {}, user_token="t")
    assert out == "恢复分析结果X"
    assert m.called
