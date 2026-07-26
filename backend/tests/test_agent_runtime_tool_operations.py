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
        expected_resource_type="diet_record",
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
    assert operation.resource_type == "diet_record"
    assert "private diet arguments" not in repr(operation.__dict__)
    assert event.payload == {
        "tool_name": "health_record",
        "effect_class": "write",
        "status": "executing",
    }


def test_claim_rejects_unregistered_expected_resource_type(
    db, auth_user_and_headers
):
    from app.services.agent_runtime import (
        AgentRuntimeCoordinator,
        AgentRuntimeError,
    )

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = _run(db, user.id, suffix="bad-resource-type")
    runtime.mark_running(admission.context)

    with pytest.raises(AgentRuntimeError, match="invalid_resource_type"):
        runtime.claim_tool_operation(
            admission.context,
            tool_name="health_record",
            effect_class="write",
            operation_fingerprint=_fingerprint("bad-resource-type"),
            expected_resource_type="private_diet_text",
        )


def test_health_record_diet_declares_reconcilable_resource_type():
    from app.services.agent_kernel.tool_registry import get_tool_spec

    spec = get_tool_spec("health_record")

    assert spec.reconciliation_resource_type(
        {"record_type": "diet", "data": {"food_items": "牛肉面"}}
    ) == "diet_record"
    assert spec.reconciliation_resource_type(
        {"record_type": "weight", "data": {"weight": 71}}
    ) is None


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


def test_unresolved_tool_operation_forces_run_reconciliation_before_success(
    db, auth_user_and_headers
):
    from app.models.agent_runtime import AgentRun, AgentRuntimeRolloutState
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = _run(db, user.id, suffix="unresolved-run")
    runtime.mark_running(admission.context)
    claim = runtime.claim_tool_operation(
        admission.context,
        tool_name="health_record",
        effect_class="write",
        operation_fingerprint=_fingerprint("unresolved-run"),
    )
    runtime.finalize_tool_operation(
        admission.context,
        operation_id=claim.operation_id,
        status="reconciliation_required",
        error_code="missing_receipt",
    )

    runtime.complete(admission.context, status="succeeded")

    run = db.query(AgentRun).filter_by(run_id=admission.context.run_id).one()
    rollout = db.query(AgentRuntimeRolloutState).filter_by(id=1).one()
    assert run.status == "reconciliation_required"
    assert run.error_code == "write_uncertain"
    assert rollout.reconciliation_generation == 1
    assert rollout.reconciliation_acknowledged_generation == 0


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


