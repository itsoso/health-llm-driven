# -*- coding: utf-8 -*-
"""把 orchestrator 的 specialist 适配成 Agent 可调用的工具(RFC 方向一 Phase A)。

背景:specialist 本是「读 Twin → 出结构化 SpecialistFinding」的纯函数,由
orchestrator 按 classify_intent 关键字路由调度。Agent Native 化的第一步,是
把它们并入 agent_executor 已成熟的 tool-calling 循环,让主 Agent 自主决定
调哪个、调几次、怎么组合——而不再依赖硬编码路由。

本模块只做「适配」:不改 specialist 内部逻辑;构建 Twin → 调 specialist.run →
把 SpecialistFinding 序列化成给 LLM 看的紧凑文本。

⚠️ SafetyGuardian 不在此暴露——安全裁决永远走确定性旁路 + 审计,不交给
Agent 自主调用(见 RFC「不可动摇的边界」)。

flag: settings.agent_specialist_tools(默认 False)。关闭时这些工具不注册,
行为与现状完全一致;开启后才进入灰度验证。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 可被 Agent 自主调用的 specialist(故意排除 safety_guardian)。
# key = tool 名(给 LLM), value = (specialist.name, 中文描述)
SPECIALIST_TOOLS: Dict[str, tuple] = {
    "analyze_recovery": ("recovery_coach", "评估恢复就绪度(HRV/睡眠/压力/身体电量加权打分),给恢复建议"),
    "analyze_fuel": ("fuel_strategist", "评估营养/热量缺口与蛋白目标,含基因驱动的饮食建议"),
    "analyze_movement": ("movement_coach", "评估训练负荷(ACWR)× 恢复就绪度,给运动处方"),
    "analyze_mental": ("mental_health_companion", "心理状态评估 + 非药物支持(危机检测走安全旁路)"),
    "analyze_hypertension": ("hypertension_specialist", "血压分级(ACC/AHA)与降压管理建议"),
    "analyze_metabolic": ("metabolic_specialist", "代谢综合征判定 + CGM 血糖时间在范围(TIR)分析"),
    "analyze_rhinitis": ("rhinitis_specialist", "鼻炎症状分级 + 环境(AQI/湿度)关联与用药依从"),
    "analyze_longitudinal": ("longitudinal_analyst", "长期趋势 + 干预事件×指标变化的因果叙事"),
}

# 只暴露这些工具的 schema(其余 specialist 如 knowledge/supplement 已有专门工具,不重复)
def specialist_tool_schemas() -> List[Dict[str, Any]]:
    """返回 specialist 工具的 OpenAI function schema 列表。"""
    schemas = []
    for tool_name, (_sp_name, desc) in SPECIALIST_TOOLS.items():
        schemas.append({
            "type": "function",
            "function": {
                "name": tool_name,
                "description": f"{desc}。读取用户的 Digital Health Twin 后给出结构化分析,不下医疗诊断。",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        })
    return schemas


def is_specialist_tool(tool_name: str) -> bool:
    return tool_name in SPECIALIST_TOOLS


def _finding_to_text(finding) -> str:
    """SpecialistFinding → 给 LLM 的紧凑文本(不回吐原始 JSON,呼应 SKILL 约束)。"""
    parts = []
    if getattr(finding, "summary", ""):
        parts.append(finding.summary)
    for f in (getattr(finding, "findings", None) or [])[:8]:
        if isinstance(f, dict):
            # 取可读字段,避免整块 JSON
            label = f.get("label") or f.get("title") or f.get("name") or ""
            val = f.get("value") or f.get("detail") or f.get("text") or ""
            if label or val:
                parts.append(f"- {label}{('：' + str(val)) if val else ''}")
            else:
                parts.append(f"- {f}")
        else:
            parts.append(f"- {f}")
    refs = getattr(finding, "evidence_refs", None) or []
    if refs:
        parts.append(f"(证据:{', '.join(refs[:5])})")
    return "\n".join(parts) if parts else "(该专家本次无显著发现)"


def run_specialist_tool(db, user_id: Optional[int], tool_name: str) -> str:
    """执行一个 specialist 工具:构建 Twin → 调 specialist.run → 序列化。

    返回给 LLM 的文本;失败给友好兜底,不泄漏原始异常/JSON。
    """
    if not is_specialist_tool(tool_name):
        return f"Error: 未知专家工具 {tool_name}"
    if not user_id:
        return "Error: 缺少用户身份,无法读取健康数据"
    sp_name, _desc = SPECIALIST_TOOLS[tool_name]
    try:
        from app.orchestrator.specialists import get_specialist
        from app.twin.builder import build_twin
        sp = get_specialist(sp_name)
        if sp is None:
            return f"暂时无法调用「{sp_name}」专家。"
        twin = build_twin(db, user_id, use_cache=True)
        finding = sp.run(twin, {})  # 工具化路径不依赖 orchestrator 的共享 ctx
        return _finding_to_text(finding)
    except Exception as e:  # noqa: BLE001
        logger.warning("[specialist_tool] %s 执行失败: %s", tool_name, e)
        return f"「{sp_name}」分析暂时没成功,你可以稍后再试,或换个问法。"
