from datetime import UTC, datetime, timedelta

import pytest
from celery.schedules import crontab
from sqlalchemy.orm import sessionmaker

from app.models.agent_runtime import AgentRunAttempt, AgentToolOperation


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=value.tzinfo or UTC).astimezone(UTC)


def _admission(db, user_id: int, *, suffix: str, deadline_at=None):
    from app.services.agent_runtime import AgentRuntimeCoordinator

    return AgentRuntimeCoordinator(db).create_or_resume_run(
        run_id=f"run-resilience-{suffix}",
        attempt_id=f"attempt-resilience-{suffix}",
        user_id=user_id,
        conversation_id=None,
        client_turn_id=f"turn-resilience-{suffix}",
        origin="test",
        deadline_at=deadline_at,
    )


def test_worker_lease_is_initialized_renewed_and_fenced(
    db, auth_user_and_headers
):
    from app.services.agent_runtime import (
        AgentRuntimeCoordinator,
        StaleRunWorker,
    )

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    context = _admission(db, user.id, suffix="lease").context
    started_at = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)

    runtime.mark_running(
        context,
        worker_id="worker-a",
        lease_seconds=60,
        now=started_at,
    )

    attempt = db.get(AgentRunAttempt, context.attempt_id)
    assert attempt.worker_id == "worker-a"
    assert _as_utc(attempt.heartbeat_at) == started_at
    assert _as_utc(attempt.lease_expires_at) == started_at + timedelta(seconds=60)

    with pytest.raises(StaleRunWorker, match="worker_mismatch"):
        runtime.renew_lease(
            context,
            worker_id="worker-b",
            lease_seconds=60,
            now=started_at + timedelta(seconds=15),
        )

    signal = runtime.renew_lease(
        context,
        worker_id="worker-a",
        lease_seconds=90,
        now=started_at + timedelta(seconds=30),
    )
    db.refresh(attempt)
    assert signal.action == "continue"
    assert _as_utc(attempt.heartbeat_at) == started_at + timedelta(seconds=30)
    assert _as_utc(attempt.lease_expires_at) == started_at + timedelta(seconds=120)


def test_running_attempt_without_a_lease_is_adopted_by_first_worker(
    db, auth_user_and_headers
):
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    context = _admission(db, user.id, suffix="adopt-unleased").context
    started_at = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
    runtime.mark_running(
        context,
        worker_id="legacy-worker",
        lease_seconds=60,
        now=started_at,
    )
    attempt = db.get(AgentRunAttempt, context.attempt_id)
    attempt.worker_id = None
    attempt.heartbeat_at = None
    attempt.lease_expires_at = None
    db.commit()

    runtime.mark_running(
        context,
        worker_id="adopting-worker",
        lease_seconds=60,
        now=started_at + timedelta(seconds=10),
    )

    db.refresh(attempt)
    assert attempt.worker_id == "adopting-worker"
    assert _as_utc(attempt.heartbeat_at) == started_at + timedelta(seconds=10)
    assert _as_utc(attempt.lease_expires_at) == started_at + timedelta(seconds=70)


def test_cancel_request_is_durable_until_worker_settles(
    db, auth_user_and_headers
):
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    context = _admission(db, user.id, suffix="cancel").context
    now = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
    runtime.mark_running(
        context,
        worker_id="worker-cancel",
        lease_seconds=60,
        now=now,
    )

    cancel_result = runtime.request_cancel(user.id, context.run_id, now=now)
    run = runtime.get_run(user.id, context.run_id)
    assert cancel_result.status == "cancellation_requested"
    assert run.status == "running"
    assert _as_utc(run.cancel_requested_at) == now
    assert [
        event.event_name
        for event in runtime.list_events_after(
            user.id,
            context.run_id,
            after_sequence=0,
            limit=10,
        )
    ] == ["run.created", "run.started", "run.cancel_requested"]

    signal = runtime.renew_lease(
        context,
        worker_id="worker-cancel",
        lease_seconds=60,
        now=now + timedelta(seconds=1),
    )
    assert signal.action == "cancel_requested"

    runtime.settle_control_stop(context, action=signal.action)
    assert runtime.get_run(user.id, context.run_id).status == "cancelled"
    assert db.get(AgentRunAttempt, context.attempt_id).status == "cancelled"


