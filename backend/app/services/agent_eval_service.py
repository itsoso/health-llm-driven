# -*- coding: utf-8 -*-
"""Agent eval / 可观测看板聚合(RFC 方向九,Phase3 横切赋能)。

主动化 + 飞轮放量的前提:不可观测就不敢放量、会骚扰用户而不自知、烧钱不自知。
数据全在(agent_audit_log 已埋 safety/orchestrator/specialist/memory/longevity_watch
+ ActionCard outcome),这里只做去标识聚合视图,服务全产品(不只抗衰)。

去标识:只出计数/比率/分位,绝不含 user_id。
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.action_card import ActionCard
from app.models.agent_audit_log import AgentAuditLog


def _percentile(values: list[float], p: float) -> Optional[float]:
    """线性插值分位数(p∈[0,1])。空 → None。无 numpy 依赖。"""
    xs = sorted(v for v in values if v is not None)
    if not xs:
        return None
    if len(xs) == 1:
        return round(float(xs[0]), 1)
    k = (len(xs) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(xs) - 1)
    frac = k - lo
    return round(xs[lo] + (xs[hi] - xs[lo]) * frac, 1)


def agent_eval_dashboard(db: Session, days: int = 30) -> dict[str, Any]:
    """近 days 天的 agent eval 聚合(去标识)。"""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    rows = (
        db.query(AgentAuditLog)
        .filter(AgentAuditLog.created_at >= cutoff)
        .all()
    )

    # ① 活动量:按 agent_type 计数
    activity: dict[str, int] = {}
    orch_ms: list[float] = []
    proactive = {"triggers": 0, "notable": 0, "notified": 0,
                 "improved": 0, "regressed": 0, "stable": 0}
    for r in rows:
        at = r.agent_type or "unknown"
        activity[at] = activity.get(at, 0) + 1
        # ② orchestrator 延迟
        if at == "orchestrator" and r.total_ms is not None:
            orch_ms.append(float(r.total_ms))
        # ③ 主动 Agent(所有 *_watch:longevity / trajectory / …)命中/推送
        if at.endswith("_watch"):
            d = r.result_detail or {}
            proactive["triggers"] += 1
            if d.get("notable"):
                proactive["notable"] += 1
            if d.get("notified"):
                proactive["notified"] += 1
            k = (d.get("kind") or "").lower()
            if k in ("improved", "regressed", "stable"):
                proactive[k] += 1

    n_trig = proactive["triggers"]
    proactive_view = {
        **proactive,
        "notable_rate": round(proactive["notable"] / n_trig, 3) if n_trig else None,
        "notified_rate": round(proactive["notified"] / n_trig, 3) if n_trig else None,
    }

    # ④ 闭环 outcome 分布(跨用户,去标识)
    closed_rows = (
        db.query(ActionCard.outcome)
        .filter(ActionCard.outcome.isnot(None))
        .all()
    )
    outcomes: dict[str, int] = {}
    for (oc,) in closed_rows:
        key = (oc or "unknown").lower()
        outcomes[key] = outcomes.get(key, 0) + 1
    graded_total = sum(outcomes.values())
    closed_loop = {
        "graded_total": graded_total,
        "distribution": outcomes,
        "improvement_rate": (
            round(outcomes.get("improved", 0) / graded_total, 3) if graded_total else None
        ),
    }

    return {
        "window_days": days,
        "activity": activity,                    # agent_type → 次数
        "orchestrator_latency_ms": {
            "count": len(orch_ms),
            "p50": _percentile(orch_ms, 0.50),
            "p95": _percentile(orch_ms, 0.95),
        },
        "proactive_agent": proactive_view,       # longevity_watch 主动推送质量
        "closed_loop": closed_loop,              # N-of-1 评分分布
        "note": "去标识聚合;闭环分布为全历史,其余为近 window_days 天。",
    }
