# -*- coding: utf-8 -*-
"""匿名同行支持 API：所有权、隐私、幂等和反应语义。"""
from datetime import date

import pytest
from sqlalchemy import event

from app.api.community import list_posts
from app.models.community import CommunityPost
from app.models.daily_health import DietRecord
from tests.conftest import create_authenticated_user


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _diet_record(db, user_id: int) -> DietRecord:
    record = DietRecord(
        user_id=user_id,
        record_date=date.today(),
        meal_type="lunch",
        food_items="三文鱼、糙米、西兰花",
        calories=620,
        protein=42,
        carbs=58,
        fat=22,
        fiber=8,
        image_url="https://private.example/meal.jpg",
        notes="在北京办公室和客户吃饭",
        ai_raw_result='{"diagnosis":"胃溃疡","medication":"奥美拉唑"}',
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def test_publish_diet_post_is_owner_scoped_idempotent_and_privacy_minimized(client, db):
    owner, owner_token = create_authenticated_user(db)
    other, other_token = create_authenticated_user(db)
    record = _diet_record(db, owner.id)
    payload = {
        "source_type": "diet_record",
        "source_id": record.id,
        "caption": "今天也认真吃饭了",
        "idempotency_key": "publish-meal-1",
    }

    denied = client.post("/api/v1/community/posts", headers=_headers(other_token), json=payload)
    assert denied.status_code == 404

    created = client.post("/api/v1/community/posts", headers=_headers(owner_token), json=payload)
    repeated = client.post("/api/v1/community/posts", headers=_headers(owner_token), json=payload)
    assert created.status_code == 201, created.text
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["id"] == created.json()["id"]

    body = created.json()
    assert body["anonymous_name"] == "同行者"
    assert body["is_owner"] is True
    assert body["caption"] == "今天也认真吃饭了"
    assert set(body["snapshot"]) == {
        "meal_type",
        "record_date",
        "food_items",
        "calories",
        "protein",
        "carbs",
        "fat",
        "fiber",
    }
    serialized = str(body["snapshot"])
    assert "private.example" not in serialized
    assert "北京" not in serialized
    assert "胃溃疡" not in serialized
    assert "奥美拉唑" not in serialized

    feed = client.get("/api/v1/community/posts", headers=_headers(other_token))
    assert feed.status_code == 200
    assert len(feed.json()["items"]) == 1
    assert feed.json()["items"][0]["is_owner"] is False
    assert other.id != owner.id


def test_publish_same_diet_record_with_a_new_request_key_reuses_active_post(client, db):
    owner, owner_token = create_authenticated_user(db)
    record = _diet_record(db, owner.id)

    first = client.post(
        "/api/v1/community/posts",
        headers=_headers(owner_token),
        json={
            "source_type": "diet_record",
            "source_id": record.id,
            "idempotency_key": "same-source-first",
        },
    )
    repeated = client.post(
        "/api/v1/community/posts",
        headers=_headers(owner_token),
        json={
            "source_type": "diet_record",
            "source_id": record.id,
            "idempotency_key": "same-source-second",
        },
    )

    assert first.status_code == 201, first.text
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["id"] == first.json()["id"]
    assert (
        db.query(CommunityPost)
        .filter(
            CommunityPost.user_id == owner.id,
            CommunityPost.source_type == "diet_record",
            CommunityPost.source_id == record.id,
            CommunityPost.status != "deleted",
        )
        .count()
        == 1
    )


def test_owner_can_restore_an_existing_share_by_source_without_cross_user_access(client, db):
    owner, owner_token = create_authenticated_user(db)
    _other, other_token = create_authenticated_user(db)
    record = _diet_record(db, owner.id)
    created = client.post(
        "/api/v1/community/posts",
        headers=_headers(owner_token),
        json={
            "source_type": "diet_record",
            "source_id": record.id,
            "idempotency_key": "source-lookup",
        },
    )

    restored = client.get(
        f"/api/v1/community/posts/source/diet_record/{record.id}",
        headers=_headers(owner_token),
    )
    denied = client.get(
        f"/api/v1/community/posts/source/diet_record/{record.id}",
        headers=_headers(other_token),
    )

    assert restored.status_code == 200, restored.text
    assert restored.json()["id"] == created.json()["id"]
    assert restored.json()["is_owner"] is True
    assert denied.status_code == 404


def test_deleted_share_can_be_published_again(client, db):
    owner, owner_token = create_authenticated_user(db)
    record = _diet_record(db, owner.id)
    first = client.post(
        "/api/v1/community/posts",
        headers=_headers(owner_token),
        json={
            "source_type": "diet_record",
            "source_id": record.id,
            "idempotency_key": "republish-first",
        },
    )
    deleted = client.delete(
        f"/api/v1/community/posts/{first.json()['id']}",
        headers=_headers(owner_token),
    )
    second = client.post(
        "/api/v1/community/posts",
        headers=_headers(owner_token),
        json={
            "source_type": "diet_record",
            "source_id": record.id,
            "idempotency_key": "republish-second",
        },
    )

    assert deleted.status_code == 204
    assert second.status_code == 201, second.text
    assert second.json()["id"] != first.json()["id"]


def test_reaction_is_one_per_user_and_updates_instead_of_double_counting(client, db):
    owner, owner_token = create_authenticated_user(db)
    peer, peer_token = create_authenticated_user(db)
    record = _diet_record(db, owner.id)
    post = client.post(
        "/api/v1/community/posts",
        headers=_headers(owner_token),
        json={
            "source_type": "diet_record",
            "source_id": record.id,
            "idempotency_key": "reaction-meal",
        },
    ).json()

    first = client.put(
        f"/api/v1/community/posts/{post['id']}/reaction",
        headers=_headers(peer_token),
        json={"reaction": "support"},
    )
    second = client.put(
        f"/api/v1/community/posts/{post['id']}/reaction",
        headers=_headers(peer_token),
        json={"reaction": "same_path"},
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["my_reaction"] == "same_path"
    assert second.json()["reaction_counts"] == {
        "support": 0,
        "same_path": 1,
        "learned": 0,
    }

    removed = client.delete(
        f"/api/v1/community/posts/{post['id']}/reaction",
        headers=_headers(peer_token),
    )
    assert removed.status_code == 200
    assert removed.json()["my_reaction"] is None
    assert sum(removed.json()["reaction_counts"].values()) == 0


def test_owner_can_delete_post_and_other_user_cannot(client, db):
    owner, owner_token = create_authenticated_user(db)
    other, other_token = create_authenticated_user(db)
    record = _diet_record(db, owner.id)
    post = client.post(
        "/api/v1/community/posts",
        headers=_headers(owner_token),
        json={
            "source_type": "diet_record",
            "source_id": record.id,
            "idempotency_key": "delete-meal",
        },
    ).json()

    denied = client.delete(f"/api/v1/community/posts/{post['id']}", headers=_headers(other_token))
    assert denied.status_code == 404
    deleted = client.delete(f"/api/v1/community/posts/{post['id']}", headers=_headers(owner_token))
    assert deleted.status_code == 204
    assert client.get("/api/v1/community/posts", headers=_headers(other_token)).json()["items"] == []


def test_report_is_idempotent_and_three_distinct_reports_remove_post_from_feed(client, db):
    owner, owner_token = create_authenticated_user(db)
    record = _diet_record(db, owner.id)
    post = client.post(
        "/api/v1/community/posts",
        headers=_headers(owner_token),
        json={
            "source_type": "diet_record",
            "source_id": record.id,
            "idempotency_key": "reported-meal",
        },
    ).json()

    reporters = [create_authenticated_user(db) for _ in range(3)]
    for index, (_user, token) in enumerate(reporters):
        response = client.post(
            f"/api/v1/community/posts/{post['id']}/report",
            headers=_headers(token),
            json={"reason": "不适当内容"},
        )
        assert response.status_code == 200
        if index == 0:
            repeated = client.post(
                f"/api/v1/community/posts/{post['id']}/report",
                headers=_headers(token),
                json={"reason": "重复举报"},
            )
            assert repeated.status_code == 200
            assert repeated.json()["report_count"] == 1

    assert response.json()["status"] == "under_review"
    feed = client.get("/api/v1/community/posts", headers=_headers(owner_token))
    assert feed.json()["items"] == []
    restored = client.get(
        f"/api/v1/community/posts/source/diet_record/{record.id}",
        headers=_headers(owner_token),
    )
    assert restored.status_code == 200
    assert restored.json()["status"] == "under_review"


@pytest.mark.asyncio
async def test_feed_serializes_posts_in_constant_query_count(db):
    viewer, _token = create_authenticated_user(db)
    db.add_all(
        [
            CommunityPost(
                user_id=viewer.id,
                source_type="diet_record",
                source_id=index,
                snapshot={
                    "meal_type": "lunch",
                    "record_date": date.today().isoformat(),
                    "food_items": f"第{index}餐",
                },
                idempotency_key=f"feed-query-{index}",
                status="active",
            )
            for index in range(1, 11)
        ]
    )
    db.commit()
    _ = viewer.id  # refresh the committed fixture before measuring feed queries

    statements: list[str] = []

    def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(db.bind, "before_cursor_execute", capture)
    try:
        response = await list_posts(
            limit=20,
            before_id=None,
            current_user=viewer,
            db=db,
        )
    finally:
        event.remove(db.bind, "before_cursor_execute", capture)

    assert len(response["items"]) == 10
    assert len(statements) <= 3


def test_owner_reports_are_rejected_in_favor_of_delete(client, db):
    owner, owner_token = create_authenticated_user(db)
    record = _diet_record(db, owner.id)
    post = client.post(
        "/api/v1/community/posts",
        headers=_headers(owner_token),
        json={
            "source_type": "diet_record",
            "source_id": record.id,
            "idempotency_key": "owner-report-meal",
        },
    ).json()

    response = client.post(
        f"/api/v1/community/posts/{post['id']}/report",
        headers=_headers(owner_token),
        json={"reason": "我想删除"},
    )

    assert response.status_code == 400
