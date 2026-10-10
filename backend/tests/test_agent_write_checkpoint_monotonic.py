"""A later admission rejection cannot settle an earlier dispatched write."""
from types import SimpleNamespace

import pytest

from app.services.agent_executor import AgentExecutor


@pytest.mark.parametrize("previous", ["in_flight", "uncertain", "verified"])
@pytest.mark.parametrize("later", ["rejected", "failed"])
def test_rejection_preserves_previous_dispatch_evidence(db, previous, later):
    executor = AgentExecutor(db)
    message = SimpleNamespace(meta={})
    # Keep the checkpoint's real commit path, replacing only ORM refresh for this
    # content-free metadata carrier.
    db.refresh = lambda value: None
    args = {"record_type": "water", "data": {"amount": 100}}
    receipt = {
        "operation_id": "test-checkpoint-water",
        "status": "verified",
        "verified": True,
    } if previous == "verified" else None
    executor._persist_turn_expected_writes(message, [("health_record", args)])
    executor._persist_turn_write_state(
        message, status=previous, tool_name="health_record", parsed_args=args,
        receipt=receipt,
    )
    executor._persist_turn_write_state(
        message, status=later, tool_name="health_record", parsed_args=args,
    )
    operation = next(iter(message.meta["write_operations"].values()))
    assert operation["status"] == previous
    assert message.meta["write_state"]["status"] == previous
    if receipt:
        assert operation["receipt_operation_id"] == receipt["operation_id"]
        assert message.meta["write_receipts"] == [receipt]


@pytest.mark.parametrize("status", ["rejected", "failed"])
def test_first_pre_dispatch_rejection_remains_terminal(db, status):
    executor = AgentExecutor(db)
    message = SimpleNamespace(meta={})
    db.refresh = lambda value: None
    args = {"record_type": "water", "data": {"amount": 100}}
    executor._persist_turn_expected_writes(message, [("health_record", args)])
    executor._persist_turn_write_state(
        message, status=status, tool_name="health_record", parsed_args=args,
    )
    assert next(iter(message.meta["write_operations"].values()))["status"] == status


@pytest.mark.asyncio
@pytest.mark.parametrize("previous", ["in_flight", "uncertain"])
@pytest.mark.parametrize("sibling", [False, True])
async def test_recovery_does_not_report_no_effect_after_rejected_retry(
    db, auth_user_and_headers, previous, sibling,
):
    from app.services.agent_conversation_service import AgentConversationService

    user, _ = auth_user_and_headers
    svc = AgentConversationService(db)
    conversation = svc.get_or_create_conversation(user.id, None, title="写入恢复测试")
    message, _ = svc.save_user_message_once(
        conversation.id, user.id, "记录饮水", client_turn_id=f"checkpoint-{previous}",
    )
    executor = AgentExecutor(db)
    args = {"record_type": "water", "data": {"amount": 100}}
    executor._persist_turn_expected_writes(message, [("health_record", args)])
    executor._persist_turn_write_state(
        message, status=previous, tool_name="health_record", parsed_args=args,
    )
    if sibling:
        other_args = {"record_type": "water", "data": {"amount": 200}}
        executor._persist_turn_expected_writes(message, [("health_record", other_args)])
        executor._persist_turn_write_state(
            message, status="rejected", tool_name="health_record", parsed_args=other_args,
        )
    executor._persist_turn_write_state(
        message, status="rejected", tool_name="health_record", parsed_args=args,
    )
    db.expire_all()
    db.refresh(message)
    events = [event async for event in executor._recover_client_turn_write_checkpoint(
        svc, user.id, message, f"checkpoint-{previous}",
    )]
    assert events[-1]["data"]["write_recovery"] == "write_checkpoint_uncertain"
    assert events[-1]["data"]["completion_status"] == "error"
    content = next(event["data"]["content"] for event in events if event["event"] == "token")
    assert "状态未知" in content
    assert "没有自动重试" in content
