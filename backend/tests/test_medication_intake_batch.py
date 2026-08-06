import uuid
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.orm import Query

from app.models.agent_conversation import AgentConversation, AgentMessage
from app.models.medication import Medication, MedicationLog
from app.models.supplement import SupplementDefinition
from app.models.user import User
from app.models.write_intent import WriteIntent
from app.services import medication_intake_batch as batch
from app.services import write_intent_service
from app.services.medication_service import MedicationService


EXACT_MESSAGE = "记录服用两种胃药：伊托必利 替普瑞酮 各一粒"
FROZEN_NOW = datetime(2026, 7, 21, 18, 32, tzinfo=ZoneInfo("Asia/Shanghai"))


def _user(db, prefix="med_batch") -> User:
    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"{prefix}_{suffix}",
        email=f"{prefix}_{suffix}@example.com",
        hashed_password="x",
        name=prefix,
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _source_message(db, user_id: int, content: str = EXACT_MESSAGE):
    conversation = AgentConversation(user_id=user_id, title="用药记录")
    db.add(conversation)
    db.flush()
    message = AgentMessage(
        conversation_id=conversation.id,
        role="user",
        content=content,
    )
    db.add(message)
    db.commit()
    db.refresh(conversation)
    db.refresh(message)
    return conversation, message


def _propose(db, user_id: int, conversation_id: int, source_message_id: int):
    intent = batch.propose_medication_intake_batch(
        db,
        user_id=user_id,
        conversation_id=conversation_id,
        source_message_id=source_message_id,
        text=EXACT_MESSAGE,
        reference_now=FROZEN_NOW,
    )
    source = db.get(AgentMessage, source_message_id)
    assert source is not None
    _attach_pending_assistant(db, source, intent)
    return intent


def _attach_pending_assistant(db, source: AgentMessage, intent: WriteIntent):
    turn_id = f"medication-batch-turn-{source.id}"
    existing = (
        db.query(AgentMessage)
        .filter(
            AgentMessage.conversation_id == source.conversation_id,
            AgentMessage.role == "assistant",
            AgentMessage.client_turn_id == turn_id,
        )
        .first()
    )
    if existing is not None:
        return existing
    source.client_turn_id = turn_id
    assistant = AgentMessage(
        conversation_id=source.conversation_id,
        role="assistant",
        content="请确认这组用药记录。",
        client_turn_id=turn_id,
        meta={
            "client_turn_id": turn_id,
            "completion_status": "complete",
            "client_turn_finalized": True,
            "pending_write_intent_ids": [intent.id],
            "pending_write_intent_kinds": [batch.WRITE_INTENT_KIND],
            "write_receipts": [],
            "cards": [{
                "type": "medication_draft",
                "data": {
                    "write_intent_id": intent.id,
                    "plan_sha256": intent.payload["plan_sha256"],
                    "items": intent.payload["items"],
                    "taken_at": (
                        f"{intent.payload['taken_date']} "
                        f"{intent.payload['taken_time']}"
                    ),
                },
                "actions": [{
                    "id": f"medication-batch-confirm:{intent.id}",
                    "action": "write_intent.confirm",
                    "label": "确认记录",
                    "endpoint": f"/write-intents/{intent.id}/confirm",
                    "payload": {"write_intent_id": intent.id},
                    "requires_manual_confirm": True,
                }, {
                    "id": f"medication-batch-dismiss:{intent.id}",
                    "action": "write_intent.dismiss",
                    "label": "取消",
                    "endpoint": f"/write-intents/{intent.id}/dismiss",
                    "payload": {"write_intent_id": intent.id},
                    "requires_manual_confirm": True,
                }],
            }],
        },
    )
    db.add(assistant)
    db.commit()
    db.refresh(assistant)
    return assistant


def test_parse_exact_two_medication_sentence_with_shared_dose():
    draft = batch.parse_medication_intake_batch(EXACT_MESSAGE)

    assert draft is not None
    assert draft["items"] == [
        {
            "medication_name": "伊托必利",
            "actual_dosage": "1粒",
            "observed_strength": None,
        },
        {
            "medication_name": "替普瑞酮",
            "actual_dosage": "1粒",
            "observed_strength": None,
        },
    ]


def test_parse_single_explicit_intake_for_same_server_owned_confirmation_path():
    draft = batch.parse_medication_intake_batch("记录服用阿奇霉素两粒")

    assert draft == {
        "items": [
            {
                "medication_name": "阿奇霉素",
                "actual_dosage": "2粒",
                "observed_strength": None,
            }
        ]
    }


