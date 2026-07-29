from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
import hashlib

import pytest


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _running_diet_operation(db, user_id: int, *, suffix: str):
    from app.services.agent_runtime import AgentRuntimeCoordinator

    runtime = AgentRuntimeCoordinator(db)
    admission = runtime.create_or_resume_run(
        run_id=f"run-reconcile-{suffix}",
        attempt_id=f"attempt-reconcile-{suffix}-1",
        user_id=user_id,
        conversation_id=None,
        client_turn_id=f"turn-reconcile-{suffix}",
        origin="test",
    )
    runtime.mark_running(admission.context)
    operation = runtime.claim_tool_operation(
        admission.context,
        tool_name="health_record",
        effect_class="write",
        operation_fingerprint=_fingerprint(suffix),
        expected_resource_type="diet_record",
        logical_operation_key="write:1",
    )
    return runtime, admission, operation


def _running_medical_exam_operation(db, user_id: int, *, suffix: str):
    from app.services.agent_runtime import AgentRuntimeCoordinator

    runtime = AgentRuntimeCoordinator(db)
    admission = runtime.create_or_resume_run(
        run_id=f"run-reconcile-medical-{suffix}",
        attempt_id=f"attempt-reconcile-medical-{suffix}-1",
        user_id=user_id,
        conversation_id=None,
        client_turn_id=f"turn-reconcile-medical-{suffix}",
        origin="test",
    )
    runtime.mark_running(admission.context)
    operation = runtime.claim_tool_operation(
        admission.context,
        tool_name="upload_medical_exam_text",
        effect_class="write",
        operation_fingerprint=_fingerprint(suffix),
        expected_resource_type="medical_exam",
        logical_operation_key=f"medical-exam:{suffix}",
    )
    return runtime, admission, operation


def test_reconciliation_verifies_existing_diet_side_effect_and_replays_receipt(
    db, auth_user_and_headers
):
    from app.models.agent_runtime import AgentRun, AgentToolOperation
    from app.models.daily_health import DietRecord

    user, _headers = auth_user_and_headers
    runtime, admission, claimed = _running_diet_operation(
        db, user.id, suffix="effect"
    )
    record = DietRecord(
        user_id=user.id,
        record_date=date.today(),
        meal_type="dinner",
        food_name="晚餐",
        food_items="晚餐",
        client_action_id=f"{claimed.operation_id}|diet-photo:photo-effect",
    )
    db.add(record)
    db.commit()
    runtime.interrupt_active(admission.context)

    result = runtime.reconcile_tool_operation(
        claimed.operation_id,
        now=datetime.now(UTC) + timedelta(seconds=120),
        grace_seconds=90,
    )

    run = db.query(AgentRun).filter_by(run_id=admission.context.run_id).one()
    operation = db.query(AgentToolOperation).filter_by(
        operation_id=claimed.operation_id
    ).one()
    assert result.disposition == "verified_effect"
    assert operation.status == "succeeded"
    assert operation.resource_type == "diet_record"
    assert operation.resource_id == str(record.id)
    assert run.status == "failed"
    assert run.retryable is True
    assert run.error_code == "write_verified_reply_incomplete"

    retry = runtime.create_or_resume_run(
        run_id="ignored-new-run-id",
        attempt_id="attempt-reconcile-effect-2",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-reconcile-effect",
        origin="test",
    )
    runtime.mark_running(retry.context)
    replay = runtime.claim_tool_operation(
        retry.context,
        tool_name="health_record",
        effect_class="write",
        operation_fingerprint=_fingerprint("effect-recomputed-values"),
        expected_resource_type="diet_record",
        logical_operation_key="write:1",
    )
    assert replay.disposition == "replay"
    assert replay.operation_id == claimed.operation_id
    assert replay.resource_id == str(record.id)


