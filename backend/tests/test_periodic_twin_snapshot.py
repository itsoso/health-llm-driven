"""周期 TwinSnapshot 任务回归。

长期规划要求 trajectory_watch/longevity_watch 不再只依赖 intervention cycle 产快照。
本任务每天为活跃用户落一份 periodic Twin 快照,给主动漂移检测提供时间序列锚点。
"""
from __future__ import annotations

from datetime import datetime, timedelta
import uuid


def _mk_user(db, *, active=True, approved=True, managed=False):
    from app.models.user import User

    user = User(
        username=f"pts_{uuid.uuid4().hex[:8]}",
        email=f"pts_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        name="Periodic Twin",
        is_active=active,
        is_approved=approved,
        is_managed=managed,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _twin_for(user_id: int) -> dict:
    return {
        "meta": {"data_sources": ["garmin", "labs"]},
        "body_composition": {"weight_kg": 70.0 + user_id},
    }


def test_periodic_twin_snapshot_creates_for_active_approved_and_managed_users(db):
    approved = _mk_user(db, active=True, approved=True)
    managed = _mk_user(db, active=True, approved=False, managed=True)
    _mk_user(db, active=True, approved=False)
    _mk_user(db, active=False, approved=True)

    called = []

    def fake_build(_db, user_id, use_cache=True):
        called.append((user_id, use_cache))
        return _twin_for(user_id)

    from app.models.twin_snapshot import TwinSnapshot
    from app.tasks.twin_snapshot import run_periodic_twin_snapshot_once

    result = run_periodic_twin_snapshot_once(
        db,
        now=datetime(2026, 6, 28, 9, 35),
        build_fn=fake_build,
    )

    assert result == {"eligible": 2, "created": 2, "skipped_recent": 0, "failed": 0}
    assert called == [(approved.id, False), (managed.id, False)]

    rows = db.query(TwinSnapshot).order_by(TwinSnapshot.user_id).all()
    assert [row.user_id for row in rows] == [approved.id, managed.id]
    assert {row.purpose for row in rows} == {"periodic"}
    assert all(row.quality_grade == "C" for row in rows)


def test_periodic_twin_snapshot_skips_when_any_recent_snapshot_exists(db):
    user = _mk_user(db, active=True, approved=True)
    now = datetime(2026, 6, 28, 9, 35)

    from app.models.twin_snapshot import TwinSnapshot
    from app.tasks.twin_snapshot import run_periodic_twin_snapshot_once

    db.add(
        TwinSnapshot(
            user_id=user.id,
            schema_version="1",
            content_hash="recent-plan",
            purpose="plan",
            quality_grade="C",
            sources=["garmin"],
            twin_json=_twin_for(user.id),
            created_at=now - timedelta(hours=2),
        )
    )
    db.commit()

    def boom_build(*_args, **_kwargs):
        raise AssertionError("recent snapshot should skip build_twin")

    result = run_periodic_twin_snapshot_once(
        db,
        now=now,
        stale_after_hours=20,
        build_fn=boom_build,
    )

    assert result == {"eligible": 1, "created": 0, "skipped_recent": 1, "failed": 0}
    assert db.query(TwinSnapshot).count() == 1


def test_periodic_twin_snapshot_continues_after_user_failure(db):
    failing = _mk_user(db, active=True, approved=True)
    ok = _mk_user(db, active=True, approved=True)

    def flaky_build(_db, user_id, use_cache=True):
        if user_id == failing.id:
            raise RuntimeError("synthetic twin build failure")
        return _twin_for(user_id)

    from app.models.twin_snapshot import TwinSnapshot
    from app.tasks.twin_snapshot import run_periodic_twin_snapshot_once

    result = run_periodic_twin_snapshot_once(
        db,
        now=datetime(2026, 6, 28, 9, 35),
        build_fn=flaky_build,
    )

    assert result == {"eligible": 2, "created": 1, "skipped_recent": 0, "failed": 1}
    rows = db.query(TwinSnapshot).all()
    assert len(rows) == 1
    assert rows[0].user_id == ok.id
    assert rows[0].purpose == "periodic"


def test_periodic_twin_snapshot_task_registered_and_scheduled():
    from celery.schedules import crontab

    from app.celery_app import celery_app
    from app.tasks.twin_snapshot import periodic_twin_snapshot  # noqa: F401

    assert "app.tasks.twin_snapshot.periodic_twin_snapshot" in celery_app.tasks
    entry = celery_app.conf.beat_schedule.get("periodic-twin-snapshot-daily")
    assert entry is not None
    assert entry["task"] == "app.tasks.twin_snapshot.periodic_twin_snapshot"
    assert entry["schedule"] == crontab(hour=9, minute=35)
