import json
from datetime import UTC, datetime, timedelta

import pytest

from app.models.agent_conversation import AgentMessage
from app.models.medication import MedicationLog
from app.models.write_intent import WriteIntent
from app.services.agent_executor import AgentExecutor
from app.services.medication_intake_batch import WRITE_INTENT_KIND


EXACT_MESSAGE = "记录服用两种胃药：伊托必利 替普瑞酮 各一粒"


def _tokens(events):
    return "".join(
        event.get("data", {}).get("content", "")
        for event in events
        if event.get("event") == "token"
    )


def _done(events):
    return next(event["data"] for event in events if event.get("event") == "done")


async def _run(executor, user_id, message, **kwargs):
    return [
        event
        async for event in executor.run_stream(
            user_id=user_id,
            message=message,
            user_auth_token="test-token",
            **kwargs,
        )
    ]


def _forbid_llm(executor, monkeypatch):
    async def must_not_stream(*args, **kwargs):
        raise AssertionError("deterministic medication confirmation must not call an LLM")
        yield  # pragma: no cover

    async def must_not_call(*args, **kwargs):
        raise AssertionError("deterministic medication confirmation must not call an LLM")

    monkeypatch.setattr(executor, "_call_llm_stream", must_not_stream)
    monkeypatch.setattr(executor, "_call_llm", must_not_call)


@pytest.mark.asyncio
async def test_exact_batch_proposes_once_before_llm_and_writes_nothing(
    db, auth_user_and_headers, monkeypatch
):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _forbid_llm(executor, monkeypatch)

    events = await _run(
        executor,
        user.id,
        EXACT_MESSAGE,
        client_turn_id="med-batch-proposal-1",
        extra_context=json.dumps({"multi_model": True}),
    )

    persisted_index = next(
        index for index, event in enumerate(events)
        if event.get("event") == "request_persisted"
    )
    token_index = next(
        index for index, event in enumerate(events)
        if event.get("event") == "token"
    )
    assert persisted_index < token_index
    assert db.query(MedicationLog).filter(MedicationLog.user_id == user.id).count() == 0
    intents = db.query(WriteIntent).filter(WriteIntent.user_id == user.id).all()
    assert len(intents) == 1
    assert intents[0].kind == WRITE_INTENT_KIND
    assert intents[0].status == "pending"

    reply = _tokens(events)
    assert "伊托必利" in reply
    assert "替普瑞酮" in reply
    assert reply.count("1粒") == 2
    assert "未确认" in reply
    done = _done(events)
    assert done["llm_rounds"] == 0
    assert done["tools_used"] == []
    assert done["write_receipts"] == []
    assert done["pending_write_intent_ids"] == [intents[0].id]
    assert done["pending_write_intent_kinds"] == [WRITE_INTENT_KIND]
    assert done["turn_outcome"]["category"] == "confirmation_required"
    assert done["record_intent_no_tool"] is False
    card = next(card for card in done["cards"] if card["type"] == "medication_draft")
    assert card["data"]["items"] == intents[0].payload["items"]
    assert card["data"]["taken_at"] == (
        f"{intents[0].payload['taken_date']} {intents[0].payload['taken_time']}"
    )
    assert {action["action"] for action in card["actions"]} == {
        "write_intent.confirm",
        "write_intent.dismiss",
    }
    assert all(action["requires_manual_confirm"] is True for action in card["actions"])
    assert all(action["payload"] == {"write_intent_id": intents[0].id} for action in card["actions"])

    assistant = (
        db.query(AgentMessage)
        .filter(AgentMessage.id == done["message_id"])
        .one()
    )
    assert assistant.meta["pending_write_intent_ids"] == [intents[0].id]
    assert assistant.meta["client_turn_finalized"] is True


@pytest.mark.asyncio
async def test_actionable_medication_card_is_not_streamed_before_assistant_is_durable(
    db, auth_user_and_headers, monkeypatch
):
    """A fast client must never be able to click an authorization not yet shown durably."""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _forbid_llm(executor, monkeypatch)

    saw_card = False
    conversation_id = None
    async for event in executor.run_stream(
        user_id=user.id,
        message=EXACT_MESSAGE,
        user_auth_token="test-token",
        client_turn_id="med-batch-durable-before-card",
    ):
        if event.get("event") == "request_persisted":
            conversation_id = (event.get("data") or {}).get("conversation_id")
        if event.get("event") != "card":
            continue
        descriptor = (event.get("data") or {}).get("descriptor") or {}
        if descriptor.get("type") != "medication_draft":
            continue
        saw_card = True
        assistant = (
            db.query(AgentMessage)
            .filter(
                AgentMessage.role == "assistant",
                AgentMessage.conversation_id == conversation_id,
            )
            .order_by(AgentMessage.id.desc())
            .one()
        )
        assert assistant.meta["completion_status"] == "complete"
        assert assistant.meta["client_turn_finalized"] is True
        assert any(
            card.get("type") == "medication_draft"
            for card in assistant.meta.get("cards") or []
        )

    assert saw_card is True


