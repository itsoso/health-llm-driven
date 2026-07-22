"""Agent conversation history API tests."""

import inspect
import json
import logging
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy.orm import sessionmaker

from app.models.agent_conversation import AgentConversation, AgentMessage
from app.models.user import User
from app.api.agent import (
    agent_stream,
    _answer_owns_its_visualization,
    _done_event_may_expose_cards,
    _merge_card_descriptors,
    _persist_done_cards,
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
            "rows": [{"date": "07-22", "value": "58"}],
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
            "v": 2,
            "columns": [
                {"key": "date", "label": "日期"},
                {"key": "value", "label": "数值"},
            ],
            "rows": [{"date": "07-22", "value": "58"}],
        },
        {"component": "line_chart", "series": []},
        {"component": "metric_line_chart", "v": 2, "series": []},
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