def test_parse_single_explicit_intake_with_quantity_before_known_medication():
    draft = batch.parse_medication_intake_batch("记录我吃了两粒阿奇霉素")

    assert draft == {
        "items": [
            {
                "medication_name": "阿奇霉素",
                "actual_dosage": "2粒",
                "observed_strength": None,
            }
        ]
    }


def test_tool_proposal_rejects_unknown_medication_name_before_write_intent(db):
    user = _user(db, "unknown_tool_medication")
    conversation, source = _source_message(
        db,
        user.id,
        content="记录我吃了两粒咔咔霉素",
    )

    with pytest.raises(
        batch.InvalidMedicationIntakePlan,
        match="controlled medication name",
    ):
        batch.propose_medication_intake_items(
            db,
            user_id=user.id,
            conversation_id=conversation.id,
            source_message_id=source.id,
            items=[{
                "medication_name": "咔咔霉素",
                "actual_dosage": "2粒",
            }],
            reference_now=FROZEN_NOW,
        )

    assert db.query(WriteIntent).filter(WriteIntent.user_id == user.id).count() == 0


def test_tool_proposal_allows_an_existing_user_medication_name(db):
    user = _user(db, "known_user_medication")
    db.add(Medication(
        user_id=user.id,
        name="医生登记的临时药甲",
        is_active=True,
    ))
    db.commit()
    conversation, source = _source_message(
        db,
        user.id,
        content="记录服用医生登记的临时药甲一粒",
    )

    intent = batch.propose_medication_intake_items(
        db,
        user_id=user.id,
        conversation_id=conversation.id,
        source_message_id=source.id,
        items=[{
            "medication_name": "医生登记的临时药甲",
            "actual_dosage": "1粒",
        }],
        reference_now=FROZEN_NOW,
    )

    assert intent.payload["items"][0]["medication_name"] == "医生登记的临时药甲"


def test_parse_keeps_strength_separate_from_actual_quantity():
    draft = batch.parse_medication_intake_batch(
        "记录服用奥美拉唑20mg一粒、替普瑞酮两粒"
    )

    assert draft is not None
    assert draft["items"] == [
        {
            "medication_name": "奥美拉唑",
            "actual_dosage": "1粒",
            "observed_strength": "20mg",
        },
        {
            "medication_name": "替普瑞酮",
            "actual_dosage": "2粒",
            "observed_strength": None,
        },
    ]


def test_parse_deduplicates_generic_and_brand_alias_for_same_medication():
    draft = batch.parse_medication_intake_batch(
        "记录服用替普瑞酮（施维舒）一粒、伊托必利一粒"
    )

    assert draft is not None
    assert [item["medication_name"] for item in draft["items"]] == [
        "替普瑞酮",
        "伊托必利",
    ]


@pytest.mark.parametrize(
    "text",
    [
        "两个胃药各一粒",
        "我是不是服用了伊托必利和替普瑞酮各一粒？",
        "不要记录伊托必利和替普瑞酮各一粒",
        "没吃伊托必利，只吃了替普瑞酮一粒",
        "记录伊托必利和伊托必利各一粒",
        "记录服用两种胃药：伊托必利 各一粒",
        "记录昨天服用伊托必利一粒",
        "记录早上服用伊托必利一粒",
        "记录昨晚八点服用伊托必利一粒",
        "记录服用伊托必利，并喝水300ml",
        "记录服用伊托必利，早餐吃了2片面包",
        "记录服用伊托必利一粒和自制药丸两粒",
        "记录刚服用胰岛素10单位和二甲双胍1片",
        "记录服用阿奇霉素0粒",
        "记录我吃了两粒阿奇霉素一粒",
        f"记录服用阿奇霉素{'1' * 100}粒",
    ],
)
def test_parse_ambiguous_or_negated_inputs_fail_closed(text):
    assert batch.parse_medication_intake_batch(text) is None


def test_parse_accepts_positive_insulin_units_when_name_is_known():
    assert batch.parse_medication_intake_batch(
        "记录服用胰岛素10单位",
        known_names=["胰岛素"],
    ) == {
        "items": [{
            "medication_name": "胰岛素",
            "actual_dosage": "10单位",
            "observed_strength": None,
        }]
    }


def test_compound_name_is_not_collapsed_to_one_contained_single_drug():
    compound = "氨氯地平贝那普利片"

    assert batch._canonical_name(compound) == compound