def test_late_cancel_wins_over_read_only_success(db, auth_user_and_headers):
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    context = _admission(db, user.id, suffix="late-cancel-read").context
    runtime.mark_running(context, worker_id="worker-late-cancel-read")
    runtime.request_cancel(user.id, context.run_id)

    runtime.complete(context, status="succeeded")

    run = runtime.get_run(user.id, context.run_id)
    assert run.status == "cancelled"
    assert run.error_code == "cancelled"


def test_verified_write_can_complete_after_late_cancel(
    db, auth_user_and_headers
):
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    context = _admission(db, user.id, suffix="late-cancel-write").context
    runtime.mark_running(context, worker_id="worker-late-cancel-write")
    operation = runtime.claim_tool_operation(
        context,
        tool_name="health_record",
        effect_class="write",
        operation_fingerprint="d" * 64,
    )
    runtime.finalize_tool_operation(
        context,
        operation_id=operation.operation_id,
        status="succeeded",
        resource_type="diet_record",
        resource_id="829",
    )
    runtime.request_cancel(user.id, context.run_id)

    runtime.complete(context, status="succeeded")

    run = runtime.get_run(user.id, context.run_id)
    assert run.status == "succeeded"
    assert run.error_code is None


@pytest.mark.parametrize("completion_status", ["waiting_for_user", "failed"])
def test_cancel_request_wins_over_non_success_completion(
    db, auth_user_and_headers, completion_status
):
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    context = _admission(
        db,
        user.id,
        suffix=f"cancel-before-{completion_status}",
    ).context
    runtime.mark_running(context, worker_id=f"worker-{completion_status}")
    runtime.request_cancel(user.id, context.run_id)

    runtime.complete(
        context,
        status=completion_status,
        error_code="tool_failed" if completion_status == "failed" else None,
        retryable=completion_status == "failed",
    )

    run = runtime.get_run(user.id, context.run_id)
    assert run.status == "cancelled"
    assert run.error_code == "cancelled"
    assert run.retryable is False


@pytest.mark.parametrize("request_cancel", [False, True])
def test_verified_write_survives_task_interruption(
    db, auth_user_and_headers, request_cancel
):
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    context = _admission(db, user.id, suffix="cancel-after-write").context
    runtime.mark_running(context, worker_id="worker-cancel-after-write")
    operation = runtime.claim_tool_operation(
        context,
        tool_name="health_record",
        effect_class="write",
        operation_fingerprint="e" * 64,
    )
    runtime.finalize_tool_operation(
        context,
        operation_id=operation.operation_id,
        status="succeeded",
        resource_type="symptom_record",
        resource_id="75",
    )
    if request_cancel:
        runtime.request_cancel(user.id, context.run_id)

    runtime.interrupt_active(context)

    run = runtime.get_run(user.id, context.run_id)
    assert run.status == "succeeded"
    assert run.error_code is None
    assert run.retryable is False


def test_worker_interruption_with_unresolved_write_requires_reconciliation(
    db, auth_user_and_headers
):
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    context = _admission(db, user.id, suffix="interrupt-unresolved-write").context
    runtime.mark_running(context, worker_id="worker-interrupt-unresolved-write")
    operation = runtime.claim_tool_operation(
        context,
        tool_name="health_record",
        effect_class="write",
        operation_fingerprint="f" * 64,
    )

    runtime.interrupt_active(context)

    run = runtime.get_run(user.id, context.run_id)
    stored_operation = db.get(AgentToolOperation, operation.operation_id)
    assert run.status == "reconciliation_required"
    assert run.error_code == "worker_interrupted_write"
    assert run.retryable is False
    assert stored_operation.status == "reconciliation_required"
    assert stored_operation.error_code == "worker_interrupted"


