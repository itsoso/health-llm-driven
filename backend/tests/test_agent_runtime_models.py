import pytest

from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app.models.agent_conversation import AgentConversation


def _conversation(db, user_id: int) -> AgentConversation:
    conversation = AgentConversation(
        user_id=user_id,
        title="runtime-test",
        session_key=f"runtime-test-{user_id}",
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def test_agent_runtime_models_register_content_free_ledger_tables(db):
    table_names = set(inspect(db.get_bind()).get_table_names())

    assert {
        "agent_runs",
        "agent_run_attempts",
        "agent_tool_operations",
        "agent_run_events",
    } <= table_names


def test_agent_run_client_turn_is_owner_scoped_unique(db, auth_user_and_headers):
    from app.models.agent_runtime import AgentRun

    user, _headers = auth_user_and_headers
    db.add(AgentRun(
        run_id="run-1",
        user_id=user.id,
        client_turn_id="turn-1",
        status="failed",
        current_attempt_id="attempt-run-1",
    ))
    db.commit()

    db.add(AgentRun(
        run_id="run-2",
        user_id=user.id,
        client_turn_id="turn-1",
        status="failed",
        current_attempt_id="attempt-run-2",
    ))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_agent_run_allows_only_one_active_run_per_conversation(db, auth_user_and_headers):
    from app.models.agent_runtime import AgentRun

    user, _headers = auth_user_and_headers
    conversation = _conversation(db, user.id)
    db.add(AgentRun(
        run_id="run-active-1",
        user_id=user.id,
        conversation_id=conversation.id,
        client_turn_id="turn-active-1",
        input_seq=1,
        status="running",
        current_attempt_id="attempt-active-1",
    ))
    db.commit()

    db.add(AgentRun(
        run_id="run-active-2",
        user_id=user.id,
        conversation_id=conversation.id,
        client_turn_id="turn-active-2",
        input_seq=2,
        status="queued",
        current_attempt_id="attempt-active-2",
    ))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_terminal_run_releases_conversation_admission(db, auth_user_and_headers):
    from app.models.agent_runtime import AgentRun

    user, _headers = auth_user_and_headers
    conversation = _conversation(db, user.id)
    first = AgentRun(
        run_id="run-terminal-1",
        user_id=user.id,
        conversation_id=conversation.id,
        client_turn_id="turn-terminal-1",
        input_seq=1,
        status="running",
        current_attempt_id="attempt-terminal-1",
    )
    db.add(first)
    db.commit()

    first.status = "succeeded"
    db.commit()
    db.add(AgentRun(
        run_id="run-terminal-2",
        user_id=user.id,
        conversation_id=conversation.id,
        client_turn_id="turn-terminal-2",
        input_seq=2,
        status="queued",
        current_attempt_id="attempt-terminal-2",
    ))
    db.commit()


def test_agent_run_rejects_unknown_status(db, auth_user_and_headers):
    from app.models.agent_runtime import AgentRun

    user, _headers = auth_user_and_headers
    db.add(AgentRun(
        run_id="run-invalid",
        user_id=user.id,
        status="made_up",
        current_attempt_id="attempt-invalid",
    ))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