def test_proposal_is_owner_source_bound_and_idempotent(db):
    user = _user(db)
    conversation, source = _source_message(db, user.id)

    first = _propose(db, user.id, conversation.id, source.id)
    second = _propose(db, user.id, conversation.id, source.id)

    assert first.id == second.id
    assert first.user_id == user.id
    assert first.kind == batch.WRITE_INTENT_KIND
    assert first.status == "pending"
    assert first.trust_tier == "manual_confirm"
    assert first.target_type == "agent_message"
    assert first.target_id == source.id
    assert first.title == "2项用药记录待确认"
    assert "伊托必利" not in first.title
    assert "替普瑞酮" not in (first.description or "")
    assert first.payload["conversation_id"] == conversation.id
    assert first.payload["source_message_id"] == source.id
    assert first.payload["taken_date"] == "2026-07-21"
    assert first.payload["taken_time"] == "18:32"
    assert first.payload["timezone"] == "Asia/Shanghai"
    assert len(first.payload["plan_sha256"]) == 64
    assert write_intent_service.list_pending(db, user.id) == []
    assert (
        db.query(WriteIntent)
        .filter(WriteIntent.kind == batch.WRITE_INTENT_KIND)
        .count()
        == 1
    )


def test_retry_reuses_first_frozen_timestamp_when_reference_time_advances(db):
    user = _user(db)
    conversation, source = _source_message(db, user.id)

    first = _propose(db, user.id, conversation.id, source.id)
    second = batch.propose_medication_intake_batch(
        db,
        user_id=user.id,
        conversation_id=conversation.id,
        source_message_id=source.id,
        text=EXACT_MESSAGE,
        reference_now=FROZEN_NOW + timedelta(minutes=3),
    )

    assert second.id == first.id
    assert second.payload == first.payload
    assert second.payload["taken_time"] == "18:32"


def test_aware_reference_time_is_converted_to_owner_timezone(db, monkeypatch):
    user = _user(db)
    conversation, source = _source_message(db, user.id)
    monkeypatch.setattr(
        batch,
        "get_user_timezone",
        lambda *args, **kwargs: ZoneInfo("Asia/Shanghai"),
    )

    intent = batch.propose_medication_intake_batch(
        db,
        user_id=user.id,
        conversation_id=conversation.id,
        source_message_id=source.id,
        text=EXACT_MESSAGE,
        reference_now=datetime(2026, 7, 21, 10, 32, tzinfo=ZoneInfo("UTC")),
    )

    assert intent.payload["taken_date"] == "2026-07-21"
    assert intent.payload["taken_time"] == "18:32"
    assert intent.payload["timezone"] == "Asia/Shanghai"


def test_pending_plan_expires_without_writing_but_executed_replay_survives_ttl(
    db, monkeypatch
):
    issued_at = datetime(2026, 7, 21, 10, 0, tzinfo=UTC)
    monkeypatch.setattr(batch, "_utc_now", lambda: issued_at)
    user = _user(db)
    conversation, source = _source_message(db, user.id)
    intent = _propose(db, user.id, conversation.id, source.id)

    monkeypatch.setattr(batch, "_utc_now", lambda: issued_at + timedelta(minutes=31))
    with pytest.raises(batch.ExpiredMedicationIntakePlan):
        write_intent_service.confirm(db, user.id, intent.id)

    db.expire_all()
    expired_intent = db.get(WriteIntent, intent.id)
    assert expired_intent.status == "dismissed"
    assert expired_intent.decision_status == "expired"
    assert db.query(MedicationLog).filter(MedicationLog.user_id == user.id).count() == 0
    expired_replay = write_intent_service.confirm(db, user.id, intent.id)
    assert expired_replay["status"] == "dismissed"
    assert expired_replay["decision_status"] == "expired"

    fresh_conversation, fresh_source = _source_message(
        db,
        user.id,
        "记录服用阿奇霉素两粒",
    )
    monkeypatch.setattr(batch, "_utc_now", lambda: issued_at)
    fresh = batch.propose_medication_intake_batch(
        db,
        user_id=user.id,
        conversation_id=fresh_conversation.id,
        source_message_id=fresh_source.id,
        text=fresh_source.content,
        reference_now=FROZEN_NOW,
    )
    _attach_pending_assistant(db, fresh_source, fresh)
    first = write_intent_service.confirm(db, user.id, fresh.id)
    monkeypatch.setattr(batch, "_utc_now", lambda: issued_at + timedelta(days=2))
    replay = write_intent_service.confirm(db, user.id, fresh.id)

    assert replay["idempotent"] is True
    assert replay["write_receipts"] == first["write_receipts"]


