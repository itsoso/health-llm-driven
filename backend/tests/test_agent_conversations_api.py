"""Agent conversation history API tests."""

import inspect
import json
import logging
from datetime import UTC, date, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy.orm import sessionmaker

from app.models.agent_conversation import AgentConversation, AgentMessage
from app.models.daily_health import DietPhotoAsset, DietRecord
from app.models.user import User
from app.api.agent import (
    agent_stream,
    _answer_owns_its_visualization,
    _done_event_may_expose_cards,
    _merge_card_descriptors,
    _persist_done_cards,
    _verified_intake_suppressions,
)
from app.services.agent_conversation_service import AgentConversationService


def _sse_events(response) -> list[dict]:
    return [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]


def _wire_live_agent_stream_test(monkeypatch, db) -> None:
    """Keep the real API card-composition wrapper; bypass unrelated runtime seams."""
    from app.config import settings

    monkeypatch.setattr(settings, "agent_runtime_mode", "off")
    monkeypatch.setattr(settings, "starter_pregen_enabled", False)
    monkeypatch.setattr(
        "app.api.agent._maybe_genui_chart_events",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "app.api.agent._dispatch_life_event_extraction",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "app.api.agent._reserve_agent_capacity",
        lambda *_args, **_kwargs: "test-capacity-lease",
    )
    monkeypatch.setattr(
        "app.api.agent._release_agent_capacity_safely",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "app.database.SessionLocal",
        sessionmaker(bind=db.get_bind(), autocommit=False, autoflush=False),
    )


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
    assert res.headers.get("cache-control") == "no-store"
    data = res.json()
    assert data["total"] == 1
    assert data["offset"] == 0
    items = data["items"]
    assert len(items) == 1
    assert items[0]["id"] == conv.id
    assert items[0]["title"] == "代谢健康问题"
    assert items[0]["last_message"] == "最近血糖怎么样？"


def test_agent_conversations_list_uses_latest_updated_conversation_as_canonical_first(
    client, db, auth_user_and_headers
):
    user, headers = auth_user_and_headers
    older = _create_conversation(db, user.id, "旧端对话")
    newer = _create_conversation(db, user.id, "另一端刚更新的对话")
    now = datetime.now(UTC)
    older.updated_at = now - timedelta(minutes=10)
    newer.updated_at = now
    db.commit()

    res = client.get("/api/v1/agent/conversations?limit=1", headers=headers)

    assert res.status_code == 200
    assert [item["id"] for item in res.json()["items"]] == [newer.id]


def test_agent_conversations_resume_only_uses_latest_user_turn_not_updated_at(
    client, db, auth_user_and_headers
):
    """Default resume must ignore assistant-only background briefings."""
    user, headers = auth_user_and_headers
    interactive = _create_conversation(db, user.id, "午餐记录")
    _add_message(db, interactive.id, "user", "记录午餐")
    briefing = _create_conversation(db, user.id, "每日健康简报 · 08-17")
    _add_message(db, briefing.id, "assistant", "今日健康简报")
    now = datetime.now(UTC)
    interactive.updated_at = now - timedelta(hours=2)
    briefing.updated_at = now
    db.commit()

    res = client.get(
        "/api/v1/agent/conversations?resume_only=true&limit=1",
        headers=headers,
    )

    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert [item["id"] for item in data["items"]] == [interactive.id]


def test_agent_conversations_resume_only_keeps_interactive_briefing_conversation(
    client, db, auth_user_and_headers
):
    """Selection is based on message roles, never on a title prefix."""
    user, headers = auth_user_and_headers
    briefing = _create_conversation(db, user.id, "每日健康简报 · 08-17")
    _add_message(db, briefing.id, "user", "我想了解今天的建议")
    _add_message(db, briefing.id, "assistant", "可以，我们先看饮水")

    res = client.get(
        "/api/v1/agent/conversations?resume_only=true&limit=1",
        headers=headers,
    )

    assert res.status_code == 200
    assert [item["id"] for item in res.json()["items"]] == [briefing.id]


def test_agent_conversations_resume_only_orders_by_latest_user_turn(
    client, db, auth_user_and_headers
):
    user, headers = auth_user_and_headers
    first = _create_conversation(db, user.id, "较早用户会话")
    first_user = _add_message(db, first.id, "user", "较早的问题")
    second = _create_conversation(db, user.id, "较晚用户会话")
    second_user = _add_message(db, second.id, "user", "较晚的问题")
    now = datetime.now(UTC)
    first_user.created_at = now - timedelta(hours=1)
    second_user.created_at = now
    # Deliberately invert conversation mutation timestamps: resume ordering
    # must follow the last user turn, not assistant/background conversation churn.
    first.updated_at = now
    second.updated_at = now - timedelta(hours=1)
    db.commit()

    res = client.get(
        "/api/v1/agent/conversations?resume_only=true&limit=2",
        headers=headers,
    )

    assert res.status_code == 200
    assert [item["id"] for item in res.json()["items"]] == [second.id, first.id]


