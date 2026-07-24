import asyncio
import json
import time

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


def test_agent_send_propagates_paused_runtime_write_block_to_executor(
    client, db, auth_user_and_headers, monkeypatch
):
    from app.services.agent_runtime_rollout import AgentRuntimeRolloutService

    user, headers = auth_user_and_headers
    captured = {}

    async def fake_run_stream(self, **kwargs):
        captured.update(kwargs)
        yield {"event": "token", "data": {"content": "read-only answer"}}
        yield {
            "event": "done",
            "data": {
                "conversation_id": None,
                "message_id": None,
                "completion_status": "complete",
            },
        }

    monkeypatch.setattr(settings, "agent_runtime_mode", "enforce")
    AgentRuntimeRolloutService(db).pause(
        actor_kind="admin",
        reason_code="manual_pause",
        actor_user_id=user.id,
    )
    monkeypatch.setattr(
        "app.services.agent_executor.AgentExecutor.run_stream",
        fake_run_stream,
    )

    response = client.post(
        "/api/v1/agent/send",
        headers=headers,
        json={
            "message": "查询今天饮水",
            "client_turn_id": "runtime-send-paused-control",
        },
    )

    assert response.status_code == 200
    assert captured["runtime_managed"] is False
    assert captured["runtime_write_block_reason"] == "circuit_paused"


def test_off_mode_ignores_invalid_runtime_deadline_configuration(
    db, auth_user_and_headers, monkeypatch
):
    from app.api.agent import _admit_agent_runtime

    user, _headers = auth_user_and_headers
    monkeypatch.setattr(settings, "agent_runtime_mode", "off")
    monkeypatch.setattr(settings, "agent_runtime_deadline_seconds", 10)

    context, owned, disposition = _admit_agent_runtime(
        db,
        run_id="run-off-invalid-deadline",
        attempt_id="attempt-off-invalid-deadline",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-off-invalid-deadline",
        origin="test",
    )

    assert context.run_id == "run-off-invalid-deadline"
    assert owned is False
    assert disposition == "execute"
    assert db.query(AgentRun).count() == 0


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
        active_run = self.db.query(AgentRun).filter(
            AgentRun.user_id == kwargs["user_id"],
            AgentRun.client_turn_id == "runtime-ledger-turn",
        ).one()
        assert active_run.conversation_id == conversation.id
        assert active_run.source_message_id == source.id
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


@pytest.mark.parametrize(
    ("percent", "allowlisted", "expected_managed"),
    [
        (0, False, False),
        (0, True, True),
        (100, False, True),
    ],
)
def test_agent_send_canary_admission_is_stable_and_backward_compatible(
    client,
    db,
    auth_user_and_headers,
    monkeypatch,
    percent,
    allowlisted,
    expected_managed,
):
    user, headers = auth_user_and_headers
    managed_flags = []

    async def fake_run_stream(self, **kwargs):
        managed_flags.append(kwargs.get("runtime_managed"))
        yield {
            "event": "done",
            "data": {
                "conversation_id": None,
                "message_id": None,
                "completion_status": "complete",
                "turn_outcome": {"category": "success"},
            },
        }

    monkeypatch.setattr(settings, "agent_runtime_mode", "canary")
    monkeypatch.setattr(settings, "agent_runtime_canary_percent", percent)
    monkeypatch.setattr(
        settings,
        "agent_runtime_canary_user_ids",
        str(user.id) if allowlisted else "",
    )
    monkeypatch.setattr(
        "app.services.agent_executor.AgentExecutor.run_stream",
        fake_run_stream,
    )

    response = client.post(
        "/api/v1/agent/send",
        headers=headers,
        json={
            "message": "canary admission",
            "client_turn_id": f"runtime-canary-{percent}-{allowlisted}",
        },
    )

    assert response.status_code == 200
    assert managed_flags == [expected_managed]
    rows = db.query(AgentRun).filter(AgentRun.user_id == user.id).all()
    assert (len(rows) == 1) is expected_managed
    if rows:
        assert rows[0].status == "succeeded"