def test_confirm_atomically_creates_two_logs_and_returns_stable_item_receipts(db):
    user = _user(db)
    conversation, source = _source_message(db, user.id)
    intent = _propose(db, user.id, conversation.id, source.id)

    result = write_intent_service.confirm(db, user.id, intent.id)

    assert result["status"] == "executed"
    assert result["idempotent"] is False
    assert result["executed_ref"].startswith("medication_logs:")
    assert len(result["write_receipts"]) == 2
    assert [receipt["resource_type"] for receipt in result["write_receipts"]] == [
        "medication_log",
        "medication_log",
    ]
    assert all(receipt["verified"] is True for receipt in result["write_receipts"])

    medications = (
        db.query(Medication)
        .filter(Medication.user_id == user.id)
        .order_by(Medication.name.asc())
        .all()
    )
    assert {medication.name for medication in medications} == {"伊托必利", "替普瑞酮"}
    assert all(medication.dosage is None for medication in medications)
    assert all(medication.frequency is None for medication in medications)
    assert all(medication.times_per_day is None for medication in medications)
    assert all(medication.is_active is False for medication in medications)
    # Defensive read contract: even if an unknown-schedule definition is later
    # activated elsewhere, it contributes no invented expected doses and never
    # crashes the adherence/Twin path.
    medications[0].is_active = True
    db.commit()
    adherence = MedicationService().get_adherence_stats(db, user.id, days=7)
    assert adherence["total_expected"] == 0

    logs = (
        db.query(MedicationLog)
        .filter(MedicationLog.user_id == user.id)
        .order_by(MedicationLog.id.asc())
        .all()
    )
    assert len(logs) == 2
    assert [log.actual_dosage for log in logs] == ["1粒", "1粒"]
    assert all(str(log.taken_date) == "2026-07-21" for log in logs)
    assert all(log.taken_time == "18:32" for log in logs)
    assert all(log.status == "taken" for log in logs)

    repeated = write_intent_service.confirm(db, user.id, intent.id)
    assert repeated["idempotent"] is True
    assert repeated["write_receipts"] == result["write_receipts"]
    assert db.query(MedicationLog).filter(MedicationLog.user_id == user.id).count() == 2


def test_receipts_are_materialized_before_commit_and_failure_rolls_back(
    db, monkeypatch
):
    user = _user(db)
    conversation, source = _source_message(db, user.id)
    intent = _propose(db, user.id, conversation.id, source.id)
    original_receipts = batch.write_receipts_for_intent
    committed = False
    original_commit = db.commit

    def tracked_commit():
        nonlocal committed
        committed = True
        return original_commit()

    def receipts_before_commit(session, write_intent):
        assert committed is False
        return original_receipts(session, write_intent)

    monkeypatch.setattr(db, "commit", tracked_commit)
    monkeypatch.setattr(batch, "write_receipts_for_intent", receipts_before_commit)

    result = write_intent_service.confirm(db, user.id, intent.id)

    assert len(result["write_receipts"]) == 2
    assert committed is True

    second_user = _user(db, "receipt_failure")
    second_conversation, second_source = _source_message(db, second_user.id)
    second_intent = _propose(
        db,
        second_user.id,
        second_conversation.id,
        second_source.id,
    )

    def fail_receipts(*args, **kwargs):
        raise RuntimeError("injected receipt materialization failure")

    monkeypatch.setattr(batch, "write_receipts_for_intent", fail_receipts)
    with pytest.raises(RuntimeError, match="receipt materialization"):
        write_intent_service.confirm(db, second_user.id, second_intent.id)

    db.expire_all()
    assert db.get(WriteIntent, second_intent.id).status == "pending"
    assert (
        db.query(MedicationLog)
        .filter(MedicationLog.user_id == second_user.id)
        .count()
        == 0
    )


def test_confirm_returns_shared_safety_result_for_first_execution_and_replay(
    db, monkeypatch
):
    user = _user(db)
    conversation, source = _source_message(db, user.id)
    intent = _propose(db, user.id, conversation.id, source.id)
    advisory = [{
        "rule_id": "medication.safety_precheck_incomplete",
        "category": "ddi",
        "severity": 3,
        "title": "用药安全预检未完成",
        "message": "这不代表安全",
        "action": "请咨询医生或药师",
    }]

    evaluations = 0

    def changing_safety_result(session, user_id, **kwargs):
        nonlocal evaluations
        evaluations += 1
        if evaluations == 1:
            return advisory
        return [{
            "rule_id": "changed.after.execution",
            "category": "ddi",
            "severity": 4,
            "title": "不应覆盖历史确认结果",
            "message": "current state changed",
            "action": "ignore for idempotent replay",
        }]

    monkeypatch.setattr(
        "app.services.medication_safety.evaluate_medication_safety_alerts",
        changing_safety_result,
    )

    first = write_intent_service.confirm(db, user.id, intent.id)
    replay = write_intent_service.confirm(db, user.id, intent.id)

    assert first["safety_alerts"] == advisory
    assert replay["safety_alerts"] == advisory
    assert evaluations == 1


