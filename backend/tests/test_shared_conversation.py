from datetime import UTC, datetime, timedelta

from app.models.shared_conversation import SharedConversation
from app.services.agent_conversation_service import AgentConversationService


def test_create_text_share_returns_public_web_url(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers

    resp = client.post(
        "/api/v1/shared/create-text",
        headers=headers,
        json={"title": "菜单分享", "message": "今晚吃鱼 + 米饭"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["share_url"].startswith("https://health.executor.life/shared/")

    shared = db.query(SharedConversation).filter_by(user_id=user.id).one()
    assert shared.source_type == "plain_text"
    assert shared.source_conversation_id == 0
    assert shared.title == "菜单分享"
    assert shared.messages_snapshot == [
        {"role": "assistant", "content": "今晚吃鱼 + 米饭", "created_at": None}
    ]
    assert shared.expires_at is not None


def test_create_text_share_rejects_empty_message(client, auth_user_and_headers):
    _, headers = auth_user_and_headers

    resp = client.post(
        "/api/v1/shared/create-text",
        headers=headers,
        json={"title": "空分享", "message": "   "},
    )

    assert resp.status_code == 400


def test_agent_share_preserves_chat_image_urls(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    svc = AgentConversationService(db)
    conv = svc.get_or_create_conversation(user.id, None, title="午餐照片")
    svc.save_message(
        conv.id,
        "user",
        "记录这餐\n[附图: 1张]",
        image_url=f'["/api/v1/upload/files/chat/{user.id}/meal.jpg?expires=1&signature=old"]',
    )

    create_resp = client.post(
        "/api/v1/shared/create",
        headers=headers,
        json={"conversation_id": conv.id, "source_type": "agent"},
    )

    assert create_resp.status_code == 200
    shared = db.query(SharedConversation).filter_by(user_id=user.id, source_type="agent").one()
    assert shared.messages_snapshot[0]["image_url"]

    get_resp = client.get(f"/api/v1/shared/{create_resp.json()['share_token']}?count_view=false")

    assert get_resp.status_code == 200
    message = get_resp.json()["messages"][0]
    assert message["content"] == "记录这餐\n[附图: 1张]"
    assert message["image_url"].startswith("[")
    assert f"/api/v1/upload/files/chat/{user.id}/meal.jpg" in message["image_url"]


def test_shared_metadata_fetch_can_skip_view_count(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    create_resp = client.post(
        "/api/v1/shared/create-text",
        headers=headers,
        json={"title": "健康分享", "message": "基因报告解读"},
    )
    share_token = create_resp.json()["share_token"]

    metadata_resp = client.get(f"/api/v1/shared/{share_token}?count_view=false")

    assert metadata_resp.status_code == 200
    shared = db.query(SharedConversation).filter_by(user_id=user.id).one()
    assert shared.view_count == 0


def test_legacy_share_without_explicit_expiry_expires_after_30_days(client, db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    shared = SharedConversation(
        user_id=user.id,
        share_token="legacyexpiredsharetoken",
        source_type="plain_text",
        source_conversation_id=0,
        title="历史分享",
        messages_snapshot=[{"role": "assistant", "content": "历史内容", "created_at": None}],
        created_at=datetime.now(UTC) - timedelta(days=31),
        expires_at=None,
        is_active=True,
    )
    db.add(shared)
    db.commit()

    resp = client.get("/api/v1/shared/legacyexpiredsharetoken")

    assert resp.status_code == 410
