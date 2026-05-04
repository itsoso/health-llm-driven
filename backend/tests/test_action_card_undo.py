"""
P8 (2026-05-04): ActionCard 撤销完成 — PATCH status=active 必须清 completed_at.
"""
from datetime import datetime, timezone


def test_patch_back_to_active_clears_completed_at(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers

    from app.models.action_card import ActionCard
    card = ActionCard(
        user_id=user.id,
        title="测试卡",
        content="...",
        source_type="manual",
        status="active",
    )
    db.add(card); db.commit(); db.refresh(card)

    # Step 1: 标记完成
    r = client.patch(f"/api/v1/action-cards/{card.id}",
                     headers=headers, json={"status": "completed"})
    assert r.status_code == 200
    db.refresh(card)
    assert card.status == "completed"
    assert card.completed_at is not None

    # Step 2: 撤销 — status 改回 active
    r = client.patch(f"/api/v1/action-cards/{card.id}",
                     headers=headers, json={"status": "active"})
    assert r.status_code == 200
    db.refresh(card)
    assert card.status == "active"
    # 关键: completed_at 必须被清空
    assert card.completed_at is None, (
        "撤销 (active) 后 completed_at 仍非空, 会让 grader / outcome view 误判"
    )


def test_archive_does_not_clear_completed_at(client, db, auth_user_and_headers):
    """归档不是撤销 — 不应清 completed_at."""
    user, headers = auth_user_and_headers

    from app.models.action_card import ActionCard
    card = ActionCard(
        user_id=user.id, title="x", content="...",
        source_type="manual", status="completed",
        completed_at=datetime.now(timezone.utc),
    )
    db.add(card); db.commit(); db.refresh(card)
    original_completed = card.completed_at

    r = client.patch(f"/api/v1/action-cards/{card.id}",
                     headers=headers, json={"status": "archived"})
    assert r.status_code == 200
    db.refresh(card)
    assert card.status == "archived"
    # archived 不会清 completed_at
    assert card.completed_at == original_completed