def test_confirm_and_idempotent_replay_invalidate_twin_and_pregen(db, monkeypatch):
    user = _user(db, "invalidation")
    conversation, source = _source_message(db, user.id)
    intent = _propose(db, user.id, conversation.id, source.id)
    invalidated: list[int] = []
    monkeypatch.setattr(
        "app.twin.cache.invalidate_twin",
        lambda user_id: invalidated.append(user_id),
    )

    first = write_intent_service.confirm(db, user.id, intent.id)
    replay = write_intent_service.confirm(db, user.id, intent.id)

    assert first["status"] == replay["status"] == "executed"
    assert invalidated == [user.id, user.id]


def test_display_generic_alias_reuses_existing_active_medication(db):
    user = _user(db, "generic_alias")
    conversation, source = _source_message(
        db,
        user.id,
        content="记录服用伊托必利一粒",
    )
    existing = Medication(
        user_id=user.id,
        name="盐酸伊托必利",
        dosage=None,
        frequency="每日三次",
        times_per_day=3,
        start_date=FROZEN_NOW.date(),
        is_active=True,
    )
    db.add(existing)
    db.commit()
    db.refresh(existing)
    intent = batch.propose_medication_intake_items(
        db,
        user_id=user.id,
        conversation_id=conversation.id,
        source_message_id=source.id,
        items=[{
            "medication_name": "伊托必利",
            "actual_dosage": "1粒",
        }],
        reference_now=FROZEN_NOW,
    )
    _attach_pending_assistant(db, source, intent)

    result = write_intent_service.confirm(db, user.id, intent.id)

    medications = db.query(Medication).filter(Medication.user_id == user.id).all()
    assert [medication.id for medication in medications] == [existing.id]
    log = db.query(MedicationLog).filter(MedicationLog.user_id == user.id).one()
    assert log.medication_id == existing.id
    assert int(result["write_receipts"][0]["resource_id"]) == log.id


def test_confirm_atomically_projects_terminal_batch_to_source_assistant_meta(
    db, monkeypatch
):
    user = _user(db, "terminal_projection")
    conversation, source = _source_message(db, user.id)
    intent = _propose(db, user.id, conversation.id, source.id)
    assistant = _attach_pending_assistant(db, source, intent)
    assistant.meta = {
        **assistant.meta,
        "pending_write_intent_ids": [intent.id, 999],
        "pending_write_intent_kinds": [batch.WRITE_INTENT_KIND, "other_kind"],
    }
    db.commit()
    advisory = [{
        "rule_id": "medication.safety_precheck_incomplete",
        "category": "ddi",
        "severity": 3,
        "title": "用药安全预检未完成",
        "message": "这不代表安全",
        "action": "请咨询医生或药师",
    }]
    monkeypatch.setattr(
        "app.services.medication_safety.evaluate_medication_safety_alerts",
        lambda session, user_id, **kwargs: advisory,
    )

    result = write_intent_service.confirm(db, user.id, intent.id)

    db.refresh(assistant)
    assert assistant.meta["pending_write_intent_ids"] == [999]
    assert assistant.meta["pending_write_intent_kinds"] == ["other_kind"]
    decision = assistant.meta["medication_batch_decision"]
    assert decision["intent_id"] == intent.id
    assert decision["status"] == "executed"
    assert decision["write_receipts"] == result["write_receipts"]
    assert decision["safety_alerts"] == advisory
    assert assistant.meta["write_receipts"] == result["write_receipts"]
    assert assistant.meta["safety_alerts"] == advisory
    card = assistant.meta["cards"][0]
    assert card["data"]["decision_status"] == "executed"
    assert card["data"]["write_receipts"] == result["write_receipts"]
    assert card["data"]["safety_alerts"] == advisory
    assert card["actions"] == []


