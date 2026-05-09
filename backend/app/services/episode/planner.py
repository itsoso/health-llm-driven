"""Planner — v3 三层瘦身架构的中间层.

MVP (Increment 1): 不调 LLM, 走 Protocol 模板. 输出结构化 ActionGraph.
Increment 2: 加入 MiniMax-M2.5 调用做文案层个性化 (Coach Persona), 保持
           JSON schema 严格约束 + retry once. Planner 接口保持兼容:

    plan(episode_context) -> ActionGraph

这样后面换 multi-agent fan-out (v3 预留开关之一) 也不用改上游.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from app.services.episode.protocol_registry import (
    Protocol, ProtocolAction, get_registry,
)
from app.services.episode.risk_tagger import (
    RiskAssessment, assess_run_episode,
)
from app.services.episode.validator import validate_actions

logger = logging.getLogger(__name__)


@dataclass
class PlannedAction:
    sequence: int
    title: str
    body: Optional[str]
    icon: Optional[str]
    action_type: str
    template_id: str
    evidence_id: Optional[str]
    time_window_start: Optional[datetime]
    time_window_end: Optional[datetime]
    condition_expr: Optional[str]
    completion_check: Optional[Dict[str, Any]]
    risk_condition: Optional[Dict[str, Any]]


@dataclass
class ActionGraph:
    protocol_slug: str
    protocol_version: str
    risk: RiskAssessment
    headline: str
    actions: List[PlannedAction] = field(default_factory=list)
    disclaimer: str = ""
    # L4 熔断时, 这里只保留一个 emergency template, actions 会被替换.
    emergency: bool = False


# ─────────────────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────────────────

def plan_run_recovery(
    occurred_at: datetime,
    context: Dict[str, Any],
) -> ActionGraph:
    """把跑步 episode context 规划成 ActionGraph.

    1. Safety gate (risk_tagger) — L4 直接出 emergency template, 不进 planner
    2. Protocol match — registry.match('run', ctx)
    3. 模板填充 + time_window 实际时间计算
    4. Validator — 黑名单拦截 + disclaimer
    """
    risk = assess_run_episode(context)

    # L4 熔断 — 不走 Protocol, 直接 emergency template
    if risk.level == "L4":
        logger.warning("L4 redflag for run episode: %s", risk.flags)
        return _emergency_graph(occurred_at, risk)

    registry = get_registry()
    proto = registry.match("run", context)
    if proto is None:
        logger.warning("No protocol matched for run context, falling back to normal")
        proto = registry.get("post_run_recovery_normal")
    if proto is None:
        # 连 normal 都没有, 只能空 graph
        return ActionGraph(
            protocol_slug="none", protocol_version="0",
            risk=risk, headline="暂无合适的恢复方案, 注意补水和休息.",
        )

    planned = _fill_template(proto, occurred_at)

    # Validator — MVP 规则版
    val = validate_actions([
        ProtocolAction(
            sequence=p.sequence,
            template_id=p.template_id,
            action_type=p.action_type,
            title=p.title,
            body=p.body,
            evidence_id=p.evidence_id,
        )
        for p in planned
    ])

    if val.blocked_actions:
        logger.warning("Validator 拦截 %d 条 actions", len(val.blocked_actions))
        planned = [p for i, p in enumerate(planned) if i not in val.blocked_actions]

    headline = _make_headline(proto, risk, context)

    return ActionGraph(
        protocol_slug=proto.slug,
        protocol_version=proto.version,
        risk=risk,
        headline=headline,
        actions=planned,
        disclaimer=val.disclaimer,
        emergency=False,
    )


# ─────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────

def _fill_template(proto: Protocol, occurred_at: datetime) -> List[PlannedAction]:
    out: List[PlannedAction] = []
    for a in proto.actions:
        tw_start = tw_end = None
        if a.time_window:
            tw_start = occurred_at + timedelta(minutes=a.time_window.offset_min_start)
            tw_end = occurred_at + timedelta(minutes=a.time_window.offset_min_end)
        out.append(PlannedAction(
            sequence=a.sequence,
            title=a.title,
            body=a.body,
            icon=a.icon,
            action_type=a.action_type,
            template_id=a.template_id,
            evidence_id=a.evidence_id,
            time_window_start=tw_start,
            time_window_end=tw_end,
            condition_expr=a.condition_expr,
            completion_check=a.completion_check.model_dump() if a.completion_check else None,
            risk_condition=a.risk_condition.model_dump() if a.risk_condition else None,
        ))
    return sorted(out, key=lambda x: x.sequence)


def _make_headline(proto: Protocol, risk: RiskAssessment, ctx: Dict[str, Any]) -> str:
    """v3 文案规则: 开头一句判定'恢复优先级: 高/中/低', 给用户心智锚点."""
    if risk.level == "L3":
        prio = "高"
        reason = "观察到风险信号"
    elif risk.level in ("L2",):
        prio = "中"
        reason = "有疼痛反馈, 以观察为主"
    elif risk.level == "L1":
        prio = "中"
        if "heat" in " ".join(risk.flags):
            reason = "高温后重点补液"
        elif "sleep_short" in " ".join(risk.flags):
            reason = "睡眠不足, 今晚要早睡"
        elif "acwr" in " ".join(risk.flags):
            reason = "训练负荷偏高"
        else:
            reason = "有可关注的标签"
    else:
        prio = "低"
        reason = "常规恢复即可"

    dist = ctx.get("distance_km")
    if dist:
        return f"本次恢复优先级: {prio} — {reason}. 跑了 {dist:.1f}km, 按下面节奏来."
    return f"本次恢复优先级: {prio} — {reason}."


def _emergency_graph(occurred_at: datetime, risk: RiskAssessment) -> ActionGraph:
    """L4 emergency template — 直接给就医指引, 跳过 Protocol."""
    actions = [
        PlannedAction(
            sequence=0,
            title="有急性症状 — 请立即就医或拨打 120",
            body="胸痛 / 晕厥 / 严重呼吸困难是急症信号, 不要等观察. "
                 "在等待就医时保持静坐, 身边有人陪伴.",
            icon="alert-circle",
            action_type="emergency_referral",
            template_id="emergency_redflag",
            evidence_id="redflag_emergency_protocol",
            time_window_start=occurred_at,
            time_window_end=occurred_at + timedelta(minutes=15),
            condition_expr=None,
            completion_check={"kind": "self_report", "prompt": "已联系医疗机构?"},
            risk_condition=None,
        ),
        PlannedAction(
            sequence=1,
            title="记录症状 + 起始时间, 告诉医生",
            body="具体症状 / 何时开始 / 是否缓解 / 伴随感觉. 医生会用得上.",
            icon="document-text",
            action_type="emergency_record",
            template_id="emergency_record_symptoms",
            evidence_id="redflag_emergency_protocol",
            time_window_start=occurred_at,
            time_window_end=occurred_at + timedelta(minutes=30),
            condition_expr=None,
            completion_check=None,
            risk_condition=None,
        ),
    ]
    return ActionGraph(
        protocol_slug="emergency",
        protocol_version="0.1.0",
        risk=risk,
        headline="⚠️ 检测到急性症状信号, 请立即就医. 本应用不能替代急救判断.",
        actions=actions,
        disclaimer="紧急情况下, 立即拨打 120 或前往最近急诊.",
        emergency=True,
    )
