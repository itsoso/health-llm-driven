"""Live Run narrative 生成任务 — 离线工具函数 + skip 路径."""
import pytest
from datetime import datetime, timedelta

from app.tasks.live_run_narrative import (
    _format_pace,
    _format_duration,
    _summarize_events,
    _summarize_recent_runs,
    generate_narrative,
)
from app.models.live_run import LiveRunSession
from app.models.user import User


@pytest.fixture
def runner(db):
    user = User(
        username="narr_runner", email="narr@example.com",
        hashed_password="x", name="复盘测试", is_active=True, is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_format_pace():
    assert _format_pace(330) == "5:30"
    assert _format_pace(360) == "6:00"
    assert _format_pace(0) == "--:--"
    assert _format_pace(None) == "--:--"


def test_format_duration():
    assert _format_duration(45) == "45秒"
    assert _format_duration(90) == "1分30秒"
    assert _format_duration(1800) == "30分0秒"
    assert _format_duration(3700) == "1小时1分"


def test_summarize_events_empty():
    assert _summarize_events([]) == "无 (节奏稳定)"


def test_summarize_events_grouped():
    out = _summarize_events([
        {"rule_id": "pace_drift"},
        {"rule_id": "pace_drift"},
        {"rule_id": "hr_zone_overload"},
    ])
    assert "配速偏快 ×2" in out
    assert "心率高区 ×1" in out


def test_summarize_recent_runs_empty(db, runner):
    s = LiveRunSession(
        user_id=runner.id, started_at=datetime.utcnow(),
        total_distance_m=2000, total_duration_s=600,
    )
    db.add(s); db.commit(); db.refresh(s)
    out = _summarize_recent_runs(db, runner.id, exclude_id=s.id)
    assert "本周首次" in out


def test_summarize_recent_runs_aggregates(db, runner):
    now = datetime.utcnow()
    cur = LiveRunSession(
        user_id=runner.id, started_at=now,
        total_distance_m=3000, total_duration_s=900,
    )
    prior1 = LiveRunSession(
        user_id=runner.id, started_at=now - timedelta(days=2),
        total_distance_m=5000, total_duration_s=1800, aborted=False,
    )
    prior2 = LiveRunSession(
        user_id=runner.id, started_at=now - timedelta(days=4),
        total_distance_m=4000, total_duration_s=1500, aborted=False,
    )
    db.add_all([cur, prior1, prior2])
    db.commit(); db.refresh(cur)
    out = _summarize_recent_runs(db, runner.id, exclude_id=cur.id)
    assert "2 次" in out
    assert "9.0 km" in out


def test_generate_narrative_skips_aborted_or_short(db, runner, monkeypatch):
    s = LiveRunSession(
        user_id=runner.id, started_at=datetime.utcnow(),
        total_distance_m=50, total_duration_s=30,
        aborted=True, narrative_status="pending",
    )
    db.add(s); db.commit(); db.refresh(s)

    # Patch SessionLocal to use our test db
    from app.tasks import live_run_narrative as mod
    monkeypatch.setattr(mod, "SessionLocal", lambda: _SessionCtx(db))
    out = generate_narrative(s.id)
    assert out["status"] == "skipped"
    db.refresh(s)
    assert s.narrative_status == "skipped"


class _SessionCtx:
    """Minimal context manager that yields the existing test session and doesn't close it."""
    def __init__(self, db):
        self.db = db
    def __enter__(self):
        return self.db
    def __exit__(self, *args):
        return False