def test_terminal_projection_preserves_other_turn_receipts_and_namespaces_batch_result(
    db, monkeypatch
):
    """Confirming a medication plan must not erase an earlier same-turn write."""
    user = _user(db, "mixed_turn_projection")
    conversation, source = _source_message(db, user.id)
    intent = _propose(db, user.id, conversation.id, source.id)
    assistant = _attach_pending_assistant(db, source, intent)
    unrelated_receipt = {
        "operation_id": "health_record:water:77",
        "status": "verified",
        "resource_type": "water_record",
        "resource_id": "77",
        "completed_at": "2026-07-21T10:32:00+00:00",
        "verified": True,
    }
    unrelated_alert = {
        "rule_id": "other.turn.advisory",
        "category": "vitals",
        "severity": 2,
        "title": "同轮既有提醒",
        "message": "必须保留",
    }
    meta = dict(assistant.meta)
    meta["write_receipts"] = [unrelated_receipt]
    meta["safety_alerts"] = [unrelated_alert]
    assistant.meta = meta
    db.commit()
    medication_alert = {
        "rule_id": "medication.batch.advisory",
        "category": "ddi",
        "severity": 3,
        "title": "本批用药提醒",
        "message": "批次结果",
    }
    monkeypatch.setattr(
        "app.services.medication_safety.evaluate_medication_safety_alerts",
        lambda session, user_id, **kwargs: [medication_alert],
    )

    result = write_intent_service.confirm(db, user.id, intent.id)

    db.refresh(assistant)
    medication_receipts = result["write_receipts"]
    assert assistant.meta["write_receipts"] == [
        unrelated_receipt,
        *medication_receipts,
    ]
    assert assistant.meta["safety_alerts"] == [
        unrelated_alert,
        medication_alert,
    ]
    decision = assistant.meta["medication_batch_decision"]
    assert decision["write_receipts"] == medication_receipts
    assert decision["safety_alerts"] == [medication_alert]
    card = assistant.meta["cards"][0]
    assert card["data"]["write_receipts"] == medication_receipts
    assert card["data"]["safety_alerts"] == [medication_alert]

    replay = write_intent_service.confirm(db, user.id, intent.id)
    db.refresh(assistant)
    assert replay["write_receipts"] == medication_receipts
    assert replay["safety_alerts"] == [medication_alert]
    assert assistant.meta["write_receipts"] == [
        unrelated_receipt,
        *medication_receipts,
    ]


@pytest.mark.parametrize(
    "damage",
    ["only_dismiss", "changed_dose", "changed_time", "changed_hash"],
)
def test_confirm_rejects_incomplete_or_changed_presented_plan(db, damage):
    user = _user(db, f"presentation_{damage}")
    conversation, source = _source_message(db, user.id)
    intent = _propose(db, user.id, conversation.id, source.id)
    assistant = _attach_pending_assistant(db, source, intent)
    meta = dict(assistant.meta)
    cards = [dict(card) for card in meta["cards"]]
    card = cards[0]
    card["data"] = dict(card["data"])
    card["actions"] = [dict(action) for action in card["actions"]]
    if damage == "only_dismiss":
        card["actions"] = [
            action
            for action in card["actions"]
            if action.get("action") == "write_intent.dismiss"
        ]
    elif damage == "changed_dose":
        card["data"]["items"] = [dict(item) for item in card["data"]["items"]]
        card["data"]["items"][0]["actual_dosage"] = "9粒"
    elif damage == "changed_time":
        card["data"]["taken_at"] = "2099-01-01 00:00"
    else:
        card["data"]["plan_sha256"] = "tampered"
    meta["cards"] = cards
    assistant.meta = meta
    db.commit()

    with pytest.raises(batch.MedicationIntakePlanNotPresented):
        write_intent_service.confirm(db, user.id, intent.id)

    db.rollback()
    db.expire_all()
    assert db.get(WriteIntent, intent.id).status == "pending"
    assert db.query(MedicationLog).filter(MedicationLog.user_id == user.id).count() == 0


