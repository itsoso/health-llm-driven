from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.config import settings


def _configure(
    monkeypatch,
    *,
    mode: str,
    percent: int = 0,
    allowlist: str = "",
) -> None:
    monkeypatch.setattr(settings, "agent_runtime_mode", mode)
    monkeypatch.setattr(settings, "agent_runtime_canary_percent", percent)
    monkeypatch.setattr(settings, "agent_runtime_canary_user_ids", allowlist)


def _runtime_row(
    db,
    *,
    user_id: int,
    suffix: str,
    status: str,
    now: datetime,
    error_code: str | None = None,
    stale_lease: bool = False,
):
    from app.models.agent_runtime import AgentRun, AgentRunAttempt
    from app.services.agent_runtime_rollout import AgentRuntimeRolloutService

    if status == "reconciliation_required":
        AgentRuntimeRolloutService(db).get_state()

    attempt_status = "running" if status == "running" else (
        "succeeded" if status == "succeeded" else "failed"
    )
    run = AgentRun(
        run_id=f"rollout-run-{suffix}",
        user_id=user_id,
        client_turn_id=f"rollout-turn-{suffix}",
        status=status,
        current_attempt_id=f"rollout-attempt-{suffix}",
        origin="test",
        privacy_mode="cloud",
        error_code=error_code,
        created_at=now - timedelta(minutes=2),
        started_at=now - timedelta(seconds=20),
        finished_at=None if status == "running" else now - timedelta(seconds=5),
    )
    attempt = AgentRunAttempt(
        attempt_id=run.current_attempt_id,
        run_id=run.run_id,
        attempt_no=1,
        status=attempt_status,
        lease_expires_at=(now - timedelta(seconds=30)) if stale_lease else None,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )
    db.add_all([run, attempt])
    if status == "reconciliation_required":
        AgentRuntimeRolloutService(db).record_reconciliation()
    db.commit()
    return run


def test_stable_canary_bucket_is_deterministic_and_bounded():
    from app.services.agent_runtime_rollout import stable_canary_bucket

    first = stable_canary_bucket(42)

    assert first == stable_canary_bucket(42)
    assert first != stable_canary_bucket(43)
    assert 0 <= first < 10_000


@pytest.mark.parametrize("invalid_percent", [-1, 101])
def test_rollout_rejects_invalid_canary_percentage(
    db,
    auth_user_and_headers,
    monkeypatch,
    invalid_percent,
):
    from app.services.agent_runtime_rollout import (
        AgentRuntimeRolloutService,
        RolloutConfigurationError,
    )

    user, _headers = auth_user_and_headers
    _configure(monkeypatch, mode="canary", percent=invalid_percent)

    with pytest.raises(RolloutConfigurationError, match="canary_percent"):
        AgentRuntimeRolloutService(db).admission_decision(user.id)


def test_rollout_rejects_unknown_runtime_mode(db, auth_user_and_headers, monkeypatch):
    from app.services.agent_runtime_rollout import (
        AgentRuntimeRolloutService,
        RolloutConfigurationError,
    )

    user, _headers = auth_user_and_headers
    _configure(monkeypatch, mode="surprise")

    with pytest.raises(RolloutConfigurationError, match="runtime_mode"):
        AgentRuntimeRolloutService(db).admission_decision(user.id)


def test_rollout_rejects_invalid_allowlist(db, auth_user_and_headers, monkeypatch):
    from app.services.agent_runtime_rollout import (
        AgentRuntimeRolloutService,
        RolloutConfigurationError,
    )

    user, _headers = auth_user_and_headers
    _configure(monkeypatch, mode="canary", allowlist="7,not-a-user,99")

    with pytest.raises(RolloutConfigurationError, match="canary_user_ids"):
        AgentRuntimeRolloutService(db).admission_decision(user.id)


@pytest.mark.parametrize(
    ("setting_name", "invalid_value", "expected_error"),
    [
        ("agent_runtime_rollout_window_minutes", 0, "window_minutes"),
        ("agent_runtime_rollout_min_terminal_runs", 0, "min_terminal_runs"),
        ("agent_runtime_rollout_failure_rate_percent", 101, "failure_rate"),
    ],
)
def test_rollout_rejects_invalid_evaluation_thresholds(
    db,
    monkeypatch,
    setting_name,
    invalid_value,
    expected_error,
):
    from app.services.agent_runtime_rollout import (
        AgentRuntimeRolloutService,
        RolloutConfigurationError,
    )

    monkeypatch.setattr(settings, setting_name, invalid_value)

    with pytest.raises(RolloutConfigurationError, match=expected_error):
        AgentRuntimeRolloutService(db).evaluate_and_maybe_pause()