def test_reconciliation_confirms_no_diet_side_effect_then_allows_safe_retry(
    db, auth_user_and_headers
):
    from app.models.agent_runtime import AgentRun, AgentToolOperation

    user, _headers = auth_user_and_headers
    runtime, admission, claimed = _running_diet_operation(
        db, user.id, suffix="no-effect"
    )
    runtime.interrupt_active(admission.context)

    result = runtime.reconcile_tool_operation(
        claimed.operation_id,
        now=datetime.now(UTC) + timedelta(seconds=120),
        grace_seconds=90,
    )

    run = db.query(AgentRun).filter_by(run_id=admission.context.run_id).one()
    operation = db.query(AgentToolOperation).filter_by(
        operation_id=claimed.operation_id
    ).one()
    assert result.disposition == "verified_no_effect"
    assert operation.status == "failed"
    assert operation.error_code == "reconciled_no_effect"
    assert run.status == "failed"
    assert run.retryable is True
    assert run.error_code == "reconciled_no_effect"

    retry = runtime.create_or_resume_run(
        run_id="ignored-new-run-id",
        attempt_id="attempt-reconcile-no-effect-2",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-reconcile-no-effect",
        origin="test",
    )
    runtime.mark_running(retry.context)
    replay = runtime.claim_tool_operation(
        retry.context,
        tool_name="health_record",
        effect_class="write",
        operation_fingerprint=_fingerprint("no-effect-recomputed-values"),
        expected_resource_type="diet_record",
        logical_operation_key="write:1",
    )
    assert replay.disposition == "execute"
    assert replay.operation_id == claimed.operation_id


def test_reconciliation_verifies_existing_medical_exam_side_effect(
    db, auth_user_and_headers
):
    from app.models.agent_runtime import AgentRun, AgentToolOperation
    from app.models.medical_exam import MedicalExam
    from app.services.agent_operation_reconciliation import (
        runtime_operation_source_fingerprint,
    )

    user, _headers = auth_user_and_headers
    runtime, admission, claimed = _running_medical_exam_operation(
        db, user.id, suffix="effect"
    )
    exam = MedicalExam(
        user_id=user.id,
        exam_date=date.today(),
        exam_type="imaging",
        source_fingerprint=runtime_operation_source_fingerprint(
            claimed.operation_id
        ),
    )
    db.add(exam)
    db.commit()
    runtime.interrupt_active(admission.context)

    result = runtime.reconcile_tool_operation(
        claimed.operation_id,
        now=datetime.now(UTC) + timedelta(seconds=120),
        grace_seconds=90,
    )

    run = db.query(AgentRun).filter_by(run_id=admission.context.run_id).one()
    operation = db.query(AgentToolOperation).filter_by(
        operation_id=claimed.operation_id
    ).one()
    assert result.disposition == "verified_effect"
    assert operation.status == "succeeded"
    assert operation.resource_type == "medical_exam"
    assert operation.resource_id == str(exam.id)
    assert run.status == "failed"
    assert run.retryable is True
    assert run.error_code == "write_verified_reply_incomplete"


def test_reconciliation_confirms_no_medical_exam_side_effect_after_grace(
    db, auth_user_and_headers
):
    from app.models.agent_runtime import AgentRun, AgentToolOperation

    user, _headers = auth_user_and_headers
    runtime, admission, claimed = _running_medical_exam_operation(
        db, user.id, suffix="no-effect"
    )
    runtime.interrupt_active(admission.context)

    result = runtime.reconcile_tool_operation(
        claimed.operation_id,
        now=datetime.now(UTC) + timedelta(seconds=120),
        grace_seconds=90,
    )

    run = db.query(AgentRun).filter_by(run_id=admission.context.run_id).one()
    operation = db.query(AgentToolOperation).filter_by(
        operation_id=claimed.operation_id
    ).one()
    assert result.disposition == "verified_no_effect"
    assert operation.status == "failed"
    assert operation.error_code == "reconciled_no_effect"
    assert run.status == "failed"
    assert run.retryable is True
    assert run.error_code == "reconciled_no_effect"


