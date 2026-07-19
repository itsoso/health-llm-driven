from __future__ import annotations

import asyncio
import hashlib

import pytest


def _run(db, user_id: int, *, suffix: str = "one"):
    from app.services.agent_runtime import AgentRuntimeCoordinator

    return AgentRuntimeCoordinator(db).create_or_resume_run(
        run_id=f"run-tool-{suffix}",
        attempt_id=f"attempt-tool-{suffix}",
        user_id=user_id,
        conversation_id=None,
        client_turn_id=f"turn-tool-{suffix}",
        origin="test",
    )


def _fingerprint(value: str = "opaque") -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def test_claim_write_operation_persists_only_content_free_control_data(
    db, auth_user_and_headers
):
    from app.models.agent_runtime import AgentRunEvent, AgentToolOperation
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = _run(db, user.id)
    runtime.mark_running(admission.context)

    claim = runtime.claim_tool_operation(
        admission.context,
        tool_name="health_record",
        effect_class="write",
        operation_fingerprint=_fingerprint("private diet arguments"),
    )

    operation = db.query(AgentToolOperation).one()
    event = db.query(AgentRunEvent).filter(
        AgentRunEvent.event_name == "tool.requested"
    ).one()
    assert claim.disposition == "execute"
    assert claim.owns_execution is True
    assert operation.status == "executing"
    assert operation.run_id == admission.context.run_id
    assert operation.attempt_id == admission.context.attempt_id
    assert operation.tool_name == "health_record"
    assert operation.effect_class == "write"
    assert "private diet arguments" not in repr(operation.__dict__)
    assert event.payload == {
        "tool_name": "health_record",
        "effect_class": "write",
        "status": "executing",
    }


def test_verified_operation_is_replayed_without_second_execution(
    db, auth_user_and_headers
):
    from app.models.agent_runtime import AgentRunEvent, AgentToolOperation
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = _run(db, user.id, suffix="verified")
    runtime.mark_running(admission.context)
    fingerprint = _fingerprint("verified")
    first = runtime.claim_tool_operation(
        admission.context,
        tool_name="health_record",
        effect_class="write",
        operation_fingerprint=fingerprint,
    )
    runtime.finalize_tool_operation(
        admission.context,
        operation_id=first.operation_id,
        status="succeeded",
        resource_type="diet_record",
        resource_id="829",
    )

    replay = runtime.claim_tool_operation(
        admission.context,
        tool_name="health_record",
        effect_class="write",
        operation_fingerprint=fingerprint,
    )

    assert replay.disposition == "replay"
    assert replay.owns_execution is False
    assert replay.resource_type == "diet_record"
    assert replay.resource_id == "829"
    assert db.query(AgentToolOperation).count() == 1
    receipt_event = db.query(AgentRunEvent).filter(
        AgentRunEvent.event_name == "tool.receipt_verified"
    ).one()
    assert receipt_event.payload["receipt_verified"] is True


def test_duplicate_in_flight_operation_requires_reconciliation(
    db, auth_user_and_headers
):
    from app.models.agent_runtime import AgentToolOperation
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = _run(db, user.id, suffix="inflight")
    runtime.mark_running(admission.context)
    fingerprint = _fingerprint("inflight")
    original = runtime.claim_tool_operation(
        admission.context,
        tool_name="health_manage",
        effect_class="write",
        operation_fingerprint=fingerprint,
    )

    duplicate = runtime.claim_tool_operation(
        admission.context,
        tool_name="health_manage",
        effect_class="write",
        operation_fingerprint=fingerprint,
    )

    operation = db.query(AgentToolOperation).one()
    assert duplicate.disposition == "reconcile"
    assert duplicate.owns_execution is False
    assert operation.status == "executing"
    assert operation.error_code is None

    runtime.finalize_tool_operation(
        admission.context,
        operation_id=original.operation_id,
        status="succeeded",
        resource_type="diet_record",
        resource_id="829",
    )
    db.refresh(operation)
    assert operation.status == "succeeded"
    assert operation.resource_id == "829"


def test_same_fingerprint_cannot_be_reused_for_a_different_tool(
    db, auth_user_and_headers
):
    from app.services.agent_runtime import (
        AgentRuntimeCoordinator,
        AgentRuntimeError,
    )

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = _run(db, user.id, suffix="identity")
    runtime.mark_running(admission.context)
    fingerprint = _fingerprint("shared")
    runtime.claim_tool_operation(
        admission.context,
        tool_name="health_record",
        effect_class="write",
        operation_fingerprint=fingerprint,
    )

    with pytest.raises(AgentRuntimeError, match="tool_operation_identity_mismatch"):
        runtime.claim_tool_operation(
            admission.context,
            tool_name="health_manage",
            effect_class="write",
            operation_fingerprint=fingerprint,
        )