def test_safety_collector_failure_cannot_rollback_confirmed_batch(
    db, monkeypatch
):
    """A failed safety read must not roll back flushed health facts invisibly.

    The legacy Twin collectors call ``Session.rollback()`` when a query fails.
    Medication batch confirmation evaluates safety before its outer commit, so
    that rollback used to erase the claim, definitions, and logs while the API
    still returned ``status=executed`` with verified-looking receipts.
    """
    user = _user(db, "collector_failure")
    conversation, source = _source_message(db, user.id)
    intent = _propose(db, user.id, conversation.id, source.id)
    original_all = Query.all

    def fail_supplement_partition(query):
        entities = {
            descriptor.get("entity")
            for descriptor in query.column_descriptions
        }
        if SupplementDefinition in entities:
            raise RuntimeError("injected safety collector query failure")
        return original_all(query)

    monkeypatch.setattr(Query, "all", fail_supplement_partition)

    result = write_intent_service.confirm(db, user.id, intent.id)

    assert result["status"] == "executed"
    assert len(result["write_receipts"]) == 2
    assert "medication.safety_precheck_incomplete" in {
        alert["rule_id"] for alert in result["safety_alerts"]
    }
    db.expire_all()
    executed_intent = db.get(WriteIntent, intent.id)
    assert executed_intent.status == "executed"
    assert executed_intent.decision_status == "executed"
    assert (
        db.query(MedicationLog)
        .filter(MedicationLog.user_id == user.id)
        .count()
        == 2
    )


def test_confirmation_after_local_midnight_still_screens_frozen_exposure(
    db, monkeypatch
):
    """The exact batch exposure must be screened even after the local day rolls."""
    user = _user(db, "midnight_safety")
    db.add(Medication(
        user_id=user.id,
        name="华法林",
        frequency="每日1次",
        times_per_day=1,
        start_date=date(2026, 7, 1),
        is_active=True,
    ))
    db.add(Medication(
        user_id=user.id,
        name="布洛芬",
        start_date=date(2026, 7, 1),
        is_active=False,
    ))
    db.commit()
    conversation, source = _source_message(
        db,
        user.id,
        "记录服用布洛芬一粒",
    )
    intent = batch.propose_medication_intake_batch(
        db,
        user_id=user.id,
        conversation_id=conversation.id,
        source_message_id=source.id,
        text=source.content,
        reference_now=datetime(
            2026, 7, 21, 23, 59, tzinfo=ZoneInfo("Asia/Shanghai")
        ),
    )
    _attach_pending_assistant(db, source, intent)
    monkeypatch.setattr(
        "app.services.medication_safety.get_user_today",
        lambda session, user_id: date(2026, 7, 22),
    )

    result = write_intent_service.confirm(db, user.id, intent.id)

    assert "ddi.warfarin_bleeding" in {
        alert["rule_id"] for alert in result["safety_alerts"]
    }


def test_plan_expiry_is_rechecked_after_owner_lock_before_any_log(db, monkeypatch):
    issued_at = datetime(2026, 7, 21, 10, 0, tzinfo=UTC)
    monkeypatch.setattr(batch, "_utc_now", lambda: issued_at)
    user = _user(db, "expiry_after_lock")
    conversation, source = _source_message(db, user.id)
    intent = _propose(db, user.id, conversation.id, source.id)
    observed_times = iter([
        issued_at + timedelta(minutes=29),
        issued_at + timedelta(minutes=31),
    ])
    monkeypatch.setattr(batch, "_utc_now", lambda: next(observed_times))

    with pytest.raises(batch.ExpiredMedicationIntakePlan):
        write_intent_service.confirm(db, user.id, intent.id)

    db.expire_all()
    expired_intent = db.get(WriteIntent, intent.id)
    assert expired_intent.status == "dismissed"
    assert expired_intent.decision_status == "expired"
    assert db.query(MedicationLog).filter(MedicationLog.user_id == user.id).count() == 0


def test_receipt_replay_rejects_missing_or_malformed_item_ids(db):
    user = _user(db)
    conversation, source = _source_message(db, user.id)
    intent = _propose(db, user.id, conversation.id, source.id)
    result = write_intent_service.confirm(db, user.id, intent.id)
    first_id = result["write_receipts"][0]["resource_id"]

    intent.executed_ref = f"medication_logs:{first_id}"
    db.commit()
    with pytest.raises(batch.InvalidMedicationIntakePlan, match="incomplete"):
        batch.write_receipts_for_intent(db, intent)

    intent.executed_ref = f"medication_logs:{first_id},"
    db.commit()
    with pytest.raises(batch.InvalidMedicationIntakePlan, match="invalid"):
        batch.write_receipts_for_intent(db, intent)


def test_single_item_plan_uses_same_manual_confirmation_and_receipt_contract(db):
    user = _user(db)
    conversation, source = _source_message(db, user.id, "记录服用阿奇霉素两粒")
    intent = batch.propose_medication_intake_batch(
        db,
        user_id=user.id,
        conversation_id=conversation.id,
        source_message_id=source.id,
        text=source.content,
        reference_now=FROZEN_NOW,
    )
    _attach_pending_assistant(db, source, intent)

    result = write_intent_service.confirm(db, user.id, intent.id)

    assert len(result["write_receipts"]) == 1
    log = db.query(MedicationLog).filter(MedicationLog.user_id == user.id).one()
    assert log.actual_dosage == "2粒"