def test_circuit_read_failure_bypasses_runtime_and_recovers_session(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.services.agent_runtime_rollout import AgentRuntimeRolloutService

    user, _headers = auth_user_and_headers
    _configure(monkeypatch, mode="enforce")
    rollout = AgentRuntimeRolloutService(db)

    def fail_state_read():
        raise OperationalError("SELECT rollout state", {}, RuntimeError("offline"))

    monkeypatch.setattr(rollout, "_get_or_create_state", fail_state_read)

    decision = rollout.admission_decision(user.id)

    assert decision.managed is False
    assert decision.reason == "circuit_unavailable"
    assert db.execute(text("SELECT 1")).scalar_one() == 1


def test_managed_admission_circuit_failure_uses_legacy_path_and_recovers_session(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.models.agent_runtime import AgentRun
    from app.services.agent_runtime_rollout import AgentRuntimeRolloutService

    user, _headers = auth_user_and_headers
    _configure(monkeypatch, mode="enforce")
    rollout = AgentRuntimeRolloutService(db)

    def fail_locked_state(**_kwargs):
        raise OperationalError("SELECT rollout state", {}, RuntimeError("offline"))

    monkeypatch.setattr(rollout, "_locked_state", fail_locked_state)

    admission = rollout.admit_run(
        run_id="run-circuit-unavailable",
        attempt_id="attempt-circuit-unavailable",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-circuit-unavailable",
        origin="test",
        deadline_at=None,
    )

    assert admission.admission is None
    assert admission.reason == "circuit_unavailable"
    assert db.query(AgentRun).count() == 0
    assert db.execute(text("SELECT 1")).scalar_one() == 1


def test_off_mode_bypasses_runtime_without_creating_rollout_state(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.models.agent_runtime import AgentRuntimeRolloutState
    from app.services.agent_runtime_rollout import AgentRuntimeRolloutService

    user, _headers = auth_user_and_headers
    _configure(monkeypatch, mode="off", percent=100)

    decision = AgentRuntimeRolloutService(db).admission_decision(user.id)

    assert decision.managed is False
    assert decision.reason == "mode_off"
    assert db.query(AgentRuntimeRolloutState).count() == 0


def test_canary_zero_percent_bypasses_without_state(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.models.agent_runtime import AgentRuntimeRolloutState
    from app.services.agent_runtime_rollout import AgentRuntimeRolloutService

    user, _headers = auth_user_and_headers
    _configure(monkeypatch, mode="canary", percent=0)

    decision = AgentRuntimeRolloutService(db).admission_decision(user.id)

    assert decision.managed is False
    assert decision.reason == "canary_not_selected"
    assert db.query(AgentRuntimeRolloutState).count() == 0


def test_canary_allowlist_precedes_zero_percent(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.models.agent_runtime import AgentRuntimeRolloutState
    from app.services.agent_runtime_rollout import AgentRuntimeRolloutService

    user, _headers = auth_user_and_headers
    _configure(monkeypatch, mode="canary", percent=0, allowlist=f"7,{user.id},99")

    decision = AgentRuntimeRolloutService(db).admission_decision(user.id)

    assert decision.managed is True
    assert decision.reason == "canary_allowlist"
    state = db.query(AgentRuntimeRolloutState).one()
    assert state.id == 1
    assert state.status == "active"


def test_canary_hundred_percent_selects_user(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.services.agent_runtime_rollout import AgentRuntimeRolloutService

    user, _headers = auth_user_and_headers
    _configure(monkeypatch, mode="canary", percent=100)

    decision = AgentRuntimeRolloutService(db).admission_decision(user.id)

    assert decision.managed is True
    assert decision.reason == "canary_bucket"


def test_enforce_selects_all_users_while_circuit_is_active(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.services.agent_runtime_rollout import AgentRuntimeRolloutService

    user, _headers = auth_user_and_headers
    _configure(monkeypatch, mode="enforce", percent=0)

    decision = AgentRuntimeRolloutService(db).admission_decision(user.id)

    assert decision.managed is True
    assert decision.reason == "mode_enforce"


def test_pause_bypasses_new_admission_and_is_audited_once(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.models.agent_runtime import (
        AgentRuntimeRolloutEvent,
        AgentRuntimeRolloutState,
    )
    from app.services.agent_runtime_rollout import AgentRuntimeRolloutService

    user, _headers = auth_user_and_headers
    _configure(monkeypatch, mode="canary", percent=100)
    rollout = AgentRuntimeRolloutService(db)

    first = rollout.pause(
        actor_kind="admin",
        reason_code="manual_pause",
        actor_user_id=user.id,
    )
    second = rollout.pause(
        actor_kind="admin",
        reason_code="manual_pause",
        actor_user_id=user.id,
    )
    decision = rollout.admission_decision(user.id)

    assert first.changed is True
    assert second.changed is False
    assert decision.managed is False
    assert decision.reason == "circuit_paused"
    state = db.query(AgentRuntimeRolloutState).one()
    assert state.status == "paused"
    assert state.reason_code == "manual_pause"
    events = db.query(AgentRuntimeRolloutEvent).all()
    assert len(events) == 1
    assert events[0].action == "pause"
    assert events[0].actor_kind == "admin"
    assert events[0].actor_user_id == user.id


@pytest.mark.parametrize(
    ("actor_kind", "reason_code", "actor_user_id", "expected_error"),
    [
        ("admin", "manual_resume", 1, "invalid_pause_reason"),
        ("admin", "system_failure_rate", 1, "invalid_pause_reason"),
        ("system", "manual_pause", None, "invalid_pause_reason"),
        ("system", "manual_resume", None, "invalid_pause_reason"),
    ],
)
def test_pause_rejects_actor_reason_mismatches(
    db,
    actor_kind,
    reason_code,
    actor_user_id,
    expected_error,
):
    from app.services.agent_runtime_rollout import AgentRuntimeRolloutService

    with pytest.raises(ValueError, match=expected_error):
        AgentRuntimeRolloutService(db).pause(
            actor_kind=actor_kind,
            reason_code=reason_code,
            actor_user_id=actor_user_id,
        )


def test_resume_is_manual_idempotent_and_does_not_store_health_text(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.models.agent_runtime import AgentRuntimeRolloutEvent
    from app.services.agent_runtime_rollout import AgentRuntimeRolloutService

    user, _headers = auth_user_and_headers
    _configure(monkeypatch, mode="enforce")
    rollout = AgentRuntimeRolloutService(db)
    rollout.pause(
        actor_kind="system",
        reason_code="reconciliation_detected",
    )

    first = rollout.resume(actor_user_id=user.id)
    second = rollout.resume(actor_user_id=user.id)
    decision = rollout.admission_decision(user.id)

    assert first.changed is True
    assert second.changed is False
    assert decision.managed is True
    events = db.query(AgentRuntimeRolloutEvent).order_by(
        AgentRuntimeRolloutEvent.id
    ).all()
    assert [event.action for event in events] == ["pause", "resume"]
    serialized = " ".join(repr(event.__dict__) for event in events)
    assert "private health" not in serialized
    assert "prompt" not in serialized
    assert "response" not in serialized


def test_manual_pause_preserves_latest_evaluation_counts(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.services.agent_runtime_rollout import AgentRuntimeRolloutService

    user, _headers = auth_user_and_headers
    now = datetime.now(UTC)
    _configure(monkeypatch, mode="canary", percent=100)
    _runtime_row(
        db,
        user_id=user.id,
        suffix="manual-pause-preserves-counts",
        status="succeeded",
        now=now,
    )
    rollout = AgentRuntimeRolloutService(db)
    rollout.evaluate_and_maybe_pause(now=now)

    rollout.pause(
        actor_kind="admin",
        reason_code="manual_pause",
        actor_user_id=user.id,
    )

    state = rollout.get_state()
    assert state.terminal_runs == 1
    assert state.failed_runs == 0


def test_rollout_snapshot_is_aggregate_only(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.models.agent_runtime import AgentToolOperation
    from app.services.agent_runtime_rollout import AgentRuntimeRolloutService

    user, _headers = auth_user_and_headers
    now = datetime.now(UTC)
    _configure(monkeypatch, mode="canary", percent=100)
    succeeded = _runtime_row(
        db,
        user_id=user.id,
        suffix="aggregate-success",
        status="succeeded",
        now=now,
    )
    failed = _runtime_row(
        db,
        user_id=user.id,
        suffix="aggregate-failed",
        status="failed",
        error_code="provider_timeout",
        now=now,
    )
    db.add_all(
        [
            AgentToolOperation(
                operation_id="rollout-op-success",
                run_id=succeeded.run_id,
                attempt_id=succeeded.current_attempt_id,
                tool_name="health_query",
                effect_class="read",
                operation_fingerprint="a" * 64,
                status="succeeded",
                created_at=now - timedelta(minutes=1),
                finished_at=now,
            ),
            AgentToolOperation(
                operation_id="rollout-op-failed",
                run_id=failed.run_id,
                attempt_id=failed.current_attempt_id,
                tool_name="health_query",
                effect_class="read",
                operation_fingerprint="b" * 64,
                status="failed",
                error_code="provider_timeout",
                created_at=now - timedelta(minutes=1),
                finished_at=now,
            ),
        ]
    )
    db.commit()

    snapshot = AgentRuntimeRolloutService(db).snapshot(now=now)
    payload = snapshot.to_dict()

    assert payload["terminal_runs"] == 2
    assert payload["status_counts"] == {"failed": 1, "succeeded": 1}
    assert payload["failed_runs"] == 1
    assert payload["tool_status_counts"] == {"failed": 1, "succeeded": 1}
    assert payload["duration_ms"]["p50"] == 15_000
    assert payload["duration_ms"]["p95"] == 15_000
    serialized = repr(payload)
    assert "user_id" not in serialized
    assert "run_id" not in serialized
    assert "tool_name" not in serialized
    assert "private" not in serialized


def test_rollout_snapshot_reports_content_free_runtime_integrity(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.models.agent_conversation import AgentConversation
    from app.services.agent_runtime_rollout import AgentRuntimeRolloutService

    user, _headers = auth_user_and_headers
    now = datetime.now(UTC)
    _configure(monkeypatch, mode="canary", percent=100)
    complete = _runtime_row(
        db,
        user_id=user.id,
        suffix="integrity-complete",
        status="succeeded",
        now=now,
    )
    complete.runtime_contract_version = "agent-runtime-v1"
    complete.tool_registry_digest = "a" * 64
    complete.capability_policy_digest = "b" * 64

    conversation = AgentConversation(
        user_id=user.id,
        title="content must not leak",
        session_key="runtime-integrity-gap",
    )
    db.add(conversation)
    db.flush()
    unlinked = _runtime_row(
        db,
        user_id=user.id,
        suffix="integrity-unlinked",
        status="succeeded",
        now=now,
    )
    unlinked.conversation_id = conversation.id
    unlinked.runtime_contract_version = "agent-runtime-v1"
    unlinked.tool_registry_digest = "c" * 64
    unlinked.capability_policy_digest = "d" * 64

    missing_attempt = _runtime_row(
        db,
        user_id=user.id,
        suffix="integrity-missing-attempt",
        status="failed",
        now=now,
    )
    missing_attempt.current_attempt_id = "attempt-does-not-exist"

    overdue = _runtime_row(
        db,
        user_id=user.id,
        suffix="integrity-overdue",
        status="running",
        now=now,
    )
    overdue.deadline_at = now - timedelta(seconds=1)

    waiting = _runtime_row(
        db,
        user_id=user.id,
        suffix="integrity-waiting",
        status="failed",
        now=now,
    )
    waiting.status = "waiting_for_user"
    waiting.finished_at = None
    waiting.created_at = now - timedelta(hours=25)
    db.commit()

    payload = AgentRuntimeRolloutService(db).snapshot(now=now).to_dict()
    integrity = payload["integrity"]

    assert integrity == {
        "window_runs": 4,
        "contract_snapshot_runs": 2,
        "contract_snapshot_coverage_percent": 50,
        "contract_versions": {"agent-runtime-v1": 2},
        "settled_message_linkage_gaps": 1,
        "missing_current_attempt_runs": 1,
        "active_over_deadline_runs": 1,
        "waiting_over_24h_runs": 1,
    }
    serialized = repr(integrity)
    assert "user_id" not in serialized
    assert "run_id" not in serialized
    assert "content must not leak" not in serialized
    assert "prompt" not in serialized
    assert "response" not in serialized


def test_deadline_exceeded_is_not_counted_as_system_failure(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.services.agent_runtime_rollout import AgentRuntimeRolloutService

    user, _headers = auth_user_and_headers
    now = datetime.now(UTC)
    _configure(monkeypatch, mode="canary", percent=100)
    _runtime_row(
        db,
        user_id=user.id,
        suffix="deadline-excluded",
        status="failed",
        error_code="deadline_exceeded",
        now=now,
    )

    snapshot = AgentRuntimeRolloutService(db).snapshot(now=now)

    assert snapshot.terminal_runs == 1
    assert snapshot.failed_runs == 0


def test_reconciliation_pauses_without_minimum_sample(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.services.agent_runtime_rollout import AgentRuntimeRolloutService

    user, _headers = auth_user_and_headers
    now = datetime.now(UTC)
    _configure(monkeypatch, mode="canary", percent=1)
    monkeypatch.setattr(settings, "agent_runtime_rollout_min_terminal_runs", 20)
    _runtime_row(
        db,
        user_id=user.id,
        suffix="reconciliation",
        status="reconciliation_required",
        error_code="write_reconciliation_required",
        now=now,
    )

    evaluation = AgentRuntimeRolloutService(db).evaluate_and_maybe_pause(now=now)

    assert evaluation.reason_code == "reconciliation_detected"
    assert evaluation.transition.changed is True
    assert evaluation.snapshot.reconciliation_runs == 1


def test_manual_resume_acknowledges_existing_reconciliation_watermark(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.services.agent_runtime_rollout import AgentRuntimeRolloutService

    user, _headers = auth_user_and_headers
    now = datetime.now(UTC)
    _configure(monkeypatch, mode="canary", percent=100)
    _runtime_row(
        db,
        user_id=user.id,
        suffix="reconciliation-before-resume",
        status="reconciliation_required",
        error_code="write_reconciliation_required",
        now=now,
    )
    rollout = AgentRuntimeRolloutService(db)
    first = rollout.evaluate_and_maybe_pause(now=now)
    rollout.resume(actor_user_id=user.id)

    repeated = rollout.evaluate_and_maybe_pause(now=now + timedelta(minutes=1))

    assert first.transition.changed is True
    assert repeated.reason_code is None
    assert repeated.transition.changed is False
    assert rollout.get_state().status == "active"


def test_evaluation_does_not_acknowledge_late_reconciliation_commit(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.services.agent_runtime_rollout import AgentRuntimeRolloutService

    user, _headers = auth_user_and_headers
    now = datetime.now(UTC)
    _configure(monkeypatch, mode="canary", percent=100)
    rollout = AgentRuntimeRolloutService(db)

    first = rollout.evaluate_and_maybe_pause(now=now)
    _runtime_row(
        db,
        user_id=user.id,
        suffix="reconciliation-late-commit",
        status="reconciliation_required",
        error_code="write_reconciliation_required",
        now=now,
    )
    second = rollout.evaluate_and_maybe_pause(now=now + timedelta(seconds=1))

    assert first.reason_code is None
    assert second.reason_code == "reconciliation_detected"
    assert second.transition.changed is True


def test_stale_lease_pauses_after_recovery_window(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.services.agent_runtime_rollout import AgentRuntimeRolloutService

    user, _headers = auth_user_and_headers
    now = datetime.now(UTC)
    _configure(monkeypatch, mode="enforce")
    _runtime_row(
        db,
        user_id=user.id,
        suffix="stale",
        status="running",
        now=now,
        stale_lease=True,
    )

    evaluation = AgentRuntimeRolloutService(db).evaluate_and_maybe_pause(now=now)

    assert evaluation.reason_code == "stale_lease_detected"
    assert evaluation.transition.changed is True
    assert evaluation.snapshot.stale_active_runs == 1


def test_failure_rate_requires_minimum_sample_and_never_auto_resumes(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.models.agent_runtime import AgentRuntimeRolloutEvent
    from app.services.agent_runtime_rollout import AgentRuntimeRolloutService

    user, _headers = auth_user_and_headers
    now = datetime.now(UTC)
    _configure(monkeypatch, mode="canary", percent=100)
    monkeypatch.setattr(settings, "agent_runtime_rollout_min_terminal_runs", 3)
    monkeypatch.setattr(settings, "agent_runtime_rollout_failure_rate_percent", 50)
    _runtime_row(
        db,
        user_id=user.id,
        suffix="rate-success",
        status="succeeded",
        now=now,
    )
    for suffix in ("rate-failed-one", "rate-failed-two"):
        _runtime_row(
            db,
            user_id=user.id,
            suffix=suffix,
            status="failed",
            error_code="provider_timeout",
            now=now,
        )
    rollout = AgentRuntimeRolloutService(db)

    paused = rollout.evaluate_and_maybe_pause(now=now)
    repeated = rollout.evaluate_and_maybe_pause(now=now)

    assert paused.reason_code == "system_failure_rate"
    assert paused.transition.changed is True
    assert repeated.transition.changed is False
    assert rollout.get_state().status == "paused"
    assert db.query(AgentRuntimeRolloutEvent).count() == 1
