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


@pytest.mark.asyncio
@pytest.mark.parametrize('case', ['omitted_item', 'missing_binding', 'source_drift', 'extra_operation', 'extra_receipt', 'full'])
async def test_orphan_mixed_intake_requires_complete_source_coverage(db, auth_user_and_headers, case):
    from app.services.agent_conversation_service import AgentConversationService
    from app.services.intake_retry import build_intake_retry_plan
    user, _ = auth_user_and_headers
    svc = AgentConversationService(db)
    conversation = svc.get_or_create_conversation(user.id, None, title='typed orphan')
    source = '记录吃了两粒鱼油，喝了一杯豆浆'
    message, _ = svc.save_user_message_once(conversation.id, user.id, source, client_turn_id='typed-orphan')
    fps = ['fish'] if case == 'omitted_item' else ['fish', 'soy']
    receipts = [{'operation_id': f'r-{fp}', 'verified': True} for fp in fps]
    meta = {'write_plan': {'sealed': True, 'fingerprints': fps},
            'write_operations': {fp: {'status': 'verified', 'receipt_operation_id': f'r-{fp}'} for fp in fps},
            'write_receipts': receipts}
    if case not in {'missing_binding', 'omitted_item'}:
        meta['intake_retry_plan'] = build_intake_retry_plan(source_text=source,
            owner_id=user.id, conversation_id=conversation.id, source_message_id=message.id,
            local_date='2026-10-01', timezone='Asia/Shanghai', item_fingerprints=fps)
    if case == 'source_drift': meta['intake_retry_plan']['source_sha256'] = '0' * 64
    if case == 'extra_operation': meta['write_operations']['unknown'] = {'status': 'in_flight'}
    if case == 'extra_receipt': meta['write_receipts'].append({'operation_id': 'unknown', 'verified': True})
    message.meta = meta
    db.commit()
    executor = AgentExecutor(db)
    events = [e async for e in executor._recover_client_turn_write_checkpoint(svc, user.id, message, 'typed-orphan')]
    done = events[-1]['data']
    assert done['completion_status'] == ('complete' if case == 'full' else 'error')
    if case != 'full':
        assert done['write_recovery'] == 'write_checkpoint_intake_coverage_unproven'
        assert '写入已完成' not in next(e['data']['content'] for e in events if e['event'] == 'token')
    assert done['write_receipts'] == receipts


@pytest.mark.asyncio
@pytest.mark.parametrize('record_type,source', [
    ('supplement', '记录补剂吃了两粒鱼油'), ('diet', '记录饮食喝了一杯豆浆'),
])
@pytest.mark.parametrize('status', ['verified', 'in_flight'])
async def test_orphan_single_intake_preserves_legacy_raw_fingerprint(db, auth_user_and_headers, record_type, source, status):
    from app.services.agent_conversation_service import AgentConversationService
    from app.services.agent_executor import _write_operation_fingerprint
    user, _ = auth_user_and_headers
    svc = AgentConversationService(db)
    conversation = svc.get_or_create_conversation(user.id, None, title='legacy intake')
    message, _ = svc.save_user_message_once(conversation.id, user.id, source, client_turn_id='legacy-intake')
    raw_fp = _write_operation_fingerprint('health_record', {'record_type': record_type, 'data': {'name': 'legacy'}})
    operation = {'status': status}
    receipts = []
    if status == 'verified':
        operation['receipt_operation_id'] = 'legacy-receipt'
        receipts = [{'operation_id': 'legacy-receipt', 'verified': True}]
    message.meta = {'write_plan': {'sealed': True, 'fingerprints': [raw_fp]},
                    'write_operations': {raw_fp: operation}, 'write_receipts': receipts}
    db.commit()
    executor = AgentExecutor(db)
    events = [e async for e in executor._recover_client_turn_write_checkpoint(svc, user.id, message, 'legacy-intake')]
    done = events[-1]['data']
    assert done['completion_status'] == ('complete' if status == 'verified' else 'error')
    assert done['write_recovery'] == ('write_checkpoint_verified' if status == 'verified' else 'write_checkpoint_uncertain')