def test_deadline_expiry_is_a_retryable_failure(db, auth_user_and_headers):
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    now = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
    context = _admission(
        db,
        user.id,
        suffix="deadline",
        deadline_at=now + timedelta(seconds=30),
    ).context
    runtime.mark_running(
        context,
        worker_id="worker-deadline",
        lease_seconds=60,
        now=now,
    )

    signal = runtime.renew_lease(
        context,
        worker_id="worker-deadline",
        lease_seconds=60,
        now=now + timedelta(seconds=31),
    )
    assert signal.action == "deadline_exceeded"

    runtime.settle_control_stop(context, action=signal.action)
    run = runtime.get_run(user.id, context.run_id)
    assert run.status == "failed"
    assert run.error_code == "deadline_exceeded"
    assert run.retryable is True


def test_deadline_is_rechecked_during_final_completion(
    db, auth_user_and_headers, monkeypatch
):
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    now = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
    context = _admission(
        db,
        user.id,
        suffix="deadline-finalize",
        deadline_at=now - timedelta(seconds=1),
    ).context
    runtime.mark_running(
        context,
        worker_id="worker-deadline-finalize",
        now=now - timedelta(seconds=30),
    )
    monkeypatch.setattr("app.services.agent_runtime._now", lambda: now)

    runtime.complete(context, status="succeeded")

    run = runtime.get_run(user.id, context.run_id)
    assert run.status == "failed"
    assert run.error_code == "deadline_exceeded"
    assert run.retryable is True


@pytest.mark.parametrize("completion_status", ["waiting_for_user", "failed"])
def test_deadline_wins_over_non_success_completion(
    db, auth_user_and_headers, monkeypatch, completion_status
):
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    now = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
    context = _admission(
        db,
        user.id,
        suffix=f"deadline-before-{completion_status}",
        deadline_at=now - timedelta(seconds=1),
    ).context
    runtime.mark_running(
        context,
        worker_id=f"worker-deadline-{completion_status}",
        now=now - timedelta(seconds=30),
    )
    monkeypatch.setattr("app.services.agent_runtime._now", lambda: now)

    runtime.complete(
        context,
        status=completion_status,
        error_code="tool_failed" if completion_status == "failed" else None,
        retryable=completion_status == "failed",
    )

    run = runtime.get_run(user.id, context.run_id)
    assert run.status == "failed"
    assert run.error_code == "deadline_exceeded"
    assert run.retryable is True


def test_internal_worker_interruption_is_retryable_not_user_cancel(
    db, auth_user_and_headers
):
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    context = _admission(db, user.id, suffix="worker-interrupted").context
    runtime.mark_running(context, worker_id="worker-interrupted")

    runtime.interrupt_active(context)

    run = runtime.get_run(user.id, context.run_id)
    assert run.status == "failed"
    assert run.error_code == "worker_interrupted"
    assert run.retryable is True


def test_cancel_with_unresolved_write_requires_reconciliation(
    db, auth_user_and_headers
):
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    context = _admission(db, user.id, suffix="cancel-write").context
    now = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
    runtime.mark_running(
        context,
        worker_id="worker-write",
        lease_seconds=60,
        now=now,
    )
    operation = runtime.claim_tool_operation(
        context,
        tool_name="health_record",
        effect_class="write",
        operation_fingerprint="a" * 64,
    )
    assert operation.owns_execution is True

    runtime.request_cancel(user.id, context.run_id, now=now)
    runtime.settle_control_stop(context, action="cancel_requested")

    run = runtime.get_run(user.id, context.run_id)
    stored_operation = db.get(AgentToolOperation, operation.operation_id)
    assert run.status == "reconciliation_required"
    assert run.error_code == "cancelled_with_unresolved_write"
    assert stored_operation.status == "reconciliation_required"
    assert stored_operation.error_code == "cancelled"


