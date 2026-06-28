"""test_diet_plan —— G-W7 我的饮食方案 endpoint."""

import uuid
from datetime import datetime, timedelta, timezone

from app.models.action_card import ActionCard
from app.models.user import User
from app.services.auth import auth_service
from app.services.diet_plan import _card_to_dict, _fetch_diet_related_cards


def _make_user(db, name="diet_user"):
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


def test_endpoint_returns_full_shape(client, db):
    user, headers = _make_user(db)
    resp = client.get("/api/v1/diet-plan/me", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    for k in [
        "has_data", "summary", "energy", "protein", "hydration",
        "next_meal", "supplement", "gene_nudges", "labs_concern",
        "proposed_experiments", "related_cards", "knowledge_evidence",
    ]:
        assert k in body, f"missing key {k}"
    assert isinstance(body["gene_nudges"], list)
    assert isinstance(body["proposed_experiments"], list)
    assert isinstance(body["related_cards"], list)
    assert "claim_boundary" in body["knowledge_evidence"]


def test_no_data_user_returns_has_data(client, db):
    user, headers = _make_user(db, "empty")
    resp = client.get("/api/v1/diet-plan/me", headers=headers)
    body = resp.json()
    # 即使用户没数据, FuelStrategist 也能跑 (hydration 总有 status)
    assert body["has_data"] is True
    # hydration 总能返回 (有默认值)
    assert body["hydration"] is not None


def test_endpoint_requires_auth(client):
    resp = client.get("/api/v1/diet-plan/me")
    assert resp.status_code in (401, 403)


def test_diet_related_cards_deduplicates_repeated_suggestions(db):
    user, _headers = _make_user(db, "diet_dedupe")
    now = datetime.now(timezone.utc)
    cards = [
        ActionCard(
            user_id=user.id,
            title="MTHFR 变异 —— 建议甲基叶酸形式",
            content="补剂 / 叶酸 / 5-MTHF",
            user_decision="accepted",
            created_at=now - timedelta(minutes=1),
        ),
        ActionCard(
            user_id=user.id,
            title="MTHFR 变异 —— 建议甲基叶酸形式",
            content="补剂 / 叶酸 / 5-MTHF",
            user_decision="accepted",
            created_at=now - timedelta(minutes=2),
        ),
        ActionCard(
            user_id=user.id,
            title="每日饮水提升至 2000ml",
            content="饮水和营养建议",
            user_decision="accepted",
            created_at=now - timedelta(minutes=3),
        ),
    ]
    db.add_all(cards)
    db.commit()

    related = _fetch_diet_related_cards(db, user.id)

    assert [card.title for card in related] == [
        "MTHFR 变异 —— 建议甲基叶酸形式",
        "每日饮水提升至 2000ml",
    ]


def test_diet_related_card_serializes_system_kb_evidence_refs(db):
    user, _headers = _make_user(db, "diet_refs")
    card = ActionCard(
        user_id=user.id,
        title="晚餐增加蛋白质",
        content="饮食建议",
        evidence_refs=["claim:c_protein_weight_loss_boundary"],
    )
    db.add(card)
    db.commit()
    db.refresh(card)

    payload = _card_to_dict(card)

    assert payload["evidence_refs"] == ["claim:c_protein_weight_loss_boundary"]
