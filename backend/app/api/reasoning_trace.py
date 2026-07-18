"""Reasoning Trace API — 决策可解释性 (阶段 4.5 第 2 步 / 阶段 6 种子).

每条 trace 回答三个问题:
  - **什么** 决策? (rule / specialist)
  - **为什么** 触发? (触发数据 + 阈值 + 引用)
  - **结果** 是什么? (ActionCard / 推送)

主数据源:
  - AnomalyAlert (确定性规则决策, 每条 = 1 个 trace)
  - AgentAuditLog (orchestrator / safety 评估历史, 有 alerts_count > 0 的算)

关联:
  - ActionCard (creator_specialist + source_id 回查)
  - MemoryFact (metric_key / subject 模糊匹配)

B 端意义: 可解释性 (保险/医院/慢病管理的硬门槛).
个人意义: "为什么 AI 说我 HRV 偏低" → 展开 trace 看数据+规则+引用.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.action_card import ActionCard
from app.models.agent_audit_log import AgentAuditLog
from app.models.anomaly_alert import AnomalyAlert
from app.models.memory_fact import MemoryFact
from app.models.user import User
from app.services.reasoning_explainer import (
    explain_safety_alert,
    explain_specialist_finding,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reasoning-trace", tags=["reasoning-trace"])


# ------------------------------------------------------------
# Severity → 置信度估算 (确定性规则: 高 severity = 高置信)
# ------------------------------------------------------------

_SEV_CONF = {
    "critical": 0.95,
    "warning": 0.85,
    "info": 0.70,
}

# metric_name → 规则引擎/类别
_RULE_CATEGORY = {
    "resting_heart_rate": "vitals",
    "hrv": "vitals",
    "sleep_score": "vitals",
    "stress_level": "vitals",
    "spo2_avg": "vitals",
    "body_battery": "vitals",
}


def _build_anomaly_trace(db: Session, alert: AnomalyAlert) -> Dict[str, Any]:
    """AnomalyAlert → 决策 trace."""
    # Outcome: 关联的 ActionCard (source_type=anomaly_alert, source_id=alert.id)
    outcome_card = (
        db.query(ActionCard)
        .filter(
            ActionCard.user_id == alert.user_id,
            ActionCard.source_type == "anomaly_alert",
            ActionCard.source_id == str(alert.id),
        )
        .first()
    )

    # Related memory: 按 metric_name 模糊匹配 (最近 14 天, 排除已 supersede 的)
    since = datetime.now(timezone.utc) - timedelta(days=14)
    related_facts_q = (
        db.query(MemoryFact)
        .filter(
            MemoryFact.user_id == alert.user_id,
            MemoryFact.superseded_at.is_(None),  # is_active 是 @property, 用底层字段
            MemoryFact.created_at >= since,
        )
    )
    if alert.metric_name:
        # metric_name='hrv' → subject 含 'HRV'/'hrv'
        like = f"%{alert.metric_name}%"
        related_facts_q = related_facts_q.filter(MemoryFact.subject.ilike(like))
    related_facts = related_facts_q.limit(5).all()

    severity = (alert.severity or "info").lower()
    conf = _SEV_CONF.get(severity, 0.7)

    from app.services.memory_service import effective_memory_predicate

    return {
        "id": f"anomaly_{alert.id}",
        "timestamp": alert.detection_date.isoformat() if alert.detection_date else None,
        "decision_type": "anomaly_rule",
        "severity": severity,
        "title": f"{alert.metric_name} {alert.alert_type}",
        "message": alert.message,
        "rule": {
            "id": alert.alert_type,
            "engine": "anomaly_detector",
            "category": _RULE_CATEGORY.get(alert.metric_name, "general"),
        },
        "evidence": {
            "metric": alert.metric_name,
            "current": alert.current_value,
            "baseline": alert.baseline_value,
            "threshold": alert.threshold_value,
            "deviation_pct": alert.deviation_pct,
        },
        "confidence": conf,
        "is_suppressed": bool(alert.is_suppressed),
        "notification_sent": bool(alert.notification_sent),
        "outcome": (
            {
                "kind": "action_card",
                "id": outcome_card.id,
                "title": outcome_card.title,
                "status": outcome_card.status,
                "check_back_date": (
                    outcome_card.check_back_date.isoformat()
                    if outcome_card.check_back_date else None
                ),
                "metric_key": outcome_card.metric_key,
            }
            if outcome_card else None
        ),
        "related_memory": [
            {
                "id": f.id,
                "tier": f.tier,
                "subject": f.subject,
                "predicate": effective_memory_predicate(
                    f.predicate, object_value=f.object_value, tags=f.tags or [],
                ),
                "object_value": f.object_value,
                "object_unit": f.object_unit,
                "confidence": f.confidence,
            }
            for f in related_facts
        ],
    }


@router.get("/recent", summary="最近 N 天的决策 trace")
def recent_traces(
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(20, ge=1, le=100),
    decision_type: Optional[str] = Query(None, description="过滤: anomaly_rule | llm_arbitration"),
    include_suppressed: bool = Query(False, description="是否包含已 suppress 的 (info/疲劳)"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """
    返回用户过去 N 天所有可解释的决策 trace, 按时间降序.

    聚合两类:
      1. AnomalyAlert (anomaly_rule) — 确定性规则决策
      2. agent_audit_logs(agent_type=llm_arbitrator) — specialist 冲突的 LLM 仲裁

    Response:
      {
        "traces": [{id, timestamp, decision_type, severity, title, rule, evidence,
                    confidence, outcome, related_memory}],
        "summary": {"total": N, "by_type": {}, "by_severity": {}}
      }
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    traces: List[Dict[str, Any]] = []

    # --- 1. AnomalyAlert → anomaly_rule trace ---
    if decision_type in (None, "anomaly_rule"):
        q = (
            db.query(AnomalyAlert)
            .filter(
                AnomalyAlert.user_id == current_user.id,
                AnomalyAlert.detection_date >= since.date(),
            )
            .order_by(AnomalyAlert.detection_date.desc(), AnomalyAlert.id.desc())
        )
        if not include_suppressed:
            q = q.filter(AnomalyAlert.is_suppressed.is_(False))
        alerts = q.limit(limit).all()
        traces.extend(_build_anomaly_trace(db, a) for a in alerts)

    # --- 2. agent_audit_logs(llm_arbitrator) → llm_arbitration trace ---
    if decision_type in (None, "llm_arbitration"):
        arb_logs = (
            db.query(AgentAuditLog)
            .filter(
                AgentAuditLog.user_id == current_user.id,
                AgentAuditLog.agent_type == "llm_arbitrator",
                AgentAuditLog.created_at >= since,
            )
            .order_by(AgentAuditLog.created_at.desc())
            .limit(limit)
            .all()
        )
        traces.extend(_build_arbitration_trace(log) for log in arb_logs)

    # 全局按时间降序 + truncate 到 limit
    traces.sort(key=lambda t: t.get("timestamp") or "", reverse=True)
    traces = traces[:limit]

    # summary
    by_type: Dict[str, int] = {}
    by_severity: Dict[str, int] = {}
    for t in traces:
        by_type[t["decision_type"]] = by_type.get(t["decision_type"], 0) + 1
        by_severity[t["severity"]] = by_severity.get(t["severity"], 0) + 1

    return {
        "traces": traces,
        "summary": {
            "total": len(traces),
            "by_type": by_type,
            "by_severity": by_severity,
            "window_days": days,
        },
    }