def test_recovery_marks_expired_read_only_run_retryable(
    db, auth_user_and_headers
):
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    now = datetime(2026, 7, 19, 13, 0, tzinfo=UTC)
    context = _admission(db, user.id, suffix="recover-read").context
    runtime.mark_running(
        context,
        worker_id="dead-worker-read",
        lease_seconds=60,
        now=now - timedelta(minutes=2),
    )

    recovered = runtime.recover_expired_runs(now=now, limit=10)

    assert [(item.run_id, item.status) for item in recovered] == [
        (context.run_id, "failed")
    ]
    run = runtime.get_run(user.id, context.run_id)
    attempt = db.get(AgentRunAttempt, context.attempt_id)
    assert run.error_code == "worker_lease_expired"
    assert run.retryable is True
    assert attempt.status == "failed"
    assert attempt.lease_expires_at is None
    assert runtime.recover_expired_runs(now=now, limit=10) == []

    from app.services.agent_runtime import StaleRunAttempt

    with pytest.raises(StaleRunAttempt, match="attempt_not_running"):
        runtime.claim_tool_operation(
            context,
            tool_name="health_record",
            effect_class="write",
            operation_fingerprint="c" * 64,
        )


def test_queued_run_past_deadline_becomes_retryable_failure(
    db, auth_user_and_headers
):
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    now = datetime(2026, 7, 19, 13, 0, tzinfo=UTC)
    context = _admission(
        db,
        user.id,
        suffix="recover-never-started",
        deadline_at=now - timedelta(seconds=1),
    ).context

    recovered = runtime.recover_expired_runs(now=now, limit=10)

    assert [
        (item.run_id, item.status, item.error_code) for item in recovered
    ] == [(context.run_id, "failed", "deadline_exceeded")]
    run = runtime.get_run(user.id, context.run_id)
    assert run.status == "failed"
    assert run.error_code == "deadline_exceeded"
    assert run.retryable is True


def test_unleased_legacy_run_is_recovered_after_grace(
    db, auth_user_and_headers
):
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    now = datetime(2026, 7, 19, 13, 0, tzinfo=UTC)
    context = _admission(db, user.id, suffix="recover-unleased").context
    runtime.mark_running(
        context,
        worker_id="legacy-unleased-worker",
        lease_seconds=60,
        now=now - timedelta(minutes=2),
    )
    attempt = db.get(AgentRunAttempt, context.attempt_id)
    attempt.worker_id = None
    attempt.heartbeat_at = None
    attempt.lease_expires_at = None
    db.commit()

    recovered = runtime.recover_expired_runs(
        now=now,
        limit=10,
        unleased_grace_seconds=90,
    )

    assert [(item.run_id, item.status) for item in recovered] == [
        (context.run_id, "failed")
    ]
    assert runtime.get_run(user.id, context.run_id).error_code == (
        "worker_lease_expired"
    )


def test_recovery_routes_expired_unresolved_write_to_reconciliation(
    db, auth_user_and_headers
):
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    now = datetime(2026, 7, 19, 13, 0, tzinfo=UTC)
    context = _admission(db, user.id, suffix="recover-write").context
    runtime.mark_running(
        context,
        worker_id="dead-worker-write",
        lease_seconds=60,
        now=now - timedelta(minutes=2),
    )
    operation = runtime.claim_tool_operation(
        context,
        tool_name="health_record",
        effect_class="write",
        operation_fingerprint="b" * 64,
    )

    recovered = runtime.recover_expired_runs(now=now, limit=10)

    assert recovered[0].status == "reconciliation_required"
    run = runtime.get_run(user.id, context.run_id)
    stored_operation = db.get(AgentToolOperation, operation.operation_id)
    assert run.status == "reconciliation_required"
    assert run.error_code == "worker_lease_expired_write"
    assert run.retryable is False
    assert stored_operation.status == "reconciliation_required"
    assert stored_operation.error_code == "worker_lease_expired"