@pytest.mark.asyncio
async def test_immediate_explicit_confirmation_atomically_writes_two_receipts(
    db, auth_user_and_headers, monkeypatch
):
    user, _ = auth_user_and_headers
    first_executor = AgentExecutor(db)
    _forbid_llm(first_executor, monkeypatch)
    first = await _run(
        first_executor,
        user.id,
        EXACT_MESSAGE,
        client_turn_id="med-batch-proposal-2",
    )
    conversation_id = _done(first)["conversation_id"]

    confirm_executor = AgentExecutor(db)
    _forbid_llm(confirm_executor, monkeypatch)
    confirmed = await _run(
        confirm_executor,
        user.id,
        "确认",
        conversation_id=conversation_id,
        client_turn_id="med-batch-confirm-2",
        extra_context=json.dumps({"multi_model": True}),
    )

    reply = _tokens(confirmed)
    assert "已记录" in reply
    assert "共2条" in reply
    done = _done(confirmed)
    assert done["llm_rounds"] == 0
    assert done["pending_write_intent_ids"] == []
    assert len(done["write_receipts"]) == 2
    assert all(receipt["verified"] is True for receipt in done["write_receipts"])
    assert done["turn_outcome"]["reason_code"] == "verified_write"
    assert db.query(MedicationLog).filter(MedicationLog.user_id == user.id).count() == 2

    # Same durable client turn replays the receipts and never executes again.
    replay_executor = AgentExecutor(db)
    _forbid_llm(replay_executor, monkeypatch)
    replay = await _run(
        replay_executor,
        user.id,
        "确认",
        conversation_id=conversation_id,
        client_turn_id="med-batch-confirm-2",
    )
    assert _done(replay)["replayed"] is True
    assert _done(replay)["write_receipts"] == done["write_receipts"]
    assert db.query(MedicationLog).filter(MedicationLog.user_id == user.id).count() == 2


@pytest.mark.asyncio
async def test_confirm_commit_crash_replays_projected_receipts_without_llm_or_duplicate(
    db, auth_user_and_headers, monkeypatch
):
    from app.services import write_intent_service
    from app.services.agent_conversation_service import AgentConversationService

    user, _ = auth_user_and_headers
    proposal_executor = AgentExecutor(db)
    _forbid_llm(proposal_executor, monkeypatch)
    proposal = await _run(
        proposal_executor,
        user.id,
        EXACT_MESSAGE,
        client_turn_id="med-batch-crash-proposal",
    )
    proposal_done = _done(proposal)
    intent = db.query(WriteIntent).filter(WriteIntent.user_id == user.id).one()
    svc = AgentConversationService(db)
    confirm_user_message, created = svc.save_user_message_once(
        proposal_done["conversation_id"],
        user.id,
        "确认",
        client_turn_id="med-batch-crash-confirm",
        meta={"client_turn_id": "med-batch-crash-confirm"},
    )
    assert created is True
    committed = write_intent_service.confirm(db, user.id, intent.id)
    assert len(committed["write_receipts"]) == 2
    assert (
        db.query(AgentMessage)
        .filter(
            AgentMessage.role == "assistant",
            AgentMessage.id > confirm_user_message.id,
        )
        .count()
        == 0
    )

    recovery_executor = AgentExecutor(db)
    _forbid_llm(recovery_executor, monkeypatch)
    recovered = await _run(
        recovery_executor,
        user.id,
        "确认",
        conversation_id=proposal_done["conversation_id"],
        client_turn_id="med-batch-crash-confirm",
    )

    recovered_done = _done(recovered)
    assert recovered_done["completion_status"] == "complete"
    assert recovered_done["write_receipts"] == committed["write_receipts"]
    assert "已记录" in _tokens(recovered)
    assert db.query(MedicationLog).filter(MedicationLog.user_id == user.id).count() == 2

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    [
        "记录服用阿奇霉素两粒",
        "记录我吃了两粒阿奇霉素",
    ],
)
async def test_single_explicit_intake_uses_the_same_zero_llm_confirmation_path(
    db, auth_user_and_headers, monkeypatch, message
):
    user, _ = auth_user_and_headers
    first_executor = AgentExecutor(db)
    _forbid_llm(first_executor, monkeypatch)
    first = await _run(first_executor, user.id, message)
    first_done = _done(first)
    assert first_done["turn_outcome"]["category"] == "confirmation_required"
    assert "阿奇霉素 2粒" in _tokens(first)

    confirm_executor = AgentExecutor(db)
    _forbid_llm(confirm_executor, monkeypatch)
    confirmed = await _run(
        confirm_executor,
        user.id,
        "确认",
        conversation_id=first_done["conversation_id"],
    )

    assert len(_done(confirmed)["write_receipts"]) == 1
    log = db.query(MedicationLog).filter(MedicationLog.user_id == user.id).one()
    assert log.actual_dosage == "2粒"