def _build_arbitration_trace(log: AgentAuditLog) -> Dict[str, Any]:
    """AgentAuditLog(agent_type=llm_arbitrator) → 决策 trace."""
    detail = log.result_detail or {}
    arb = detail.get("arbitration") or {}
    conflicts = detail.get("conflicts") or []

    winning = arb.get("winning_side", "?")
    winning_label = {
        "specialist_a": "采纳 A 方",
        "specialist_b": "采纳 B 方",
        "both": "两方兼顾",
        "neither": "升级人工",
    }.get(winning, winning)

    # Severity: 按 winning_side 和 conflicts hard 数量估算
    hard_count = sum(1 for c in conflicts if c.get("severity") == "hard")
    if winning == "neither" or hard_count >= 2:
        sev = "critical"
    elif hard_count >= 1:
        sev = "warning"
    else:
        sev = "info"

    # 冲突双方列表
    specialists = set()
    for c in conflicts:
        if c.get("specialist_a"):
            specialists.add(c["specialist_a"])
        if c.get("specialist_b"):
            specialists.add(c["specialist_b"])

    return {
        "id": f"arb_{log.id}",
        "timestamp": log.created_at.isoformat() if log.created_at else None,
        "decision_type": "llm_arbitration",
        "severity": sev,
        "title": f"LLM 仲裁: {winning_label}",
        "message": arb.get("rationale", "")[:500] or log.result_summary or "",
        "rule": {
            "id": "llm_arbitrator",
            "engine": "orchestrator_arbitration",
            "category": "multi_agent",
        },
        "evidence": {
            "metric": None,
            "current": None,
            "baseline": None,
            "threshold": None,
            "deviation_pct": None,
        },
        "confidence": float(arb.get("confidence", 0.7)),
        "is_suppressed": False,
        "notification_sent": False,
        "outcome": (
            {
                "kind": "recommendation",
                "id": 0,
                "title": arb.get("final_recommendation", "") or "(无具体建议)",
                "status": "issued",
                "check_back_date": None,
                "metric_key": None,
            }
            if arb.get("final_recommendation") else None
        ),
        # 关联信息: 仲裁涉及的 specialist + caveats
        "related_memory": [
            {
                "id": -1,  # 虚拟 id (不对应 MemoryFact)
                "tier": "semantic",
                "subject": "conflict",
                "predicate": f"{c.get('specialist_a')} vs {c.get('specialist_b')}",
                "object_value": c.get("description", "")[:200],
                "object_unit": None,
                "confidence": 0.9 if c.get("severity") == "hard" else 0.6,
            }
            for c in conflicts[:5]
        ],
        "arbitration_extra": {
            "winning_side": winning,
            "caveats": arb.get("caveats") or [],
            "conflicts_addressed": arb.get("conflicts_addressed", len(conflicts)),
            "specialists_involved": sorted(specialists),
        },
    }