def test_strength_is_frozen_and_does_not_attach_to_different_strength_definition(db):
    user = _user(db)
    existing = Medication(
        user_id=user.id,
        name="奥美拉唑",
        dosage="40mg",
        times_per_day=1,
        is_active=True,
    )
    db.add(existing)
    db.commit()
    conversation, source = _source_message(
        db,
        user.id,
        "记录服用奥美拉唑20mg一粒",
    )
    intent = batch.propose_medication_intake_batch(
        db,
        user_id=user.id,
        conversation_id=conversation.id,
        source_message_id=source.id,
        text=source.content,
        reference_now=FROZEN_NOW,
    )
    _attach_pending_assistant(db, source, intent)

    assert intent.payload["items"][0]["observed_strength"] == "20mg"
    result = write_intent_service.confirm(db, user.id, intent.id)

    assert len(result["write_receipts"]) == 1
    log = db.query(MedicationLog).filter(MedicationLog.user_id == user.id).one()
    assert log.medication_id != existing.id
    assert log.medication.dosage == "20mg"
    assert log.medication.is_active is False


def test_published_tool_plan_is_immutable_and_cannot_gain_an_unpreviewed_item(db):
    user = _user(db)
    conversation, source = _source_message(
        db,
        user.id,
        "帮我记录刚才吃的两种药",
    )
    first = batch.propose_medication_intake_items(
        db,
        user_id=user.id,
        conversation_id=conversation.id,
        source_message_id=source.id,
        items=[{"medication_name": "伊托必利", "actual_dosage": "1粒"}],
        reference_now=FROZEN_NOW,
        allow_merge_pending=True,
    )
    with pytest.raises(batch.InvalidMedicationIntakePlan, match="different"):
        batch.propose_medication_intake_items(
            db,
            user_id=user.id,
            conversation_id=conversation.id,
            source_message_id=source.id,
            items=[{"medication_name": "替普瑞酮", "actual_dosage": "1粒"}],
            reference_now=FROZEN_NOW,
            allow_merge_pending=True,
        )

    db.refresh(first)
    assert [item["medication_name"] for item in first.payload["items"]] == ["伊托必利"]
    assert db.query(WriteIntent).filter(WriteIntent.user_id == user.id).count() == 1


def test_second_item_failure_rolls_back_medications_logs_and_claim(
    db, monkeypatch
):
    user = _user(db)
    conversation, source = _source_message(db, user.id)
    intent = _propose(db, user.id, conversation.id, source.id)
    original_insert = batch._insert_medication_log
    calls = 0

    def fail_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("injected second item failure")
        return original_insert(*args, **kwargs)

    monkeypatch.setattr(batch, "_insert_medication_log", fail_second)

    with pytest.raises(RuntimeError, match="second item failure"):
        write_intent_service.confirm(db, user.id, intent.id)

    db.expire_all()
    assert db.get(WriteIntent, intent.id).status == "pending"
    assert db.query(Medication).filter(Medication.user_id == user.id).count() == 0
    assert db.query(MedicationLog).filter(MedicationLog.user_id == user.id).count() == 0


def test_tampered_plan_hash_fails_without_any_medication_write(db):
    user = _user(db)
    conversation, source = _source_message(db, user.id)
    intent = _propose(db, user.id, conversation.id, source.id)
    payload = dict(intent.payload)
    items = [dict(item) for item in payload["items"]]
    items[0]["actual_dosage"] = "9粒"
    payload["items"] = items
    intent.payload = payload
    db.commit()

    with pytest.raises(batch.InvalidMedicationIntakePlan, match="hash"):
        write_intent_service.confirm(db, user.id, intent.id)

    db.expire_all()
    assert db.get(WriteIntent, intent.id).status == "pending"
    assert db.query(MedicationLog).filter(MedicationLog.user_id == user.id).count() == 0


def test_other_user_cannot_confirm_batch(db):
    owner = _user(db, "owner")
    attacker = _user(db, "attacker")
    conversation, source = _source_message(db, owner.id)
    intent = _propose(db, owner.id, conversation.id, source.id)

    with pytest.raises(LookupError):
        write_intent_service.confirm(db, attacker.id, intent.id)

    assert db.query(MedicationLog).count() == 0
    db.refresh(intent)
    assert intent.status == "pending"