@pytest.mark.asyncio
async def test_strength_is_visible_in_confirmation_preview(
    db, auth_user_and_headers, monkeypatch
):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _forbid_llm(executor, monkeypatch)

    events = await _run(executor, user.id, "记录服用奥美拉唑20mg一粒")

    assert "奥美拉唑 20mg × 1粒" in _tokens(events)
    card = next(
        card for card in _done(events)["cards"]
        if card["type"] == "medication_draft"
    )
    assert card["data"]["items"][0]["observed_strength"] == "20mg"


@pytest.mark.asyncio
async def test_expired_confirmation_is_terminal_and_never_writes(
    db, auth_user_and_headers, monkeypatch
):
    import app.services.medication_intake_batch as batch

    issued_at = datetime(2026, 7, 21, 10, 0, tzinfo=UTC)
    monkeypatch.setattr(batch, "_utc_now", lambda: issued_at)
    user, _ = auth_user_and_headers
    proposal_executor = AgentExecutor(db)
    _forbid_llm(proposal_executor, monkeypatch)
    proposal = await _run(proposal_executor, user.id, EXACT_MESSAGE)
    conversation_id = _done(proposal)["conversation_id"]

    monkeypatch.setattr(batch, "_utc_now", lambda: issued_at + timedelta(minutes=31))
    confirm_executor = AgentExecutor(db)
    _forbid_llm(confirm_executor, monkeypatch)
    result = await _run(
        confirm_executor,
        user.id,
        "确认",
        conversation_id=conversation_id,
    )

    assert "已过期" in _tokens(result)
    assert "没有写入" in _tokens(result)
    assert _done(result)["pending_write_intent_ids"] == []
    assert db.query(MedicationLog).filter(MedicationLog.user_id == user.id).count() == 0
    assert db.query(WriteIntent).filter(WriteIntent.user_id == user.id).one().status == "dismissed"


@pytest.mark.asyncio
async def test_safety_precheck_failure_is_visible_after_text_confirmation(
    db, auth_user_and_headers, monkeypatch
):
    user, _ = auth_user_and_headers
    proposal_executor = AgentExecutor(db)
    _forbid_llm(proposal_executor, monkeypatch)
    proposal = await _run(proposal_executor, user.id, EXACT_MESSAGE)

    monkeypatch.setattr(
        "app.services.medication_safety.evaluate_medication_safety_alerts",
        lambda *args, **kwargs: [{
            "rule_id": "medication.safety_precheck_incomplete",
            "category": "ddi",
            "severity": 3,
            "title": "用药安全预检未完成",
            "message": "这不代表安全",
            "action": "请咨询医生或药师",
            "requires_medical_attention": True,
        }],
    )
    confirm_executor = AgentExecutor(db)
    _forbid_llm(confirm_executor, monkeypatch)
    result = await _run(
        confirm_executor,
        user.id,
        "确认",
        conversation_id=_done(proposal)["conversation_id"],
    )

    reply = _tokens(result)
    assert "用药安全预检未完成" in reply
    assert "这不代表" in reply
    assert len(_done(result)["write_receipts"]) == 2


@pytest.mark.asyncio
async def test_text_confirmation_preserves_every_high_severity_safety_alert(
    db, auth_user_and_headers, monkeypatch
):
    """The fourth warning must not disappear behind a non-authoritative link."""
    user, _ = auth_user_and_headers
    proposal_executor = AgentExecutor(db)
    _forbid_llm(proposal_executor, monkeypatch)
    proposal = await _run(proposal_executor, user.id, EXACT_MESSAGE)
    alerts = [
        {
            "rule_id": f"medication.safety.{index}",
            "category": "ddi",
            "severity": 4,
            "title": f"用药安全提示 {index}",
            "message": f"提示正文 {index}",
            "action": "请咨询医生或药师",
            "requires_medical_attention": True,
        }
        for index in range(1, 5)
    ]
    monkeypatch.setattr(
        "app.services.medication_safety.evaluate_medication_safety_alerts",
        lambda *args, **kwargs: alerts,
    )

    confirm_executor = AgentExecutor(db)
    _forbid_llm(confirm_executor, monkeypatch)
    result = await _run(
        confirm_executor,
        user.id,
        "确认",
        conversation_id=_done(proposal)["conversation_id"],
    )

    done = _done(result)
    assert done["safety_alerts"] == alerts
    assert [card["data"]["title"] for card in done["cards"]] == [
        alert["title"] for alert in alerts
    ]
    for alert in alerts:
        assert alert["title"] in _tokens(result)