def test_non_reconciliation_retry_rejects_an_unrelated_new_write(
    db, auth_user_and_headers
):
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = runtime.create_or_resume_run(
        run_id="run-retry-distinct-write",
        attempt_id="attempt-retry-distinct-write-1",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-retry-distinct-write",
        origin="test",
    )
    runtime.mark_running(admission.context)
    first = runtime.claim_tool_operation(
        admission.context,
        tool_name="health_record",
        effect_class="write",
        operation_fingerprint=_fingerprint("first-write"),
        expected_resource_type="diet_record",
        logical_operation_key="write:1",
    )
    runtime.finalize_tool_operation(
        admission.context,
        operation_id=first.operation_id,
        status="succeeded",
        resource_type="diet_record",
        resource_id="101",
    )
    runtime.complete(
        admission.context,
        status="failed",
        error_code="executor_failed",
        retryable=True,
    )

    retry = runtime.create_or_resume_run(
        run_id="ignored-new-run-id",
        attempt_id="attempt-retry-distinct-write-2",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-retry-distinct-write",
        origin="test",
    )
    runtime.mark_running(retry.context)
    second = runtime.claim_tool_operation(
        retry.context,
        tool_name="health_record",
        effect_class="write",
        operation_fingerprint=_fingerprint("second-write"),
        expected_resource_type="diet_record",
        logical_operation_key="write:2",
    )

    assert second.disposition == "reject"
    assert second.error_code == "retry_plan_mismatch"
    assert second.operation_id != first.operation_id


def test_retry_replays_each_logical_write_without_crossing_operation_lineage(
    db, auth_user_and_headers
):
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = runtime.create_or_resume_run(
        run_id="run-retry-two-writes",
        attempt_id="attempt-retry-two-writes-1",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-retry-two-writes",
        origin="test",
    )
    runtime.mark_running(admission.context)
    first = runtime.claim_tool_operation(
        admission.context,
        tool_name="health_record",
        effect_class="write",
        operation_fingerprint=_fingerprint("first-write-original"),
        expected_resource_type="diet_record",
        logical_operation_key="health_record:diet:2026-07-20:breakfast",
    )
    runtime.finalize_tool_operation(
        admission.context,
        operation_id=first.operation_id,
        status="succeeded",
        resource_type="diet_record",
        resource_id="101",
    )
    second = runtime.claim_tool_operation(
        admission.context,
        tool_name="health_record",
        effect_class="write",
        operation_fingerprint=_fingerprint("second-write-original"),
        expected_resource_type="diet_record",
        logical_operation_key="health_record:diet:2026-07-20:dinner",
    )
    runtime.interrupt_active(admission.context)
    reconciled = runtime.reconcile_tool_operation(
        second.operation_id,
        now=datetime.now(UTC) + timedelta(seconds=120),
        grace_seconds=90,
    )
    assert reconciled.disposition == "verified_no_effect"

    retry = runtime.create_or_resume_run(
        run_id="ignored-new-run-id",
        attempt_id="attempt-retry-two-writes-2",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-retry-two-writes",
        origin="test",
    )
    runtime.mark_running(retry.context)
    # The retry model emits the calls in the opposite order and recomputes
    # nutrition arguments. Business-target lineage must still bind correctly.
    retry_second = runtime.claim_tool_operation(
        retry.context,
        tool_name="health_record",
        effect_class="write",
        operation_fingerprint=_fingerprint("second-write-recomputed"),
        expected_resource_type="diet_record",
        logical_operation_key="health_record:diet:2026-07-20:dinner",
    )
    replay_first = runtime.claim_tool_operation(
        retry.context,
        tool_name="health_record",
        effect_class="write",
        operation_fingerprint=_fingerprint("first-write-recomputed"),
        expected_resource_type="diet_record",
        logical_operation_key="health_record:diet:2026-07-20:breakfast",
    )

    assert replay_first.disposition == "replay"
    assert replay_first.operation_id == first.operation_id
    assert replay_first.resource_id == "101"
    assert retry_second.disposition == "execute"
    assert retry_second.operation_id == second.operation_id