@router.get("/{trace_id}", summary="单条 trace 详情 (含更多 related memory)")
def trace_detail(
    trace_id: str,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """
    trace_id 格式: '<decision_type>_<db_id>' 如 'anomaly_42'.

    详情版返回 related_memory 扩到 20 条.
    """
    parts = trace_id.split("_", 1)
    if len(parts) != 2:
        raise HTTPException(400, "trace_id 格式错误")
    kind, raw_id = parts
    try:
        db_id = int(raw_id)
    except ValueError:
        raise HTTPException(400, "trace_id 格式错误")

    if kind == "anomaly":
        alert = (
            db.query(AnomalyAlert)
            .filter(AnomalyAlert.id == db_id, AnomalyAlert.user_id == current_user.id)
            .first()
        )
        if not alert:
            raise HTTPException(404, "alert 不存在")
        trace = _build_anomaly_trace(db, alert)

        # 详情扩 related_memory: 放宽到 20 条 + 按 metric 关键字
        since = datetime.now(timezone.utc) - timedelta(days=30)
        q = (
            db.query(MemoryFact)
            .filter(
                MemoryFact.user_id == current_user.id,
                MemoryFact.superseded_at.is_(None),
                MemoryFact.created_at >= since,
            )
        )
        if alert.metric_name:
            like = f"%{alert.metric_name}%"
            q = q.filter(MemoryFact.subject.ilike(like))
        wider_facts = q.order_by(MemoryFact.created_at.desc()).limit(20).all()
        from app.services.memory_service import effective_memory_predicate

        trace["related_memory"] = [
            {
                "id": f.id, "tier": f.tier, "subject": f.subject,
                "predicate": effective_memory_predicate(
                    f.predicate, object_value=f.object_value, tags=f.tags or [],
                ), "object_value": f.object_value,
                "object_unit": f.object_unit, "confidence": f.confidence,
                "created_at": f.created_at.isoformat() if f.created_at else None,
            }
            for f in wider_facts
        ]
        return trace

    if kind == "arb":
        log = (
            db.query(AgentAuditLog)
            .filter(
                AgentAuditLog.id == db_id,
                AgentAuditLog.user_id == current_user.id,
                AgentAuditLog.agent_type == "llm_arbitrator",
            )
            .first()
        )
        if not log:
            raise HTTPException(404, "arbitration log 不存在")
        return _build_arbitration_trace(log)

    raise HTTPException(400, f"未知 decision_type: {kind}")


# ------------------------------------------------------------
# Explain endpoints — Task 2.2: Mobile ExplainSheet 数据源
# ------------------------------------------------------------


@router.get("/safety/{audit_id}", summary="Safety 告警推理链 (按 rule_id 反查)")
def explain_safety(
    audit_id: int,
    rule_id: str = Query(..., description="alert 的 rule_id"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    logger.info(
        "[reasoning-trace] safety audit_id=%s rule_id=%s user_id=%s",
        audit_id,
        rule_id,
        current_user.id,
    )
    return explain_safety_alert(
        db, audit_id=audit_id, rule_id=rule_id, user_id=current_user.id,
    )


@router.get("/specialist/{audit_id}", summary="Specialist finding 推理链")
def explain_specialist(
    audit_id: int,
    specialist: str = Query(..., description="specialist 名字, 如 recovery_coach"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    logger.info(
        "[reasoning-trace] specialist audit_id=%s specialist=%s user_id=%s",
        audit_id,
        specialist,
        current_user.id,
    )
    return explain_specialist_finding(
        db, audit_id=audit_id, specialist=specialist, user_id=current_user.id,
    )
