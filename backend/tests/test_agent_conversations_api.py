"""Agent conversation history API tests."""

import json
from urllib.parse import parse_qs, urlparse

from app.models.agent_conversation import AgentConversation, AgentMessage
from app.models.user import User
from app.api.agent import (
    _done_event_may_expose_cards,
    _merge_card_descriptors,
    _persist_done_cards,
)
from app.services.agent_conversation_service import AgentConversationService


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


def _create_conversation(db, user_id: int, title: str = "测试对话") -> AgentConversation:
    conv = AgentConversation(user_id=user_id, title=title, session_key=f"test-{user_id}")
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


def _add_message(db, conversation_id: int, role: str, content: str) -> AgentMessage:
    msg = AgentMessage(conversation_id=conversation_id, role=role, content=content)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def test_postgres_turn_lock_uses_an_engine_outside_the_business_queue_pool(monkeypatch):
    class FakeResult:
        @staticmethod
        def scalar():
            return True

    class FakeTransaction:
        def __init__(self):
            self.rolled_back = False

        def rollback(self):
            self.rolled_back = True

    class FakeConnection:
        def __init__(self):
            self.transaction = FakeTransaction()
            self.closed = False
            self.statements = []

        def begin(self):
            return self.transaction

        def execute(self, statement, params):
            self.statements.append((str(statement), params))
            return FakeResult()

        def close(self):
            self.closed = True

    class FakeBind:
        class dialect:
            name = "postgresql"

        def connect(self):
            raise AssertionError("turn lock must not consume the business QueuePool")

    class FakeLockEngine:
        def __init__(self):
            self.connection = FakeConnection()

        def connect(self):
            return self.connection

    class FakeSession:
        def __init__(self):
            self.bind = FakeBind()

        def get_bind(self):
            return self.bind

    session = FakeSession()
    lock_engine = FakeLockEngine()
    monkeypatch.setattr(
        "app.services.agent_conversation_service._get_client_turn_lock_engine",
        lambda bind: lock_engine,
        raising=False,
    )
    service = AgentConversationService(session)

    assert service.try_acquire_client_turn_execution(7, "turn-7") is True
    connection = lock_engine.connection
    assert connection.closed is False
    assert connection.transaction.rolled_back is False
    assert "pg_try_advisory_xact_lock" in connection.statements[0][0]
    assert len(connection.statements) == 2
    assert connection.statements[0][1]["slot_namespace"] > 0
    assert connection.statements[1][1]["lock_key"] == service._client_turn_lock_key(7, "turn-7")

    service.release_client_turn_execution(7, "turn-7")

    assert connection.transaction.rolled_back is True
    assert connection.closed is True


def test_postgres_turn_lock_engine_has_a_hard_connection_cap(monkeypatch):
    from app.services import agent_conversation_service as module

    captured = {}
    sentinel = object()

    class SourceEngine:
        url = "postgresql+psycopg2://example.invalid/health"

    def fake_create_engine(url, **kwargs):
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(module, "create_engine", fake_create_engine)
    source = SourceEngine()

    assert module._get_client_turn_lock_engine(source) is sentinel
    assert captured["pool_size"] == module.CLIENT_TURN_LOCK_POOL_SIZE
    assert captured["max_overflow"] == 0
    assert captured["pool_timeout"] == module.CLIENT_TURN_LOCK_POOL_TIMEOUT_SECONDS


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


def test_agent_send_collects_first_party_executor_stream(client, auth_user_and_headers, monkeypatch):
    _, headers = auth_user_and_headers

    async def fake_run_stream(self, **kwargs):
        assert kwargs["message"] == "小程序非流式入口"
        assert kwargs["conversation_id"] is None
        yield {"event": "token", "data": {"content": "已接入"}}
        yield {"event": "token", "data": {"content": "第一方 Agent"}}
        yield {
            "event": "done",
            "data": {"conversation_id": 123, "message_id": 456, "elapsed_ms": 17},
        }

    monkeypatch.setattr(
        "app.services.agent_executor.AgentExecutor.run_stream",
        fake_run_stream,
    )

    res = client.post(
        "/api/v1/agent/send",
        headers=headers,
        json={"message": "小程序非流式入口"},
    )

    assert res.status_code == 200
    assert res.json() == {
        "reply": "已接入第一方 Agent",
        "conversation_id": 123,
        "message_id": 456,
        "mode": "agent",
        "elapsed_ms": 17,
    }


def test_agent_send_forwards_client_turn_id(client, auth_user_and_headers, monkeypatch):
    _, headers = auth_user_and_headers

    async def fake_run_stream(self, **kwargs):
        assert kwargs["client_turn_id"] == "turn-mobile-42"
        yield {"event": "token", "data": {"content": "ok"}}
        yield {"event": "done", "data": {"conversation_id": 7, "message_id": 8}}

    monkeypatch.setattr(
        "app.services.agent_executor.AgentExecutor.run_stream",
        fake_run_stream,
    )

    res = client.post(
        "/api/v1/agent/send",
        headers=headers,
        json={"message": "test", "client_turn_id": "turn-mobile-42"},
    )

    assert res.status_code == 200


def test_agent_send_returns_503_when_request_was_not_persisted(
    client, auth_user_and_headers, monkeypatch
):
    _, headers = auth_user_and_headers

    async def fake_run_stream(*args, **kwargs):
        yield {
            "event": "done",
            "data": {
                "conversation_id": None,
                "message_id": None,
                "completion_status": "interrupted",
                "request_persisted": False,
            },
        }

    monkeypatch.setattr(
        "app.services.agent_executor.AgentExecutor.run_stream",
        fake_run_stream,
    )
    res = client.post(
        "/api/v1/agent/send",
        headers=headers,
        json={"message": "容量已满", "client_turn_id": "turn-capacity-full"},
    )

    assert res.status_code == 503
    assert "未被持久化" in res.json()["detail"]