def test_logical_operation_key_cannot_change_arguments_inside_one_attempt(
    db, auth_user_and_headers
):
    from app.services.agent_runtime import (
        AgentRuntimeCoordinator,
        AgentRuntimeError,
    )

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = _run(db, user.id, suffix="logical-key-identity")
    runtime.mark_running(admission.context)
    runtime.claim_tool_operation(
        admission.context,
        tool_name="health_record",
        effect_class="write",
        operation_fingerprint=_fingerprint("first-arguments"),
        logical_operation_key="write:1",
    )

    with pytest.raises(AgentRuntimeError, match="tool_operation_identity_mismatch"):
        runtime.claim_tool_operation(
            admission.context,
            tool_name="health_record",
            effect_class="write",
            operation_fingerprint=_fingerprint("changed-arguments"),
            logical_operation_key="write:1",
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
    assert _runtime_write_operation_fingerprint(
        "health_manage",
        {"record_type": "diet", "operation": "delete", "record_id": 829},
    ) == _runtime_write_operation_fingerprint(
        "health_manage",
        {
            "record_type": "diet",
            "operation": "delete",
            "record_id": 829,
            "confirmed": True,
            "confirm": True,
        },
    )


def test_runtime_write_fingerprint_uses_dispatched_diet_payload():
    from app.services.agent_executor import _runtime_write_operation_fingerprint

    top_level = {
        "type": "diet",
        "record_date": "2026-07-20T12:00:00+08:00",
        "meal_type": "早餐",
        "meal_time": "09:05:30+08:00",
        "food_items": "小米粥",
        "data": {},
    }
    nested = {
        "record_type": "diet",
        "data": {
            "record_date": "2026-07-20",
            "meal_type": "breakfast",
            "meal_time": "09:05",
            "food_items": "小米粥",
        },
    }

    assert _runtime_write_operation_fingerprint(
        "health_record",
        top_level,
        default_record_date="2026-07-21",
    ) == _runtime_write_operation_fingerprint(
        "health_record",
        nested,
        default_record_date="2026-07-21",
    )


def test_photo_diet_fingerprint_ignores_confirmation_control_fields():
    from app.services.agent_executor import _runtime_write_operation_fingerprint

    base = {
        "record_type": "diet",
        "data": {
            "record_date": "2026-07-20",
            "meal_type": "dinner",
            "food_items": "烤鱼",
            "photo_draft_token": "photo-draft-829",
        },
    }
    with_confirmation = {
        "record_type": "diet",
        "data": {
            **base["data"],
            "confirmed": True,
            "_fast_record_requires_confirmation": True,
        },
    }

    assert _runtime_write_operation_fingerprint(
        "health_record",
        base,
        default_record_date="2026-07-21",
    ) == _runtime_write_operation_fingerprint(
        "health_record",
        with_confirmation,
        default_record_date="2026-07-21",
    )


def test_canonical_diet_replay_in_same_attempt_returns_verified_receipt(
    db, auth_user_and_headers
):
    from app.services.agent_executor import (
        _runtime_write_operation_fingerprint,
        _runtime_write_operation_identity,
    )
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = _run(db, user.id, suffix="canonical-diet-replay")
    runtime.mark_running(admission.context)
    first_args = {
        "record_type": "diet",
        "data": {
            "record_date": "2026-07-20T12:00:00+08:00",
            "meal_type": "早餐",
            "meal_time": "09:05:30+08:00",
            "food_items": "小米粥",
        },
    }
    replay_args = {
        "record_type": "diet",
        "data": {
            "record_date": "2026-07-20",
            "meal_type": "breakfast",
            "meal_time": "09:05",
            "food_items": "小米粥",
        },
    }

    def claim(args):
        logical_key, scope_key, discriminator_kind, discriminator_key = (
            _runtime_write_operation_identity(
                "health_record",
                args,
                default_record_date="2026-07-21",
            )
        )
        return runtime.claim_tool_operation(
            admission.context,
            tool_name="health_record",
            effect_class="write",
            operation_fingerprint=_runtime_write_operation_fingerprint(
                "health_record",
                args,
                default_record_date="2026-07-21",
            ),
            logical_operation_key=logical_key,
            logical_operation_scope_key=scope_key,
            logical_operation_discriminator_kind=discriminator_kind,
            logical_operation_discriminator_key=discriminator_key,
        )

    first = claim(first_args)
    runtime.finalize_tool_operation(
        admission.context,
        operation_id=first.operation_id,
        status="succeeded",
        resource_type="diet_record",
        resource_id="829",
    )
    replay = claim(replay_args)

    assert replay.disposition == "replay"
    assert replay.operation_id == first.operation_id
    assert replay.resource_id == "829"


def test_runtime_write_logical_key_uses_stable_diet_target_not_call_order():
    from app.services.agent_executor import _runtime_write_logical_operation_key

    breakfast_before = {
        "record_type": "diet",
        "data": {
            "record_date": "2026-07-20",
            "meal_type": "breakfast",
            "food_items": "小米粥",
            "calories": 260,
        },
    }
    breakfast_recomputed = {
        "type": "diet",
        "data": {
            "record_date": "2026-07-20",
            "meal_type": "breakfast",
            "food_items": " 小米粥 ",
            "calories": 380,
        },
    }
    dinner = {
        "record_type": "diet",
        "data": {
            "record_date": "2026-07-20",
            "meal_type": "dinner",
            "food_items": "烤鱼",
        },
    }

    assert _runtime_write_logical_operation_key(
        "health_record", breakfast_before
    ) == _runtime_write_logical_operation_key(
        "health_record", breakfast_recomputed
    )
    assert _runtime_write_logical_operation_key(
        "health_record", breakfast_before
    ) != _runtime_write_logical_operation_key("health_record", dinner)


def test_runtime_write_logical_key_keeps_distinct_records_in_the_same_meal():
    from app.services.agent_executor import _runtime_write_logical_operation_key

    common = {"record_date": "2026-07-20", "meal_type": "lunch"}
    rice = {
        "record_type": "diet",
        "data": {**common, "food_items": "米饭"},
    }
    fish = {
        "record_type": "diet",
        "data": {**common, "food_items": "烤鱼"},
    }

    assert _runtime_write_logical_operation_key(
        "health_record", rice
    ) != _runtime_write_logical_operation_key("health_record", fish)


def test_runtime_write_logical_key_keeps_same_food_at_distinct_meal_times():
    from app.services.agent_executor import _runtime_write_logical_operation_key

    common = {
        "record_date": "2026-07-20",
        "meal_type": "snack",
        "food_items": "拿铁",
    }
    morning = {"record_type": "diet", "data": {**common, "meal_time": "10:00"}}
    afternoon = {
        "record_type": "diet",
        "data": {**common, "meal_time": "15:00:00"},
    }

    assert _runtime_write_logical_operation_key(
        "health_record", morning
    ) != _runtime_write_logical_operation_key("health_record", afternoon)


def test_runtime_write_logical_key_normalizes_time_and_ignores_optional_food_id():
    from app.services.agent_executor import _runtime_write_logical_operation_key

    before = {
        "record_type": "diet",
        "data": {
            "record_date": "2026-07-20",
            "meal_type": "snack",
            "meal_time": "9:05",
            "food_id": "CFC:LATTE",
            "food_items": "拿铁",
        },
    }
    recomputed = {
        "record_type": "diet",
        "data": {
            "record_date": "2026-07-20",
            "meal_type": "snack",
            "meal_time": "09:05:00",
            "food_items": "拿铁",
        },
    }

    assert _runtime_write_logical_operation_key(
        "health_record", before
    ) == _runtime_write_logical_operation_key("health_record", recomputed)


def test_runtime_write_identity_keeps_optional_discriminator_in_same_scope():
    from app.services.agent_executor import _runtime_write_operation_identity

    common = {
        "record_date": "2026-07-20",
        "meal_type": "snack",
        "food_items": "拿铁",
    }
    without_time = _runtime_write_operation_identity(
        "health_record",
        {"record_type": "diet", "data": common},
    )
    with_time = _runtime_write_operation_identity(
        "health_record",
        {"record_type": "diet", "data": {**common, "meal_time": "10:00"}},
    )

    assert without_time[0] != with_time[0]
    assert without_time[1] == with_time[1]
    assert without_time[2:] == (None, None)
    assert with_time[2] == "meal_time"
    assert with_time[3] is not None


def test_runtime_write_identity_scope_survives_photo_token_loss_and_food_rephrase():
    from app.services.agent_executor import _runtime_write_operation_identity

    photographed = _runtime_write_operation_identity(
        "health_record",
        {
            "record_type": "diet",
            "data": {
                "record_date": "2026-07-20",
                "meal_type": "snack",
                "food_items": "拿铁",
                "photo_draft_token": "photo-token-1",
            },
        },
    )
    rephrased = _runtime_write_operation_identity(
        "health_record",
        {
            "record_type": "diet",
            "data": {
                "record_date": "2026-07-20",
                "meal_type": "snack",
                "food_items": "咖啡拿铁1杯",
                "meal_time": "10:00",
            },
        },
    )

    assert photographed[0] != rephrased[0]
    assert photographed[1] == rephrased[1]
    assert photographed[2] == "photo_token"
    assert rephrased[2] == "meal_time"


def test_diet_scope_rejects_photo_token_loss_with_food_rephrase(
    db, auth_user_and_headers
):
    from app.models.agent_runtime import AgentToolOperation
    from app.services.agent_executor import _runtime_write_operation_identity
    from app.services.agent_runtime import (
        AgentRuntimeCoordinator,
        AgentRuntimeError,
    )

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = _run(db, user.id, suffix="photo-token-loss-rephrase")
    runtime.mark_running(admission.context)
    photographed = _runtime_write_operation_identity(
        "health_record",
        {
            "record_type": "diet",
            "data": {
                "record_date": "2026-07-20",
                "meal_type": "snack",
                "food_items": "拿铁",
                "photo_draft_token": "photo-token-1",
            },
        },
    )
    rephrased = _runtime_write_operation_identity(
        "health_record",
        {
            "record_type": "diet",
            "data": {
                "record_date": "2026-07-20",
                "meal_type": "snack",
                "food_items": "咖啡拿铁1杯",
                "meal_time": "10:00",
            },
        },
    )

    runtime.claim_tool_operation(
        admission.context,
        tool_name="health_record",
        effect_class="write",
        operation_fingerprint=_fingerprint("photo-latte"),
        logical_operation_key=photographed[0],
        logical_operation_scope_key=photographed[1],
        logical_operation_discriminator_kind=photographed[2],
        logical_operation_discriminator_key=photographed[3],
    )
    with pytest.raises(AgentRuntimeError, match="tool_operation_identity_mismatch"):
        runtime.claim_tool_operation(
            admission.context,
            tool_name="health_record",
            effect_class="write",
            operation_fingerprint=_fingerprint("rephrased-latte"),
            logical_operation_key=rephrased[0],
            logical_operation_scope_key=rephrased[1],
            logical_operation_discriminator_kind=rephrased[2],
            logical_operation_discriminator_key=rephrased[3],
        )

    assert db.query(AgentToolOperation).count() == 1


def test_diet_scope_allows_explicit_distinct_meal_slots(
    db, auth_user_and_headers
):
    from app.models.agent_runtime import AgentToolOperation
    from app.services.agent_executor import _runtime_write_operation_identity
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = _run(db, user.id, suffix="distinct-meal-slots")
    runtime.mark_running(admission.context)
    args_by_meal = (
        {
            "record_type": "diet",
            "data": {
                "record_date": "2026-07-20",
                "meal_type": "breakfast",
                "food_items": "小米粥",
            },
        },
        {
            "record_type": "diet",
            "data": {
                "record_date": "2026-07-20",
                "meal_type": "lunch",
                "food_items": "烤鱼",
                "meal_time": "12:30",
            },
        },
    )

    for index, args in enumerate(args_by_meal):
        identity = _runtime_write_operation_identity("health_record", args)
        result = runtime.claim_tool_operation(
            admission.context,
            tool_name="health_record",
            effect_class="write",
            operation_fingerprint=_fingerprint(f"meal-slot-{index}"),
            logical_operation_key=identity[0],
            logical_operation_scope_key=identity[1],
            logical_operation_discriminator_kind=identity[2],
            logical_operation_discriminator_key=identity[3],
        )
        assert result.disposition == "execute"

    assert db.query(AgentToolOperation).count() == 2


def test_runtime_write_identity_normalizes_meal_aliases():
    from app.services.agent_executor import _runtime_write_operation_identity

    chinese = _runtime_write_operation_identity(
        "health_record",
        {
            "record_type": "diet",
            "data": {
                "record_date": "2026-07-20",
                "meal_type": "早餐",
                "food_items": "小米粥",
            },
        },
    )
    canonical = _runtime_write_operation_identity(
        "health_record",
        {
            "record_type": "diet",
            "data": {
                "record_date": "2026-07-20",
                "meal_type": "breakfast",
                "food_items": "小米粥",
            },
        },
    )

    assert chinese == canonical


def test_runtime_write_identity_normalizes_date_and_datetime_forms():
    from app.services.agent_executor import _runtime_write_operation_identity

    as_date = _runtime_write_operation_identity(
        "health_record",
        {
            "record_type": "diet",
            "data": {
                "record_date": "2026-07-20",
                "meal_type": "breakfast",
                "food_items": "小米粥",
            },
        },
    )
    as_datetime = _runtime_write_operation_identity(
        "health_record",
        {
            "record_type": "diet",
            "data": {
                "record_date": "2026-07-20T00:00:00+08:00",
                "meal_type": "breakfast",
                "food_items": "小米粥",
            },
        },
    )

    assert as_date == as_datetime


def test_runtime_write_identity_normalizes_timezone_meal_time_to_storage_minute():
    from app.services.agent_executor import _runtime_write_operation_identity

    common = {
        "record_date": "2026-07-20",
        "meal_type": "snack",
        "food_items": "拿铁",
    }
    short = _runtime_write_operation_identity(
        "health_record",
        {
            "record_type": "diet",
            "data": {**common, "meal_time": "09:05+08:00"},
        },
    )
    with_seconds = _runtime_write_operation_identity(
        "health_record",
        {
            "record_type": "diet",
            "data": {**common, "meal_time": "09:05:00+08:00"},
        },
    )

    assert short == with_seconds


def test_diet_create_normalizer_merges_top_level_fields_into_write_payload():
    from app.services.agent_executor import _normalize_diet_create_data

    normalized = _normalize_diet_create_data(
        {
            "record_type": "diet",
            "record_date": "2026-07-20T12:00:00+08:00",
            "meal_type": "早餐",
            "meal_time": "09:05:30+08:00",
            "food_items": "小米粥",
            "data": {},
        },
        default_record_date="2026-07-21",
    )

    assert normalized["record_date"] == "2026-07-20"
    assert normalized["meal_type"] == "breakfast"
    assert normalized["meal_time"] == "09:05"
    assert normalized["food_items"] == "小米粥"


@pytest.mark.asyncio
async def test_diet_adapter_dispatches_the_same_normalized_top_level_payload(db):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    posted = {}

    async def capture_post(url, headers, payload):
        posted.update({"url": url, "headers": headers, "payload": payload})
        return '{"id": 1, "resource_type": "diet_record"}'

    executor._api_post = capture_post
    await executor._exec_health_record(
        "http://example.test",
        {},
        {
            "record_type": "diet",
            "record_date": "2026-07-20T12:00:00+08:00",
            "meal_type": "早餐",
            "meal_time": "09:05:30+08:00",
            "food_items": "小米粥",
            "data": {"confirmed": True},
        },
    )

    assert posted["url"].endswith("/diet/records")
    assert posted["payload"]["record_date"] == "2026-07-20"
    assert posted["payload"]["meal_type"] == "breakfast"
    assert posted["payload"]["meal_time"] == "09:05"
    assert posted["payload"]["food_items"] == "小米粥"
    assert "confirmed" not in posted["payload"]


def test_diet_identity_defaults_date_before_distinguishing_meals(
    db, auth_user_and_headers
):
    from app.models.agent_runtime import AgentToolOperation
    from app.services.agent_executor import _runtime_write_operation_identity
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = _run(db, user.id, suffix="default-date-distinct-meals")
    runtime.mark_running(admission.context)

    for index, meal_type in enumerate(("breakfast", "lunch")):
        identity = _runtime_write_operation_identity(
            "health_record",
            {
                "record_type": "diet",
                "data": {
                    "meal_type": meal_type,
                    "food_items": "小米粥" if index == 0 else "烤鱼",
                },
            },
            default_record_date="2026-07-20",
        )
        result = runtime.claim_tool_operation(
            admission.context,
            tool_name="health_record",
            effect_class="write",
            operation_fingerprint=_fingerprint(f"default-date-{meal_type}"),
            logical_operation_key=identity[0],
            logical_operation_scope_key=identity[1],
            logical_operation_discriminator_kind=identity[2],
            logical_operation_discriminator_key=identity[3],
        )
        assert result.disposition == "execute"

    assert db.query(AgentToolOperation).count() == 2


def test_same_scope_allows_two_explicit_distinct_meal_times(
    db, auth_user_and_headers
):
    from app.models.agent_runtime import AgentToolOperation
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = _run(db, user.id, suffix="distinct-time-discriminators")
    runtime.mark_running(admission.context)

    first = runtime.claim_tool_operation(
        admission.context,
        tool_name="health_record",
        effect_class="write",
        operation_fingerprint=_fingerprint("latte-at-10"),
        logical_operation_key="target:latte-at-10",
        logical_operation_scope_key="scope:snack-latte",
        logical_operation_discriminator_kind="meal_time",
        logical_operation_discriminator_key="10:00:00",
    )
    second = runtime.claim_tool_operation(
        admission.context,
        tool_name="health_record",
        effect_class="write",
        operation_fingerprint=_fingerprint("latte-at-15"),
        logical_operation_key="target:latte-at-15",
        logical_operation_scope_key="scope:snack-latte",
        logical_operation_discriminator_kind="meal_time",
        logical_operation_discriminator_key="15:00:00",
    )

    assert first.disposition == "execute"
    assert second.disposition == "execute"
    assert db.query(AgentToolOperation).count() == 2


def test_same_scope_rejects_an_optional_discriminator_appearing_later(
    db, auth_user_and_headers
):
    from app.models.agent_runtime import AgentToolOperation
    from app.services.agent_runtime import (
        AgentRuntimeCoordinator,
        AgentRuntimeError,
    )

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = _run(db, user.id, suffix="optional-time-appears")
    runtime.mark_running(admission.context)
    runtime.claim_tool_operation(
        admission.context,
        tool_name="health_record",
        effect_class="write",
        operation_fingerprint=_fingerprint("latte-without-time"),
        logical_operation_key="target:latte-without-time",
        logical_operation_scope_key="scope:snack-latte",
    )

    with pytest.raises(AgentRuntimeError, match="tool_operation_identity_mismatch"):
        runtime.claim_tool_operation(
            admission.context,
            tool_name="health_record",
            effect_class="write",
            operation_fingerprint=_fingerprint("latte-with-time"),
            logical_operation_key="target:latte-at-10",
            logical_operation_scope_key="scope:snack-latte",
            logical_operation_discriminator_kind="meal_time",
            logical_operation_discriminator_key="10:00:00",
        )

    assert db.query(AgentToolOperation).count() == 1


def test_runtime_write_logical_key_uses_record_id_for_mutations():
    from app.services.agent_executor import _runtime_write_logical_operation_key

    before = {
        "record_type": "diet",
        "operation": "update",
        "record_id": 829,
        "data": {"calories": 520},
    }
    recomputed = {
        "record_type": "diet",
        "operation": "update",
        "record_id": "829",
        "data": {"calories": 480, "protein": 35},
    }

    assert _runtime_write_logical_operation_key(
        "health_manage", before
    ) == _runtime_write_logical_operation_key("health_manage", recomputed)


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


def test_runtime_write_fingerprint_is_keyed_and_not_plain_sha256(monkeypatch):
    import hashlib
    import json

    from app.config import settings
    from app.services.agent_executor import _runtime_write_operation_fingerprint

    monkeypatch.setattr(settings, "secret_key", "a" * 32)
    args = {"record_type": "water", "data": {"amount": 500}}
    fingerprint = _runtime_write_operation_fingerprint("health_record", args)
    plain = hashlib.sha256(
        json.dumps(
            {"tool": "health_record", "args": args},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
    ).hexdigest()

    assert len(fingerprint) == 64
    assert fingerprint != plain
    assert _runtime_write_operation_fingerprint("health_record", args) == fingerprint


def test_runtime_logical_operation_hashes_are_keyed(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.config import settings
    from app.models.agent_runtime import AgentToolOperation
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    monkeypatch.setattr(settings, "secret_key", "a" * 32)
    runtime = AgentRuntimeCoordinator(db)
    admission = _run(db, user.id, suffix="keyed-logical-hashes")
    runtime.mark_running(admission.context)
    logical_key = "diet:2026-07-24:lunch"
    logical_scope = "diet:2026-07-24"
    discriminator = "lunch"

    runtime.claim_tool_operation(
        admission.context,
        tool_name="health_record",
        effect_class="write",
        operation_fingerprint=_fingerprint("keyed-logical-hashes"),
        logical_operation_key=logical_key,
        logical_operation_scope_key=logical_scope,
        logical_operation_discriminator_kind="meal_time",
        logical_operation_discriminator_key=discriminator,
    )

    operation = db.query(AgentToolOperation).one()
    assert operation.logical_operation_key_hash != hashlib.sha256(
        logical_key.encode()
    ).hexdigest()
    assert operation.logical_operation_scope_hash != hashlib.sha256(
        logical_scope.encode()
    ).hexdigest()
    assert operation.logical_operation_discriminator_hash != hashlib.sha256(
        discriminator.encode()
    ).hexdigest()


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
    runtime.mark_running(retry.context)

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


def test_legacy_null_lineage_replays_by_exact_fingerprint(
    db, auth_user_and_headers
):
    from app.models.agent_runtime import AgentToolOperation
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = _run(db, user.id, suffix="legacy-null-lineage")
    runtime.mark_running(admission.context)
    fingerprint = _fingerprint("legacy-same-arguments")
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
    operation = db.query(AgentToolOperation).one()
    operation.logical_operation_key_hash = None
    db.commit()

    replay = runtime.claim_tool_operation(
        admission.context,
        tool_name="health_record",
        effect_class="write",
        operation_fingerprint=fingerprint,
        logical_operation_key="health_record:diet:2026-07-20:lunch",
    )

    assert replay.disposition == "replay"
    assert replay.operation_id == first.operation_id
    assert db.query(AgentToolOperation).count() == 1


def test_success_requires_a_verified_resource_identity(db, auth_user_and_headers):
    from app.services.agent_runtime import (
        AgentRuntimeCoordinator,
        AgentRuntimeError,
    )

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = _run(db, user.id, suffix="receipt")
    runtime.mark_running(admission.context)
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


@pytest.mark.parametrize(
    ("resource_type", "resource_id", "expected_error"),
    [
        ("胃溃疡诊断", "829", "invalid_resource_type"),
        ("future_private_record", "829", "invalid_resource_type"),
        ("diet_record", "早餐吃了牛肉面", "invalid_resource_id"),
        ("diet_record", "829/用户健康正文", "invalid_resource_id"),
        ("diet_record", "gastritis", "invalid_resource_id"),
        ("diet_record", "hiv_stage3", "invalid_resource_id"),
        ("diet_record", "gastritis_stage2", "invalid_resource_id"),
    ],
)
def test_verified_resource_identity_rejects_unregistered_or_private_text(
    db,
    auth_user_and_headers,
    resource_type,
    resource_id,
    expected_error,
):
    from app.services.agent_runtime import (
        AgentRuntimeCoordinator,
        AgentRuntimeError,
    )

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = _run(db, user.id, suffix=f"private-receipt-{expected_error}")
    runtime.mark_running(admission.context)
    claim = runtime.claim_tool_operation(
        admission.context,
        tool_name="health_record",
        effect_class="write",
        operation_fingerprint=_fingerprint(f"{resource_type}:{resource_id}"),
    )

    with pytest.raises(AgentRuntimeError, match=expected_error):
        runtime.finalize_tool_operation(
            admission.context,
            operation_id=claim.operation_id,
            status="succeeded",
            resource_type=resource_type,
            resource_id=resource_id,
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
    executor._runtime_managed = True
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
    assert executor._agent_kernel_event_bus is not None
    tool_results = [
        event
        for event in executor._agent_kernel_event_bus.events
        if event.name == "agent.tool_result"
    ]
    assert len(tool_results) == 2
    assert tool_results[-1].data["success"] is True
    assert "health_record" not in executor._agent_kernel_tool_failure_tools


@pytest.mark.asyncio
async def test_executor_passes_runtime_operation_id_to_reconcilable_diet_write(
    db, auth_user_and_headers, monkeypatch
):
    from app.models.agent_runtime import AgentToolOperation
    from app.services.agent_executor import AgentExecutor
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    admission = _run(db, user.id, suffix="executor-diet-idempotency")
    AgentRuntimeCoordinator(db).mark_running(admission.context)
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    executor._current_turn_user_message = "记录午餐吃了牛肉面"
    executor._runtime_run_id = admission.context.run_id
    executor._runtime_attempt_id = admission.context.attempt_id
    executor._runtime_managed = True
    observed_headers = []

    monkeypatch.setattr(
        "app.services.llm.tool_validator.validate_tool_call",
        lambda tool_name, args, db, user_id, reference_now=None: {
            "error": None,
            "data": args,
        },
    )

    async def fake_write(base_url, headers, args):
        observed_headers.append(dict(headers))
        return '{"id": 832, "resource_type": "diet_record"}'

    monkeypatch.setattr(executor, "_exec_health_record", fake_write)

    await executor._execute_tool(
        "health_record",
        {"record_type": "diet", "data": {"food_items": "牛肉面"}},
        None,
    )

    operation = db.query(AgentToolOperation).one()
    assert observed_headers == [{"Idempotency-Key": operation.operation_id}]


@pytest.mark.asyncio
async def test_executor_does_not_attach_runtime_id_to_unregistered_write(
    db, auth_user_and_headers, monkeypatch
):
    from app.services.agent_executor import AgentExecutor
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    admission = _run(db, user.id, suffix="executor-weight-no-idempotency")
    AgentRuntimeCoordinator(db).mark_running(admission.context)
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    executor._current_turn_user_message = "记录体重71公斤"
    executor._runtime_run_id = admission.context.run_id
    executor._runtime_attempt_id = admission.context.attempt_id
    executor._runtime_managed = True
    observed_headers = []

    monkeypatch.setattr(
        "app.services.llm.tool_validator.validate_tool_call",
        lambda tool_name, args, db, user_id, reference_now=None: {
            "error": None,
            "data": args,
        },
    )

    async def fake_write(base_url, headers, args):
        observed_headers.append(dict(headers))
        return '{"id": 833, "resource_type": "weight_record"}'

    monkeypatch.setattr(executor, "_exec_health_record", fake_write)

    await executor._execute_tool(
        "health_record",
        {"record_type": "weight", "data": {"weight": 71}},
        None,
    )

    assert observed_headers == [{}]


@pytest.mark.asyncio
async def test_executor_canary_managed_run_ledgers_verified_write(
    db, auth_user_and_headers, monkeypatch
):
    from app.models.agent_runtime import AgentToolOperation
    from app.services.agent_executor import AgentExecutor
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    admission = _run(db, user.id, suffix="executor-canary-ledger")
    AgentRuntimeCoordinator(db).mark_running(admission.context)
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    executor._current_turn_user_message = "记录午餐吃了牛肉面"
    executor._runtime_run_id = admission.context.run_id
    executor._runtime_attempt_id = admission.context.attempt_id
    executor._runtime_managed = True

    monkeypatch.setattr(
        "app.services.agent_executor.settings.agent_runtime_mode", "canary"
    )
    monkeypatch.setattr(
        "app.services.llm.tool_validator.validate_tool_call",
        lambda tool_name, args, db, user_id, reference_now=None: {
            "error": None,
            "data": args,
        },
    )

    async def fake_write(base_url, headers, args):
        return '{"id": 831, "resource_type": "diet_record"}'

    monkeypatch.setattr(executor, "_exec_health_record", fake_write)

    await executor._execute_tool(
        "health_record",
        {"record_type": "diet", "data": {"food_items": "牛肉面"}},
        None,
    )

    operation = db.query(AgentToolOperation).one()
    assert operation.status == "succeeded"
    assert operation.resource_type == "diet_record"
    assert operation.resource_id == "831"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("record_type", "operation_name", "expected_resource_type"),
    [
        ("supplement_definition", "update", "supplement_definition"),
        ("supplement_definition", "delete", "supplement_definition"),
        ("medication_log", "update", "medication_log"),
        ("medication_log", "delete", "medication_log"),
    ],
)
async def test_executor_ledgers_health_manage_mutations_with_typed_receipt(
    db,
    auth_user_and_headers,
    monkeypatch,
    record_type,
    operation_name,
    expected_resource_type,
):
    from app.models.agent_runtime import AgentToolOperation
    from app.services.agent_executor import AgentExecutor
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = _run(
        db,
        user.id,
        suffix=f"{record_type}-{operation_name}",
    )
    runtime.mark_running(admission.context)
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    executor._current_turn_user_message = "调整补剂定义"
    executor._runtime_run_id = admission.context.run_id
    executor._runtime_attempt_id = admission.context.attempt_id
    executor._runtime_managed = True

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

    async def fake_manage(base_url, headers, args):
        return '{"id":55,"message":"操作成功"}'

    monkeypatch.setattr(executor, "_exec_health_manage", fake_manage)
    args = {
        "record_type": record_type,
        "operation": operation_name,
        "record_id": 55,
        "data": {"dosage": "1000IU"},
    }

    await executor._execute_tool("health_manage", args, None)

    stored = db.query(AgentToolOperation).one()
    assert stored.status == "succeeded"
    assert stored.resource_type == expected_resource_type
    assert stored.resource_id == "55"


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
    executor._runtime_managed = True

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
async def test_executor_marks_local_medication_plan_rejection_failed_not_uncertain(
    db, auth_user_and_headers, monkeypatch
):
    from app.models.agent_runtime import AgentToolOperation
    from app.services.agent_executor import AgentExecutor
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = _run(db, user.id, suffix="executor-medication-local-rejection")
    runtime.mark_running(admission.context)
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    executor._current_turn_user_message = "记录本次服药"
    executor._runtime_run_id = admission.context.run_id
    executor._runtime_attempt_id = admission.context.attempt_id
    executor._runtime_managed = True
    executor._turn_medication_tool_preflight_error = (
        "服务端未能封存完整的用药确认计划"
    )

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

    await executor._execute_tool(
        "health_record",
        {
            "record_type": "medication",
            "data": {
                "medication_name": "测试药物",
                "actual_dosage": "1片",
            },
        },
        None,
    )

    operation = db.query(AgentToolOperation).one()
    assert operation.status == "failed"
    assert operation.error_code == "tool_rejected"


@pytest.mark.asyncio
async def test_executor_marks_registered_adapter_local_rejection_failed_not_uncertain(
    db, auth_user_and_headers, monkeypatch
):
    from app.models.agent_runtime import AgentToolOperation
    from app.services.agent_executor import AgentExecutor
    from app.services.agent_kernel.types import ToolExecutionRequest
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = _run(db, user.id, suffix="executor-genetic-local-rejection")
    runtime.mark_running(admission.context)
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    executor._runtime_run_id = admission.context.run_id
    executor._runtime_attempt_id = admission.context.attempt_id
    executor._runtime_managed = True

    monkeypatch.setattr(
        "app.services.agent_executor.settings.agent_runtime_mode", "enforce"
    )

    result = await executor._dispatch_tool_request(
        ToolExecutionRequest(
            tool_name="upload_genetic_txt",
            arguments={"txt_content": "too short"},
            source="test",
        ),
        None,
    )

    payload = __import__("json").loads(result)
    assert payload["dispatch_started"] is False
    operation = db.query(AgentToolOperation).one()
    assert operation.status == "failed"
    assert operation.error_code == "tool_rejected"


@pytest.mark.asyncio
async def test_executor_logs_content_free_warning_for_legacy_local_rejection(
    db, auth_user_and_headers, monkeypatch, caplog
):
    import logging

    from app.services.agent_executor import AgentExecutor
    from app.services.agent_kernel.types import ToolExecutionRequest
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = _run(db, user.id, suffix="executor-legacy-local-rejection")
    runtime.mark_running(admission.context)
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    executor._runtime_run_id = admission.context.run_id
    executor._runtime_attempt_id = admission.context.attempt_id
    executor._runtime_managed = True

    async def legacy_rejection(base_url, headers, args):
        return "Error: 需要提供 private-health-content"

    monkeypatch.setattr(executor, "_exec_upload_genetic_txt", legacy_rejection)
    caplog.set_level(logging.WARNING, logger="app.services.agent_executor")

    await executor._dispatch_tool_request(
        ToolExecutionRequest(
            tool_name="upload_genetic_txt",
            arguments={"txt_content": "x" * 80},
            source="test",
        ),
        None,
    )

    warning = next(
        record
        for record in caplog.records
        if "legacy local write rejection contract" in record.getMessage()
    )
    assert "upload_genetic_txt" in warning.getMessage()
    assert "private-health-content" not in warning.getMessage()


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
    executor._runtime_managed = True
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
    db, auth_user_and_headers, monkeypatch, caplog
):
    import logging

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
    executor._runtime_managed = True

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
        user.name = "committed-before-error"
        db.commit()
        raise RuntimeError("private-health-content")

    monkeypatch.setattr(executor, "_exec_health_record", exploding_write)
    caplog.set_level(logging.ERROR, logger="app.services.agent_executor")
    result = await executor._execute_tool(
        "health_record",
        {"record_type": "diet", "data": {"food_items": "牛肉面"}},
        None,
    )

    operation = db.query(AgentToolOperation).one()
    assert result.startswith("Error:")
    assert operation.status == "reconciliation_required"
    assert operation.error_code == "write_uncertain"
    assert "private-health-content" not in caplog.text
    db.expire_all()
    assert user.name == "committed-before-error"


@pytest.mark.asyncio
async def test_executor_http_timeout_after_claim_is_marked_for_reconciliation(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    import httpx

    from app.models.agent_runtime import AgentToolOperation
    from app.services.agent_executor import AgentExecutor
    from app.services.agent_runtime import AgentRuntimeCoordinator

    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = _run(db, user.id, suffix="executor-http-timeout")
    runtime.mark_running(admission.context)
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    executor._current_turn_user_message = "记录午餐吃了牛肉面"
    executor._runtime_run_id = admission.context.run_id
    executor._runtime_attempt_id = admission.context.attempt_id
    executor._runtime_managed = True

    monkeypatch.setattr(
        "app.services.agent_executor.settings.agent_runtime_mode",
        "enforce",
    )
    monkeypatch.setattr(
        "app.services.llm.tool_validator.validate_tool_call",
        lambda tool_name, args, db, user_id, reference_now=None: {
            "error": None,
            "data": args,
        },
    )

    async def timed_out_write(base_url, headers, args):
        raise httpx.ReadTimeout("private-upstream-detail")

    monkeypatch.setattr(executor, "_exec_health_record", timed_out_write)

    result = await executor._execute_tool(
        "health_record",
        {"record_type": "diet", "data": {"food_items": "牛肉面"}},
        None,
    )

    operation = db.query(AgentToolOperation).one()
    assert "处理超时" in result
    assert operation.status == "reconciliation_required"
    assert operation.error_code == "write_uncertain"
