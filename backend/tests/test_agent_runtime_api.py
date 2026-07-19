import json

import pytest
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models.agent_conversation import AgentConversation, AgentMessage
from app.models.agent_runtime import AgentRun


def test_agent_send_passes_one_canonical_identity_to_executor(
    client, auth_user_and_headers, monkeypatch
):
    _user, headers = auth_user_and_headers
    captured = {}

    async def fake_run_stream(self, **kwargs):
        captured.update(kwargs)
        yield {"event": "token", "data": {"content": "ok"}}
        yield {
            "event": "done",
            "data": {
                "conversation_id": None,
                "message_id": None,
                "completion_status": "complete",
            },
        }

    monkeypatch.setattr(settings, "agent_runtime_mode", "off")
    monkeypatch.setattr(
        "app.services.agent_executor.AgentExecutor.run_stream",
        fake_run_stream,
    )

    response = client.post(
        "/api/v1/agent/send",
        headers=headers,
        json={"message": "runtime identity", "client_turn_id": "runtime-api-identity"},
    )

    assert response.status_code == 200
    body = response.json()
    assert captured["run_id"].startswith("send_")
    assert captured["attempt_id"].startswith("attempt_")
    assert body["run_id"] == captured["run_id"]
    assert body["attempt_id"] == captured["attempt_id"]


def test_agent_send_enforce_mode_persists_and_finishes_run(
    client, db, auth_user_and_headers, monkeypatch
):
    user, headers = auth_user_and_headers

    async def fake_run_stream(self, **kwargs):
        conversation = AgentConversation(
            user_id=kwargs["user_id"],
            title="runtime",
            session_key="runtime-send-ledger",
        )
        self.db.add(conversation)
        self.db.commit()
        source = AgentMessage(
            conversation_id=conversation.id,
            role="user",
            content="private source",
        )
        self.db.add(source)
        self.db.commit()
        yield {
            "event": "request_persisted",
            "data": {
                "conversation_id": conversation.id,
                "user_message_id": source.id,
            },
        }
        assistant = AgentMessage(
            conversation_id=conversation.id,
            role="assistant",
            content="private answer",
        )
        self.db.add(assistant)
        self.db.commit()
        yield {"event": "token", "data": {"content": "private answer"}}
        yield {
            "event": "done",
            "data": {
                "conversation_id": conversation.id,
                "message_id": assistant.id,
                "completion_status": "complete",
                "turn_outcome": {"category": "success"},
            },
        }

    monkeypatch.setattr(settings, "agent_runtime_mode", "enforce")
    monkeypatch.setattr(
        "app.services.agent_executor.AgentExecutor.run_stream",
        fake_run_stream,
    )

    response = client.post(
        "/api/v1/agent/send",
        headers=headers,
        json={"message": "private source", "client_turn_id": "runtime-ledger-turn"},
    )

    assert response.status_code == 200
    run = db.query(AgentRun).filter(
        AgentRun.user_id == user.id,
        AgentRun.client_turn_id == "runtime-ledger-turn",
    ).one()
    assert run.run_id == response.json()["run_id"]
    assert run.status == "succeeded"
    assert run.conversation_id == response.json()["conversation_id"]
    assert run.source_message_id is not None
    assert run.assistant_message_id == response.json()["message_id"]
    assert "private source" not in repr(run.__dict__)