def test_recovery_honors_durable_cancel_request(db, auth_user_and_headers):
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    now = datetime(2026, 7, 19, 13, 0, tzinfo=UTC)
    context = _admission(db, user.id, suffix="recover-cancel").context
    runtime.mark_running(
        context,
        worker_id="dead-worker-cancel",
        lease_seconds=60,
        now=now - timedelta(minutes=2),
    )
    runtime.request_cancel(
        user.id,
        context.run_id,
        now=now - timedelta(seconds=90),
    )

    recovered = runtime.recover_expired_runs(now=now, limit=10)

    assert recovered[0].status == "cancelled"
    assert runtime.get_run(user.id, context.run_id).status == "cancelled"


def test_runtime_event_cursor_is_owner_scoped_and_bounded(
    db, auth_user_and_headers
):
    from app.models.user import User
    from app.services.agent_runtime import AgentRuntimeCoordinator, AgentRuntimeError

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    context = _admission(db, user.id, suffix="cursor").context
    runtime.mark_running(context, worker_id="worker-cursor")
    runtime.complete(context, status="succeeded")

    first_page = runtime.list_events_after(
        user.id,
        context.run_id,
        after_sequence=0,
        limit=2,
    )
    second_page = runtime.list_events_after(
        user.id,
        context.run_id,
        after_sequence=first_page[-1].sequence_no,
        limit=2,
    )

    assert [event.sequence_no for event in first_page] == [1, 2]
    assert [event.sequence_no for event in second_page] == [3]
    assert [event.event_name for event in first_page + second_page] == [
        "run.created",
        "run.started",
        "run.succeeded",
    ]
    assert "content" not in repr(first_page + second_page)

    other = User(
        username="runtime-cursor-other",
        email="runtime-cursor-other@example.com",
        hashed_password="hashed",
        name="runtime-cursor-other",
        is_active=True,
        is_approved=True,
    )
    db.add(other)
    db.commit()
    with pytest.raises(AgentRuntimeError, match="run_not_found"):
        runtime.list_events_after(
            other.id,
            context.run_id,
            after_sequence=0,
            limit=10,
        )


def test_runtime_event_cursor_rejects_unbounded_requests(
    db, auth_user_and_headers
):
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    context = _admission(db, user.id, suffix="cursor-bounds").context

    with pytest.raises(ValueError, match="invalid_event_cursor"):
        runtime.list_events_after(
            user.id,
            context.run_id,
            after_sequence=-1,
            limit=10,
        )
    with pytest.raises(ValueError, match="invalid_event_limit"):
        runtime.list_events_after(
            user.id,
            context.run_id,
            after_sequence=0,
            limit=501,
        )


def test_recovery_task_is_registered_and_runs_every_minute():
    from app.celery_app import celery_app
    from app.tasks.maintenance import recover_expired_agent_runs  # noqa: F401

    assert "app.tasks.maintenance.recover_expired_agent_runs" in celery_app.tasks
    entry = celery_app.conf.beat_schedule.get("recover-expired-agent-runs")
    assert entry is not None
    assert entry["task"] == "app.tasks.maintenance.recover_expired_agent_runs"
    assert entry["schedule"] == crontab(minute="*")


def test_recovery_task_is_inert_until_runtime_is_enforced(monkeypatch):
    from app.config import settings
    from app.tasks.maintenance import recover_expired_agent_runs

    monkeypatch.setattr(settings, "agent_runtime_mode", "off")

    assert recover_expired_agent_runs() == {
        "status": "disabled",
        "recovered": 0,
    }


def test_unleased_recovery_grace_covers_deadline_and_deploy_drain(
    db, monkeypatch
):
    from app.config import settings
    from app.services.agent_runtime import AgentRuntimeCoordinator
    from app.tasks.maintenance import _agent_runtime_unleased_grace_seconds

    monkeypatch.setattr(settings, "agent_runtime_deadline_seconds", 900)
    monkeypatch.setattr(settings, "agent_runtime_unleased_grace_seconds", 90)

    grace_seconds = _agent_runtime_unleased_grace_seconds()

    assert grace_seconds == 1020
    assert AgentRuntimeCoordinator(db).recover_expired_runs(
        unleased_grace_seconds=grace_seconds
    ) == []


