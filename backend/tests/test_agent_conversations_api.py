"""Agent conversation history API tests."""

from app.models.openclaw import OpenClawConversation, OpenClawMessage
from app.models.user import User
from app.api.agent import _merge_card_descriptors


def _create_user(db, suffix: str) -> User:
    user = User(
        username=f"agent_history_{suffix}",
        email=f"agent_history_{suffix}@example.com",
        hashed_password="x",
        name=f"Agent History {suffix}",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _create_conversation(db, user_id: int, title: str = "测试对话") -> OpenClawConversation:
    conv = OpenClawConversation(user_id=user_id, title=title, session_key=f"test-{user_id}")
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


def _add_message(db, conversation_id: int, role: str, content: str) -> OpenClawMessage:
    msg = OpenClawMessage(conversation_id=conversation_id, role=role, content=content)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def test_agent_conversations_list_returns_user_history_with_last_user_message(
    client, db, auth_user_and_headers
):
    user, headers = auth_user_and_headers
    conv = _create_conversation(db, user.id, "代谢健康问题")
    _add_message(db, conv.id, "assistant", "你好")
    _add_message(db, conv.id, "user", "最近血糖怎么样？")

    other = _create_user(db, "other")
    other_conv = _create_conversation(db, other.id, "其他人的对话")
    _add_message(db, other_conv.id, "user", "不能泄露")

    res = client.get("/api/v1/agent/conversations", headers=headers)

    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["offset"] == 0
    items = data["items"]
    assert len(items) == 1
    assert items[0]["id"] == conv.id
    assert items[0]["title"] == "代谢健康问题"
    assert items[0]["last_message"] == "最近血糖怎么样？"


def test_agent_conversations_pagination_offset_and_total(client, db, auth_user_and_headers):
    """翻页:total 反映全部,limit/offset 切出当前页,不与其它页重叠。"""
    user, headers = auth_user_and_headers
    for i in range(5):
        conv = OpenClawConversation(user_id=user.id, title=f"对话{i}", session_key=f"pg-{user.id}-{i}")
        db.add(conv)
    db.commit()

    page1 = client.get("/api/v1/agent/conversations?limit=2&offset=0", headers=headers).json()
    assert page1["total"] == 5
    assert page1["limit"] == 2 and page1["offset"] == 0
    assert len(page1["items"]) == 2

    page2 = client.get("/api/v1/agent/conversations?limit=2&offset=2", headers=headers).json()
    assert page2["total"] == 5
    assert len(page2["items"]) == 2

    page3 = client.get("/api/v1/agent/conversations?limit=2&offset=4", headers=headers).json()
    assert len(page3["items"]) == 1  # 余 1 条

    ids = [c["id"] for c in page1["items"] + page2["items"] + page3["items"]]
    assert len(set(ids)) == 5  # 三页无重叠、无遗漏


def test_agent_conversation_detail_returns_messages(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    conv = _create_conversation(db, user.id, "训练计划")
    first = _add_message(db, conv.id, "user", "明天怎么跑？")
    second = _add_message(db, conv.id, "assistant", "先做 Zone 2。")

    res = client.get(f"/api/v1/agent/conversations/{conv.id}", headers=headers)

    assert res.status_code == 200
    data = res.json()
    assert data["id"] == conv.id
    assert data["title"] == "训练计划"
    assert [m["id"] for m in data["messages"]] == [first.id, second.id]
    assert data["messages"][0]["role"] == "user"
    assert data["messages"][1]["content"] == "先做 Zone 2。"


def test_agent_conversation_detail_returns_persisted_card_meta(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    conv = _create_conversation(db, user.id, "知识卡片")
    msg = _add_message(db, conv.id, "assistant", "已结合知识库回答。")
    msg.meta = {
        "cards": [
            {
                "type": "system_knowledge_evidence",
                "data": {"entity": {"title": "MTHFR"}, "claims": []},
            }
        ]
    }
    db.commit()

    res = client.get(f"/api/v1/agent/conversations/{conv.id}", headers=headers)

    assert res.status_code == 200
    data = res.json()
    assert data["messages"][0]["meta"]["cards"][0]["type"] == "system_knowledge_evidence"


def test_merge_card_descriptors_preserves_existing_and_deduplicates():
    existing = [{"type": "system_knowledge_evidence", "data": {"entity": {"title": "MTHFR"}}}]
    inline = [{"type": "menu_share", "data": {"title": "分享", "items": []}}]

    merged = _merge_card_descriptors(inline, existing, existing)

    assert [card["type"] for card in merged] == ["menu_share", "system_knowledge_evidence"]


def test_agent_conversation_detail_enforces_user_isolation(client, db, auth_user_and_headers):
    _, headers = auth_user_and_headers
    other = _create_user(db, "isolated")
    other_conv = _create_conversation(db, other.id, "其他人的对话")

    res = client.get(f"/api/v1/agent/conversations/{other_conv.id}", headers=headers)

    assert res.status_code == 404


def test_agent_conversation_delete_removes_owned_conversation(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    conv = _create_conversation(db, user.id, "要删除的对话")
    _add_message(db, conv.id, "user", "删除我")

    res = client.delete(f"/api/v1/agent/conversations/{conv.id}", headers=headers)

    assert res.status_code == 200
    assert res.json()["ok"] is True
    assert db.query(OpenClawConversation).filter(OpenClawConversation.id == conv.id).first() is None


def test_agent_conversation_title_update_renames_owned_conversation(
    client, db, auth_user_and_headers
):
    user, headers = auth_user_and_headers
    conv = _create_conversation(db, user.id, "分析我最近的代谢健康")

    res = client.patch(
        f"/api/v1/agent/conversations/{conv.id}",
        headers=headers,
        json={"title": "5月代谢复盘"},
    )

    assert res.status_code == 200
    assert res.json()["title"] == "5月代谢复盘"
    db.refresh(conv)
    assert conv.title == "5月代谢复盘"


def test_agent_conversation_title_update_enforces_user_isolation(
    client, db, auth_user_and_headers
):
    _, headers = auth_user_and_headers
    other = _create_user(db, "rename_isolated")
    other_conv = _create_conversation(db, other.id, "其他人的对话")

    res = client.patch(
        f"/api/v1/agent/conversations/{other_conv.id}",
        headers=headers,
        json={"title": "不该成功"},
    )

    assert res.status_code == 404
    db.refresh(other_conv)
    assert other_conv.title == "其他人的对话"


def test_openclaw_conversation_title_update_uses_same_store(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    conv = _create_conversation(db, user.id, "旧标题")

    res = client.patch(
        f"/api/v1/openclaw/conversations/{conv.id}",
        headers=headers,
        json={"title": "移动端新标题"},
    )

    assert res.status_code == 200
    assert res.json()["title"] == "移动端新标题"
    db.refresh(conv)
    assert conv.title == "移动端新标题"