def test_runtime_write_fingerprint_canonicalizes_supported_aliases():
    from app.services.agent_executor import _runtime_write_operation_fingerprint

    diet_data = {"food_items": "牛肉面", "calories": 520}
    assert _runtime_write_operation_fingerprint(
        "health_record",
        {"type": "diet", "data": diet_data},
    ) == _runtime_write_operation_fingerprint(
        "health_record",
        {"record_type": "diet", "data": diet_data},
    )
    assert _runtime_write_operation_fingerprint(
        "intervention_cycle",
        {"action": "start", "confirm": True, "days": 90},
    ) == _runtime_write_operation_fingerprint(
        "intervention_cycle",
        {"action": "start", "confirmed": True, "days": 90},
    )


@pytest.mark.parametrize("fingerprint", ["", "not-a-hash", "f" * 63, "G" * 64])
def test_operation_fingerprint_must_be_an_opaque_sha256(
    db, auth_user_and_headers, fingerprint
):
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = _run(db, user.id, suffix=f"bad-{len(fingerprint)}")

    with pytest.raises(ValueError, match="invalid_operation_fingerprint"):
        runtime.claim_tool_operation(
            admission.context,
            tool_name="health_record",
            effect_class="write",
            operation_fingerprint=fingerprint,
        )


def test_stale_attempt_cannot_claim_or_finalize_tool_operation(
    db, auth_user_and_headers
):
    from app.services.agent_runtime import (
        AgentRuntimeCoordinator,
        StaleRunAttempt,
    )

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    first = _run(db, user.id, suffix="stale")
    runtime.mark_running(first.context)
    runtime.complete(
        first.context,
        status="failed",
        error_code="provider_timeout",
        retryable=True,
    )
    retry = runtime.create_or_resume_run(
        run_id="run-ignored",
        attempt_id="attempt-tool-stale-2",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-tool-stale",
        origin="test",
    )

    with pytest.raises(StaleRunAttempt):
        runtime.claim_tool_operation(
            first.context,
            tool_name="health_record",
            effect_class="write",
            operation_fingerprint=_fingerprint("stale"),
        )

    claim = runtime.claim_tool_operation(
        retry.context,
        tool_name="health_record",
        effect_class="write",
        operation_fingerprint=_fingerprint("fresh"),
    )
    with pytest.raises(StaleRunAttempt):
        runtime.finalize_tool_operation(
            first.context,
            operation_id=claim.operation_id,
            status="failed",
            error_code="tool_failed",
        )


def test_success_requires_a_verified_resource_identity(db, auth_user_and_headers):
    from app.services.agent_runtime import (
        AgentRuntimeCoordinator,
        AgentRuntimeError,
    )

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = _run(db, user.id, suffix="receipt")
    claim = runtime.claim_tool_operation(
        admission.context,
        tool_name="health_record",
        effect_class="write",
        operation_fingerprint=_fingerprint("receipt"),
    )

    with pytest.raises(AgentRuntimeError, match="verified_resource_required"):
        runtime.finalize_tool_operation(
            admission.context,
            operation_id=claim.operation_id,
            status="succeeded",
        )


def test_runtime_event_registry_accepts_registered_specialist_tool(
    db, auth_user_and_headers
):
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = _run(db, user.id, suffix="specialist-event")

    runtime.record_event(
        admission.context,
        "tool.requested",
        {
            "tool_name": "analyze_recovery",
            "effect_class": "read",
            "status": "executing",
        },
    )


@pytest.mark.asyncio
async def test_executor_enforce_mode_ledgers_and_replays_verified_write(
    db, auth_user_and_headers, monkeypatch
):
    from app.models.agent_runtime import AgentToolOperation
    from app.services.agent_executor import AgentExecutor
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = _run(db, user.id, suffix="executor-replay")
    runtime.mark_running(admission.context)
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    executor._current_turn_user_message = "记录午餐吃了牛肉面"
    executor._runtime_run_id = admission.context.run_id
    executor._runtime_attempt_id = admission.context.attempt_id
    calls = []

    monkeypatch.setattr(
        "app.services.agent_executor.settings.agent_runtime_mode", "enforce"
    )
    monkeypatch.setattr(
        "app.services.llm.tool_validator.validate_tool_call",
        lambda tool_name, args, db, user_id, reference_now=None: {
            "error": None,
            "data": args,
        },
    )

    async def fake_write(base_url, headers, args):
        calls.append(args)
        return '{"id": 829, "resource_type": "diet_record"}'

    monkeypatch.setattr(executor, "_exec_health_record", fake_write)
    args = {"record_type": "diet", "data": {"food_items": "牛肉面"}}

    first = await executor._execute_tool("health_record", args, None)
    replay = await executor._execute_tool("health_record", args, None)

    operation = db.query(AgentToolOperation).one()
    assert len(calls) == 1
    assert '"id": 829' in first
    assert '"resource_id": "829"' in replay
    assert '"replayed": true' in replay
    assert operation.status == "succeeded"
    assert operation.resource_type == "diet_record"
    assert operation.resource_id == "829"