@pytest.mark.asyncio
async def test_immediate_explicit_dismissal_writes_no_medication_log(
    db, auth_user_and_headers, monkeypatch
):
    user, _ = auth_user_and_headers
    first_executor = AgentExecutor(db)
    _forbid_llm(first_executor, monkeypatch)
    first = await _run(first_executor, user.id, EXACT_MESSAGE)
    conversation_id = _done(first)["conversation_id"]

    dismiss_executor = AgentExecutor(db)
    _forbid_llm(dismiss_executor, monkeypatch)
    dismissed = await _run(
        dismiss_executor,
        user.id,
        "取消",
        conversation_id=conversation_id,
    )

    assert "没有写入" in _tokens(dismissed)
    assert _done(dismissed)["write_receipts"] == []
    assert db.query(MedicationLog).filter(MedicationLog.user_id == user.id).count() == 0
    intent = db.query(WriteIntent).filter(WriteIntent.user_id == user.id).one()
    assert intent.status == "dismissed"
    assert intent.decision_status == "dismissed"


@pytest.mark.asyncio
async def test_text_dismiss_honors_a_concurrent_confirm_winner(
    db, auth_user_and_headers, monkeypatch
):
    from app.services import write_intent_service

    user, _ = auth_user_and_headers
    proposal_executor = AgentExecutor(db)
    _forbid_llm(proposal_executor, monkeypatch)
    proposal = await _run(proposal_executor, user.id, EXACT_MESSAGE)
    conversation_id = _done(proposal)["conversation_id"]
    real_confirm = write_intent_service.confirm

    def confirm_wins(session, user_id, intent_id):
        return real_confirm(session, user_id, intent_id)

    monkeypatch.setattr(write_intent_service, "dismiss", confirm_wins)
    dismiss_executor = AgentExecutor(db)
    _forbid_llm(dismiss_executor, monkeypatch)

    result = await _run(
        dismiss_executor,
        user.id,
        "取消",
        conversation_id=conversation_id,
    )

    assert "已记录" in _tokens(result)
    assert "没有写入" not in _tokens(result)
    assert len(_done(result)["write_receipts"]) == 2
    assert db.query(MedicationLog).filter(MedicationLog.user_id == user.id).count() == 2


@pytest.mark.asyncio
async def test_text_confirm_honors_a_concurrent_dismiss_winner(
    db, auth_user_and_headers, monkeypatch
):
    from app.services import write_intent_service

    user, _ = auth_user_and_headers
    proposal_executor = AgentExecutor(db)
    _forbid_llm(proposal_executor, monkeypatch)
    proposal = await _run(proposal_executor, user.id, EXACT_MESSAGE)
    conversation_id = _done(proposal)["conversation_id"]
    real_dismiss = write_intent_service.dismiss

    def dismiss_wins(session, user_id, intent_id):
        return real_dismiss(session, user_id, intent_id)

    monkeypatch.setattr(write_intent_service, "confirm", dismiss_wins)
    confirm_executor = AgentExecutor(db)
    _forbid_llm(confirm_executor, monkeypatch)

    result = await _run(
        confirm_executor,
        user.id,
        "确认",
        conversation_id=conversation_id,
    )

    assert "已取消" in _tokens(result)
    assert "重试" not in _tokens(result)
    assert _done(result)["write_receipts"] == []
    assert _done(result)["pending_write_intent_ids"] == []
    assert db.query(MedicationLog).filter(MedicationLog.user_id == user.id).count() == 0


@pytest.mark.asyncio
async def test_transient_text_dismiss_failure_never_prompts_user_to_confirm(
    db, auth_user_and_headers, monkeypatch
):
    from app.services import write_intent_service

    user, _ = auth_user_and_headers
    proposal_executor = AgentExecutor(db)
    _forbid_llm(proposal_executor, monkeypatch)
    proposal = await _run(proposal_executor, user.id, EXACT_MESSAGE)
    proposal_done = _done(proposal)

    def fail_dismiss(*args, **kwargs):
        raise RuntimeError("transient projection failure")

    monkeypatch.setattr(write_intent_service, "dismiss", fail_dismiss)
    dismiss_executor = AgentExecutor(db)
    _forbid_llm(dismiss_executor, monkeypatch)
    result = await _run(
        dismiss_executor,
        user.id,
        "取消",
        conversation_id=proposal_done["conversation_id"],
    )

    reply = _tokens(result)
    intent = db.query(WriteIntent).filter(WriteIntent.user_id == user.id).one()
    assert "取消未完成" in reply
    assert "回复“取消”重试" in reply
    assert "确认”重试" not in reply
    assert _done(result)["pending_write_intent_ids"] == [intent.id]
    assert intent.status == "pending"
    assert db.query(MedicationLog).filter(MedicationLog.user_id == user.id).count() == 0


