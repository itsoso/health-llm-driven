"""test_movement_plan —— G-W6 我的运动方案 endpoint."""

import uuid

from app.models.action_card import ActionCard
from app.models.user import User
from app.services.auth import auth_service
from app.services.movement_plan import _card_to_dict


def _make_user(db, name="movement_user"):
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


def test_no_data_user_returns_has_data_true_with_unknown_status(client, db):
    """新用户没 Garmin 数据, MovementCoach 仍能跑 (status=unknown)."""
    user, headers = _make_user(db)
    resp = client.get("/api/v1/movement/plan/me", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    # twin build 不会失败 (空 twin), coach.run 也能跑
    assert body["has_data"] is True
    assert "training_status" in body
    assert "today" in body
    # 新用户 status 应该是 unknown
    assert body["training_status"]["status"] == "unknown"
    assert body["training_status"]["status_zh"] == "负荷未知"


def test_endpoint_returns_full_shape(client, db):
    user, headers = _make_user(db, "shape")
    resp = client.get("/api/v1/movement/plan/me", headers=headers)
    body = resp.json()
    # 必备 keys
    for k in [
        "has_data", "summary", "training_status", "today",
        "fitness", "gene_biases", "week_adjustment",
        "recent_workouts", "proposed_experiments", "related_cards",
    ]:
        assert k in body, f"missing key {k}"
    assert isinstance(body["gene_biases"], list)
    assert isinstance(body["proposed_experiments"], list)
    assert isinstance(body["related_cards"], list)


def test_endpoint_requires_auth(client):
    resp = client.get("/api/v1/movement/plan/me")
    assert resp.status_code in (401, 403)


def test_movement_related_card_serializes_system_kb_evidence_refs(db):
    user, _headers = _make_user(db, "movement_refs")
    card = ActionCard(
        user_id=user.id,
        title="恢复差时降低训练强度",
        content="运动建议",
        evidence_refs=["claim:c_recovery_low_reduce_intensity"],
    )
    db.add(card)
    db.commit()
    db.refresh(card)

    payload = _card_to_dict(card)

    assert payload["evidence_refs"] == ["claim:c_recovery_low_reduce_intensity"]
