"""Medication intake creates only the minimum definition after server confirmation."""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.models.agent_conversation import AgentConversation, AgentMessage
from app.models.medication import Medication, MedicationLog
from app.services.agent_executor import AgentExecutor
from app.services.medication_intake_batch import propose_medication_intake_items
from app.services.write_intent_service import confirm


def _source(db, user_id: int, content: str):
    conversation = AgentConversation(user_id=user_id, title="用药")
    db.add(conversation)
    db.flush()
    message = AgentMessage(
        conversation_id=conversation.id,
        role="user",
        content=content,
    )
    db.add(message)
    db.commit()
    return conversation, message


def _intent(db, user_id: int, name: str, dosage: str):
    conversation, source = _source(db, user_id, f"记录服用{name}{dosage}")
    intent = propose_medication_intake_items(
        db,
        user_id=user_id,
        conversation_id=conversation.id,
        source_message_id=source.id,
        items=[{"medication_name": name, "actual_dosage": dosage}],
        reference_now=datetime(2026, 7, 21, 9, 5, tzinfo=ZoneInfo("Asia/Shanghai")),
    )
    turn_id = f"medication-autocreate-{source.id}"
    source.client_turn_id = turn_id
    db.add(AgentMessage(
        conversation_id=conversation.id,
        role="assistant",
        content="请确认这次用药记录。",
        client_turn_id=turn_id,
        meta={
            "completion_status": "complete",
            "client_turn_finalized": True,
            "pending_write_intent_ids": [intent.id],
            "pending_write_intent_kinds": ["medication_intake_batch"],
            "cards": [
                AgentExecutor(db)._medication_batch_confirmation_card(
                    intent,
                    intent.payload,
                )
            ],
            "write_receipts": [],
        },
    ))
    db.commit()
    return intent


def test_confirmed_intake_autocreates_minimal_medication_definition(
    db, auth_user_and_headers
):
    user, _ = auth_user_and_headers
    intent = _intent(db, user.id, "阿奇霉素", "2粒")

    result = confirm(db, user.id, intent.id)

    medication = db.query(Medication).filter(Medication.user_id == user.id).one()
    assert medication.name == "阿奇霉素"
    assert medication.dosage is None
    assert medication.frequency is None
    assert medication.times_per_day is None
    log = db.query(MedicationLog).filter(MedicationLog.user_id == user.id).one()
    assert log.medication_id == medication.id
    assert log.actual_dosage == "2粒"
    assert len(result["write_receipts"]) == 1


def test_confirmed_intake_reuses_existing_active_definition(
    db, auth_user_and_headers
):
    user, _ = auth_user_and_headers
    existing = Medication(
        user_id=user.id,
        name="二甲双胍",
        dosage="500mg",
        frequency="遵医嘱",
        is_active=True,
    )
    db.add(existing)
    db.commit()
    intent = _intent(db, user.id, "二甲双胍", "1片")

    confirm(db, user.id, intent.id)

    assert db.query(Medication).filter(Medication.user_id == user.id).count() == 1
    log = db.query(MedicationLog).filter(MedicationLog.user_id == user.id).one()
    assert log.medication_id == existing.id
    assert log.actual_dosage == "1片"


@pytest.mark.asyncio
async def test_model_confirmed_flag_never_reaches_legacy_medication_http_path(
    db, auth_user_and_headers
):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    executor._current_user_id = user.id

    async def must_not_call(*args, **kwargs):
        raise AssertionError("legacy medication HTTP path must not authorize model flags")

    executor._api_get_json = must_not_call
    executor._api_post_json = must_not_call
    executor._api_post = must_not_call
    result = await executor._exec_health_record(
        "http://unused",
        {},
        {
            "record_type": "medication",
            "confirmed": True,
            "data": {
                "medication_name": "阿奇霉素",
                "actual_dosage": "2粒",
                "confirmed": True,
            },
        },
    )

    payload = json.loads(result)
    assert payload["status"] == "rejected"
    assert payload["success"] is False
    assert payload["dispatch_started"] is False
    assert payload["error_code"] == "medication_plan_context_missing"
    assert "确认计划未能建立" in payload["message"]
    assert db.query(MedicationLog).filter(MedicationLog.user_id == user.id).count() == 0