@pytest.mark.asyncio
async def test_expired_confirm_commit_crash_replays_expired_without_llm(
    db, auth_user_and_headers, monkeypatch
):
    import app.services.medication_intake_batch as batch
    from app.services import write_intent_service
    from app.services.agent_conversation_service import AgentConversationService

    issued_at = datetime(2026, 7, 21, 10, 0, tzinfo=UTC)
    monkeypatch.setattr(batch, "_utc_now", lambda: issued_at)
    user, _ = auth_user_and_headers
    proposal_executor = AgentExecutor(db)
    _forbid_llm(proposal_executor, monkeypatch)
    proposal = await _run(
        proposal_executor,
        user.id,
        EXACT_MESSAGE,
        client_turn_id="med-batch-expired-crash-proposal",
    )
    proposal_done = _done(proposal)
    intent = db.query(WriteIntent).filter(WriteIntent.user_id == user.id).one()
    svc = AgentConversationService(db)
    _, created = svc.save_user_message_once(
        proposal_done["conversation_id"],
        user.id,
        "确认",
        client_turn_id="med-batch-expired-crash-confirm",
        meta={"client_turn_id": "med-batch-expired-crash-confirm"},
    )
    assert created is True

    monkeypatch.setattr(batch, "_utc_now", lambda: issued_at + timedelta(minutes=31))
    with pytest.raises(batch.ExpiredMedicationIntakePlan):
        write_intent_service.confirm(db, user.id, intent.id)

    recovery_executor = AgentExecutor(db)
    _forbid_llm(recovery_executor, monkeypatch)
    recovered = await _run(
        recovery_executor,
        user.id,
        "确认",
        conversation_id=proposal_done["conversation_id"],
        client_turn_id="med-batch-expired-crash-confirm",
    )

    assert "已过期" in _tokens(recovered)
    assert "已取消" not in _tokens(recovered)
    assert _done(recovered)["pending_write_intent_ids"] == []
    db.refresh(intent)
    assert intent.status == "dismissed"
    assert intent.decision_status == "expired"


def test_unpresented_expiry_crash_keeps_logical_expired_on_recovery(
    db, auth_user_and_headers, monkeypatch
):
    import app.services.medication_intake_batch as batch
    from app.services.agent_conversation_service import AgentConversationService

    issued_at = datetime(2026, 7, 21, 10, 0, tzinfo=UTC)
    monkeypatch.setattr(batch, "_utc_now", lambda: issued_at)
    user, _ = auth_user_and_headers
    svc = AgentConversationService(db)
    conversation = svc.get_or_create_conversation(user.id, None, title="过期恢复")
    source, _ = svc.save_user_message_once(
        conversation.id,
        user.id,
        EXACT_MESSAGE,
        client_turn_id="med-batch-unpresented-expiry",
    )
    intent = batch.propose_medication_intake_batch(
        db,
        user_id=user.id,
        conversation_id=conversation.id,
        source_message_id=source.id,
        text=source.content,
        reference_now=issued_at,
    )
    assert intent is not None
    monkeypatch.setattr(batch, "_utc_now", lambda: issued_at + timedelta(minutes=31))

    first_worker = AgentExecutor(db)
    lost_result = first_worker._resolve_medication_batch_turn(
        user_id=user.id,
        conversation_id=conversation.id,
        user_message=source,
        message=EXACT_MESSAGE,
    )
    assert lost_result is not None and lost_result["action"] == "expired"

    db.expire_all()
    recovered_intent = db.get(WriteIntent, intent.id)
    assert recovered_intent.status == "dismissed"
    assert recovered_intent.decision_status == "expired"
    second_worker = AgentExecutor(db)
    replayed = second_worker._resolve_medication_batch_turn(
        user_id=user.id,
        conversation_id=conversation.id,
        user_message=source,
        message=EXACT_MESSAGE,
    )

    assert replayed is not None
    assert replayed["action"] == "expired_recovery"
    assert "已过期" in replayed["reply"]
    assert "已取消" not in replayed["reply"]


@pytest.mark.asyncio
async def test_ambiguous_confirmation_phrase_does_not_authorize_pending_batch(
    db, auth_user_and_headers, monkeypatch
):
    user, _ = auth_user_and_headers
    first_executor = AgentExecutor(db)
    _forbid_llm(first_executor, monkeypatch)
    first = await _run(first_executor, user.id, EXACT_MESSAGE)
    conversation_id = _done(first)["conversation_id"]

    executor = AgentExecutor(db)
    monkeypatch.setattr(executor, "_build_system_prompt", lambda *args, **kwargs: "SYS")
    monkeypatch.setattr(
        "app.services.agent_executor.get_health_tools",
        lambda subset=None: [],
    )

    async def fake_stream(messages, tools):
        yield {"type": "content", "text": "我可以先帮你核对剂量，但还没有执行记录。"}
        yield {"type": "finish", "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_call_llm_stream", fake_stream)
    events = await _run(
        executor,
        user.id,
        "确认一下剂量对不对",
        conversation_id=conversation_id,
    )

    assert "还没有执行记录" in _tokens(events)
    assert db.query(MedicationLog).filter(MedicationLog.user_id == user.id).count() == 0
    intent = db.query(WriteIntent).filter(WriteIntent.user_id == user.id).one()
    assert intent.status == "pending"


