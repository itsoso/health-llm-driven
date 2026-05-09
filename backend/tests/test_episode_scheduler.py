"""Episode scheduler tests — Increment 3 §3.

覆盖:
  1. due reminder 推送: time_window_start 已到, push_sent_at 应该被标
  2. expired 翻状态: time_window_end 已过, status → expired
  3. 全部终态后自动 close + 写 Outcome
  4. dedup: 同条 action 跑两次扫描只发一次推送 (push_sent_at 已落库)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch, AsyncMock

import pytest

from app.models.episode import EpisodeAction, EpisodeOutcome, HealthEpisode
from app.services.episode import persist_action_graph, plan_run_recovery
from app.tasks.episode_scheduler import scan_episode_action_windows


def _now_utc():
    return datetime.now(timezone.utc)


@pytest.fixture
def open_episode(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    ctx = {
        "distance_km": 8.0, "duration_min": 45, "avg_hr": 148,
        "sleep_prior_h": 7.5, "weather": {"temperature_c": 22}, "symptoms": [],
    }
    graph = plan_run_recovery(_now_utc(), ctx)
    ep = persist_action_graph(
        db, user_id=user.id, episode_type="run_recovery",
        occurred_at=_now_utc(), graph=graph,
        source_type="workout", source_id=4242,
        context_snapshot=ctx, baseline_snapshot={},
    )
    return user, ep


def _patch_session_local(monkeypatch, db):
    """让 scheduler 用 test 的 db session, 避免真连数据库."""
    class _CM:
        def __enter__(self_inner):
            return db
        def __exit__(self_inner, *a):
            return False
    monkeypatch.setattr(
        "app.tasks.episode_scheduler.SessionLocal",
        lambda: _CM(),
    )


def _stub_push(monkeypatch):
    sent = []
    async def _fake_send(self, **kw):
        sent.append(kw)
        return {"success": True, "channels": {"telegram": {"success": True}}}
    monkeypatch.setattr(
        "app.services.notification.push_service.PushService.send_notification",
        _fake_send,
    )
    return sent


# ─────────────────────────────────────────────────────────

def test_scan_pushes_due_reminder_and_marks_push_sent(
    db, monkeypatch, open_episode,
):
    user, ep = open_episode
    # 把第一条 action 的 time_window_start 设到 30 秒前 — 应当被扫到.
    # 其它 action 推到未来, 避免被一起扫到污染计数.
    a0 = ep.actions[0]
    a0.time_window_start = _now_utc() - timedelta(seconds=30)
    a0.time_window_end = _now_utc() + timedelta(hours=1)
    a0.push_sent_at = None
    for a in ep.actions[1:]:
        a.time_window_start = _now_utc() + timedelta(hours=4)
        a.time_window_end = _now_utc() + timedelta(hours=8)
        a.push_sent_at = None
    db.commit()

    _patch_session_local(monkeypatch, db)
    sent = _stub_push(monkeypatch)

    result = scan_episode_action_windows.run()
    assert result["reminded"] == 1
    assert len(sent) == 1
    # deep_link 应当指向 episode 详情
    assert sent[0]["data"]["deep_link"] == f"/episode/{ep.id}"
    assert sent[0]["data"]["action_id"] == a0.id

    db.expire_all()
    a0_after = db.query(EpisodeAction).filter_by(id=a0.id).first()
    assert a0_after.push_sent_at is not None


def test_scan_expires_actions_past_window_end(
    db, monkeypatch, open_episode,
):
    user, ep = open_episode
    # 全部 action 的 time_window_end 设到 1 小时前 — 都应翻 expired.
    for a in ep.actions:
        a.time_window_start = _now_utc() - timedelta(hours=2)
        a.time_window_end = _now_utc() - timedelta(hours=1)
    db.commit()

    _patch_session_local(monkeypatch, db)
    _stub_push(monkeypatch)

    result = scan_episode_action_windows.run()
    assert result["expired"] == len(ep.actions)
    # 因为全部 expired = 全终态, episode 应当 close
    assert result["closed"] == 1

    db.expire_all()
    ep_after = db.query(HealthEpisode).filter_by(id=ep.id).first()
    assert ep_after.status == "closed"
    assert ep_after.closed_at is not None
    outcome = db.query(EpisodeOutcome).filter_by(episode_id=ep.id).first()
    assert outcome is not None
    assert outcome.actions_total == len(ep.actions)
    assert outcome.actions_done == 0


def test_scan_dedup_does_not_push_twice(
    db, monkeypatch, open_episode,
):
    """已经标过 push_sent_at 的 action 不再扫到 — 第二次扫描 0 reminder."""
    user, ep = open_episode
    a0 = ep.actions[0]
    a0.time_window_start = _now_utc() - timedelta(seconds=30)
    a0.time_window_end = _now_utc() + timedelta(hours=1)
    # 把其它 action 推到未来, 避免污染计数
    for a in ep.actions[1:]:
        a.time_window_start = _now_utc() + timedelta(hours=4)
        a.time_window_end = _now_utc() + timedelta(hours=8)
    db.commit()

    _patch_session_local(monkeypatch, db)
    sent = _stub_push(monkeypatch)

    r1 = scan_episode_action_windows.run()
    assert r1["reminded"] == 1
    assert len(sent) == 1

    # 再扫一次 — 不应再推
    r2 = scan_episode_action_windows.run()
    assert r2["reminded"] == 0
    assert len(sent) == 1


def test_scan_skips_closed_episode(db, monkeypatch, open_episode):
    """Episode.status != open 时, 即使 action 仍 pending 也不应被扫到."""
    user, ep = open_episode
    # 手动关 episode
    ep.status = "closed"
    ep.closed_at = _now_utc()
    a0 = ep.actions[0]
    a0.time_window_start = _now_utc() - timedelta(seconds=30)
    a0.time_window_end = _now_utc() + timedelta(hours=1)
    db.commit()

    _patch_session_local(monkeypatch, db)
    sent = _stub_push(monkeypatch)

    result = scan_episode_action_windows.run()
    assert result["reminded"] == 0
    assert result["expired"] == 0
    assert len(sent) == 0