@pytest.mark.asyncio
async def test_executor_enforce_mode_marks_missing_receipt_for_reconciliation(
    db, auth_user_and_headers, monkeypatch
):
    from app.models.agent_runtime import AgentToolOperation
    from app.services.agent_executor import AgentExecutor
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = _run(db, user.id, suffix="executor-uncertain")
    runtime.mark_running(admission.context)
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    executor._current_turn_user_message = "记录午餐吃了牛肉面"
    executor._runtime_run_id = admission.context.run_id
    executor._runtime_attempt_id = admission.context.attempt_id

    monkeypatch.setattr(
        "app.services.agent_executor.settings.agent_runtime_mode", "enforce"
    )
    monkeypatch.setattr(
        "app.services.llm.tool_validator.validate_tool_call",
        lambda tool_name, args, db, user_id, reference_now=None: {
            "error": None,
            "data": args,
        },
    )

    async def uncertain_write(base_url, headers, args):
        return '{"status":"uncertain","dispatch_started":true}'

    monkeypatch.setattr(executor, "_exec_health_record", uncertain_write)
    await executor._execute_tool(
        "health_record",
        {"record_type": "diet", "data": {"food_items": "牛肉面"}},
        None,
    )

    operation = db.query(AgentToolOperation).one()
    assert operation.status == "reconciliation_required"
    assert operation.error_code == "write_uncertain"


@pytest.mark.asyncio
async def test_executor_cancellation_marks_claimed_write_for_reconciliation(
    db, auth_user_and_headers, monkeypatch
):
    from app.models.agent_runtime import AgentToolOperation
    from app.services.agent_executor import AgentExecutor
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = _run(db, user.id, suffix="executor-cancelled")
    runtime.mark_running(admission.context)
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    executor._current_turn_user_message = "记录午餐吃了牛肉面"
    executor._runtime_run_id = admission.context.run_id
    executor._runtime_attempt_id = admission.context.attempt_id
    dispatch_started = asyncio.Event()

    monkeypatch.setattr(
        "app.services.agent_executor.settings.agent_runtime_mode", "enforce"
    )
    monkeypatch.setattr(
        "app.services.llm.tool_validator.validate_tool_call",
        lambda tool_name, args, db, user_id, reference_now=None: {
            "error": None,
            "data": args,
        },
    )

    async def cancelled_write(base_url, headers, args):
        dispatch_started.set()
        await asyncio.Event().wait()
        return '{"id": 829, "resource_type": "diet_record"}'

    monkeypatch.setattr(executor, "_exec_health_record", cancelled_write)
    task = asyncio.create_task(
        executor._execute_tool(
            "health_record",
            {"record_type": "diet", "data": {"food_items": "牛肉面"}},
            None,
        )
    )
    await dispatch_started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    operation = db.query(AgentToolOperation).one()
    assert operation.status == "reconciliation_required"
    assert operation.error_code == "write_uncertain"


@pytest.mark.asyncio
async def test_executor_off_mode_keeps_runtime_operation_ledger_empty(
    db, auth_user_and_headers, monkeypatch
):
    from app.models.agent_runtime import AgentToolOperation
    from app.services.agent_executor import AgentExecutor

    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    executor._current_turn_user_message = "记录午餐吃了牛肉面"
    executor._runtime_run_id = "legacy-run-without-ledger"
    executor._runtime_attempt_id = "legacy-attempt-without-ledger"

    monkeypatch.setattr(
        "app.services.agent_executor.settings.agent_runtime_mode", "off"
    )
    monkeypatch.setattr(
        "app.services.llm.tool_validator.validate_tool_call",
        lambda tool_name, args, db, user_id, reference_now=None: {
            "error": None,
            "data": args,
        },
    )

    async def fake_write(base_url, headers, args):
        return '{"id": 830, "resource_type": "diet_record"}'

    monkeypatch.setattr(executor, "_exec_health_record", fake_write)
    result = await executor._execute_tool(
        "health_record",
        {"record_type": "diet", "data": {"food_items": "牛肉面"}},
        None,
    )

    assert '"id": 830' in result
    assert db.query(AgentToolOperation).count() == 0


@pytest.mark.asyncio
async def test_executor_exception_after_claim_is_marked_for_reconciliation(
    db, auth_user_and_headers, monkeypatch
):
    from app.models.agent_runtime import AgentToolOperation
    from app.services.agent_executor import AgentExecutor
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = _run(db, user.id, suffix="executor-exception")
    runtime.mark_running(admission.context)
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    executor._current_turn_user_message = "记录午餐吃了牛肉面"
    executor._runtime_run_id = admission.context.run_id
    executor._runtime_attempt_id = admission.context.attempt_id

    monkeypatch.setattr(
        "app.services.agent_executor.settings.agent_runtime_mode", "enforce"
    )
    monkeypatch.setattr(
        "app.services.llm.tool_validator.validate_tool_call",
        lambda tool_name, args, db, user_id, reference_now=None: {
            "error": None,
            "data": args,
        },
    )

    async def exploding_write(base_url, headers, args):
        raise RuntimeError("transport dropped after dispatch")

    monkeypatch.setattr(executor, "_exec_health_record", exploding_write)
    result = await executor._execute_tool(
        "health_record",
        {"record_type": "diet", "data": {"food_items": "牛肉面"}},
        None,
    )

    operation = db.query(AgentToolOperation).one()
    assert result.startswith("Error:")
    assert operation.status == "reconciliation_required"
    assert operation.error_code == "write_uncertain"