def test_recovery_task_settles_an_expired_run(
    db, auth_user_and_headers, monkeypatch
):
    from app.config import settings
    from app.services.agent_runtime import AgentRuntimeCoordinator
    from app.tasks.maintenance import recover_expired_agent_runs

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    now = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
    context = _admission(db, user.id, suffix="scheduled-recovery").context
    runtime.mark_running(
        context,
        worker_id="worker-scheduled-recovery",
        lease_seconds=30,
        now=now - timedelta(minutes=2),
    )
    monkeypatch.setattr(settings, "agent_runtime_mode", "enforce")
    monkeypatch.setattr("app.services.agent_runtime._now", lambda: now)
    monkeypatch.setattr(
        "app.tasks.maintenance.SessionLocal",
        sessionmaker(bind=db.get_bind(), autocommit=False, autoflush=False),
    )

    result = recover_expired_agent_runs(now_iso=now.isoformat())

    db.expire_all()
    assert result == {
        "status": "ok",
        "recovered": 1,
        "failed": 1,
        "reconciliation_required": 0,
        "reconciled": 0,
        "rollout": {
            "changed": False,
            "reason_code": None,
            "status": "active",
            "snapshot": {
                "window_started_at": "2026-07-19T11:45:00+00:00",
                "evaluated_at": "2026-07-19T12:00:00+00:00",
                "terminal_runs": 1,
                "failed_runs": 1,
                "reconciliation_runs": 0,
                "stale_active_runs": 0,
                "status_counts": {"failed": 1},
                "tool_status_counts": {},
                "duration_ms": {"p50": 120000, "p95": 120000},
                "integrity": {
                    "window_runs": 0,
                    "contract_snapshot_runs": 0,
                    "contract_snapshot_coverage_percent": 100,
                    "contract_versions": {},
                    "settled_message_linkage_gaps": 0,
                    "missing_current_attempt_runs": 0,
                    "active_over_deadline_runs": 0,
                    "waiting_over_24h_runs": 0,
                },
            },
        },
    }
    assert runtime.get_run(user.id, context.run_id).status == "failed"


def test_recovery_task_pauses_rollout_after_uncertain_write(
    db, auth_user_and_headers, monkeypatch, caplog
):
    from app.config import settings
    from app.models.agent_runtime import AgentRuntimeRolloutEvent
    from app.services.agent_runtime import AgentRuntimeCoordinator
    from app.tasks.maintenance import recover_expired_agent_runs

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    now = datetime(2026, 7, 19, 12, 30, tzinfo=UTC)
    context = _admission(db, user.id, suffix="scheduled-reconciliation").context
    runtime.mark_running(
        context,
        worker_id="worker-scheduled-reconciliation",
        lease_seconds=30,
        now=now - timedelta(minutes=2),
    )
    runtime.claim_tool_operation(
        context,
        tool_name="health_record",
        effect_class="write",
        operation_fingerprint="c" * 64,
    )
    monkeypatch.setattr(settings, "agent_runtime_mode", "canary")
    monkeypatch.setattr(settings, "agent_runtime_canary_percent", 100)
    monkeypatch.setattr("app.services.agent_runtime._now", lambda: now)
    monkeypatch.setattr(
        "app.tasks.maintenance.SessionLocal",
        sessionmaker(bind=db.get_bind(), autocommit=False, autoflush=False),
    )

    with caplog.at_level("CRITICAL"):
        result = recover_expired_agent_runs(now_iso=now.isoformat())

    db.expire_all()
    assert result["recovered"] == 1
    assert result["reconciliation_required"] == 1
    assert result["rollout"]["changed"] is True
    assert result["rollout"]["status"] == "paused"
    assert result["rollout"]["reason_code"] == "reconciliation_detected"
    assert result["rollout"]["snapshot"]["reconciliation_runs"] == 1
    event = db.query(AgentRuntimeRolloutEvent).one()
    assert event.action == "pause"
    assert event.actor_kind == "system"
    assert event.reason_code == "reconciliation_detected"
    assert (
        "[agent-runtime] write circuit paused "
        "reason=reconciliation_detected"
    ) in caplog.text
    assert "reconciliation_generation=1 acknowledged_generation=0" in caplog.text