def test_existing_managed_turn_stays_managed_after_circuit_pause(
    db, auth_user_and_headers, monkeypatch
):
    from app.api.agent import _admit_agent_runtime
    from app.services.agent_runtime_rollout import AgentRuntimeRolloutService

    user, _headers = auth_user_and_headers
    monkeypatch.setattr(settings, "agent_runtime_mode", "canary")
    monkeypatch.setattr(settings, "agent_runtime_canary_percent", 100)
    monkeypatch.setattr(settings, "agent_runtime_canary_user_ids", "")
    first, first_owned, first_disposition = _admit_agent_runtime(
        db,
        run_id="run-before-pause",
        attempt_id="attempt-before-pause",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-before-pause",
        origin="test",
    )
    AgentRuntimeRolloutService(db).pause(
        actor_kind="system",
        reason_code="stale_lease_detected",
    )

    repeated, repeated_owned, repeated_disposition = _admit_agent_runtime(
        db,
        run_id="run-after-pause",
        attempt_id="attempt-after-pause",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-before-pause",
        origin="test",
    )

    assert first_owned is True
    assert first_disposition == "execute"
    assert repeated.run_id == first.run_id
    assert repeated_owned is False
    assert repeated_disposition == "observe"


def test_existing_managed_turn_stays_managed_after_canary_percentage_shrinks(
    db, auth_user_and_headers, monkeypatch
):
    from app.api.agent import _admit_agent_runtime

    user, _headers = auth_user_and_headers
    monkeypatch.setattr(settings, "agent_runtime_mode", "canary")
    monkeypatch.setattr(settings, "agent_runtime_canary_percent", 100)
    monkeypatch.setattr(settings, "agent_runtime_canary_user_ids", "")
    first, _owned, _disposition = _admit_agent_runtime(
        db,
        run_id="run-before-shrink",
        attempt_id="attempt-before-shrink",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-before-shrink",
        origin="test",
    )
    monkeypatch.setattr(settings, "agent_runtime_canary_percent", 0)

    repeated, repeated_owned, repeated_disposition = _admit_agent_runtime(
        db,
        run_id="run-after-shrink",
        attempt_id="attempt-after-shrink",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-before-shrink",
        origin="test",
    )

    assert repeated.run_id == first.run_id
    assert repeated_owned is False
    assert repeated_disposition == "observe"


def test_off_mode_does_not_resume_an_existing_managed_turn(
    db, auth_user_and_headers, monkeypatch
):
    from app.api.agent import _admit_agent_runtime

    user, _headers = auth_user_and_headers
    monkeypatch.setattr(settings, "agent_runtime_mode", "enforce")
    first, _owned, _disposition = _admit_agent_runtime(
        db,
        run_id="run-before-off",
        attempt_id="attempt-before-off",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-before-off",
        origin="test",
    )
    monkeypatch.setattr(settings, "agent_runtime_mode", "off")

    repeated, repeated_owned, repeated_disposition = _admit_agent_runtime(
        db,
        run_id="run-after-off",
        attempt_id="attempt-after-off",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-before-off",
        origin="test",
    )

    assert repeated.run_id != first.run_id
    assert repeated.run_id == "run-after-off"
    assert repeated_owned is False
    assert repeated_disposition == "execute"


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


def test_agent_send_enforce_mode_does_not_execute_duplicate_active_turn(
    client, db, auth_user_and_headers, monkeypatch
):
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, headers = auth_user_and_headers
    AgentRuntimeCoordinator(db).create_or_resume_run(
        run_id="run-active-duplicate",
        attempt_id="attempt-active-duplicate",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-active-duplicate",
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
            "message": "same turn",
            "client_turn_id": "turn-active-duplicate",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "该消息仍在处理中，请稍后重试"
    assert called is False


def test_agent_send_replays_terminal_run_without_executor(
    client, db, auth_user_and_headers, monkeypatch
):
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, headers = auth_user_and_headers
    conversation = AgentConversation(
        user_id=user.id,
        title="replay",
        session_key="runtime-terminal-replay",
    )
    db.add(conversation)
    db.commit()
    source = AgentMessage(
        conversation_id=conversation.id,
        role="user",
        content="private replay source",
        meta={"client_turn_id": "turn-terminal-replay"},
    )
    assistant = AgentMessage(
        conversation_id=conversation.id,
        role="assistant",
        content="durable replay answer",
        meta={
            "client_turn_id": "turn-terminal-replay",
            "completion_status": "complete",
            "turn_outcome": {"category": "success"},
        },
    )
    db.add_all([source, assistant])
    db.commit()
    runtime = AgentRuntimeCoordinator(db)
    admission = runtime.create_or_resume_run(
        run_id="run-terminal-replay",
        attempt_id="attempt-terminal-replay",
        user_id=user.id,
        conversation_id=conversation.id,
        client_turn_id="turn-terminal-replay",
        origin="agent_send",
    )
    runtime.mark_running(admission.context)
    runtime.bind_messages(
        admission.context,
        conversation_id=conversation.id,
        source_message_id=source.id,
        assistant_message_id=assistant.id,
    )
    runtime.complete(admission.context, status="succeeded")
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
            "message": "private replay source",
            "conversation_id": conversation.id,
            "client_turn_id": "turn-terminal-replay",
        },
    )

    assert response.status_code == 200
    assert response.json()["reply"] == "durable replay answer"
    assert response.json()["run_id"] == admission.context.run_id
    assert response.json()["attempt_id"] == admission.context.attempt_id
    assert response.json()["meta"]["replayed"] is True
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


