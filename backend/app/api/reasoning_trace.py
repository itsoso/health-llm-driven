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
from app.models.anomaly_alert import AnomalyAlert
from app.models.memory_fact import MemoryFact
from app.models.user import User

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
                "predicate": f.predicate,
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
    decision_type: Optional[str] = Query(None, description="过滤: anomaly_rule"),
    include_suppressed: bool = Query(False, description="是否包含已 suppress 的 (info/疲劳)"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """
    返回用户过去 N 天所有可解释的决策 trace, 按时间降序.

    Response:
      {
        "traces": [{id, timestamp, decision_type, severity, title, rule, evidence,
                    confidence, outcome, related_memory}],
        "summary": {"total": N, "by_type": {}, "by_severity": {}}
      }
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

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

    traces = [_build_anomaly_trace(db, a) for a in alerts]
    if decision_type:
        traces = [t for t in traces if t["decision_type"] == decision_type]

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
        trace["related_memory"] = [
            {
                "id": f.id, "tier": f.tier, "subject": f.subject,
                "predicate": f.predicate, "object_value": f.object_value,
                "object_unit": f.object_unit, "confidence": f.confidence,
                "created_at": f.created_at.isoformat() if f.created_at else None,
            }
            for f in wider_facts
        ]
        return trace

    raise HTTPException(400, f"未知 decision_type: {kind}")
