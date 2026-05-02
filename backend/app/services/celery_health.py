"""Celery beat 健康探针 — 不新增监控表, 基于现有日志反推.

每个 task 的 "observed" 来自已存在的 DB 副作用 (audit log / action card / journal):
任务真跑过会留痕, 没痕就是 stale. 不直接连 Celery / Redis, 避免 broker 故障误报.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List

from sqlalchemy import func
from sqlalchemy.orm import Session


# 硬编码 5 个关键 Celery beat 任务的探针规格. 调整时记得同步 celery_app.py.
_TASK_SPECS: List[Dict] = [
    {
        "task": "morning_briefing",
        "probe_model": "agent_audit_log",
        "probe_filter": {"agent_type": "orchestrator"},
        "expected_per_day": 1,
        "window_hours": 36,
    },
    {
        "task": "open_loop_daily_briefing",
        "probe_model": "open_loop_history",
        "probe_filter": {},
        "expected_per_day": 1,
        "window_hours": 36,
    },
    {
        "task": "outcome_grader",
        "probe_model": "action_card",
        "probe_filter": {"has_graded_at": True},
        "expected_per_day": 1,
        "window_hours": 48,
    },
    {
        "task": "doctor_weekly_report",
        "probe_model": "clinical_journal",
        "probe_filter": {"created_by": "doctor_weekly_task"},
        "expected_per_week": 1,
        "window_hours": 192,  # 7 天 + 24h 缓冲
    },
    {
        "task": "safety_evaluation",
        "probe_model": "agent_audit_log",
        "probe_filter": {"agent_type": "safety_guardian"},
        "expected_per_day": 1,
        "window_hours": 48,
    },
]


def _probe_last(
    db: Session, model: str, filters: dict, window_hours: int,
) -> tuple[int, datetime | None]:
    """返回 (observed_count_in_window, last_event_at)."""
    since = datetime.now(timezone.utc) - timedelta(hours=window_hours)

    if model == "agent_audit_log":
        from app.models.agent_audit_log import AgentAuditLog
        q = db.query(AgentAuditLog).filter(AgentAuditLog.created_at >= since)
        if "agent_type" in filters:
            q = q.filter(AgentAuditLog.agent_type == filters["agent_type"])
        count = q.count()
        last = q.with_entities(func.max(AgentAuditLog.created_at)).scalar()
        return count, last

    if model == "open_loop_history":
        from app.models.open_loop_history import OpenLoopHistory
        q = db.query(OpenLoopHistory).filter(OpenLoopHistory.sent_at >= since)
        count = q.count()
        last = q.with_entities(func.max(OpenLoopHistory.sent_at)).scalar()
        return count, last

    if model == "action_card":
        from app.models.action_card import ActionCard
        if filters.get("has_graded_at"):
            q = db.query(ActionCard).filter(ActionCard.graded_at >= since)
            col = ActionCard.graded_at
        else:
            q = db.query(ActionCard).filter(ActionCard.created_at >= since)
            col = ActionCard.created_at
        count = q.count()
        last = q.with_entities(func.max(col)).scalar()
        return count, last

    if model == "clinical_journal":
        from app.models.clinical_journal import ClinicalJournalEntry
        q = db.query(ClinicalJournalEntry).filter(
            ClinicalJournalEntry.generated_at >= since,
        )
        if "created_by" in filters:
            q = q.filter(ClinicalJournalEntry.created_by == filters["created_by"])
        count = q.count()
        last = q.with_entities(func.max(ClinicalJournalEntry.generated_at)).scalar()
        return count, last

    return 0, None


def _classify(observed: int, expected_in_window: int) -> str:
    """ok / stale / observing / no_data."""
    if observed == 0:
        return "stale" if expected_in_window > 0 else "no_data"
    if expected_in_window <= 0:
        return "observing"
    ratio = observed / expected_in_window
    if ratio < 0.5 or ratio > 2.0:
        return "stale"  # 大幅偏离 (太少 / 太多) — 文案标红
    return "ok"


def celery_health_snapshot(db: Session) -> dict:
    tasks = []
    for spec in _TASK_SPECS:
        count, last = _probe_last(
            db,
            spec["probe_model"],
            spec.get("probe_filter", {}),
            spec["window_hours"],
        )
        if "expected_per_day" in spec:
            expected_window = int(round(
                spec["expected_per_day"] * (spec["window_hours"] / 24.0)
            ))
        elif "expected_per_week" in spec:
            expected_window = int(round(
                spec["expected_per_week"] * (spec["window_hours"] / 168.0)
            ))
        else:
            expected_window = 0
        expected_window = max(expected_window, 1)  # 防 0

        status = _classify(count, expected_window)
        tasks.append({
            "task": spec["task"],
            "expected_per_day": spec.get("expected_per_day"),
            "expected_per_week": spec.get("expected_per_week"),
            "window_hours": spec["window_hours"],
            "observed": int(count),
            "last_run": last.isoformat() if last else None,
            "status": status,
        })

    return {
        "tasks": tasks,
        "note": (
            "间接推算: 读现有 DB 表 (audit log / open_loop / action_card / journal) "
            "的 created_at 推任务是否跑过, 不直接连 Celery/Redis. "
            "broker 故障期间 Celery 真停了, 这里也会正确标 stale."
        ),
    }