def test_agent_conversations_resume_only_returns_empty_for_assistant_only_history(
    client, db, auth_user_and_headers
):
    user, headers = auth_user_and_headers
    briefing = _create_conversation(db, user.id, "每日健康简报 · 08-17")
    _add_message(db, briefing.id, "assistant", "今日健康简报")

    res = client.get(
        "/api/v1/agent/conversations?resume_only=true&limit=1",
        headers=headers,
    )

    assert res.status_code == 200
    assert res.json()["items"] == []
    assert res.json()["total"] == 0


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
    body = res.json()
    # 老字段零变化(additive meta 上线后契约不回退)。
    assert body["reply"] == "已接入第一方 Agent"
    assert body["conversation_id"] == 123
    assert body["message_id"] == 456
    assert body["mode"] == "agent"
    assert body["elapsed_ms"] == 17
    # 纯附加 meta 恒存在(即使没模型/成本也给结构,值为 None)。
    assert "meta" in body and isinstance(body["meta"], dict)
    assert set(body["meta"].keys()) == {
        "model", "rounds", "usage", "cost_estimate", "latency", "tools_used"
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


def test_agent_send_forwards_client_time_context(client, auth_user_and_headers, monkeypatch):
    _, headers = auth_user_and_headers

    async def fake_run_stream(self, **kwargs):
        assert kwargs["client_time_context"] == {
            "client_now_iso": "2026-07-16T15:40:00.000Z",
            "timezone": "Asia/Shanghai",
            "timezone_offset_minutes": 480,
            "locale": "zh-CN",
        }
        yield {"event": "token", "data": {"content": "ok"}}
        yield {"event": "done", "data": {"conversation_id": 7, "message_id": 8}}

    monkeypatch.setattr(
        "app.services.agent_executor.AgentExecutor.run_stream",
        fake_run_stream,
    )

    res = client.post(
        "/api/v1/agent/send",
        headers=headers,
        json={
            "message": "test",
            "client_time_context": {
                "client_now_iso": "2026-07-16T15:40:00.000Z",
                "timezone": "Asia/Shanghai",
                "timezone_offset_minutes": 480,
                "locale": "zh-CN",
            },
        },
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


@pytest.mark.parametrize(
    ("receipts", "expected"),
    [
        (
            [{
                "status": "verified",
                "verified": True,
                "resource_type": "diet_record",
                "resource_id": "830",
            }],
            {"diet"},
        ),
        (
            [{
                "status": "failed",
                "verified": False,
                "resource_type": "diet_record",
                "resource_id": "830",
            }],
            set(),
        ),
        ([], set()),
    ],
)
def test_verified_intake_suppressions_require_a_verified_receipt(
    receipts,
    expected,
):
    assert _verified_intake_suppressions({"write_receipts": receipts}) == expected


@pytest.mark.parametrize(
    ("receipts", "diet_should_be_suppressed"),
    [
        ([], False),
        (
            [{
                "status": "verified",
                "verified": True,
                "resource_type": "diet_record",
                "resource_id": "830",
            }],
            True,
        ),
    ],
)
def test_agent_stream_suppresses_diet_projection_by_receipt_not_tool_attempt(
    client,
    db,
    auth_user_and_headers,
    monkeypatch,
    receipts,
    diet_should_be_suppressed,
):
    from app.services import inline_cards

    user, headers = auth_user_and_headers
    conversation = _create_conversation(db, user.id, "回执驱动卡片压制")
    assistant = _add_message(db, conversation.id, "assistant", "处理完成。")
    assistant.meta = {"cards": []}
    db.commit()

    build_calls = []

    def build_cards_spy(*_args, **kwargs):
        build_calls.append(kwargs.copy())
        return []

    async def fake_run_stream(self, **kwargs):
        yield {
            "event": "done",
            "data": {
                "conversation_id": conversation.id,
                "message_id": assistant.id,
                "completion_status": "complete",
                "tools_used": ["health_record"],
                "write_receipts": receipts,
                "cards": [],
            },
        }

    _wire_live_agent_stream_test(monkeypatch, db)
    monkeypatch.setattr(inline_cards, "build_cards", build_cards_spy)
    monkeypatch.setattr(
        "app.services.agent_executor.AgentExecutor.run_stream",
        fake_run_stream,
    )

    response = client.post(
        "/api/v1/agent/stream",
        headers=headers,
        json={
            "message": "记录吃了一个桃子",
            "conversation_id": conversation.id,
            "client_turn_id": f"receipt-card-suppression-{diet_should_be_suppressed}",
        },
    )

    assert response.status_code == 200
    assert build_calls
    suppressions = build_calls[-1]["suppress_intake_kinds"]
    assert ("diet" in suppressions) is diet_should_be_suppressed


@pytest.mark.parametrize(
    "category",
    [
        "action_not_executed",
        "tool_failed",
        "tool_blocked",
        "write_reconciliation_required",
        "service_unavailable",
        "execution_error",
        "confirmation_required",
    ],
)
def test_agent_stream_terminal_write_state_suppresses_query_intake_projection(
    client,
    db,
    auth_user_and_headers,
    monkeypatch,
    category,
):
    from app.services import inline_cards

    user, headers = auth_user_and_headers
    conversation = _create_conversation(db, user.id, f"终态摄入卡压制-{category}")
    assistant = _add_message(db, conversation.id, "assistant", "本次没有写入。")
    assistant.meta = {"cards": []}
    db.commit()

    build_calls = []

    def build_cards_spy(*_args, **kwargs):
        build_calls.append(kwargs.copy())
        return []

    async def fake_run_stream(self, **kwargs):
        yield {
            "event": "done",
            "data": {
                "conversation_id": conversation.id,
                "message_id": assistant.id,
                "completion_status": "complete",
                "write_receipts": [],
                "cards": [],
                "turn_outcome": {"category": category},
            },
        }

    _wire_live_agent_stream_test(monkeypatch, db)
    monkeypatch.setattr(inline_cards, "build_cards", build_cards_spy)
    monkeypatch.setattr(
        "app.services.agent_executor.AgentExecutor.run_stream",
        fake_run_stream,
    )

    response = client.post(
        "/api/v1/agent/stream",
        headers=headers,
        json={
            "message": "记录我吃了两粒阿奇霉素",
            "conversation_id": conversation.id,
            "client_turn_id": f"terminal-card-suppression-{category}",
        },
    )

    assert response.status_code == 200
    assert build_calls
    assert "medication" in build_calls[-1]["suppress_intake_kinds"]


def test_done_cards_report_persistence_failure_without_logging_health_payload(
    db, auth_user_and_headers, monkeypatch, caplog
):
    user, _ = auth_user_and_headers
    conversation = _create_conversation(db, user.id, "卡片持久化失败")
    message = _add_message(db, conversation.id, "assistant", "回答")
    sensitive = "伊托必利 999粒 SENTINEL"
    monkeypatch.setattr(
        db,
        "commit",
        lambda: (_ for _ in ()).throw(RuntimeError(sensitive)),
    )

    with caplog.at_level(logging.DEBUG, logger="app.api.agent"):
        persisted = _persist_done_cards(
            db,
            message.id,
            [{"type": "medication_draft", "data": {"items": [sensitive]}, "actions": []}],
        )

    assert persisted is False
    assert sensitive not in caplog.text
    assert "error_type=RuntimeError" in caplog.text
    assert _done_event_may_expose_cards({
        "message_id": None,
        "completion_status": "interrupted",
        "request_persisted": True,
    }) is False


def test_persist_done_cards_canonicalizes_before_dedupe(
    db, auth_user_and_headers
):
    user, _ = auth_user_and_headers
    conversation = _create_conversation(db, user.id, "饮食卡归一化")
    message = _add_message(db, conversation.id, "assistant", "晚餐已记录。")
    persisted_diet = {
        "type": "diet_draft",
        "data": {
            "recorded": True,
            "record_id": 830,
            "meal_type": "dinner",
            "description": "牛肉面",
        },
        "actions": [],
    }
    message.meta = {"cards": [persisted_diet]}
    db.commit()

    live_diet = {
        **persisted_diet,
        "data": {
            **persisted_diet["data"],
            "photo_url": "/api/v1/upload/files/chat/1/dinner.jpg?signature=live",
        },
    }
    distinct_quality_card = {
        "type": "record_quality",
        "data": {"domain": "diet", "record_id": 830, "title": "记录质量"},
        "actions": [],
    }

    assert _persist_done_cards(
        db,
        message.id,
        [live_diet, distinct_quality_card],
    ) is True

    db.refresh(message)
    assert [card["type"] for card in message.meta["cards"]] == [
        "diet_draft",
        "record_quality",
    ]
    assert "photo_url" not in message.meta["cards"][0]["data"]


@pytest.mark.parametrize(
    ("contextual_state", "turn_suffix"),
    [
        ({"recorded": True, "record_id": 830}, "recorded"),
        ({"photo_draft_token": "photo-draft-token"}, "pending"),
    ],
)
def test_agent_stream_contextual_diet_card_occupies_draft_projection(
    client,
    db,
    auth_user_and_headers,
    monkeypatch,
    contextual_state,
    turn_suffix,
):
    from app.services import inline_cards

    user, headers = auth_user_and_headers
    conversation = _create_conversation(db, user.id, f"上下文饮食卡-{turn_suffix}")
    assistant = _add_message(db, conversation.id, "assistant", "晚餐已识别。")
    contextual_card = {
        "type": "diet_draft",
        "data": {
            "meal_type": "dinner",
            "food_items": "牛肉面",
            **contextual_state,
        },
        "actions": [],
    }
    assistant.meta = {"cards": [contextual_card]}
    db.commit()

    represented_calls = []
    real_represented_kinds = inline_cards.represented_intake_kinds

    def represented_spy(*card_lists):
        result = real_represented_kinds(*card_lists)
        represented_calls.append((card_lists, result))
        return result

    async def fake_run_stream(self, **kwargs):
        assert kwargs["message"] == "记录晚餐牛肉面 500 kcal"
        yield {
            "event": "done",
            "data": {
                "conversation_id": conversation.id,
                "message_id": assistant.id,
                "completion_status": "complete",
                "tools_used": [],
                "cards": [contextual_card],
            },
        }

    _wire_live_agent_stream_test(monkeypatch, db)
    monkeypatch.setattr(inline_cards, "represented_intake_kinds", represented_spy)
    monkeypatch.setattr(
        "app.services.agent_executor.AgentExecutor.run_stream",
        fake_run_stream,
    )

    response = client.post(
        "/api/v1/agent/stream",
        headers=headers,
        json={
            "message": "记录晚餐牛肉面 500 kcal",
            "conversation_id": conversation.id,
            "client_turn_id": f"diet-card-wiring-{turn_suffix}",
        },
    )

    assert response.status_code == 200
    done = next(event for event in _sse_events(response) if event["event"] == "done")
    assert represented_calls and represented_calls[-1][1] == {"diet"}
    assert done["data"]["cards"] == [contextual_card]

    db.expire_all()
    persisted = db.query(AgentMessage).filter(AgentMessage.id == assistant.id).one()
    assert persisted.meta["cards"] == [contextual_card]


def test_agent_stream_deterministic_diet_summary_owns_snapshot_projection(
    client,
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.services import inline_cards

    user, headers = auth_user_and_headers
    query = "今天饮食如何"
    unsuppressed = inline_cards.build_cards(db, user.id, query)
    assert any(card["type"] == "diet" for card in unsuppressed), (
        "前提：该查询在 wrapper 未识别 GenUI 时会追加 legacy diet 快照"
    )

    conversation = _create_conversation(db, user.id, "确定性饮食汇总")
    summary = (
        "今日饮食汇总如下。\n"
        "```reva-ui\n"
        '{"type":"diet_daily_summary","v":1,"data":{"meals":[],"totals":{}}}\n'
        "```"
    )
    assistant = _add_message(db, conversation.id, "assistant", summary)
    assistant.meta = {"cards": []}
    db.commit()

    build_calls = []
    real_build_cards = inline_cards.build_cards

    def build_cards_spy(*args, **kwargs):
        build_calls.append(kwargs.copy())
        return real_build_cards(*args, **kwargs)

    async def fake_run_stream(self, **kwargs):
        assert kwargs["message"] == query
        yield {"event": "token", "data": {"content": summary}}
        yield {
            "event": "done",
            "data": {
                "conversation_id": conversation.id,
                "message_id": assistant.id,
                "completion_status": "complete",
                "tools_used": ["health_query"],
            },
        }

    _wire_live_agent_stream_test(monkeypatch, db)
    monkeypatch.setattr(inline_cards, "build_cards", build_cards_spy)
    monkeypatch.setattr(
        "app.services.agent_executor.AgentExecutor.run_stream",
        fake_run_stream,
    )

    response = client.post(
        "/api/v1/agent/stream",
        headers=headers,
        json={
            "message": query,
            "conversation_id": conversation.id,
            "client_turn_id": "diet-summary-visualization-wiring",
        },
    )

    assert response.status_code == 200
    done = next(event for event in _sse_events(response) if event["event"] == "done")
    assert build_calls and build_calls[-1]["suppress_snapshot_cards"] is True
    assert not any(card["type"] == "diet" for card in done["data"].get("cards", []))

    db.expire_all()
    persisted = db.query(AgentMessage).filter(AgentMessage.id == assistant.id).one()
    assert not any(card["type"] == "diet" for card in persisted.meta.get("cards", []))


def test_agent_stream_client_rejected_diet_fence_keeps_snapshot_projection(
    client,
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.services import inline_cards

    user, headers = auth_user_and_headers
    query = "今天饮食如何"
    unsuppressed = inline_cards.build_cards(db, user.id, query)
    assert any(card["type"] == "diet" for card in unsuppressed), (
        "前提：客户端无法渲染 GenUI 时，wrapper 能追加 legacy diet 快照"
    )

    conversation = _create_conversation(db, user.id, "客户端拒绝的饮食汇总")
    summary = (
        "今日饮食汇总如下。\n"
        "```reva-ui\n"
        '{"type":"diet_daily_summary","v":1,"data":{"calories":NaN}}\n'
        "```"
    )
    assistant = _add_message(db, conversation.id, "assistant", summary)
    assistant.meta = {"cards": []}
    db.commit()

    build_calls = []
    real_build_cards = inline_cards.build_cards

    def build_cards_spy(*args, **kwargs):
        build_calls.append(kwargs.copy())
        return real_build_cards(*args, **kwargs)

    async def fake_run_stream(self, **kwargs):
        assert kwargs["message"] == query
        yield {"event": "token", "data": {"content": summary}}
        yield {
            "event": "done",
            "data": {
                "conversation_id": conversation.id,
                "message_id": assistant.id,
                "completion_status": "complete",
                "tools_used": ["health_query"],
            },
        }

    _wire_live_agent_stream_test(monkeypatch, db)
    monkeypatch.setattr(inline_cards, "build_cards", build_cards_spy)
    monkeypatch.setattr(
        "app.services.agent_executor.AgentExecutor.run_stream",
        fake_run_stream,
    )

    response = client.post(
        "/api/v1/agent/stream",
        headers=headers,
        json={
            "message": query,
            "conversation_id": conversation.id,
            "client_turn_id": "diet-summary-client-rejected-wiring",
        },
    )

    assert response.status_code == 200
    done = next(event for event in _sse_events(response) if event["event"] == "done")
    assert build_calls and build_calls[-1]["suppress_snapshot_cards"] is False
    assert any(card["type"] == "diet" for card in done["data"].get("cards", []))

    db.expire_all()
    persisted = db.query(AgentMessage).filter(AgentMessage.id == assistant.id).one()
    assert any(card["type"] == "diet" for card in persisted.meta.get("cards", []))


def test_agent_stream_failure_logs_do_not_interpolate_raw_exceptions():
    source = inspect.getsource(agent_stream)

    assert 'logger.debug(f"inline_cards 失败: {e}")' not in source
    assert 'logger.error(f"Agent bg 流式异常: {e}", exc_info=True)' not in source


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
    assert res.headers.get("cache-control") == "no-store"
    data = res.json()
    assert data["id"] == conv.id
    assert data["title"] == "训练计划"
    assert [m["id"] for m in data["messages"]] == [first.id, second.id]
    assert data["messages"][0]["role"] == "user"
    assert data["messages"][1]["content"] == "先做 Zone 2。"


def test_agent_conversation_detail_supports_cursor_pagination(
    client, db, auth_user_and_headers
):
    user, headers = auth_user_and_headers
    conv = _create_conversation(db, user.id, "长对话")
    messages = [
        _add_message(db, conv.id, "user" if index % 2 == 0 else "assistant", f"消息{index}")
        for index in range(5)
    ]

    latest = client.get(
        f"/api/v1/agent/conversations/{conv.id}?limit=2",
        headers=headers,
    )
    assert latest.status_code == 200
    latest_body = latest.json()
    assert [item["id"] for item in latest_body["messages"]] == [
        messages[3].id,
        messages[4].id,
    ]
    assert latest_body["total_messages"] == 5
    assert latest_body["has_more"] is True
    assert latest_body["oldest_message_id"] == messages[3].id

    older = client.get(
        f"/api/v1/agent/conversations/{conv.id}"
        f"?limit=2&before_message_id={latest_body['oldest_message_id']}",
        headers=headers,
    )
    assert older.status_code == 200
    older_body = older.json()
    assert [item["id"] for item in older_body["messages"]] == [
        messages[1].id,
        messages[2].id,
    ]
    assert older_body["has_more"] is True

    oldest = client.get(
        f"/api/v1/agent/conversations/{conv.id}"
        f"?limit=2&before_message_id={older_body['oldest_message_id']}",
        headers=headers,
    )
    assert oldest.status_code == 200
    oldest_body = oldest.json()
    assert [item["id"] for item in oldest_body["messages"]] == [messages[0].id]
    assert oldest_body["has_more"] is False
    assert oldest_body["oldest_message_id"] == messages[0].id


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


def test_agent_conversation_detail_restores_each_persisted_diet_card_photo(
    client, db, auth_user_and_headers
):
    user, headers = auth_user_and_headers
    conv = _create_conversation(db, user.id, "连续拍照记餐")
    first = _add_message(db, conv.id, "assistant", "早餐已记录。")
    second = _add_message(db, conv.id, "assistant", "午餐已记录。")
    records = [
        DietRecord(
            user_id=user.id,
            record_date=date.today(),
            meal_type=meal_type,
            food_name=label,
            food_items=label,
            source="chat_photo",
        )
        for meal_type, label in (("breakfast", "早餐"), ("lunch", "午餐"))
    ]
    db.add_all(records)
    db.flush()
    assets = [
        DietPhotoAsset(
            id=f"diet-history-photo-{ordinal}",
            user_id=user.id,
            diet_record_id=records[ordinal].id,
            storage_key=(
                f"/api/v1/upload/files/diet/{user.id}/meal-{ordinal}.jpg"
            ),
            content_sha256=str(ordinal + 1) * 64,
            media_type="image/jpeg",
            origin="chat",
            ordinal=ordinal,
            classification="food",
            recognition_confidence=0.93,
            intent_decision="auto_record",
            recognition_snapshot={"food_count": 1},
            lifecycle="attached",
        )
        for ordinal in range(2)
    ]
    db.add_all(assets)
    first.meta = {
        "cards": [{
            "type": "diet_draft",
            "data": {
                "recorded": True,
                "record_id": records[0].id,
                "photo_asset_id": assets[0].id,
                "food_items": "早餐",
            },
            "actions": [],
        }],
    }
    second.meta = {
        "cards": [{
            "type": "diet_draft",
            "data": {
                "recorded": True,
                "record_id": records[1].id,
                "photo_asset_id": assets[1].id,
                "food_items": "午餐",
            },
            "actions": [],
        }],
    }
    db.commit()

    response = client.get(f"/api/v1/agent/conversations/{conv.id}", headers=headers)

    assert response.status_code == 200
    cards = [
        message["meta"]["cards"][0]
        for message in response.json()["messages"]
    ]
    for ordinal, card in enumerate(cards):
        photo_url = card["data"]["photo_url"]
        parsed = urlparse(photo_url)
        query = parse_qs(parsed.query)
        assert parsed.path == (
            f"/api/v1/upload/files/diet/{user.id}/meal-{ordinal}.jpg"
        )
        assert "expires" in query
        assert "signature" in query

    db.refresh(first)
    db.refresh(second)
    assert "photo_url" not in first.meta["cards"][0]["data"]
    assert "photo_url" not in second.meta["cards"][0]["data"]


def test_agent_conversation_detail_never_restores_another_users_diet_photo(
    client, db, auth_user_and_headers
):
    user, headers = auth_user_and_headers
    other = _create_user(db, "diet_photo_owner")
    foreign_record = DietRecord(
        user_id=other.id,
        record_date=date.today(),
        meal_type="lunch",
        food_name="私有餐食",
        food_items="私有餐食",
        source="chat_photo",
    )
    db.add(foreign_record)
    db.flush()
    foreign_asset = DietPhotoAsset(
        id="foreign-diet-history-photo",
        user_id=other.id,
        diet_record_id=foreign_record.id,
        storage_key=(
            f"/api/v1/upload/files/diet/{other.id}/private-meal.jpg"
        ),
        content_sha256="f" * 64,
        media_type="image/jpeg",
        origin="chat",
        ordinal=0,
        classification="food",
        recognition_confidence=0.91,
        intent_decision="auto_record",
        recognition_snapshot={"food_count": 1},
        lifecycle="attached",
    )
    db.add(foreign_asset)
    conv = _create_conversation(db, user.id, "隔离照片")
    message = _add_message(db, conv.id, "assistant", "餐食已记录。")
    message.meta = {
        "cards": [{
            "type": "diet_draft",
            "data": {
                "recorded": True,
                "record_id": foreign_record.id,
                "photo_asset_id": foreign_asset.id,
                "photo_url": (
                    f"/api/v1/upload/files/diet/{other.id}/private-meal.jpg"
                    "?expires=9999999999&signature=untrusted"
                ),
            },
            "actions": [],
        }],
    }
    db.commit()

    response = client.get(f"/api/v1/agent/conversations/{conv.id}", headers=headers)

    assert response.status_code == 200
    card_data = response.json()["messages"][0]["meta"]["cards"][0]["data"]
    assert "photo_url" not in card_data


def test_agent_conversation_detail_restores_one_multi_photo_card_in_asset_order(
    client, db, auth_user_and_headers
):
    user, headers = auth_user_and_headers
    conv = _create_conversation(db, user.id, "多图午餐")
    message = _add_message(db, conv.id, "assistant", "午餐已记录。")
    record = DietRecord(
        user_id=user.id,
        record_date=date.today(),
        meal_type="lunch",
        food_name="多图午餐",
        food_items="多图午餐",
        source="chat_photo",
    )
    db.add(record)
    db.flush()
    assets = [
        DietPhotoAsset(
            id=f"multi-photo-{ordinal}",
            user_id=user.id,
            diet_record_id=record.id,
            storage_key=f"/api/v1/upload/files/diet/{user.id}/multi-{ordinal}.jpg",
            content_sha256=str(ordinal + 3) * 64,
            media_type="image/jpeg",
            origin="chat",
            ordinal=ordinal,
            classification="food",
            recognition_confidence=0.9,
            intent_decision="auto_record",
            recognition_snapshot={"food_count": 1},
            lifecycle="attached",
        )
        for ordinal in range(2)
    ]
    db.add_all(assets)
    message.meta = {
        "cards": [{
            "type": "diet_draft",
            "data": {
                "card_id": f"diet-record:{record.id}",
                "recorded": True,
                "record_id": record.id,
                "photo_asset_id": assets[0].id,
                "photo_asset_ids": [assets[1].id, assets[0].id],
            },
            "actions": [],
        }],
    }
    db.commit()

    response = client.get(f"/api/v1/agent/conversations/{conv.id}", headers=headers)

    assert response.status_code == 200
    data = response.json()["messages"][0]["meta"]["cards"][0]["data"]
    assert data["photo_asset_ids"] == [assets[1].id, assets[0].id]
    assert len(data["photo_urls"]) == 2
    assert [
        urlparse(value).path
        for value in data["photo_urls"]
    ] == [
        f"/api/v1/upload/files/diet/{user.id}/multi-1.jpg",
        f"/api/v1/upload/files/diet/{user.id}/multi-0.jpg",
    ]
    assert data["photo_url"] == data["photo_urls"][0]

    db.refresh(message)
    durable_data = message.meta["cards"][0]["data"]
    assert "photo_url" not in durable_data
    assert "photo_urls" not in durable_data


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


def test_merge_card_descriptors_replaces_same_stable_card_with_fresher_projection():
    first = {
        "type": "diet_draft",
        "data": {"card_id": "diet-record:42", "photo_asset_ids": ["one"]},
    }
    fresher = {
        "type": "diet_draft",
        "data": {"card_id": "diet-record:42", "photo_asset_ids": ["one", "two"]},
    }

    merged = _merge_card_descriptors([first], [fresher])

    assert merged == [fresher]


def test_answer_owns_visualization_for_closed_deterministic_reva_ui_fences():
    payloads = [
        {"type": "diet_daily_summary", "v": 1, "data": {}},
        {
            "type": "metric_table",
            "v": 1,
            "columns": [
                {"key": "date", "label": "日期"},
                {"key": "value", "label": "数值"},
            ],
            "rows": [{"date": "07-22", "value": 58}],
        },
        {"type": "sleep_summary", "v": 1, "data": {}},
        {"type": "medication_list", "v": 1, "data": {}},
        {"component": "line_chart", "v": 1, "series": []},
        {"component": "metric_line_chart", "v": 1, "series": []},
        {"component": "metric_empty_state", "v": 1},
    ]

    for payload in payloads:
        answer = f"结论如下。\n```reva-ui\n{json.dumps(payload)}\n```"
        assert _answer_owns_its_visualization(answer, ["health_query"]) is True


def test_answer_does_not_own_visualization_for_untrusted_reva_ui_text():
    controls = [
        "正文只提到了 diet_daily_summary。",
        '```reva-ui\n{"type":"unknown_widget","v":1}\n```',
        '```reva-ui\n{"type":"diet_daily_summary",}\n```',
        '```reva-ui\n{"type":"diet_daily_summary","v":1}',
    ]

    for answer in controls:
        assert _answer_owns_its_visualization(answer, ["health_query"]) is False


def test_answer_does_not_own_client_rejected_reva_ui_fences():
    controls = [
        {"type": "diet_daily_summary", "data": {}},
        {"type": "diet_daily_summary", "v": 2, "data": {}},
        {"type": "diet_daily_summary", "v": "1", "data": {}},
        {"type": "diet_daily_summary", "v": True, "data": {}},
        {"type": "sleep_summary", "v": 1},
        {"type": "medication_list", "v": 1, "data": []},
        {"type": "metric_table", "v": 1, "columns": [], "rows": []},
        {"type": "metric_table", "v": 1, "columns": {}, "rows": []},
        {"type": "metric_table", "v": 1, "columns": [], "rows": {}},
        {
            "type": "metric_table",
            "v": 1,
            "columns": [{"key": "value", "label": "数值"}],
            "rows": [{"value": "58"}],
        },
        {
            "type": "metric_table",
            "v": 1,
            "columns": [
                {"key": "value", "label": "数值"},
                {"key": "value", "label": "重复数值"},
            ],
            "rows": [{"value": "58"}],
        },
        {
            "type": "metric_table",
            "v": 1,
            "columns": [
                {"key": "date", "label": "日期"},
                {"key": "value", "label": "数值"},
            ],
            "rows": [{}],
        },
        {
            "type": "metric_table",
            "v": 1,
            "columns": [
                {"key": "date", "label": "日期"},
                {"key": "value", "label": "数值"},
            ],
            "rows": [{"date": "  ", "value": ""}],
        },
        {
            "type": "metric_table",
            "v": 1,
            "columns": [
                {"key": "date", "label": "日期"},
                {"key": "value", "label": "数值"},
            ],
            "rows": [{"date": None, "value": True}],
        },
        {
            "type": "metric_table",
            "v": 1,
            "columns": [
                {"key": "date", "label": "日期"},
                {"key": "value", "label": "数值"},
            ],
            "rows": [{"date": float("nan"), "value": float("nan")}],
        },
        {
            "type": "metric_table",
            "v": 2,
            "columns": [
                {"key": "date", "label": "日期"},
                {"key": "value", "label": "数值"},
            ],
            "rows": [{"date": "07-22", "value": "58"}],
        },
        {"component": "line_chart", "series": []},
        {"component": "metric_line_chart", "v": 2, "series": []},
        {"type": "diet_daily_summary", "v": 1, "data": {"value": float("nan")}},
        {"type": "diet_daily_summary", "v": 1, "data": {"value": float("inf")}},
        {"type": "diet_daily_summary", "v": 1, "data": {"value": float("-inf")}},
    ]

    for payload in controls:
        answer = f"结论如下。\n```reva-ui\n{json.dumps(payload)}\n```"
        assert _answer_owns_its_visualization(answer, ["health_query"]) is False


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


# ---------------------------------------------------------------------------
# /agent/send 保活流式聚合回归(2026-07-06)
# 实锤:重量级深分析回合 >60s 被 main.py 请求超时中间件杀成 504。
# 修法:超窗切 chunked JSON(前导空白保活 + 末尾完整对象)。
# 测试把时间尺度压缩:中间件 1s + 回合 2.5s,修复前必 504、修复后 200。
# ---------------------------------------------------------------------------


def test_agent_send_slow_turn_streams_keepalive_not_504(
    client, auth_user_and_headers, monkeypatch
):
    import asyncio
    import json as jsonlib

    import main as main_module
    from app.api import agent as agent_api

    _, headers = auth_user_and_headers
    monkeypatch.setattr(main_module, "REQUEST_TIMEOUT", 1)
    monkeypatch.setattr(agent_api, "AGENT_SEND_KEEPALIVE_SECONDS", 0.1)

    async def fake_run_stream(self, **kwargs):
        yield {"event": "token", "data": {"content": "深度"}}
        await asyncio.sleep(2.5)  # > 中间件 1s:修复前 wait_for 在这里杀成 504
        yield {"event": "token", "data": {"content": "分析结论"}}
        yield {
            "event": "done",
            "data": {"conversation_id": 7, "message_id": 8, "elapsed_ms": 2500},
        }

    monkeypatch.setattr(
        "app.services.agent_executor.AgentExecutor.run_stream", fake_run_stream
    )

    res = client.post(
        "/api/v1/agent/send",
        headers=headers,
        json={"message": "慢回合保活回归"},
    )

    assert res.status_code == 200, f"长回合不应再 504/500: {res.status_code} {res.text[:200]}"
    raw = res.text
    # 确实吐过保活前导空白(证明流式路径生效,而非碰巧快窗完成)
    assert raw != raw.lstrip(), "长回合应含保活前导空白"
    assert set(raw[: len(raw) - len(raw.lstrip())]) <= {" ", "\t", "\r", "\n"}
    # 前导空白后仍是合法完整 JSON(RFC 8259 允许前导 ws → 现有客户端零感知)
    body = jsonlib.loads(raw)
    # 老字段零变化;additive meta 也随保活路径一起回(与快窗一致)。
    assert body["reply"] == "深度分析结论"
    assert body["conversation_id"] == 7
    assert body["message_id"] == 8
    assert body["mode"] == "agent"
    assert body["elapsed_ms"] == 2500
    assert isinstance(body.get("meta"), dict)


def test_agent_send_error_after_stream_started_yields_error_envelope(
    client, auth_user_and_headers, monkeypatch
):
    """流开始后(200 已定格)失败 → in-body error 字段,不再是 HTTP 500。"""
    import asyncio
    import json as jsonlib

    from app.api import agent as agent_api

    _, headers = auth_user_and_headers
    monkeypatch.setattr(agent_api, "AGENT_SEND_KEEPALIVE_SECONDS", 0.1)

    async def fake_run_stream(self, **kwargs):
        yield {"event": "token", "data": {"content": "半截"}}
        await asyncio.sleep(0.5)
        yield {"event": "error", "data": {"message": "上游 LLM 断连"}}

    monkeypatch.setattr(
        "app.services.agent_executor.AgentExecutor.run_stream", fake_run_stream
    )

    res = client.post(
        "/api/v1/agent/send",
        headers=headers,
        json={"message": "流后错误 envelope"},
    )

    assert res.status_code == 200
    body = jsonlib.loads(res.text)
    assert isinstance(body.get("error"), str) and body["error"]
    assert body["reply"] == ""
    assert body["mode"] == "agent"


def test_agent_send_fast_error_keeps_http_500(client, auth_user_and_headers, monkeypatch):
    """快窗内失败保持历史语义:HTTP 500 + detail,契约不变。"""

    async def fake_run_stream(self, **kwargs):
        yield {"event": "error", "data": {"message": "配置错误"}}

    monkeypatch.setattr(
        "app.services.agent_executor.AgentExecutor.run_stream", fake_run_stream
    )
    _, headers = auth_user_and_headers

    res = client.post(
        "/api/v1/agent/send",
        headers=headers,
        json={"message": "快窗错误保持500"},
    )

    assert res.status_code == 500
    assert res.json()["detail"]


def test_agent_send_hard_cap_cancels_turn_and_reports_timeout(
    client, auth_user_and_headers, monkeypatch
):
    """硬上限兜底:真卡死的回合被取消(不吊死 worker)+ in-body 超时报错。"""
    import asyncio
    import json as jsonlib

    from app.api import agent as agent_api

    _, headers = auth_user_and_headers
    monkeypatch.setattr(agent_api, "AGENT_SEND_KEEPALIVE_SECONDS", 0.1)
    monkeypatch.setattr(agent_api, "AGENT_SEND_HARD_CAP_SECONDS", 0.5)

    cancelled = {"flag": False}

    async def fake_run_stream(self, **kwargs):
        yield {"event": "token", "data": {"content": "卡"}}
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled["flag"] = True
            raise

    monkeypatch.setattr(
        "app.services.agent_executor.AgentExecutor.run_stream", fake_run_stream
    )

    res = client.post(
        "/api/v1/agent/send",
        headers=headers,
        json={"message": "硬上限取消回合"},
    )

    assert res.status_code == 200
    body = jsonlib.loads(res.text)
    assert "超时" in (body.get("error") or "")
    assert cancelled["flag"], "硬上限触发后底层回合必须被真实取消"


def test_agent_conversations_search_matches_title_and_content(
    client, db, auth_user_and_headers
):
    """search 同时命中标题与消息正文;user-isolation 不破。"""
    user, headers = auth_user_and_headers
    # A: 命中标题
    conv_title = _create_conversation(db, user.id, "睡眠质量复盘")
    _add_message(db, conv_title.id, "user", "帮我看看最近怎么样")
    # B: 标题不含关键词, 但消息正文含
    conv_body = _create_conversation(db, user.id, "随便聊聊")
    _add_message(db, conv_body.id, "user", "我的睡眠总是很浅")
    # C: 都不含
    conv_miss = _create_conversation(db, user.id, "训练计划")
    _add_message(db, conv_miss.id, "user", "今天练腿")
    # 他人含关键词 — 必须被隔离
    other = _create_user(db, "search_other")
    other_conv = _create_conversation(db, other.id, "睡眠问题")
    _add_message(db, other_conv.id, "user", "睡不好")

    res = client.get("/api/v1/agent/conversations?search=睡眠", headers=headers)
    assert res.status_code == 200
    data = res.json()
    ids = {it["id"] for it in data["items"]}
    assert conv_title.id in ids  # 标题命中
    assert conv_body.id in ids   # 正文命中
    assert conv_miss.id not in ids
    assert other_conv.id not in ids  # 用户隔离
    assert data["total"] == 2


def test_agent_conversations_search_no_duplicate_rows_on_multi_message_match(
    client, db, auth_user_and_headers
):
    """一条对话里多条消息都命中关键词 → 结果仍只出现一次(EXISTS 而非 join)。"""
    user, headers = auth_user_and_headers
    conv = _create_conversation(db, user.id, "健康问答")
    _add_message(db, conv.id, "user", "血压有点高")
    _add_message(db, conv.id, "assistant", "血压需要持续监测")
    _add_message(db, conv.id, "user", "血压怎么降")

    res = client.get("/api/v1/agent/conversations?search=血压", headers=headers)
    data = res.json()
    ids = [it["id"] for it in data["items"]]
    assert ids.count(conv.id) == 1
    assert data["total"] == 1