def test_shortcut_cleanup_recovers_after_finalize_session_failure(
    db, auth_user_and_headers, monkeypatch
):
    from app.api.agent import _finalize_agent_runtime_events
    from app.models.agent_runtime import AgentRun
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = runtime.create_or_resume_run(
        run_id="run-shortcut-rollback",
        attempt_id="attempt-shortcut-rollback",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-shortcut-rollback",
        origin="agent_stream",
    )

    def fail_with_pending_rollback(session, context, **_kwargs):
        session.add(
            AgentRun(
                run_id=context.run_id,
                user_id=context.user_id,
                status="queued",
                origin="test",
                privacy_mode="cloud",
            )
        )
        session.flush()

    monkeypatch.setattr(
        "app.api.agent._finalize_agent_runtime",
        fail_with_pending_rollback,
    )

    with pytest.raises(Exception):
        _finalize_agent_runtime_events(
            db,
            admission.context,
            managed=True,
            events=[
                {
                    "event": "done",
                    "data": {
                        "conversation_id": None,
                        "message_id": None,
                        "completion_status": "complete",
                    },
                }
            ],
        )

    db.expire_all()
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


def test_agent_stream_propagates_paused_runtime_write_block_to_executor(
    client, db, auth_user_and_headers, monkeypatch
):
    from app.services.agent_runtime_rollout import AgentRuntimeRolloutService

    user, headers = auth_user_and_headers
    captured = {}

    async def fake_run_stream(self, **kwargs):
        captured.update(kwargs)
        yield {"event": "token", "data": {"content": "read-only answer"}}
        yield {
            "event": "done",
            "data": {
                "conversation_id": None,
                "message_id": None,
                "completion_status": "complete",
            },
        }

    monkeypatch.setattr(settings, "agent_runtime_mode", "enforce")
    AgentRuntimeRolloutService(db).pause(
        actor_kind="admin",
        reason_code="manual_pause",
        actor_user_id=user.id,
    )
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
        json={
            "message": "查询今天饮水",
            "client_turn_id": "runtime-stream-paused-control",
        },
    )

    assert response.status_code == 200
    assert captured["runtime_managed"] is False
    assert captured["runtime_write_block_reason"] == "circuit_paused"


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


