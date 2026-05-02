"""Celery beat health probe — 3 case: 全 no_data / ok / stale."""
from datetime import datetime, timedelta, timezone

from app.models.agent_audit_log import AgentAuditLog
from app.services.celery_health import celery_health_snapshot


def test_celery_health_empty_db_all_no_data(db):
    """空库每个 task 要么 stale 要么 no_data — 都是 non-ok."""
    snap = celery_health_snapshot(db)
    assert "tasks" in snap
    assert len(snap["tasks"]) == 5
    assert all(t["status"] in ("stale", "no_data") for t in snap["tasks"])


def test_celery_health_ok_when_recent_audit_exists(db):
    """orchestrator audit 最近 3h 有一条 → morning_briefing 不是 stale."""
    db.add(AgentAuditLog(
        user_id=1, agent_type="orchestrator", action="run",
        result_summary="brief",
        created_at=datetime.now(timezone.utc) - timedelta(hours=3),
    ))
    db.commit()

    snap = celery_health_snapshot(db)
    brief = next(t for t in snap["tasks"] if t["task"] == "morning_briefing")
    assert brief["status"] in ("ok", "observing")
    assert brief["observed"] >= 1
    assert brief["last_run"] is not None


def test_celery_health_stale_when_very_old(db):
    """5 天前的 audit → 窗口外 → observed=0 → stale."""
    db.add(AgentAuditLog(
        user_id=1, agent_type="orchestrator", action="run",
        created_at=datetime.now(timezone.utc) - timedelta(days=5),
    ))
    db.commit()

    snap = celery_health_snapshot(db)
    brief = next(t for t in snap["tasks"] if t["task"] == "morning_briefing")
    assert brief["status"] == "stale"
    assert brief["observed"] == 0
