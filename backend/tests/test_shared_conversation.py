from app.models.shared_conversation import SharedConversation


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


def test_create_text_share_rejects_empty_message(client, auth_user_and_headers):
    _, headers = auth_user_and_headers

    resp = client.post(
        "/api/v1/shared/create-text",
        headers=headers,
        json={"title": "空分享", "message": "   "},
    )

    assert resp.status_code == 400