def test_agent_runtime_cancel_endpoint_cancels_queued_run(
    client, db, auth_user_and_headers, monkeypatch
):
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, headers = auth_user_and_headers
    monkeypatch.setattr(settings, "agent_runtime_mode", "enforce")
    admission = AgentRuntimeCoordinator(db).create_or_resume_run(
        run_id="run-api-cancel-queued",
        attempt_id="attempt-api-cancel-queued",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-api-cancel-queued",
        origin="test",
    )

    response = client.post(
        f"/api/v1/agent/runs/{admission.context.run_id}/cancel",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json() == {
        "run_id": admission.context.run_id,
        "status": "cancelled",
    }
    assert AgentRuntimeCoordinator(db).get_run(
        user.id, admission.context.run_id
    ).status == "cancelled"


def test_agent_runtime_existing_run_remains_operable_after_canary_pause(
    client, db, auth_user_and_headers, monkeypatch
):
    from app.services.agent_runtime import AgentRuntimeCoordinator
    from app.services.agent_runtime_rollout import AgentRuntimeRolloutService

    user, headers = auth_user_and_headers
    monkeypatch.setattr(settings, "agent_runtime_mode", "canary")
    monkeypatch.setattr(settings, "agent_runtime_canary_percent", 100)
    monkeypatch.setattr(settings, "agent_runtime_canary_user_ids", "")
    admission = AgentRuntimeCoordinator(db).create_or_resume_run(
        run_id="run-api-canary-paused",
        attempt_id="attempt-api-canary-paused",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-api-canary-paused",
        origin="test",
    )
    AgentRuntimeRolloutService(db).pause(
        actor_kind="system",
        reason_code="stale_lease_detected",
    )

    status_response = client.get(
        f"/api/v1/agent/runs/{admission.context.run_id}",
        headers=headers,
    )
    cancel_response = client.post(
        f"/api/v1/agent/runs/{admission.context.run_id}/cancel",
        headers=headers,
    )

    assert status_response.status_code == 200
    assert status_response.json()["status"] == "queued"
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled"


def test_agent_runtime_cancel_endpoint_requests_running_worker_stop(
    client, db, auth_user_and_headers, monkeypatch
):
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, headers = auth_user_and_headers
    monkeypatch.setattr(settings, "agent_runtime_mode", "enforce")
    runtime = AgentRuntimeCoordinator(db)
    admission = runtime.create_or_resume_run(
        run_id="run-api-cancel-running",
        attempt_id="attempt-api-cancel-running",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-api-cancel-running",
        origin="test",
    )
    runtime.mark_running(admission.context, worker_id="remote-worker")

    response = client.post(
        f"/api/v1/agent/runs/{admission.context.run_id}/cancel",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "cancellation_requested"
    db.expire_all()
    run = runtime.get_run(user.id, admission.context.run_id)
    assert run.status == "running"
    assert run.cancel_requested_at is not None


def test_agent_runtime_cancel_endpoint_hides_other_users_run(
    client, db, auth_user_and_headers, monkeypatch
):
    from app.models.user import User
    from app.services.agent_runtime import AgentRuntimeCoordinator

    _user, headers = auth_user_and_headers
    monkeypatch.setattr(settings, "agent_runtime_mode", "enforce")
    other = User(
        username="runtime-cancel-other",
        email="runtime-cancel-other@example.com",
        hashed_password="hashed",
        name="runtime-cancel-other",
        is_active=True,
        is_approved=True,
    )
    db.add(other)
    db.commit()
    admission = AgentRuntimeCoordinator(db).create_or_resume_run(
        run_id="run-api-cancel-other",
        attempt_id="attempt-api-cancel-other",
        user_id=other.id,
        conversation_id=None,
        client_turn_id="turn-api-cancel-other",
        origin="test",
    )

    response = client.post(
        f"/api/v1/agent/runs/{admission.context.run_id}/cancel",
        headers=headers,
    )

    assert response.status_code == 404


@pytest.mark.parametrize(
    ("request_cancel", "expected_status", "expected_error", "expected_retryable"),
    [
        (False, "failed", "worker_interrupted", True),
        (True, "cancelled", "cancelled", False),
    ],
)
def test_agent_runtime_api_interruption_preserves_cancel_intent(
    db,
    auth_user_and_headers,
    request_cancel,
    expected_status,
    expected_error,
    expected_retryable,
):
    from app.api.agent import _interrupt_agent_runtime
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    suffix = "cancel" if request_cancel else "worker"
    runtime = AgentRuntimeCoordinator(db)
    admission = runtime.create_or_resume_run(
        run_id=f"run-api-interrupt-{suffix}",
        attempt_id=f"attempt-api-interrupt-{suffix}",
        user_id=user.id,
        conversation_id=None,
        client_turn_id=f"turn-api-interrupt-{suffix}",
        origin="test",
    )
    runtime.mark_running(
        admission.context,
        worker_id=f"worker-api-interrupt-{suffix}",
    )
    if request_cancel:
        runtime.request_cancel(user.id, admission.context.run_id)

    _interrupt_agent_runtime(db, admission.context, managed=True)

    run = runtime.get_run(user.id, admission.context.run_id)
    assert run.status == expected_status
    assert run.error_code == expected_error
    assert run.retryable is expected_retryable


@pytest.mark.asyncio
async def test_agent_runtime_task_registry_cancels_and_cleans():
    from app.api.agent import (
        _BACKGROUND_AGENT_TASKS_BY_RUN,
        _cancel_agent_runtime_task,
        _register_agent_runtime_task,
    )

    started = asyncio.Event()

    async def wait_forever():
        started.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(wait_forever())
    task_retried = asyncio.create_task(wait_forever())
    await started.wait()
    _register_agent_runtime_task("run-registry-cancel", task)
    _register_agent_runtime_task("run-registry-cancel", task_retried)

    assert _cancel_agent_runtime_task("run-registry-cancel") is True
    with pytest.raises(asyncio.CancelledError):
        await task
    with pytest.raises(asyncio.CancelledError):
        await task_retried
    await asyncio.sleep(0)
    assert "run-registry-cancel" not in _BACKGROUND_AGENT_TASKS_BY_RUN


@pytest.mark.asyncio
async def test_agent_runtime_heartbeat_renews_with_an_independent_session(
    db, auth_user_and_headers, monkeypatch
):
    from app.api.agent import _agent_runtime_heartbeat
    from app.models.agent_runtime import AgentRunAttempt
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = runtime.create_or_resume_run(
        run_id="run-api-heartbeat",
        attempt_id="attempt-api-heartbeat",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-api-heartbeat",
        origin="test",
    )
    runtime.mark_running(
        admission.context,
        worker_id="worker-heartbeat",
        lease_seconds=5,
    )
    original = db.get(AgentRunAttempt, admission.context.attempt_id).heartbeat_at
    monkeypatch.setattr(settings, "agent_runtime_heartbeat_seconds", 1)
    monkeypatch.setattr(settings, "agent_runtime_lease_seconds", 5)
    monkeypatch.setattr(
        "app.database.SessionLocal",
        sessionmaker(bind=db.get_bind(), autocommit=False, autoflush=False),
    )

    owner = asyncio.create_task(asyncio.sleep(5))
    heartbeat = asyncio.create_task(
        _agent_runtime_heartbeat(
            admission.context,
            managed=True,
            worker_id="worker-heartbeat",
            owner_task=owner,
            initial_lease_deadline=time.monotonic() + 5,
        )
    )
    await asyncio.sleep(1.1)
    db.expire_all()
    renewed = db.get(AgentRunAttempt, admission.context.attempt_id)

    assert renewed.heartbeat_at > original
    heartbeat.cancel()
    owner.cancel()
    with pytest.raises(asyncio.CancelledError):
        await heartbeat
    with pytest.raises(asyncio.CancelledError):
        await owner


@pytest.mark.asyncio
async def test_agent_runtime_heartbeat_exits_cleanly_after_run_completes(
    db, auth_user_and_headers, monkeypatch
):
    from app.api.agent import _agent_runtime_heartbeat
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = runtime.create_or_resume_run(
        run_id="run-api-heartbeat-complete-race",
        attempt_id="attempt-api-heartbeat-complete-race",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-api-heartbeat-complete-race",
        origin="test",
    )
    runtime.mark_running(
        admission.context,
        worker_id="worker-heartbeat-complete-race",
        lease_seconds=5,
    )
    runtime.complete(admission.context, status="succeeded")
    monkeypatch.setattr(settings, "agent_runtime_heartbeat_seconds", 1)
    monkeypatch.setattr(settings, "agent_runtime_lease_seconds", 5)
    monkeypatch.setattr(
        "app.database.SessionLocal",
        sessionmaker(bind=db.get_bind(), autocommit=False, autoflush=False),
    )

    owner = asyncio.create_task(asyncio.sleep(5))
    heartbeat = asyncio.create_task(
        _agent_runtime_heartbeat(
            admission.context,
            managed=True,
            worker_id="worker-heartbeat-complete-race",
            owner_task=owner,
            initial_lease_deadline=time.monotonic() + 5,
        )
    )

    await asyncio.wait_for(heartbeat, timeout=1.5)
    assert owner.cancelled() is False
    assert owner.done() is False
    owner.cancel()
    with pytest.raises(asyncio.CancelledError):
        await owner


@pytest.mark.asyncio
async def test_agent_runtime_heartbeat_cancels_worker_reaped_by_recovery(
    db, auth_user_and_headers, monkeypatch
):
    from app.api.agent import _agent_runtime_heartbeat
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = runtime.create_or_resume_run(
        run_id="run-api-heartbeat-reaped",
        attempt_id="attempt-api-heartbeat-reaped",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-api-heartbeat-reaped",
        origin="test",
    )
    runtime.mark_running(
        admission.context,
        worker_id="worker-heartbeat-reaped",
        lease_seconds=5,
    )
    runtime.complete(
        admission.context,
        status="failed",
        error_code="worker_lease_expired",
        retryable=True,
    )
    monkeypatch.setattr(settings, "agent_runtime_heartbeat_seconds", 1)
    monkeypatch.setattr(settings, "agent_runtime_lease_seconds", 5)
    monkeypatch.setattr(
        "app.database.SessionLocal",
        sessionmaker(bind=db.get_bind(), autocommit=False, autoflush=False),
    )

    owner = asyncio.create_task(asyncio.sleep(5))
    await asyncio.wait_for(
        _agent_runtime_heartbeat(
            admission.context,
            managed=True,
            worker_id="worker-heartbeat-reaped",
            owner_task=owner,
            initial_lease_deadline=time.monotonic() + 5,
        ),
        timeout=1.5,
    )

    with pytest.raises(asyncio.CancelledError):
        await owner


@pytest.mark.asyncio
async def test_agent_runtime_heartbeat_cancels_superseded_attempt(
    db, auth_user_and_headers, monkeypatch
):
    from app.api.agent import _agent_runtime_heartbeat
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    first = runtime.create_or_resume_run(
        run_id="run-api-heartbeat-superseded",
        attempt_id="attempt-api-heartbeat-superseded-a",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-api-heartbeat-superseded",
        origin="test",
    )
    runtime.mark_running(
        first.context,
        worker_id="worker-heartbeat-superseded-a",
        lease_seconds=5,
    )
    runtime.complete(
        first.context,
        status="failed",
        error_code="worker_lease_expired",
        retryable=True,
    )
    second = runtime.create_or_resume_run(
        run_id=first.context.run_id,
        attempt_id="attempt-api-heartbeat-superseded-b",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-api-heartbeat-superseded",
        origin="test",
    )
    runtime.mark_running(
        second.context,
        worker_id="worker-heartbeat-superseded-b",
        lease_seconds=5,
    )
    monkeypatch.setattr(settings, "agent_runtime_heartbeat_seconds", 1)
    monkeypatch.setattr(settings, "agent_runtime_lease_seconds", 5)
    monkeypatch.setattr(
        "app.database.SessionLocal",
        sessionmaker(bind=db.get_bind(), autocommit=False, autoflush=False),
    )

    owner = asyncio.create_task(asyncio.sleep(5))
    await asyncio.wait_for(
        _agent_runtime_heartbeat(
            first.context,
            managed=True,
            worker_id="worker-heartbeat-superseded-a",
            owner_task=owner,
            initial_lease_deadline=time.monotonic() + 5,
        ),
        timeout=1.5,
    )

    with pytest.raises(asyncio.CancelledError):
        await owner


@pytest.mark.asyncio
async def test_agent_runtime_heartbeat_retries_transient_database_failure(
    db, auth_user_and_headers, monkeypatch
):
    from app.api.agent import _agent_runtime_heartbeat
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = runtime.create_or_resume_run(
        run_id="run-api-heartbeat-transient",
        attempt_id="attempt-api-heartbeat-transient",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-api-heartbeat-transient",
        origin="test",
    )
    runtime.mark_running(
        admission.context,
        worker_id="worker-heartbeat-transient",
        lease_seconds=5,
    )
    monkeypatch.setattr(settings, "agent_runtime_heartbeat_seconds", 1)
    monkeypatch.setattr(settings, "agent_runtime_lease_seconds", 5)
    real_factory = sessionmaker(
        bind=db.get_bind(), autocommit=False, autoflush=False
    )
    calls = 0

    def flaky_session():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary database failure")
        return real_factory()

    monkeypatch.setattr("app.database.SessionLocal", flaky_session)
    owner = asyncio.create_task(asyncio.sleep(5))
    heartbeat = asyncio.create_task(
        _agent_runtime_heartbeat(
            admission.context,
            managed=True,
            worker_id="worker-heartbeat-transient",
            owner_task=owner,
            initial_lease_deadline=time.monotonic() + 5,
        )
    )

    await asyncio.sleep(2.2)

    assert calls >= 2
    assert heartbeat.done() is False
    assert owner.done() is False
    heartbeat.cancel()
    owner.cancel()
    with pytest.raises(asyncio.CancelledError):
        await heartbeat
    with pytest.raises(asyncio.CancelledError):
        await owner


@pytest.mark.asyncio
async def test_agent_runtime_heartbeat_respects_preexisting_lease_deadline(
    db, auth_user_and_headers, monkeypatch
):
    from app.api.agent import _agent_runtime_heartbeat
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = runtime.create_or_resume_run(
        run_id="run-api-heartbeat-delayed-start",
        attempt_id="attempt-api-heartbeat-delayed-start",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-api-heartbeat-delayed-start",
        origin="test",
    )
    runtime.mark_running(
        admission.context,
        worker_id="worker-heartbeat-delayed-start",
        lease_seconds=5,
    )
    monkeypatch.setattr(settings, "agent_runtime_heartbeat_seconds", 1)
    monkeypatch.setattr(settings, "agent_runtime_lease_seconds", 5)
    monkeypatch.setattr(
        "app.database.SessionLocal",
        lambda: (_ for _ in ()).throw(RuntimeError("database unavailable")),
    )
    owner = asyncio.create_task(asyncio.sleep(10))
    initial_lease_deadline = time.monotonic() + 1.25

    try:
        await asyncio.wait_for(
            _agent_runtime_heartbeat(
                admission.context,
                managed=True,
                worker_id="worker-heartbeat-delayed-start",
                owner_task=owner,
                initial_lease_deadline=initial_lease_deadline,
            ),
            timeout=1.75,
        )
        with pytest.raises(asyncio.CancelledError):
            await owner
    finally:
        if not owner.done():
            owner.cancel()
            with pytest.raises(asyncio.CancelledError):
                await owner


@pytest.mark.asyncio
async def test_agent_runtime_heartbeat_uses_renew_start_for_local_lease_deadline(
    db, auth_user_and_headers, monkeypatch
):
    from app.api.agent import _agent_runtime_heartbeat
    from app.services.agent_runtime import AgentRuntimeCoordinator, RunControlSignal

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = runtime.create_or_resume_run(
        run_id="run-api-heartbeat-slow-renewal",
        attempt_id="attempt-api-heartbeat-slow-renewal",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-api-heartbeat-slow-renewal",
        origin="test",
    )
    runtime.mark_running(
        admission.context,
        worker_id="worker-heartbeat-slow-renewal",
        lease_seconds=5,
    )
    monkeypatch.setattr(settings, "agent_runtime_heartbeat_seconds", 1)
    monkeypatch.setattr(settings, "agent_runtime_lease_seconds", 3)
    real_factory = sessionmaker(
        bind=db.get_bind(), autocommit=False, autoflush=False
    )
    session_calls = 0

    def session_factory():
        nonlocal session_calls
        session_calls += 1
        if session_calls > 1:
            raise RuntimeError("database unavailable after slow renewal")
        return real_factory()

    def slow_renew(self, *args, **kwargs):
        time.sleep(1.25)
        return RunControlSignal("continue")

    monkeypatch.setattr("app.database.SessionLocal", session_factory)
    monkeypatch.setattr(AgentRuntimeCoordinator, "renew_lease", slow_renew)
    owner = asyncio.create_task(asyncio.sleep(10))

    await asyncio.wait_for(
        _agent_runtime_heartbeat(
            admission.context,
            managed=True,
            worker_id="worker-heartbeat-slow-renewal",
            owner_task=owner,
            initial_lease_deadline=time.monotonic() + 3,
        ),
        timeout=3.8,
    )

    with pytest.raises(asyncio.CancelledError):
        await owner


@pytest.mark.asyncio
async def test_agent_runtime_heartbeat_does_not_extend_lease_on_control_stop(
    db, auth_user_and_headers, monkeypatch
):
    from app.api.agent import _agent_runtime_heartbeat
    from app.services.agent_runtime import AgentRuntimeCoordinator, RunControlSignal

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = runtime.create_or_resume_run(
        run_id="run-api-heartbeat-control-stop",
        attempt_id="attempt-api-heartbeat-control-stop",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-api-heartbeat-control-stop",
        origin="test",
    )
    runtime.mark_running(
        admission.context,
        worker_id="worker-heartbeat-control-stop",
        lease_seconds=5,
    )
    monkeypatch.setattr(settings, "agent_runtime_heartbeat_seconds", 1)
    monkeypatch.setattr(settings, "agent_runtime_lease_seconds", 2)
    monkeypatch.setattr(
        "app.database.SessionLocal",
        sessionmaker(bind=db.get_bind(), autocommit=False, autoflush=False),
    )

    def fail_settlement(self, *args, **kwargs):
        raise RuntimeError("temporary settlement failure")

    monkeypatch.setattr(
        AgentRuntimeCoordinator,
        "renew_lease",
        lambda self, *args, **kwargs: RunControlSignal("cancel_requested"),
    )
    monkeypatch.setattr(AgentRuntimeCoordinator, "settle_control_stop", fail_settlement)
    owner = asyncio.create_task(asyncio.sleep(10))

    await asyncio.wait_for(
        _agent_runtime_heartbeat(
            admission.context,
            managed=True,
            worker_id="worker-heartbeat-control-stop",
            owner_task=owner,
            initial_lease_deadline=time.monotonic() + 2,
        ),
        timeout=1.5,
    )

    with pytest.raises(asyncio.CancelledError):
        await owner


@pytest.mark.asyncio
async def test_agent_runtime_heartbeat_cancels_owner_when_session_close_fails(
    db, auth_user_and_headers, monkeypatch
):
    from app.api.agent import _agent_runtime_heartbeat
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = runtime.create_or_resume_run(
        run_id="run-api-heartbeat-close-failure",
        attempt_id="attempt-api-heartbeat-close-failure",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-api-heartbeat-close-failure",
        origin="test",
    )
    runtime.mark_running(
        admission.context,
        worker_id="worker-heartbeat-close-failure",
        lease_seconds=5,
    )
    monkeypatch.setattr(settings, "agent_runtime_heartbeat_seconds", 1)
    monkeypatch.setattr(settings, "agent_runtime_lease_seconds", 5)
    real_factory = sessionmaker(
        bind=db.get_bind(), autocommit=False, autoflush=False
    )

    class CloseFailureSession:
        def __init__(self):
            self._session = real_factory()

        def __getattr__(self, name):
            return getattr(self._session, name)

        def close(self):
            self._session.close()
            raise RuntimeError("session close failed")

    monkeypatch.setattr("app.database.SessionLocal", CloseFailureSession)
    owner = asyncio.create_task(asyncio.sleep(10))

    await asyncio.wait_for(
        _agent_runtime_heartbeat(
            admission.context,
            managed=True,
            worker_id="worker-heartbeat-close-failure",
            owner_task=owner,
            initial_lease_deadline=time.monotonic() + 5,
        ),
        timeout=1.5,
    )

    with pytest.raises(asyncio.CancelledError):
        await owner


@pytest.mark.asyncio
async def test_agent_runtime_heartbeat_cancels_owner_before_lease_expires(
    db, auth_user_and_headers, monkeypatch
):
    from app.api.agent import _agent_runtime_heartbeat
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = runtime.create_or_resume_run(
        run_id="run-api-heartbeat-database-down",
        attempt_id="attempt-api-heartbeat-database-down",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-api-heartbeat-database-down",
        origin="test",
    )
    runtime.mark_running(
        admission.context,
        worker_id="worker-heartbeat-database-down",
        lease_seconds=5,
    )
    monkeypatch.setattr(settings, "agent_runtime_heartbeat_seconds", 1)
    monkeypatch.setattr(settings, "agent_runtime_lease_seconds", 5)

    def unavailable_session():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr("app.database.SessionLocal", unavailable_session)
    owner = asyncio.create_task(asyncio.sleep(10))

    await asyncio.wait_for(
        _agent_runtime_heartbeat(
            admission.context,
            managed=True,
            worker_id="worker-heartbeat-database-down",
            owner_task=owner,
            initial_lease_deadline=time.monotonic() + 5,
        ),
        timeout=5,
    )

    with pytest.raises(asyncio.CancelledError):
        await owner


@pytest.mark.asyncio
async def test_heartbeat_cleanup_does_not_override_main_result(caplog):
    from app.api.agent import _stop_agent_runtime_heartbeat

    started = asyncio.Event()

    async def fail_heartbeat():
        started.set()
        raise RuntimeError("heartbeat database unavailable")

    heartbeat = asyncio.create_task(fail_heartbeat())
    await started.wait()
    await asyncio.sleep(0)

    with caplog.at_level("ERROR"):
        await _stop_agent_runtime_heartbeat(
            heartbeat,
            run_id="run-heartbeat-cleanup",
        )

    assert "Agent Runtime heartbeat failed" in caplog.text


@pytest.mark.asyncio
async def test_bounded_sse_bridge_unblocks_producer_after_disconnect():
    from app.api.agent import _BoundedSSEBridge

    bridge = _BoundedSSEBridge(max_chunks=1)
    assert await bridge.publish("chunk-1") is True
    blocked_publish = asyncio.create_task(bridge.publish("chunk-2"))
    await asyncio.sleep(0)
    assert blocked_publish.done() is False

    bridge.detach()

    assert await blocked_publish is False
    assert await bridge.publish("chunk-3") is False
    assert bridge.buffered_chunks == 1


def test_agent_runtime_status_endpoint_returns_content_free_cursor(
    client, db, auth_user_and_headers, monkeypatch
):
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, headers = auth_user_and_headers
    monkeypatch.setattr(settings, "agent_runtime_mode", "enforce")
    runtime = AgentRuntimeCoordinator(db)
    admission = runtime.create_or_resume_run(
        run_id="run-api-event-cursor",
        attempt_id="attempt-api-event-cursor",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-api-event-cursor",
        origin="test",
    )
    runtime.mark_running(admission.context, worker_id="worker-api-cursor")

    response = client.get(
        f"/api/v1/agent/runs/{admission.context.run_id}",
        headers=headers,
        params={"after": 0, "limit": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == admission.context.run_id
    assert body["status"] == "running"
    assert [event["sequence_no"] for event in body["events"]] == [1]
    assert body["next_after"] == 1
    assert "private" not in response.text
    assert "content" not in response.text