def test_recovery_task_pauses_rollout_when_reconciliation_scan_fails(
    db, auth_user_and_headers, monkeypatch
):
    from app.config import settings
    from app.models.agent_runtime import AgentRuntimeRolloutEvent
    from app.services.agent_runtime import AgentRuntimeCoordinator
    from app.tasks.maintenance import recover_expired_agent_runs

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    now = datetime(2026, 7, 19, 12, 45, tzinfo=UTC)
    context = _admission(db, user.id, suffix="reconciliation-scan-failure").context
    runtime.mark_running(
        context,
        worker_id="worker-reconciliation-scan-failure",
        lease_seconds=30,
        now=now - timedelta(minutes=2),
    )
    runtime.claim_tool_operation(
        context,
        tool_name="health_record",
        effect_class="write",
        operation_fingerprint="d" * 64,
    )
    monkeypatch.setattr(settings, "agent_runtime_mode", "canary")
    monkeypatch.setattr(settings, "agent_runtime_canary_percent", 100)
    monkeypatch.setattr("app.services.agent_runtime._now", lambda: now)
    monkeypatch.setattr(
        "app.tasks.maintenance.SessionLocal",
        sessionmaker(bind=db.get_bind(), autocommit=False, autoflush=False),
    )

    def _raise_scan_failure(*_args, **_kwargs):
        raise RuntimeError("reconciliation_backend_unavailable")

    monkeypatch.setattr(
        AgentRuntimeCoordinator,
        "reconcile_pending_tool_operations",
        _raise_scan_failure,
    )

    with pytest.raises(RuntimeError, match="reconciliation_backend_unavailable"):
        recover_expired_agent_runs(now_iso=now.isoformat())

    db.expire_all()
    assert runtime.get_run(user.id, context.run_id).status == (
        "reconciliation_required"
    )
    event = db.query(AgentRuntimeRolloutEvent).one()
    assert event.action == "pause"
    assert event.actor_kind == "system"
    assert event.reason_code == "reconciliation_detected"


def test_recovery_task_runs_for_paused_canary_existing_runs(
    db, auth_user_and_headers, monkeypatch
):
    from app.config import settings
    from app.services.agent_runtime import AgentRuntimeCoordinator
    from app.services.agent_runtime_rollout import AgentRuntimeRolloutService
    from app.tasks.maintenance import recover_expired_agent_runs

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    now = datetime(2026, 7, 19, 13, 0, tzinfo=UTC)
    context = _admission(db, user.id, suffix="paused-canary-recovery").context
    runtime.mark_running(
        context,
        worker_id="worker-paused-canary-recovery",
        lease_seconds=30,
        now=now - timedelta(minutes=2),
    )
    monkeypatch.setattr(settings, "agent_runtime_mode", "canary")
    monkeypatch.setattr(settings, "agent_runtime_canary_percent", 0)
    monkeypatch.setattr(settings, "agent_runtime_canary_user_ids", "")
    AgentRuntimeRolloutService(db).pause(
        actor_kind="admin",
        reason_code="manual_pause",
        actor_user_id=user.id,
    )
    monkeypatch.setattr(
        "app.tasks.maintenance.SessionLocal",
        sessionmaker(bind=db.get_bind(), autocommit=False, autoflush=False),
    )

    result = recover_expired_agent_runs(now_iso=now.isoformat())

    db.expire_all()
    assert result["status"] == "ok"
    assert result["recovered"] == 1
    assert result["rollout"]["status"] == "paused"
    assert result["rollout"]["changed"] is False
    assert runtime.get_run(user.id, context.run_id).status == "failed"
