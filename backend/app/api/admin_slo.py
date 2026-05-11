"""admin_slo —— 三条主链路 SLO (Phase 4 P4-4, 2026-05-11).

SLO:
  1. APNs 送达率: NotificationLog 24h 内 sent / (sent + failed)
     - 绿 ≥ 95% / 黄 80-95% / 红 < 80%
  2. Twin build P99: AgentAuditLog.twin_build_ms 24h
     - 绿 < 800ms / 黄 800-2000ms / 红 ≥ 2000ms
  3. Orchestrator P99: AgentAuditLog.total_ms (orchestrator 类) 24h
     - 绿 < 8000ms / 黄 8000-15000ms / 红 ≥ 15000ms

接 admin/wscla 看板顶部 SLO 区块. 不动 system_health_score.py (部署 gate).
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.admin import get_admin_user
from app.database import get_db
from app.models.agent_audit_log import AgentAuditLog
from app.models.notification import NotificationLog, NotificationStatus
from app.models.user import User

router = APIRouter()


def _percentile(values: List[float], pct: float) -> Optional[float]:
    """简化 P99 / P95 — 排序后取索引位置. 不用 numpy 减依赖."""
    if not values:
        return None
    s = sorted(values)
    k = int(round((pct / 100) * (len(s) - 1)))
    return s[k]


def _grade(value: Optional[float], green_max: float, yellow_max: float, lower_is_better: bool = True) -> str:
    """返回 'green' / 'yellow' / 'red' / 'unknown'.

    lower_is_better=True (默认): value < green_max → green
    lower_is_better=False: value >= green_max → green (送达率)
    """
    if value is None:
        return "unknown"
    if lower_is_better:
        if value < green_max:
            return "green"
        if value < yellow_max:
            return "yellow"
        return "red"
    else:
        if value >= green_max:
            return "green"
        if value >= yellow_max:
            return "yellow"
        return "red"


@router.get("")
def get_slo_dashboard(
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """三条主链路 SLO + 颜色 + 详情."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)

    # ── 1. APNs 送达率 ─────────────────────────────────────
    push_total = (
        db.query(func.count(NotificationLog.id))
        .filter(
            NotificationLog.created_at >= cutoff,
            NotificationLog.status.in_([
                NotificationStatus.SENT.value,
                NotificationStatus.FAILED.value,
            ]),
        )
        .scalar() or 0
    )
    push_sent = (
        db.query(func.count(NotificationLog.id))
        .filter(
            NotificationLog.created_at >= cutoff,
            NotificationLog.status == NotificationStatus.SENT.value,
        )
        .scalar() or 0
    )
    push_rate = (push_sent / push_total) if push_total > 0 else None

    # ── 2. Twin build P99 ──────────────────────────────────
    twin_rows = (
        db.query(AgentAuditLog.twin_build_ms)
        .filter(
            AgentAuditLog.created_at >= cutoff,
            AgentAuditLog.twin_build_ms.isnot(None),
            AgentAuditLog.twin_build_ms > 0,
        )
        .all()
    )
    twin_values = [r[0] for r in twin_rows]
    twin_p99 = _percentile(twin_values, 99)
    twin_p50 = _percentile(twin_values, 50)

    # ── 3. Orchestrator P99 ────────────────────────────────
    orch_rows = (
        db.query(AgentAuditLog.total_ms)
        .filter(
            AgentAuditLog.created_at >= cutoff,
            AgentAuditLog.agent_type == "orchestrator",
            AgentAuditLog.total_ms.isnot(None),
            AgentAuditLog.total_ms > 0,
        )
        .all()
    )
    orch_values = [r[0] for r in orch_rows]
    orch_p99 = _percentile(orch_values, 99)
    orch_p50 = _percentile(orch_values, 50)

    return {
        "window": {
            "since": cutoff.isoformat(),
            "until": now.isoformat(),
        },
        "slos": [
            {
                "key": "apns_delivery",
                "name": "APNs 送达率",
                "value": push_rate,
                "value_display": f"{push_rate * 100:.1f}%" if push_rate is not None else "—",
                "unit": "%",
                "grade": _grade(push_rate, 0.95, 0.80, lower_is_better=False),
                "thresholds": {"green_min": 0.95, "yellow_min": 0.80},
                "detail": f"{push_sent}/{push_total} sent (24h)",
            },
            {
                "key": "twin_build_p99",
                "name": "Twin Build P99",
                "value": twin_p99,
                "value_display": f"{twin_p99:.0f}ms" if twin_p99 is not None else "—",
                "unit": "ms",
                "grade": _grade(twin_p99, 800, 2000, lower_is_better=True),
                "thresholds": {"green_max": 800, "yellow_max": 2000},
                "detail": f"P50 {twin_p50:.0f}ms · n={len(twin_values)}" if twin_p50 is not None else "无数据",
            },
            {
                "key": "orchestrator_p99",
                "name": "Orchestrator P99",
                "value": orch_p99,
                "value_display": f"{orch_p99:.0f}ms" if orch_p99 is not None else "—",
                "unit": "ms",
                "grade": _grade(orch_p99, 8000, 15000, lower_is_better=True),
                "thresholds": {"green_max": 8000, "yellow_max": 15000},
                "detail": f"P50 {orch_p50:.0f}ms · n={len(orch_values)}" if orch_p50 is not None else "无数据",
            },
        ],
    }
