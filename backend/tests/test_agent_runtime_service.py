import pytest

from app.models.agent_conversation import AgentConversation


def _conversation(db, user_id: int, suffix: str = "one") -> AgentConversation:
    conversation = AgentConversation(
        user_id=user_id,
        title="runtime-test",
        session_key=f"runtime-test-{user_id}-{suffix}",
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def test_create_or_resume_run_keeps_one_logical_identity(db, auth_user_and_headers):
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    conversation = _conversation(db, user.id)
    runtime = AgentRuntimeCoordinator(db)

    first = runtime.create_or_resume_run(
        run_id="run-first",
        attempt_id="attempt-first",
        user_id=user.id,
        conversation_id=conversation.id,
        client_turn_id="client-turn-1",
        origin="mobile",
    )
    duplicate = runtime.create_or_resume_run(
        run_id="run-ignored",
        attempt_id="attempt-ignored",
        user_id=user.id,
        conversation_id=conversation.id,
        client_turn_id="client-turn-1",
        origin="mobile",
    )

    assert first.resumed is False
    assert first.disposition == "execute"
    assert first.owns_execution is True
    assert duplicate.resumed is True
    assert duplicate.disposition == "observe"
    assert duplicate.owns_execution is False
    assert duplicate.context.run_id == "run-first"
    assert duplicate.context.attempt_id == "attempt-first"
    assert duplicate.context.input_seq == 1


def test_busy_conversation_rejects_a_distinct_turn(db, auth_user_and_headers):
    from app.services.agent_runtime import AgentRuntimeCoordinator, RunBusyError

    user, _headers = auth_user_and_headers
    conversation = _conversation(db, user.id)
    runtime = AgentRuntimeCoordinator(db)
    runtime.create_or_resume_run(
        run_id="run-active",
        attempt_id="attempt-active",
        user_id=user.id,
        conversation_id=conversation.id,
        client_turn_id="turn-active",
        origin="web",
    )

    with pytest.raises(RunBusyError) as exc:
        runtime.create_or_resume_run(
            run_id="run-busy",
            attempt_id="attempt-busy",
            user_id=user.id,
            conversation_id=conversation.id,
            client_turn_id="turn-busy",
            origin="mobile",
        )

    assert exc.value.active_run_id == "run-active"


def test_runtime_admission_rejects_conversation_owned_by_another_user(
    db, auth_user_and_headers
):
    from app.models.agent_runtime import AgentRun
    from app.models.user import User
    from app.services.agent_runtime import AgentRuntimeCoordinator, AgentRuntimeError

    user, _headers = auth_user_and_headers
    other = User(
        username="runtime-other-user",
        email="runtime-other@example.com",
        hashed_password="hashed",
        name="other",
        is_active=True,
        is_approved=True,
    )
    db.add(other)
    db.commit()
    conversation = _conversation(db, other.id, suffix="other-owner")

    with pytest.raises(AgentRuntimeError, match="conversation_not_found"):
        AgentRuntimeCoordinator(db).create_or_resume_run(
            run_id="run-cross-owner",
            attempt_id="attempt-cross-owner",
            user_id=user.id,
            conversation_id=conversation.id,
            client_turn_id="turn-cross-owner",
            origin="mobile",
        )

    assert db.query(AgentRun).filter(
        AgentRun.run_id == "run-cross-owner"
    ).count() == 0


def test_runtime_enforces_state_transitions_and_binds_messages(db, auth_user_and_headers):
    from app.models.agent_conversation import AgentMessage
    from app.services.agent_runtime import AgentRuntimeCoordinator, InvalidRunTransition

    user, _headers = auth_user_and_headers
    conversation = _conversation(db, user.id)
    source = AgentMessage(conversation_id=conversation.id, role="user", content="private health text")
    assistant = AgentMessage(conversation_id=conversation.id, role="assistant", content="private answer")
    db.add_all([source, assistant])
    db.commit()
    runtime = AgentRuntimeCoordinator(db)
    admission = runtime.create_or_resume_run(
        run_id="run-state",
        attempt_id="attempt-state",
        user_id=user.id,
        conversation_id=conversation.id,
        client_turn_id="turn-state",
        origin="mac",
    )

    runtime.mark_running(admission.context)
    runtime.bind_messages(
        admission.context,
        conversation_id=conversation.id,
        source_message_id=source.id,
        assistant_message_id=assistant.id,
    )
    runtime.complete(admission.context, status="succeeded")

    run = runtime.get_run(user.id, "run-state")
    assert run.status == "succeeded"
    assert run.source_message_id == source.id
    assert run.assistant_message_id == assistant.id
    assert "private health text" not in repr(run.__dict__)
    with pytest.raises(InvalidRunTransition):
        runtime.mark_running(admission.context)


def test_runtime_event_payload_rejects_health_content(db, auth_user_and_headers):
    from app.services.agent_runtime import (
        AgentRuntimeCoordinator,
        UnsafeRunEventPayload,
    )

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = runtime.create_or_resume_run(
        run_id="run-event",
        attempt_id="attempt-event",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-event",
        origin="voice",
    )

    runtime.record_event(
        admission.context,
        "run.started",
        {"status": "running", "replayed": False},
    )
    with pytest.raises(UnsafeRunEventPayload):
        runtime.record_event(
            admission.context,
            "run.failed",
            {"content": "我正在服用某药"},
        )
    with pytest.raises(UnsafeRunEventPayload):
        runtime.record_event(
            admission.context,
            "run.failed",
            {"error_code": "胃癌治疗失败"},
        )
    with pytest.raises(UnsafeRunEventPayload):
        runtime.record_event(
            admission.context,
            "run.failed",
            {"error_code": "cancer"},
        )
    with pytest.raises(UnsafeRunEventPayload, match="event_replayed_not_bool"):
        runtime.record_event(
            admission.context,
            "run.started",
            {"status": "running", "replayed": "false"},
        )
    with pytest.raises(UnsafeRunEventPayload, match="event_receipt_not_bool"):
        runtime.record_event(
            admission.context,
            "tool.receipt_verified",
            {
                "tool_name": "health_record",
                "effect_class": "write",
                "receipt_verified": 1,
            },
        )
    with pytest.raises(UnsafeRunEventPayload, match="event_input_seq_not_positive_int"):
        runtime.record_event(
            admission.context,
            "run.started",
            {"status": "running", "input_seq": 0},
        )


def test_runtime_unknown_error_code_is_coarsened(db, auth_user_and_headers):
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = runtime.create_or_resume_run(
        run_id="run-coarse-error",
        attempt_id="attempt-coarse-error",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-coarse-error",
        origin="test",
    )
    runtime.mark_running(admission.context)
    runtime.complete(
        admission.context,
        status="failed",
        error_code="patient_has_cancer",
    )

    run = runtime.get_run(user.id, admission.context.run_id)
    assert run.error_code == "unclassified_error"


def test_terminal_run_allows_next_input_sequence(db, auth_user_and_headers):
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    conversation = _conversation(db, user.id)
    runtime = AgentRuntimeCoordinator(db)
    first = runtime.create_or_resume_run(
        run_id="run-seq-1",
        attempt_id="attempt-seq-1",
        user_id=user.id,
        conversation_id=conversation.id,
        client_turn_id="turn-seq-1",
        origin="web",
    )
    runtime.mark_running(first.context)
    runtime.complete(first.context, status="failed", error_code="provider_timeout")
    second = runtime.create_or_resume_run(
        run_id="run-seq-2",
        attempt_id="attempt-seq-2",
        user_id=user.id,
        conversation_id=conversation.id,
        client_turn_id="turn-seq-2",
        origin="web",
    )

    assert first.context.input_seq == 1
    assert second.context.input_seq == 2


def test_terminal_client_turn_retry_reuses_run_with_new_attempt(
    db, auth_user_and_headers
):
    from app.models.agent_runtime import AgentRunAttempt
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    conversation = _conversation(db, user.id)
    runtime = AgentRuntimeCoordinator(db)
    first = runtime.create_or_resume_run(
        run_id="run-retry",
        attempt_id="attempt-retry-1",
        user_id=user.id,
        conversation_id=conversation.id,
        client_turn_id="turn-retry",
        origin="mobile",
    )
    runtime.mark_running(first.context)
    runtime.complete(
        first.context,
        status="failed",
        error_code="provider_timeout",
        retryable=True,
    )

    retry = runtime.create_or_resume_run(
        run_id="run-ignored",
        attempt_id="attempt-retry-2",
        user_id=user.id,
        conversation_id=conversation.id,
        client_turn_id="turn-retry",
        origin="mobile",
    )

    run = runtime.get_run(user.id, "run-retry")
    attempts = db.query(AgentRunAttempt).filter(
        AgentRunAttempt.run_id == "run-retry"
    ).order_by(AgentRunAttempt.attempt_no).all()
    assert retry.resumed is True
    assert retry.disposition == "execute"
    assert retry.owns_execution is True
    assert retry.context.run_id == "run-retry"
    assert retry.context.attempt_id == "attempt-retry-2"
    assert run.status == "queued"
    assert run.error_code is None
    assert run.finished_at is None
    assert [(attempt.attempt_no, attempt.status) for attempt in attempts] == [
        (1, "failed"),
        (2, "queued"),
    ]


@pytest.mark.parametrize(
    "terminal_status",
    ["succeeded", "waiting_for_user", "reconciliation_required", "cancelled"],
)
def test_non_retryable_client_turn_is_replayed_without_new_attempt(
    db,
    auth_user_and_headers,
    terminal_status,
):
    from app.models.agent_runtime import AgentRunAttempt
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    conversation = _conversation(db, user.id, suffix=f"no-retry-{terminal_status}")
    runtime = AgentRuntimeCoordinator(db)
    first = runtime.create_or_resume_run(
        run_id=f"run-no-retry-{terminal_status}",
        attempt_id=f"attempt-no-retry-{terminal_status}",
        user_id=user.id,
        conversation_id=conversation.id,
        client_turn_id=f"turn-no-retry-{terminal_status}",
        origin="mobile",
    )
    runtime.mark_running(first.context)
    runtime.complete(
        first.context,
        status=terminal_status,
        error_code=(
            "write_checkpoint_uncertain"
            if terminal_status == "reconciliation_required"
            else None
        ),
    )

    duplicate = runtime.create_or_resume_run(
        run_id=f"run-ignored-{terminal_status}",
        attempt_id=f"attempt-ignored-{terminal_status}",
        user_id=user.id,
        conversation_id=conversation.id,
        client_turn_id=f"turn-no-retry-{terminal_status}",
        origin="mobile",
    )

    run = runtime.get_run(user.id, first.context.run_id)
    attempts = db.query(AgentRunAttempt).filter(
        AgentRunAttempt.run_id == first.context.run_id
    ).all()
    assert duplicate.disposition == "replay"
    assert duplicate.owns_execution is False
    assert duplicate.context.attempt_id == first.context.attempt_id
    assert run.status == terminal_status
    assert len(attempts) == 1


def test_failed_client_turn_requires_explicit_retryable_flag(
    db,
    auth_user_and_headers,
):
    from app.models.agent_runtime import AgentRunAttempt
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    first = runtime.create_or_resume_run(
        run_id="run-failed-no-retry",
        attempt_id="attempt-failed-no-retry",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-failed-no-retry",
        origin="mobile",
    )
    runtime.mark_running(first.context)
    runtime.complete(
        first.context,
        status="failed",
        error_code="provider_timeout",
    )

    duplicate = runtime.create_or_resume_run(
        run_id="run-failed-no-retry-ignored",
        attempt_id="attempt-failed-no-retry-ignored",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-failed-no-retry",
        origin="mobile",
    )

    run = runtime.get_run(user.id, first.context.run_id)
    assert duplicate.disposition == "replay"
    assert run.status == "failed"
    assert run.retryable is False
    assert db.query(AgentRunAttempt).filter(
        AgentRunAttempt.run_id == first.context.run_id
    ).count() == 1


def test_stale_attempt_cannot_mutate_retried_run(db, auth_user_and_headers):
    from app.models.agent_runtime import AgentRunEvent
    from app.services.agent_runtime import AgentRuntimeCoordinator, StaleRunAttempt

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    first = runtime.create_or_resume_run(
        run_id="run-fenced",
        attempt_id="attempt-fenced-1",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-fenced",
        origin="mobile",
    )
    runtime.mark_running(first.context)
    runtime.complete(
        first.context,
        status="failed",
        error_code="provider_timeout",
        retryable=True,
    )
    retry = runtime.create_or_resume_run(
        run_id="run-fenced-ignored",
        attempt_id="attempt-fenced-2",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-fenced",
        origin="mobile",
    )

    with pytest.raises(StaleRunAttempt):
        runtime.mark_running(first.context)
    with pytest.raises(StaleRunAttempt):
        runtime.complete(first.context, status="succeeded")
    with pytest.raises(StaleRunAttempt):
        runtime.record_event(
            first.context,
            "run.started",
            {"status": "running"},
        )

    run = runtime.get_run(user.id, first.context.run_id)
    event_attempts = {
        event.attempt_id
        for event in db.query(AgentRunEvent).filter(
            AgentRunEvent.run_id == first.context.run_id,
        )
    }
    assert run.status == "queued"
    assert run.current_attempt_id == retry.context.attempt_id
    assert retry.context.attempt_id in event_attempts


def test_terminal_client_turn_retry_cannot_bypass_new_active_run(
    db, auth_user_and_headers
):
    from app.services.agent_runtime import AgentRuntimeCoordinator, RunBusyError

    user, _headers = auth_user_and_headers
    conversation = _conversation(db, user.id)
    runtime = AgentRuntimeCoordinator(db)
    old = runtime.create_or_resume_run(
        run_id="run-old",
        attempt_id="attempt-old",
        user_id=user.id,
        conversation_id=conversation.id,
        client_turn_id="turn-old",
        origin="web",
    )
    runtime.mark_running(old.context)
    runtime.complete(
        old.context,
        status="failed",
        error_code="provider_timeout",
        retryable=True,
    )
    runtime.create_or_resume_run(
        run_id="run-new-active",
        attempt_id="attempt-new-active",
        user_id=user.id,
        conversation_id=conversation.id,
        client_turn_id="turn-new-active",
        origin="web",
    )

    with pytest.raises(RunBusyError) as exc:
        runtime.create_or_resume_run(
            run_id="run-ignored",
            attempt_id="attempt-old-retry",
            user_id=user.id,
            conversation_id=conversation.id,
            client_turn_id="turn-old",
            origin="web",
        )

    assert exc.value.active_run_id == "run-new-active"


def test_unbound_terminal_retry_joins_conversation_admission(
    db, auth_user_and_headers
):
    from app.services.agent_runtime import AgentRuntimeCoordinator, RunBusyError

    user, _headers = auth_user_and_headers
    conversation = _conversation(db, user.id, suffix="late-bind")
    runtime = AgentRuntimeCoordinator(db)
    unbound = runtime.create_or_resume_run(
        run_id="run-unbound-old",
        attempt_id="attempt-unbound-old",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-unbound-old",
        origin="mobile",
    )
    runtime.mark_running(unbound.context)
    runtime.complete(
        unbound.context,
        status="failed",
        error_code="provider_timeout",
        retryable=True,
    )
    runtime.create_or_resume_run(
        run_id="run-late-bind-active",
        attempt_id="attempt-late-bind-active",
        user_id=user.id,
        conversation_id=conversation.id,
        client_turn_id="turn-late-bind-active",
        origin="mobile",
    )

    with pytest.raises(RunBusyError) as exc:
        runtime.create_or_resume_run(
            run_id="run-ignored",
            attempt_id="attempt-unbound-retry",
            user_id=user.id,
            conversation_id=conversation.id,
            client_turn_id="turn-unbound-old",
            origin="mobile",
        )

    assert exc.value.active_run_id == "run-late-bind-active"


@pytest.mark.parametrize(
    ("done_data", "expected_status", "expected_error", "expected_retryable"),
    [
        (
            {"completion_status": "complete", "turn_outcome": {"category": "success"}},
            "succeeded",
            None,
            False,
        ),
        (
            {
                "completion_status": "complete",
                "turn_outcome": {
                    "category": "confirmation_required",
                    "reason_code": "health_record",
                },
            },
            "waiting_for_user",
            "health_record",
            False,
        ),
        (
            {
                "completion_status": "error",
                "write_recovery": "write_checkpoint_uncertain",
            },
            "reconciliation_required",
            "write_checkpoint_uncertain",
            False,
        ),
        (
            {
                "completion_status": "error",
                "turn_outcome": {
                    "category": "tool_failed",
                    "reason_code": "health_query",
                    "retryable": True,
                },
            },
            "failed",
            "health_query",
            True,
        ),
        (
            {
                "completion_status": "complete",
                "request_persisted": False,
                "turn_outcome": {"category": "success"},
            },
            "failed",
            "request_not_persisted",
            True,
        ),
    ],
)
def test_executor_done_maps_to_runtime_state(
    done_data,
    expected_status,
    expected_error,
    expected_retryable,
):
    from app.services.agent_runtime import runtime_outcome_from_done

    assert runtime_outcome_from_done(done_data) == (
        expected_status,
        expected_error,
        expected_retryable,
    )