def test_agent_send_returns_503_when_persisted_request_is_interrupted(
    client, auth_user_and_headers, monkeypatch
):
    _, headers = auth_user_and_headers

    async def fake_run_stream(*args, **kwargs):
        yield {
            "event": "done",
            "data": {
                "conversation_id": 99,
                "message_id": None,
                "completion_status": "interrupted",
                "request_persisted": True,
            },
        }

    monkeypatch.setattr(
        "app.services.agent_executor.AgentExecutor.run_stream",
        fake_run_stream,
    )
    res = client.post(
        "/api/v1/agent/send",
        headers=headers,
        json={"message": "仍在执行", "client_turn_id": "turn-still-running"},
    )

    assert res.status_code == 503
    assert "尚未完成" in res.json()["detail"]


def test_only_complete_persisted_done_events_may_expose_action_cards():
    assert _done_event_may_expose_cards({
        "message_id": 7,
        "completion_status": "complete",
    }) is True
    assert _done_event_may_expose_cards({
        "message_id": 7,
        "completion_status": "complete",
        "request_persisted": False,
    }) is False


def test_done_cards_report_persistence_failure(
    db, auth_user_and_headers, monkeypatch
):
    user, _ = auth_user_and_headers
    conversation = _create_conversation(db, user.id, "卡片持久化失败")
    message = _add_message(db, conversation.id, "assistant", "回答")
    monkeypatch.setattr(
        db,
        "commit",
        lambda: (_ for _ in ()).throw(RuntimeError("commit failed")),
    )

    persisted = _persist_done_cards(
        db,
        message.id,
        [{"type": "diet", "data": {}, "actions": []}],
    )

    assert persisted is False
    assert _done_event_may_expose_cards({
        "message_id": None,
        "completion_status": "interrupted",
        "request_persisted": True,
    }) is False


def test_agent_conversations_pagination_offset_and_total(client, db, auth_user_and_headers):
    """翻页:total 反映全部,limit/offset 切出当前页,不与其它页重叠。"""
    user, headers = auth_user_and_headers
    for i in range(5):
        conv = AgentConversation(user_id=user.id, title=f"对话{i}", session_key=f"pg-{user.id}-{i}")
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


def test_agent_conversation_detail_refreshes_private_chat_image_signature(
    client, db, auth_user_and_headers
):
    user, headers = auth_user_and_headers
    conv = _create_conversation(db, user.id, "午餐图片")
    message = _add_message(db, conv.id, "user", "午餐")
    message.image_url = json.dumps([
        f"/api/v1/upload/files/chat/{user.id}/meal.jpg?expires=1&signature=expired",
    ])
    db.commit()

    response = client.get(f"/api/v1/agent/conversations/{conv.id}", headers=headers)

    assert response.status_code == 200
    image_url = json.loads(response.json()["messages"][0]["image_url"])[0]
    parsed = urlparse(image_url)
    query = parse_qs(parsed.query)
    assert parsed.path == f"/api/v1/upload/files/chat/{user.id}/meal.jpg"
    assert int(query["expires"][0]) > 1
    assert query["signature"][0] != "expired"


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
    assert db.query(AgentConversation).filter(AgentConversation.id == conv.id).first() is None


def test_agent_conversation_delete_removes_its_private_chat_images(
    client, db, auth_user_and_headers, tmp_path, monkeypatch
):
    from app.services import chat_utils

    user, headers = auth_user_and_headers
    monkeypatch.setattr(chat_utils, "_UPLOAD_DIR", str(tmp_path / "chat"))
    owner_dir = tmp_path / "chat" / str(user.id)
    owner_dir.mkdir(parents=True)
    image_path = owner_dir / "delete-with-conversation.jpg"
    image_path.write_bytes(b"sensitive-chat-image")
    conv = _create_conversation(db, user.id, "带图片的对话")
    message = _add_message(db, conv.id, "user", "删除图片")
    message.image_url = json.dumps([
        f"/api/v1/upload/files/chat/{user.id}/{image_path.name}",
    ])
    db.commit()

    res = client.delete(f"/api/v1/agent/conversations/{conv.id}", headers=headers)

    assert res.status_code == 200
    assert image_path.exists() is False


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


def test_agent_message_rate_toggles_owned_message(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    conv = _create_conversation(db, user.id, "评价对话")
    msg = _add_message(db, conv.id, "assistant", "可评价的回复")

    res = client.post(
        f"/api/v1/agent/messages/{msg.id}/rate",
        headers=headers,
        json={"rating": 1},
    )
    assert res.status_code == 200
    assert res.json()["rating"] == 1
    db.refresh(msg)
    assert msg.rating == 1

    res2 = client.post(
        f"/api/v1/agent/messages/{msg.id}/rate",
        headers=headers,
        json={"rating": 1},
    )
    assert res2.status_code == 200
    assert res2.json()["rating"] is None
    db.refresh(msg)
    assert msg.rating is None


def test_agent_message_rate_enforces_user_isolation(client, db, auth_user_and_headers):
    _, headers = auth_user_and_headers
    other = _create_user(db, "rate_isolated")
    other_conv = _create_conversation(db, other.id, "别人的回复")
    other_msg = _add_message(db, other_conv.id, "assistant", "不可评价")

    res = client.post(
        f"/api/v1/agent/messages/{other_msg.id}/rate",
        headers=headers,
        json={"rating": 1},
    )

    assert res.status_code == 404