def test_agent_send_enforce_mode_rejects_busy_conversation_before_executor(
    client, db, auth_user_and_headers, monkeypatch
):
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, headers = auth_user_and_headers
    conversation = AgentConversation(
        user_id=user.id,
        title="busy",
        session_key="runtime-busy",
    )
    db.add(conversation)
    db.commit()
    AgentRuntimeCoordinator(db).create_or_resume_run(
        run_id="run-already-active",
        attempt_id="attempt-already-active",
        user_id=user.id,
        conversation_id=conversation.id,
        client_turn_id="turn-already-active",
        origin="agent_send",
    )
    called = False

    async def must_not_run(self, **kwargs):
        nonlocal called
        called = True
        yield {"event": "done", "data": {}}

    monkeypatch.setattr(settings, "agent_runtime_mode", "enforce")
    monkeypatch.setattr(
        "app.services.agent_executor.AgentExecutor.run_stream",
        must_not_run,
    )

    response = client.post(
        "/api/v1/agent/send",
        headers=headers,
        json={
            "message": "second turn",
            "conversation_id": conversation.id,
            "client_turn_id": "turn-busy-second",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "上一条消息仍在处理，请稍后重试"
    assert called is False


def test_agent_send_enforce_mode_hides_foreign_conversation(
    client, db, auth_user_and_headers, monkeypatch
):
    from app.models.user import User

    _user, headers = auth_user_and_headers
    other = User(
        username="runtime-api-other",
        email="runtime-api-other@example.com",
        hashed_password="hashed",
        name="other",
        is_active=True,
        is_approved=True,
    )
    db.add(other)
    db.commit()
    conversation = AgentConversation(
        user_id=other.id,
        title="private",
        session_key="runtime-api-private",
    )
    db.add(conversation)
    db.commit()
    monkeypatch.setattr(settings, "agent_runtime_mode", "enforce")

    response = client.post(
        "/api/v1/agent/send",
        headers=headers,
        json={
            "message": "must not access",
            "conversation_id": conversation.id,
            "client_turn_id": "runtime-api-cross-owner",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "对话不存在"


def test_shortcut_finalization_failure_closes_active_run(
    db, auth_user_and_headers
):
    from app.api.agent import _finalize_agent_runtime_events
    from app.services.agent_runtime import AgentRuntimeCoordinator, AgentRuntimeError

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = runtime.create_or_resume_run(
        run_id="run-shortcut-cleanup",
        attempt_id="attempt-shortcut-cleanup",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-shortcut-cleanup",
        origin="agent_stream",
    )
    events = [
        {
            "event": "done",
            "data": {
                "conversation_id": 999999,
                "message_id": None,
                "completion_status": "complete",
            },
        }
    ]

    with pytest.raises(AgentRuntimeError, match="conversation_not_found"):
        _finalize_agent_runtime_events(
            db,
            admission.context,
            managed=True,
            events=events,
        )

    run = runtime.get_run(user.id, admission.context.run_id)
    assert run.status == "failed"
    assert run.error_code == "shortcut_finalize_failed"


def test_agent_stream_passes_canonical_identity_to_executor(
    client, db, auth_user_and_headers, monkeypatch
):
    _user, headers = auth_user_and_headers
    captured = {}

    async def fake_run_stream(self, **kwargs):
        captured.update(kwargs)
        yield {"event": "token", "data": {"content": "stream-ok"}}
        yield {
            "event": "done",
            "data": {
                "conversation_id": None,
                "message_id": None,
                "completion_status": "complete",
            },
        }

    monkeypatch.setattr(settings, "agent_runtime_mode", "off")
    monkeypatch.setattr(
        "app.services.agent_executor.AgentExecutor.run_stream",
        fake_run_stream,
    )
    monkeypatch.setattr(
        "app.database.SessionLocal",
        sessionmaker(bind=db.get_bind(), autocommit=False, autoflush=False),
    )

    response = client.post(
        "/api/v1/agent/stream",
        headers=headers,
        json={"message": "stream identity", "client_turn_id": "runtime-stream-identity"},
    )

    assert response.status_code == 200
    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    done = next(event for event in events if event.get("event") == "done")
    assert captured["run_id"].startswith("run_")
    assert captured["attempt_id"].startswith("attempt_")
    assert done["data"]["run_id"] == captured["run_id"]
    assert done["data"]["attempt_id"] == captured["attempt_id"]


def test_agent_stream_genui_shortcut_gets_runtime_identity(
    client, db, auth_user_and_headers, monkeypatch
):
    user, headers = auth_user_and_headers
    conversation = AgentConversation(
        user_id=user.id,
        title="runtime-genui",
        session_key="runtime-genui-shortcut",
    )
    db.add(conversation)
    db.commit()
    source = AgentMessage(
        conversation_id=conversation.id,
        role="user",
        content="show chart",
    )
    assistant = AgentMessage(
        conversation_id=conversation.id,
        role="assistant",
        content="chart",
    )
    db.add_all([source, assistant])
    db.commit()
    events = [
        {
            "event": "request_persisted",
            "data": {
                "conversation_id": conversation.id,
                "user_message_id": source.id,
            },
        },
        {"event": "token", "data": {"content": "chart"}},
        {
            "event": "done",
            "data": {
                "conversation_id": conversation.id,
                "message_id": assistant.id,
                "completion_status": "complete",
                "turn_outcome": {"category": "success"},
            },
        },
    ]

    monkeypatch.setattr(settings, "agent_runtime_mode", "enforce")
    monkeypatch.setattr(
        "app.api.agent._maybe_genui_chart_events",
        lambda *_args, **_kwargs: (events, conversation.id, assistant.id),
    )

    response = client.post(
        "/api/v1/agent/stream",
        headers={**headers, "X-Reva-Client-Caps": "genui-v1"},
        json={"message": "show chart", "client_turn_id": "runtime-genui-turn"},
    )

    assert response.status_code == 200
    emitted = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    done = next(event for event in emitted if event.get("event") == "done")
    run = db.query(AgentRun).filter(
        AgentRun.user_id == user.id,
        AgentRun.client_turn_id == "runtime-genui-turn",
    ).one()
    assert run.status == "succeeded"
    assert done["data"]["run_id"] == run.run_id
    assert done["data"]["attempt_id"].startswith("attempt_")
