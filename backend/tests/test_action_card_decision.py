"""test_action_card_decision —— P1-4 决策 + P1-5 click 回写 endpoint."""

from datetime import datetime, timezone
import uuid

from app.models.action_card import ActionCard
from app.models.user import User
from app.services.auth import auth_service


def _other_headers(db):
    u = User(
        username=f"other_{uuid.uuid4().hex[:8]}",
        email=f"other_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        name="other",
        is_active=True,
        is_approved=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    token = auth_service.create_access_token({"sub": str(u.id)})
    return u, {"Authorization": f"Bearer {token}"}


def _make_card(db, user_id, **kw):
    base = dict(user_id=user_id, title="t", content="c")
    base.update(kw)
    card = ActionCard(**base)
    db.add(card)
    db.commit()
    db.refresh(card)
    return card


def test_decision_accepted(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    card = _make_card(db, user.id)

    resp = client.post(
        f"/api/v1/action-cards/{card.id}/decision",
        headers=headers,
        json={"decision": "accepted", "reason": "好的"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_decision"] == "accepted"
    assert body["decided_at"] is not None
    # accepted 不归档
    assert body["status"] != "archived"


def test_decision_declined_archives(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    card = _make_card(db, user.id)

    resp = client.post(
        f"/api/v1/action-cards/{card.id}/decision",
        headers=headers,
        json={"decision": "declined"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_decision"] == "declined"
    assert body["status"] == "archived"


def test_decision_false_positive_archives(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    card = _make_card(db, user.id, source_type="safety_alert", severity="high")

    resp = client.post(
        f"/api/v1/action-cards/{card.id}/decision",
        headers=headers,
        json={"decision": "false_positive", "reason": "刚跑完步"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_decision"] == "false_positive"
    assert body["status"] == "archived"


def test_decision_invalid_rejected(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    card = _make_card(db, user.id)

    resp = client.post(
        f"/api/v1/action-cards/{card.id}/decision",
        headers=headers,
        json={"decision": "bogus"},
    )
    assert resp.status_code == 400


def test_decision_other_user_404(client, db, auth_user_and_headers):
    user, _headers = auth_user_and_headers
    card = _make_card(db, user.id)

    _, other_headers = _other_headers(db)
    resp = client.post(
        f"/api/v1/action-cards/{card.id}/decision",
        headers=other_headers,
        json={"decision": "accepted"},
    )
    # 跨用户应 404 (查不到)
    assert resp.status_code == 404


def test_decision_idempotent_same_decision(client, db, auth_user_and_headers):
    """同 decision 重复调用, decided_at 不刷新."""
    user, headers = auth_user_and_headers
    card = _make_card(db, user.id)

    r1 = client.post(
        f"/api/v1/action-cards/{card.id}/decision",
        headers=headers,
        json={"decision": "accepted"},
    )
    assert r1.status_code == 200
    first_decided_at = r1.json()["decided_at"]

    r2 = client.post(
        f"/api/v1/action-cards/{card.id}/decision",
        headers=headers,
        json={"decision": "accepted", "reason": "second call"},
    )
    assert r2.status_code == 200
    assert r2.json()["decided_at"] == first_decided_at
    # reason 仍更新
    db.refresh(card)
    assert card.decision_reason == "second call"


def test_decision_change_updates_timestamp(client, db, auth_user_and_headers):
    """换 decision (accepted → declined) 应该刷新 decided_at."""
    user, headers = auth_user_and_headers
    card = _make_card(db, user.id)

    client.post(
        f"/api/v1/action-cards/{card.id}/decision",
        headers=headers,
        json={"decision": "accepted"},
    )
    db.refresh(card)
    first_at = card.decided_at

    import time
    time.sleep(0.01)

    client.post(
        f"/api/v1/action-cards/{card.id}/decision",
        headers=headers,
        json={"decision": "declined"},
    )
    db.refresh(card)
    assert card.decided_at > first_at


def test_click_stamps_push_clicked_at_and_seen_at(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    card = _make_card(db, user.id)
    assert card.push_clicked_at is None
    assert card.seen_at is None

    resp = client.post(
        f"/api/v1/action-cards/{card.id}/click",
        headers=headers,
    )
    assert resp.status_code == 200
    db.refresh(card)
    assert card.push_clicked_at is not None
    assert card.seen_at is not None


def test_click_idempotent(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    card = _make_card(db, user.id)

    r1 = client.post(f"/api/v1/action-cards/{card.id}/click", headers=headers)
    assert r1.status_code == 200
    db.refresh(card)
    first_at = card.push_clicked_at

    import time
    time.sleep(0.01)

    r2 = client.post(f"/api/v1/action-cards/{card.id}/click", headers=headers)
    assert r2.status_code == 200
    db.refresh(card)
    assert card.push_clicked_at == first_at  # 不被覆盖


def test_click_other_user_404(client, db, auth_user_and_headers):
    user, _headers = auth_user_and_headers
    card = _make_card(db, user.id)

    _, other_headers = _other_headers(db)
    resp = client.post(
        f"/api/v1/action-cards/{card.id}/click",
        headers=other_headers,
    )
    assert resp.status_code == 404