@pytest.mark.asyncio
async def test_model_confirmed_flag_without_server_plan_cannot_write(
    db, auth_user_and_headers
):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    executor._current_user_id = user.id

    async def must_not_call_api(*args, **kwargs):
        raise AssertionError("model-controlled confirmed flag reached medication API")

    executor._api_get_json = must_not_call_api
    executor._api_post_json = must_not_call_api
    executor._api_post = must_not_call_api

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
    assert payload["dispatch_started"] is False
    assert payload["error_code"] == "medication_plan_context_missing"
    assert "确认计划" in payload["message"]
    assert db.query(MedicationLog).filter(MedicationLog.user_id == user.id).count() == 0


@pytest.mark.asyncio
async def test_proposal_failure_log_redacts_exception_text(
    db, auth_user_and_headers, monkeypatch, caplog
):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _forbid_llm(executor, monkeypatch)
    sensitive = "SENTINEL_DRUG 999粒"

    def fail_proposal(*args, **kwargs):
        raise RuntimeError(sensitive)

    monkeypatch.setattr(
        "app.services.medication_intake_batch.propose_medication_intake_batch",
        fail_proposal,
    )
    events = await _run(executor, user.id, EXACT_MESSAGE)

    assert sensitive not in caplog.text
    assert sensitive not in _tokens(events)
    assert "RuntimeError" in caplog.text


@pytest.mark.asyncio
async def test_llm_medication_tool_can_only_propose_a_server_owned_plan(
    db, auth_user_and_headers, monkeypatch
):
    """Unparsed wording still works, but model ``confirmed`` never authorizes it."""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    monkeypatch.setattr(executor, "_build_system_prompt", lambda *args, **kwargs: "SYS")
    calls = 0

    async def fake_stream(messages, tools):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise AssertionError("pending medication plan should terminate the tool loop")
        yield {
            "type": "tool_calls",
            "tool_calls": [{
                "id": "model-medication-proposal",
                "type": "function",
                "function": {
                    "name": "health_record",
                    "arguments": json.dumps({
                        "record_type": "medication",
                        "confirmed": True,
                        "data": {
                            "medication_name": "阿奇霉素",
                            "actual_dosage": "2粒",
                            "confirmed": True,
                        },
                    }, ensure_ascii=False),
                },
            }],
        }
        yield {"type": "finish", "finish_reason": "tool_calls"}

    monkeypatch.setattr(executor, "_call_llm_stream", fake_stream)
    first = await _run(
        executor,
        user.id,
        "帮我记录刚才那次服药",
        client_turn_id="med-tool-proposal",
    )

    assert db.query(MedicationLog).filter(MedicationLog.user_id == user.id).count() == 0
    intent = db.query(WriteIntent).filter(WriteIntent.user_id == user.id).one()
    assert intent.status == "pending"
    assert intent.source == "agent_medication_tool"
    done = _done(first)
    assert done["pending_write_intent_ids"] == [intent.id]
    assert done["turn_outcome"]["category"] == "confirmation_required"
    assert "阿奇霉素" in _tokens(first) and "2粒" in _tokens(first)
    assert not any(
        event.get("event") == "card"
        and ((event.get("data") or {}).get("descriptor") or {}).get("type")
        == "medication_draft"
        for event in first
    )
    assert any(card.get("type") == "medication_draft" for card in done["cards"])

    confirm_executor = AgentExecutor(db)
    _forbid_llm(confirm_executor, monkeypatch)
    confirmed = await _run(
        confirm_executor,
        user.id,
        "确认",
        conversation_id=done["conversation_id"],
        client_turn_id="med-tool-confirm",
    )
    assert len(_done(confirmed)["write_receipts"]) == 1
    assert db.query(MedicationLog).filter(MedicationLog.user_id == user.id).count() == 1


@pytest.mark.asyncio
async def test_llm_medication_tool_rejects_unknown_name_without_pending_plan(
    db, auth_user_and_headers, monkeypatch
):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    monkeypatch.setattr(executor, "_build_system_prompt", lambda *args, **kwargs: "SYS")
    calls = 0

    async def fake_stream(messages, tools):
        nonlocal calls
        calls += 1
        if calls == 1:
            yield {
                "type": "tool_calls",
                "tool_calls": [{
                    "id": "unknown-medication-proposal",
                    "type": "function",
                    "function": {
                        "name": "health_record",
                        "arguments": json.dumps({
                            "record_type": "medication",
                            "data": {
                                "medication_name": "咔咔霉素",
                                "actual_dosage": "2粒",
                            },
                        }, ensure_ascii=False),
                    },
                }],
            }
            yield {"type": "finish", "finish_reason": "tool_calls"}
            return
        yield {"type": "content", "text": "未建立用药确认计划，本轮没有写入。"}
        yield {"type": "finish", "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_call_llm_stream", fake_stream)
    events = await _run(
        executor,
        user.id,
        "记录我吃了两粒咔咔霉素",
        client_turn_id="unknown-medication-tool-plan",
    )

    done = _done(events)
    assert calls >= 2
    assert done["pending_write_intent_ids"] == []
    assert done["write_receipts"] == []
    assert done["turn_outcome"]["category"] in {
        "action_not_executed",
        "tool_failed",
    }
    assert db.query(WriteIntent).filter(WriteIntent.user_id == user.id).count() == 0
    assert db.query(MedicationLog).filter(MedicationLog.user_id == user.id).count() == 0


