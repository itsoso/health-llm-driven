"""Episode Reflection Worker tests — Increment 4 §1.

覆盖:
  1. 次日 GarminData 存在 → 写入 metrics_delta + summary
  2. 次日数据缺失 → skipped_no_data 计数, 不写 outcome
  3. 已有 summary 的 outcome 跳过 (幂等)
  4. 48h 之外 closed 的 episode 不被扫到
  5. baseline_snapshot 缺失时回退 hrv_7day_avg
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.daily_health import GarminData
from app.models.episode import EpisodeOutcome, HealthEpisode
from app.services.episode import persist_action_graph, plan_run_recovery
from app.tasks.episode_reflection import run_episode_reflection


def _now_utc():
    return datetime.now(timezone.utc)


def _close_episode(db, ep, completion_rate=1.0, actions_done=None):
    """把 episode 标 closed 并写一个空的 EpisodeOutcome (summary=None)."""
    ep.status = "closed"
    ep.closed_at = _now_utc()
    total = len(ep.actions)
    done = total if actions_done is None else actions_done
    skipped = total - done
    outcome = EpisodeOutcome(
        episode_id=ep.id,
        actions_total=total,
        actions_done=done,
        actions_skipped=skipped,
        completion_rate=completion_rate,
    )
    db.add(outcome)
    db.commit()
    db.refresh(outcome)
    return outcome


def _make_run_episode(db, user_id, occurred_at=None, baseline=None):
    occurred_at = occurred_at or _now_utc()
    ctx = {
        "distance_km": 8.0, "duration_min": 45, "avg_hr": 148,
        "sleep_prior_h": 7.5, "weather": {"temperature_c": 22}, "symptoms": [],
    }
    graph = plan_run_recovery(occurred_at, ctx)
    ep = persist_action_graph(
        db, user_id=user_id, episode_type="run_recovery",
        occurred_at=occurred_at, graph=graph,
        source_type="workout", source_id=4242,
        context_snapshot=ctx,
        baseline_snapshot=baseline or {},
    )
    return ep


def _patch_session_local(monkeypatch, db):
    class _CM:
        def __enter__(self_inner): return db
        def __exit__(self_inner, *a): return False
    monkeypatch.setattr(
        "app.tasks.episode_reflection.SessionLocal",
        lambda: _CM(),
    )


# ─────────────────────────────────────────────────────────

def test_reflection_writes_delta_and_summary(db, monkeypatch, auth_user_and_headers):
    user, _ = auth_user_and_headers
    occurred = _now_utc() - timedelta(hours=20)
    ep = _make_run_episode(
        db, user.id, occurred_at=occurred,
        baseline={"hrv_7d_avg": 50.0, "sleep_total_min_30d": 420},
    )
    _close_episode(db, ep)

    next_date = (occurred + timedelta(hours=12)).date() + timedelta(days=1)
    db.add(GarminData(
        user_id=user.id,
        record_date=next_date,
        hrv=58.0,
        hrv_7day_avg=50.5,
        sleep_score=82,
        total_sleep_duration=440,
        deep_sleep_duration=95,
    ))
    db.commit()

    _patch_session_local(monkeypatch, db)
    result = run_episode_reflection.run()

    assert result["reflected"] == 1
    assert result["skipped_no_data"] == 0

    db.expire_all()
    outcome = db.query(EpisodeOutcome).filter_by(episode_id=ep.id).first()
    assert outcome.summary is not None
    assert "完整执行" in outcome.summary or "完成" in outcome.summary
    assert outcome.metrics_delta["hrv_next_morning"] == 58.0
    assert outcome.metrics_delta["hrv_delta_vs_baseline"] == 8.0  # 58 - 50
    assert outcome.metrics_delta["sleep_score_next_night"] == 82
    assert outcome.metrics_delta["sleep_total_min_next_night"] == 440
    assert outcome.metrics_delta["sleep_delta_min_vs_baseline"] == 20  # 440 - 420
    assert outcome.metrics_delta["deep_sleep_min_next_night"] == 95


def test_reflection_skipped_when_no_next_day_data(db, monkeypatch, auth_user_and_headers):
    user, _ = auth_user_and_headers
    ep = _make_run_episode(db, user.id)
    _close_episode(db, ep)

    _patch_session_local(monkeypatch, db)
    result = run_episode_reflection.run()

    assert result["reflected"] == 0
    assert result["skipped_no_data"] == 1

    db.expire_all()
    outcome = db.query(EpisodeOutcome).filter_by(episode_id=ep.id).first()
    assert outcome.summary is None
    assert outcome.metrics_delta is None


def test_reflection_idempotent_on_existing_summary(db, monkeypatch, auth_user_and_headers):
    """Outcome 已有 summary 的不再被扫. 写一条数据但 outcome.summary 已存在 → reflected=0."""
    user, _ = auth_user_and_headers
    occurred = _now_utc() - timedelta(hours=20)
    ep = _make_run_episode(db, user.id, occurred_at=occurred)
    outcome = _close_episode(db, ep)
    outcome.summary = "已经写过了"
    db.commit()

    next_date = (occurred + timedelta(hours=12)).date() + timedelta(days=1)
    db.add(GarminData(user_id=user.id, record_date=next_date, hrv=60.0))
    db.commit()

    _patch_session_local(monkeypatch, db)
    result = run_episode_reflection.run()
    assert result["reflected"] == 0

    db.expire_all()
    outcome_after = db.query(EpisodeOutcome).filter_by(episode_id=ep.id).first()
    assert outcome_after.summary == "已经写过了"


def test_reflection_skips_old_closed_episodes(db, monkeypatch, auth_user_and_headers):
    """closed_at 超过 48h 的 episode 不在扫描窗口."""
    user, _ = auth_user_and_headers
    occurred = _now_utc() - timedelta(days=5)
    ep = _make_run_episode(db, user.id, occurred_at=occurred)
    ep.status = "closed"
    ep.closed_at = _now_utc() - timedelta(hours=72)
    outcome = EpisodeOutcome(
        episode_id=ep.id,
        actions_total=len(ep.actions),
        actions_done=len(ep.actions),
        actions_skipped=0,
        completion_rate=1.0,
    )
    db.add(outcome)

    next_date = (occurred + timedelta(hours=12)).date() + timedelta(days=1)
    db.add(GarminData(user_id=user.id, record_date=next_date, hrv=60.0))
    db.commit()

    _patch_session_local(monkeypatch, db)
    result = run_episode_reflection.run()
    assert result["reflected"] == 0
    assert result["skipped_no_data"] == 0


def test_reflection_falls_back_to_hrv_7day_avg(db, monkeypatch, auth_user_and_headers):
    """baseline_snapshot 没有 hrv_7d_avg 时, 用 GarminData.hrv_7day_avg 算 delta."""
    user, _ = auth_user_and_headers
    occurred = _now_utc() - timedelta(hours=20)
    ep = _make_run_episode(db, user.id, occurred_at=occurred, baseline={})
    _close_episode(db, ep)

    next_date = (occurred + timedelta(hours=12)).date() + timedelta(days=1)
    db.add(GarminData(
        user_id=user.id, record_date=next_date,
        hrv=45.0, hrv_7day_avg=50.0,
    ))
    db.commit()

    _patch_session_local(monkeypatch, db)
    result = run_episode_reflection.run()
    assert result["reflected"] == 1

    db.expire_all()
    outcome = db.query(EpisodeOutcome).filter_by(episode_id=ep.id).first()
    assert outcome.metrics_delta["hrv_delta_vs_baseline"] == -5.0
    assert "恢复偏弱" in outcome.summary or "偏弱" in outcome.summary