def test_retry_refuses_a_new_write_that_was_not_in_the_original_plan(
    db, auth_user_and_headers
):
    from app.models.agent_runtime import AgentToolOperation
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = runtime.create_or_resume_run(
        run_id="run-retry-plan-mismatch",
        attempt_id="attempt-retry-plan-mismatch-1",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-retry-plan-mismatch",
        origin="test",
    )
    runtime.mark_running(admission.context)
    original = runtime.claim_tool_operation(
        admission.context,
        tool_name="health_record",
        effect_class="write",
        operation_fingerprint=_fingerprint("breakfast-original"),
        expected_resource_type="diet_record",
        logical_operation_key="health_record:diet:2026-07-20:breakfast",
    )
    runtime.finalize_tool_operation(
        admission.context,
        operation_id=original.operation_id,
        status="succeeded",
        resource_type="diet_record",
        resource_id="101",
    )
    runtime.complete(
        admission.context,
        status="failed",
        error_code="executor_failed",
        retryable=True,
    )
    retry = runtime.create_or_resume_run(
        run_id="ignored-new-run-id",
        attempt_id="attempt-retry-plan-mismatch-2",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-retry-plan-mismatch",
        origin="test",
    )
    runtime.mark_running(retry.context)

    unexpected = runtime.claim_tool_operation(
        retry.context,
        tool_name="health_record",
        effect_class="write",
        operation_fingerprint=_fingerprint("unexpected-dinner"),
        expected_resource_type="diet_record",
        logical_operation_key="health_record:diet:2026-07-20:dinner",
    )

    assert unexpected.disposition == "reject"
    assert unexpected.error_code == "retry_plan_mismatch"
    assert db.query(AgentToolOperation).count() == 1


def test_retry_without_prior_operations_can_execute_multiple_planned_writes(
    db, auth_user_and_headers
):
    from app.models.agent_runtime import AgentToolOperation
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = runtime.create_or_resume_run(
        run_id="run-retry-empty-plan",
        attempt_id="attempt-retry-empty-plan-1",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-retry-empty-plan",
        origin="test",
    )
    runtime.mark_running(admission.context)
    runtime.complete(
        admission.context,
        status="failed",
        error_code="provider_timeout",
        retryable=True,
    )
    retry = runtime.create_or_resume_run(
        run_id="ignored-new-run-id",
        attempt_id="attempt-retry-empty-plan-2",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-retry-empty-plan",
        origin="test",
    )
    runtime.mark_running(retry.context)

    first = runtime.claim_tool_operation(
        retry.context,
        tool_name="health_record",
        effect_class="write",
        operation_fingerprint=_fingerprint("retry-new-breakfast"),
        expected_resource_type="diet_record",
        logical_operation_key="health_record:diet:2026-07-20:breakfast:porridge",
    )
    second = runtime.claim_tool_operation(
        retry.context,
        tool_name="health_record",
        effect_class="write",
        operation_fingerprint=_fingerprint("retry-new-dinner"),
        expected_resource_type="diet_record",
        logical_operation_key="health_record:diet:2026-07-20:dinner:fish",
    )

    assert first.disposition == "execute"
    assert second.disposition == "execute"
    operations = db.query(AgentToolOperation).all()
    assert len(operations) == 2
    assert {operation.created_attempt_no for operation in operations} == {2}


def test_reconciliation_does_not_assume_no_effect_inside_grace_window(
    db, auth_user_and_headers
):
    from app.models.agent_runtime import AgentRun, AgentToolOperation

    user, _headers = auth_user_and_headers
    runtime, admission, claimed = _running_diet_operation(
        db, user.id, suffix="grace"
    )
    runtime.interrupt_active(admission.context)

    result = runtime.reconcile_tool_operation(
        claimed.operation_id,
        now=datetime.now(UTC) + timedelta(seconds=10),
        grace_seconds=90,
    )

    run = db.query(AgentRun).filter_by(run_id=admission.context.run_id).one()
    operation = db.query(AgentToolOperation).filter_by(
        operation_id=claimed.operation_id
    ).one()
    assert result.disposition == "unknown"
    assert result.reason_code == "reconciliation_grace_period"
    assert operation.status == "reconciliation_required"
    assert run.status == "reconciliation_required"


def test_reconciliation_rejects_an_operation_that_is_still_executing(
    db, auth_user_and_headers
):
    from app.services.agent_runtime import AgentRuntimeError

    user, _headers = auth_user_and_headers
    runtime, _admission, claimed = _running_diet_operation(
        db, user.id, suffix="still-executing"
    )

    with pytest.raises(AgentRuntimeError, match="tool_operation_not_reconcilable"):
        runtime.reconcile_tool_operation(
            claimed.operation_id,
            now=datetime.now(UTC) + timedelta(seconds=120),
            grace_seconds=90,
        )