@pytest.mark.asyncio
async def test_one_model_response_seals_two_medication_calls_before_preview(
    db, auth_user_and_headers, monkeypatch
):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    monkeypatch.setattr(executor, "_build_system_prompt", lambda *args, **kwargs: "SYS")
    calls = 0

    async def fake_stream(messages, tools):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise AssertionError("sealed medication plan must terminate the tool loop")
        yield {
            "type": "tool_calls",
            "tool_calls": [
                {
                    "id": "med-one",
                    "type": "function",
                    "function": {
                        "name": "health_record",
                        "arguments": json.dumps({
                            "record_type": "medication",
                            "data": {
                                "medication_name": "伊托必利",
                                "actual_dosage": "1粒",
                            },
                        }, ensure_ascii=False),
                    },
                },
                {
                    "id": "med-two",
                    "type": "function",
                    "function": {
                        "name": "health_record",
                        "arguments": json.dumps({
                            "record_type": "medication",
                            "data": {
                                "medication_name": "替普瑞酮",
                                "actual_dosage": "1粒",
                            },
                        }, ensure_ascii=False),
                    },
                },
            ],
        }
        yield {"type": "finish", "finish_reason": "tool_calls"}

    monkeypatch.setattr(executor, "_call_llm_stream", fake_stream)
    events = await _run(
        executor,
        user.id,
        "帮我记录刚才吃的那两种药",
        client_turn_id="two-medication-tool-plan",
    )

    intents = db.query(WriteIntent).filter(WriteIntent.user_id == user.id).all()
    assert len(intents) == 1
    assert [item["medication_name"] for item in intents[0].payload["items"]] == [
        "伊托必利",
        "替普瑞酮",
    ]
    assert all(item["actual_dosage"] == "1粒" for item in intents[0].payload["items"])
    done = _done(events)
    assert done["pending_write_intent_ids"] == [intents[0].id]
    assert done["turn_outcome"]["category"] == "confirmation_required"
    card = next(card for card in done["cards"] if card["type"] == "medication_draft")
    assert card["data"]["items"] == intents[0].payload["items"]
    assert "伊托必利" in _tokens(events)
    assert "替普瑞酮" in _tokens(events)
    assert db.query(MedicationLog).filter(MedicationLog.user_id == user.id).count() == 0


@pytest.mark.asyncio
async def test_confirmation_cannot_jump_over_an_intervening_message(
    db, auth_user_and_headers, monkeypatch
):
    user, _ = auth_user_and_headers
    proposal_executor = AgentExecutor(db)
    _forbid_llm(proposal_executor, monkeypatch)
    proposal = await _run(proposal_executor, user.id, EXACT_MESSAGE)
    conversation_id = _done(proposal)["conversation_id"]

    db.add(AgentMessage(
        conversation_id=conversation_id,
        role="user",
        content="先等等，我要核对一下。",
    ))
    db.commit()

    executor = AgentExecutor(db)
    monkeypatch.setattr(executor, "_build_system_prompt", lambda *args, **kwargs: "SYS")
    monkeypatch.setattr("app.services.agent_executor.get_health_tools", lambda subset=None: [])

    async def fake_stream(messages, tools):
        yield {"type": "content", "text": "没有执行任何用药记录。"}
        yield {"type": "finish", "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_call_llm_stream", fake_stream)
    events = await _run(
        executor,
        user.id,
        "确认",
        conversation_id=conversation_id,
    )

    assert "没有执行" in _tokens(events)
    assert db.query(MedicationLog).filter(MedicationLog.user_id == user.id).count() == 0
    intent = db.query(WriteIntent).filter(WriteIntent.user_id == user.id).one()
    assert intent.status == "pending"


@pytest.mark.asyncio
async def test_failed_or_cardless_assistant_cannot_authorize_bare_confirmation(
    db, auth_user_and_headers, monkeypatch
):
    user, _ = auth_user_and_headers
    proposal_executor = AgentExecutor(db)
    _forbid_llm(proposal_executor, monkeypatch)
    proposal = await _run(
        proposal_executor,
        user.id,
        EXACT_MESSAGE,
        client_turn_id="unpresented-medication-plan",
    )
    proposal_done = _done(proposal)
    assistant = db.get(AgentMessage, proposal_done["message_id"])
    assistant.meta = {
        **assistant.meta,
        "completion_status": "error",
        "cards": [],
    }
    db.commit()

    current = AgentMessage(
        conversation_id=proposal_done["conversation_id"],
        role="user",
        content="确认",
    )
    db.add(current)
    db.commit()
    db.refresh(current)

    resolver = AgentExecutor(db)
    assert resolver._immediately_pending_medication_intent(
        user_id=user.id,
        conversation_id=proposal_done["conversation_id"],
        current_user_message=current,
        action="confirm",
    ) is None
    assert resolver._has_pending_medication_confirmation_for_route(
        user_id=user.id,
        conversation_id=proposal_done["conversation_id"],
    ) is False
    assert db.query(MedicationLog).filter(MedicationLog.user_id == user.id).count() == 0
    assert db.query(WriteIntent).filter(WriteIntent.user_id == user.id).one().status == "pending"


