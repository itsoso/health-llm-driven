"""test_action_card_progress —— G-W5 用户视角进度看板."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.action_card import ActionCard
from app.models.user import User
from app.services.auth import auth_service


def _make_user(db, name="progress_user"):
    u = User(
        username=f"{name}_{uuid.uuid4().hex[:8]}",
        email=f"{name}_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        name=name,
        is_active=True,
        is_approved=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    token = auth_service.create_access_token({"sub": str(u.id)})
    return u, {"Authorization": f"Bearer {token}"}


def _add_card(db, user_id, **kw):
    base = dict(
        user_id=user_id,
        title="t",
        content="c",
        card_type="recommendation",
        source_type="weekly_advisor",
    )
    base.update(kw)
    db.add(ActionCard(**base))
    db.commit()


def test_empty_progress_returns_zero_stats(client, db):
    user, headers = _make_user(db)
    resp = client.get("/api/v1/action-cards/me/progress", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["stats"]["total_surfaced"] == 0
    assert body["stats"]["accepted"] == 0
    assert body["stats"]["acceptance_rate"] is None
    assert body["closed_cards"] == []
    assert body["verifying_cards"] == []


def test_progress_counts_lifecycle(client, db):
    user, headers = _make_user(db, "lifecycle")
    now = datetime.now(timezone.utc)

    # 已闭环 improved
    _add_card(
        db, user.id, title="a", user_decision="accepted",
        completed_at=now - timedelta(days=2), graded_at=now - timedelta(hours=1),
        outcome="improved", effect_size=0.15,
        metric_key="hrv", baseline_value="50", actual_value="58",
    )
    # 已闭环 worsened
    _add_card(
        db, user.id, title="b", user_decision="accepted",
        completed_at=now - timedelta(days=3), graded_at=now,
        outcome="worsened", effect_size=-0.10,
    )
    # 验证中 (accepted + completed but not graded)
    _add_card(
        db, user.id, title="c", user_decision="accepted",
        completed_at=now - timedelta(hours=2),
    )
    # accepted 但还没 completed
    _add_card(db, user.id, title="d", user_decision="accepted")
    # declined
    _add_card(db, user.id, title="e", user_decision="declined")
    # pending
    _add_card(db, user.id, title="f")

    resp = client.get("/api/v1/action-cards/me/progress?days=30", headers=headers)
    body = resp.json()
    s = body["stats"]
    assert s["total_surfaced"] == 6
    assert s["accepted"] == 4
    assert s["declined"] == 1
    assert s["pending"] == 1
    assert s["completed"] == 3  # a + b + c
    assert s["graded"] == 2  # a + b
    assert s["improved"] == 1
    assert s["worsened"] == 1
    assert s["safe_closed"] == 1  # only improved (unchanged 0)
    # rates
    assert s["acceptance_rate"] == 0.8  # 4/(4+1)
    assert s["verification_rate"] == round(2/3, 4)  # 2 graded / 3 completed
    assert s["improvement_rate"] == 0.5  # 1/2

    # closed list
    assert len(body["closed_cards"]) == 2
    assert body["closed_cards"][0]["title"] == "b"  # graded_at most recent

    # verifying list
    assert len(body["verifying_cards"]) == 1
    assert body["verifying_cards"][0]["title"] == "c"


def test_window_excludes_old(client, db):
    user, headers = _make_user(db, "window")
    now = datetime.now(timezone.utc)
    # 90 天前的卡, 不算
    old_card = ActionCard(
        user_id=user.id, title="old", content="c",
        card_type="recommendation", source_type="weekly_advisor",
        user_decision="accepted",
        created_at=now - timedelta(days=90),
    )
    db.add(old_card)
    # 7 天内的卡
    _add_card(db, user.id, title="recent", user_decision="accepted")
    db.commit()

    resp = client.get("/api/v1/action-cards/me/progress?days=14", headers=headers)
    assert resp.json()["stats"]["total_surfaced"] == 1
    assert resp.json()["stats"]["accepted"] == 1


def test_progress_requires_auth(client):
    resp = client.get("/api/v1/action-cards/me/progress")
    assert resp.status_code in (401, 403)


@pytest.mark.parametrize(
    ("metric_key", "title"),
    [("ldl", "降低 LDL"), ("blood_glucose", "控制血糖")],
)
def test_progress_excludes_clinician_gated_legacy_outcome_from_efficacy_rates(
    client, db, metric_key, title,
):
    user, headers = _make_user(db, "clinician_progress")
    now = datetime.now(timezone.utc)
    _add_card(
        db, user.id, title=title, metric_key=metric_key, user_decision="accepted",
        completed_at=now - timedelta(days=1), graded_at=now,
        outcome="improved", accuracy_score=95,
    )

    body = client.get("/api/v1/action-cards/me/progress", headers=headers).json()

    assert body["stats"]["graded"] == 0
    assert body["stats"]["improved"] == 0
    assert body["stats"]["improvement_rate"] is None
    assert body["closed_cards"][0]["outcome"] == "inconclusive"