def test_legacy_operation_without_reconciliation_resource_stays_fail_closed(
    db, auth_user_and_headers
):
    from app.models.agent_runtime import AgentRun
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = runtime.create_or_resume_run(
        run_id="run-reconcile-legacy",
        attempt_id="attempt-reconcile-legacy",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-reconcile-legacy",
        origin="test",
    )
    runtime.mark_running(admission.context)
    operation = runtime.claim_tool_operation(
        admission.context,
        tool_name="health_record",
        effect_class="write",
        operation_fingerprint=_fingerprint("legacy"),
    )
    runtime.interrupt_active(admission.context)

    result = runtime.reconcile_tool_operation(
        operation.operation_id,
        now=datetime.now(UTC) + timedelta(seconds=120),
        grace_seconds=90,
    )

    run = db.query(AgentRun).filter_by(run_id=admission.context.run_id).one()
    assert result.disposition == "unknown"
    assert result.reason_code == "unsupported_reconciliation_resource"
    assert run.status == "reconciliation_required"


def test_manual_effect_resolution_rejects_a_resource_owned_by_another_user(
    db, auth_user_and_headers
):
    from app.models.daily_health import DietRecord
    from app.models.user import User
    from app.services.agent_runtime import AgentRuntimeError

    user, _headers = auth_user_and_headers
    other = User(
        username="runtime-reconcile-other",
        email="runtime-reconcile-other@example.com",
        hashed_password="hashed",
        name="runtime-reconcile-other",
        is_active=True,
        is_approved=True,
    )
    db.add(other)
    db.flush()
    other_record = DietRecord(
        user_id=other.id,
        record_date=date.today(),
        meal_type="dinner",
        food_name="晚餐",
        food_items="晚餐",
    )
    db.add(other_record)
    db.commit()

    runtime, admission, claimed = _running_diet_operation(
        db, user.id, suffix="cross-owner"
    )
    runtime.interrupt_active(admission.context)

    with pytest.raises(AgentRuntimeError, match="verified_resource_owner_mismatch"):
        runtime.resolve_tool_operation_manually(
            claimed.operation_id,
            outcome="verified_effect",
            resource_type="diet_record",
            resource_id=str(other_record.id),
        )


def test_manual_medical_exam_effect_resolution_verifies_the_run_owner(
    db, auth_user_and_headers
):
    from app.models.agent_runtime import AgentRun, AgentToolOperation
    from app.models.medical_exam import MedicalExam

    user, _headers = auth_user_and_headers
    exam = MedicalExam(
        user_id=user.id,
        exam_date=date.today(),
        exam_type="imaging",
    )
    db.add(exam)
    db.commit()

    runtime, admission, claimed = _running_medical_exam_operation(
        db, user.id, suffix="manual-effect"
    )
    runtime.interrupt_active(admission.context)

    result = runtime.resolve_tool_operation_manually(
        claimed.operation_id,
        outcome="verified_effect",
        resource_type="medical_exam",
        resource_id=str(exam.id),
    )

    run = db.query(AgentRun).filter_by(run_id=admission.context.run_id).one()
    operation = db.query(AgentToolOperation).filter_by(
        operation_id=claimed.operation_id
    ).one()
    assert result.disposition == "verified_effect"
    assert result.resource_id == str(exam.id)
    assert operation.status == "succeeded"
    assert run.status == "failed"
    assert run.retryable is True
    assert run.error_code == "write_verified_reply_incomplete"


def test_pending_reconciliation_scan_settles_supported_operation_once(
    db, auth_user_and_headers
):
    from app.models.agent_runtime import AgentRun

    user, _headers = auth_user_and_headers
    runtime, admission, _claimed = _running_diet_operation(
        db, user.id, suffix="scan-no-effect"
    )
    runtime.interrupt_active(admission.context)
    scan_time = datetime.now(UTC) + timedelta(seconds=120)

    first = runtime.reconcile_pending_tool_operations(
        now=scan_time,
        grace_seconds=90,
        limit=10,
    )
    second = runtime.reconcile_pending_tool_operations(
        now=scan_time,
        grace_seconds=90,
        limit=10,
    )

    run = db.query(AgentRun).filter_by(run_id=admission.context.run_id).one()
    assert [item.disposition for item in first] == ["verified_no_effect"]
    assert second == []
    assert run.status == "failed"
    assert run.retryable is True