def test_multi_model_tool_preflight_cannot_create_hidden_medication_plan(
    db, auth_user_and_headers
):
    from app.services.agent_conversation_service import AgentConversationService

    user, _ = auth_user_and_headers
    svc = AgentConversationService(db)
    conv = svc.get_or_create_conversation(user.id, None, title="多模型分析")
    source, _ = svc.save_user_message_once(
        conv.id,
        user.id,
        "结合最近数据分析；顺便记录我刚服用了阿奇霉素两粒",
        client_turn_id=None,
    )
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    executor._current_turn_conversation_id = conv.id
    executor._current_turn_source_message_id = source.id
    executor._multi_model_turn = True

    executor._prepare_medication_tool_plan([{
        "function": {
            "name": "health_record",
            "arguments": json.dumps({
                "record_type": "medication",
                "data": {
                    "medication_name": "阿奇霉素",
                    "actual_dosage": "2粒",
                },
            }, ensure_ascii=False),
        },
    }])

    assert db.query(WriteIntent).filter(WriteIntent.user_id == user.id).count() == 0
    assert executor._turn_medication_tool_intent_id is None
    assert "多模型" in (executor._turn_medication_tool_preflight_error or "")


def test_health_record_schema_requires_actual_dosage_not_historical_taken_time():
    from app.services.tool_schema_registry import get_health_tools

    health_record = next(
        tool for tool in get_health_tools()
        if tool["function"]["name"] == "health_record"
    )
    description = health_record["function"]["parameters"]["properties"]["data"]["description"]
    assert '"actual_dosage": "1片"' in description
    assert '"observed_strength": "200mg"' in description
    assert 'medication:       {"medication_name": "布洛芬", "taken_time"' not in description
    assert "本次实际服量" in description


@pytest.mark.asyncio
async def test_unrelated_bare_agreement_still_uses_requested_multi_model_panel(
    db, auth_user_and_headers, monkeypatch
):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    called = False

    async def fake_multi_model(*args, **kwargs):
        nonlocal called
        called = True
        yield {
            "event": "done",
            "data": {
                "conversation_id": None,
                "message_id": None,
                "completion_status": "complete",
            },
        }

    monkeypatch.setattr(executor, "_run_multi_model_stream", fake_multi_model)
    await _run(
        executor,
        user.id,
        "对",
        extra_context=json.dumps({"multi_model": True}),
    )

    assert called is True


@pytest.mark.asyncio
async def test_orphaned_model_tool_plan_recovers_exact_preview_not_unknown_write(
    db, auth_user_and_headers, monkeypatch
):
    from app.services.agent_conversation_service import AgentConversationService
    from app.services.medication_intake_batch import propose_medication_intake_items

    user, _ = auth_user_and_headers
    svc = AgentConversationService(db)
    conv = svc.get_or_create_conversation(user.id, None, title="服药")
    user_message, _ = svc.save_user_message_once(
        conv.id,
        user.id,
        "帮我记录刚才那次服药",
        client_turn_id="orphaned-medication-tool-plan",
        meta={"client_turn_id": "orphaned-medication-tool-plan"},
    )
    intent = propose_medication_intake_items(
        db,
        user_id=user.id,
        conversation_id=conv.id,
        source_message_id=user_message.id,
        items=[{
            "medication_name": "阿奇霉素",
            "actual_dosage": "2粒",
        }],
        reference_now=datetime(2026, 7, 21, 12, 0, tzinfo=UTC),
    )
    user_message.meta = {
        **(user_message.meta or {}),
        "write_state": {
            "status": "in_flight",
            "tool": "health_record",
            "fingerprint": "redacted",
        },
    }
    db.commit()

    executor = AgentExecutor(db)
    _forbid_llm(executor, monkeypatch)
    events = await _run(
        executor,
        user.id,
        "帮我记录刚才那次服药",
        client_turn_id="orphaned-medication-tool-plan",
    )

    reply = _tokens(events)
    assert "阿奇霉素 2粒" in reply
    assert "请确认" in reply
    assert "状态未知" not in reply
    assert _done(events)["pending_write_intent_ids"] == [intent.id]
    assert db.query(MedicationLog).filter(MedicationLog.user_id == user.id).count() == 0
