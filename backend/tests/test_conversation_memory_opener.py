"""test_conversation_memory_opener —— P3-3 opener endpoint."""

import uuid

from app.models.conversation_memory import ConversationMemory
from app.models.user import User
from app.services.auth import auth_service


def _user_headers(db, name="opener"):
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


def test_opener_empty_when_no_memory(client, db):
    user, headers = _user_headers(db)
    resp = client.get("/api/v1/conversation-memory/opener", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"items": []}


def test_opener_returns_priority_types_first(client, db):
    user, headers = _user_headers(db, "priority")
    db.add(ConversationMemory(
        user_id=user.id, memory_type="fact", content="背景",
        status="active",
    ))
    db.add(ConversationMemory(
        user_id=user.id, memory_type="allergy", content="对花粉过敏",
        status="active",
    ))
    db.commit()

    resp = client.get("/api/v1/conversation-memory/opener", headers=headers)
    body = resp.json()
    assert len(body["items"]) >= 1
    # allergy 优先
    assert body["items"][0]["type"] == "allergy"
    assert body["items"][0]["type_label"] == "过敏"


def test_opener_excludes_superseded(client, db):
    user, headers = _user_headers(db, "exclude_super")
    db.add(ConversationMemory(
        user_id=user.id, memory_type="medical", content="老医嘱",
        status="superseded",
    ))
    db.add(ConversationMemory(
        user_id=user.id, memory_type="medical", content="新医嘱",
        status="active",
    ))
    db.commit()

    resp = client.get("/api/v1/conversation-memory/opener", headers=headers)
    contents = [m["content"] for m in resp.json()["items"]]
    assert "新医嘱" in contents
    assert "老医嘱" not in contents


def test_opener_respects_k_param(client, db):
    user, headers = _user_headers(db, "k_param")
    for i in range(3):
        db.add(ConversationMemory(
            user_id=user.id, memory_type="allergy", content=f"过敏{i}",
            status="active",
        ))
    db.commit()

    resp = client.get("/api/v1/conversation-memory/opener?k=1", headers=headers)
    assert len(resp.json()["items"]) == 1


def test_opener_sanitizes_json_blob_memory_content(client, db):
    user, headers = _user_headers(db, "sanitize_blob")
    db.add(ConversationMemory(
        user_id=user.id,
        memory_type="medical",
        content='{"建议":"鼻炎发作时优先生理盐水冲洗。", "注意事项": "不要连续使用含麻黄碱喷剂。"}',
        status="active",
    ))
    db.commit()

    resp = client.get("/api/v1/conversation-memory/opener", headers=headers)
    body = resp.json()

    assert resp.status_code == 200
    content = body["items"][0]["content"]
    assert "鼻炎发作时优先生理盐水冲洗" in content
    assert "建议" not in content
    assert "注意事项" not in content
    assert "{" not in content


def test_opener_skips_memory_when_sanitized_content_is_empty(client, db):
    user, headers = _user_headers(db, "skip_blob")
    db.add(ConversationMemory(
        user_id=user.id,
        memory_type="medical",
        content='{"x":"短"}',
        status="active",
    ))
    db.commit()

    resp = client.get("/api/v1/conversation-memory/opener", headers=headers)

    assert resp.status_code == 200
    assert resp.json() == {"items": []}


def test_opener_requires_auth(client):
    resp = client.get("/api/v1/conversation-memory/opener")
    assert resp.status_code in (401, 403)
