"""Episode Increment 1 golden case tests — v3 planner 结果稳定性.

覆盖 4 个关键分支 (Rule Engine → Protocol 匹配 → ActionGraph 输出):
  1. normal      常温 / 充足睡眠 → post_run_recovery_normal, 无 risk flags
  2. hot         高温 28°C+ → post_run_recovery_hot_weather, heat flag
  3. sleep_short 前夜睡眠 < 6h → post_run_recovery_sleep_deprived, sleep_short flag
  4. redflag     症状胸痛 → L4 emergency template 熔断, 不走 Protocol

另外跑一个 API smoke: GET /episodes/me + GET /{id} + POST /feedback 端到端.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services.episode import plan_run_recovery


def _utc(y=2026, m=5, d=9, hh=8):
    return datetime(y, m, d, hh, 0, tzinfo=timezone.utc)


# ─────────────────────────────────────────────────────────
# Planner 4 个 golden case
# ─────────────────────────────────────────────────────────

def test_plan_normal_case():
    """常温 + 睡眠充足 → normal protocol, L0."""
    ctx = {
        "distance_km": 8.0,
        "duration_min": 45,
        "avg_hr": 148,
        "sleep_prior_h": 7.5,
        "weather": {"temperature_c": 22},
        "symptoms": [],
    }
    graph = plan_run_recovery(_utc(), ctx)
    assert graph.protocol_slug == "post_run_recovery_normal"
    assert graph.risk.level == "L0"
    assert not graph.emergency
    assert len(graph.actions) >= 2
    # 每条 action 都能持久化 — 必备字段非空
    for a in graph.actions:
        assert a.title
        assert a.action_type
        assert a.template_id


def test_plan_hot_weather_case():
    """温度 >= 28 → hot weather protocol, L1 heat flag."""
    ctx = {
        "distance_km": 10.0,
        "duration_min": 55,
        "avg_hr": 158,
        "sleep_prior_h": 7.0,
        "weather": {"temperature_c": 32},
        "symptoms": [],
    }
    graph = plan_run_recovery(_utc(), ctx)
    assert graph.protocol_slug == "post_run_recovery_hot_weather"
    assert graph.risk.level == "L1"
    assert any("heat" in f for f in graph.risk.flags)


def test_plan_sleep_deprived_case():
    """睡眠 < 6h → sleep deprived protocol, L1 sleep_short flag."""
    ctx = {
        "distance_km": 6.0,
        "duration_min": 35,
        "avg_hr": 145,
        "sleep_prior_h": 4.5,
        "weather": {"temperature_c": 20},
        "symptoms": [],
    }
    graph = plan_run_recovery(_utc(), ctx)
    assert graph.protocol_slug == "post_run_recovery_sleep_deprived"
    assert graph.risk.level == "L1"
    assert any("sleep_short" in f for f in graph.risk.flags)


def test_plan_redflag_emergency_case():
    """胸痛 symptom → L4 熔断, emergency template."""
    ctx = {
        "distance_km": 5.0,
        "duration_min": 30,
        "avg_hr": 140,
        "sleep_prior_h": 7.0,
        "weather": {"temperature_c": 20},
        "symptoms": ["chest_pain"],
    }
    graph = plan_run_recovery(_utc(), ctx)
    assert graph.emergency is True
    assert graph.protocol_slug == "emergency"
    assert graph.risk.level == "L4"
    assert any("redflag:chest_pain" in f for f in graph.risk.flags)
    # emergency 第一条必须引导就医
    assert graph.actions[0].action_type == "emergency_referral"


# ─────────────────────────────────────────────────────────
# API 端到端 smoke — auth / list / detail / feedback
# ─────────────────────────────────────────────────────────

@pytest.fixture
def episode_fixture(db, auth_user_and_headers):
    """在 DB 里造一个 Episode + 2 条 Action, 返回 (user, headers, ep)."""
    from app.services.episode import persist_action_graph
    user, headers = auth_user_and_headers
    ctx = {
        "distance_km": 8.0,
        "duration_min": 45,
        "avg_hr": 148,
        "sleep_prior_h": 7.5,
        "weather": {"temperature_c": 22},
        "symptoms": [],
    }
    graph = plan_run_recovery(_utc(), ctx)
    ep = persist_action_graph(
        db,
        user_id=user.id,
        episode_type="run_recovery",
        occurred_at=_utc(),
        graph=graph,
        source_type="workout",
        source_id=999,
        context_snapshot=ctx,
        baseline_snapshot={"avg_hr_7d": 145},
    )
    return user, headers, ep


def test_api_list_my_episodes(client, episode_fixture):
    user, headers, ep = episode_fixture
    r = client.get("/api/v1/episodes/me", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 1
    assert data[0]["id"] == ep.id
    assert data[0]["protocol_slug"] == "post_run_recovery_normal"
    assert data[0]["actions_total"] >= 2


def test_api_get_episode_detail(client, episode_fixture):
    _, headers, ep = episode_fixture
    r = client.get(f"/api/v1/episodes/{ep.id}", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == ep.id
    assert "actions" in data and len(data["actions"]) >= 2
    # sequence 排序
    seqs = [a["sequence"] for a in data["actions"]]
    assert seqs == sorted(seqs)


def test_api_get_episode_403_when_not_owner(client, db, episode_fixture):
    from tests.conftest import create_authenticated_user
    _, _, ep = episode_fixture
    other_user, other_token = create_authenticated_user(db)
    r = client.get(
        f"/api/v1/episodes/{ep.id}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert r.status_code == 403


def test_api_submit_feedback_marks_action_done(client, episode_fixture):
    _, headers, ep = episode_fixture
    action_id = ep.actions[0].id
    r = client.post(
        f"/api/v1/episodes/{ep.id}/feedback",
        headers=headers,
        json={"kind": "action_done", "action_id": action_id},
    )
    assert r.status_code == 200
    assert r.json()["kind"] == "action_done"

    # 再读 detail, action 应当变 done
    detail = client.get(f"/api/v1/episodes/{ep.id}", headers=headers).json()
    done_action = next(a for a in detail["actions"] if a["id"] == action_id)
    assert done_action["status"] == "done"
    assert done_action["completed_at"] is not None


# ─────────────────────────────────────────────────────────
# Increment 3 §1 — Episode auto-close 状态机
# ─────────────────────────────────────────────────────────

def test_api_episode_auto_closes_when_all_actions_done(
    client, db, episode_fixture,
):
    """所有 action done/skipped → Episode.status 翻 closed + 写 Outcome."""
    from app.models.episode import EpisodeOutcome, HealthEpisode

    _, headers, ep = episode_fixture
    action_ids = [a.id for a in ep.actions]
    assert len(action_ids) >= 2

    # 标除最后一条以外全部 done
    for aid in action_ids[:-1]:
        client.post(
            f"/api/v1/episodes/{ep.id}/feedback",
            headers=headers,
            json={"kind": "action_done", "action_id": aid},
        )

    # 还没全部终态 — 应当仍是 open
    db.expire_all()
    ep_mid = db.query(HealthEpisode).filter_by(id=ep.id).first()
    assert ep_mid.status == "open"
    assert ep_mid.closed_at is None

    # 标最后一条 skipped → 应当翻 closed
    client.post(
        f"/api/v1/episodes/{ep.id}/feedback",
        headers=headers,
        json={"kind": "action_skipped", "action_id": action_ids[-1],
              "payload": {"reason": "已经做了"}},
    )

    db.expire_all()
    ep_done = db.query(HealthEpisode).filter_by(id=ep.id).first()
    assert ep_done.status == "closed"
    assert ep_done.closed_at is not None

    outcome = db.query(EpisodeOutcome).filter_by(episode_id=ep.id).first()
    assert outcome is not None
    assert outcome.actions_total == len(action_ids)
    assert outcome.actions_done == len(action_ids) - 1
    assert outcome.actions_skipped == 1
    assert outcome.completion_rate == pytest.approx(
        (len(action_ids) - 1) / len(action_ids)
    )


def test_lifecycle_partial_done_keeps_open(db, episode_fixture):
    """直接调 maybe_close_episode — 部分 done 应当不关闭."""
    from datetime import datetime, timezone
    from app.services.episode.lifecycle import maybe_close_episode

    _, _, ep = episode_fixture
    # 只翻一条 done
    ep.actions[0].status = "done"
    ep.actions[0].completed_at = datetime.now(timezone.utc)
    db.flush()

    closed = maybe_close_episode(db, ep)
    assert closed is False
    assert ep.status == "open"


def test_lifecycle_idempotent_on_already_closed(db, episode_fixture):
    """已经 closed 的 Episode 再次调用不会改 closed_at, 不会重写 Outcome."""
    from datetime import datetime, timezone
    from app.services.episode.lifecycle import maybe_close_episode
    from app.models.episode import EpisodeOutcome

    _, _, ep = episode_fixture
    now = datetime.now(timezone.utc)
    for a in ep.actions:
        a.status = "done"
        a.completed_at = now
    db.flush()

    assert maybe_close_episode(db, ep) is True
    db.commit()
    first_closed_at = ep.closed_at
    outcome = db.query(EpisodeOutcome).filter_by(episode_id=ep.id).first()
    outcome.summary = "manual reflection"
    db.commit()

    # 再次调用 — Episode 已 closed, 不应再动 Outcome.summary
    assert maybe_close_episode(db, ep) is False
    db.refresh(ep)
    assert ep.closed_at == first_closed_at
    db.refresh(outcome)
    assert outcome.summary == "manual reflection"
