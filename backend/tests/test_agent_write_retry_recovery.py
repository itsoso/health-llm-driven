from __future__ import annotations

import json

import pytest

from app.services.agent_turn_retry import (
    RETRY_SOURCE_ACTION_TYPE,
    build_retry_source_action,
    build_retry_source_action_if_safe,
    materialize_retryable_turn_images,
    resolve_retryable_turn_recovery,
    restore_retryable_turn_recovery,
)


def _save_failed_turn(
    service,
    user_id: int,
    conversation_id: int,
    *,
    source_meta=None,
    image_url=json.dumps(["/api/v1/upload/files/chat/1/dinner.jpg"]),
    message="记录晚餐：牛排和蔬菜",
):
    source, _ = service.save_user_message_once(
        conversation_id,
        user_id,
        message,
        client_turn_id="source-turn",
        image_url=image_url,
        meta=source_meta or {"client_turn_id": "source-turn"},
    )
    action = build_retry_source_action(
        source_message_id=source.id,
        root_source_message_id=source.id,
        reason_code="completion_error",
    )
    assistant = service.save_message(
        conversation_id,
        "assistant",
        "系统暂时无法完成记录。",
        meta={
            "client_turn_finalized": True,
            "completion_status": "error",
            "write_receipts": [],
            "turn_outcome": {
                "category": "execution_error",
                "retryable": True,
            },
            "recovery_action": action,
        },
    )
    return source, assistant


def test_retry_action_contains_only_control_plane_identity():
    action = build_retry_source_action(
        source_message_id=42,
        root_source_message_id=40,
        reason_code="completion_error",
    )

    assert action == {
        "version": 1,
        "type": RETRY_SOURCE_ACTION_TYPE,
        "status": "active",
        "source_message_id": 42,
        "root_source_message_id": 40,
        "reason_code": "completion_error",
    }
    assert "content" not in action
    assert "arguments" not in action


@pytest.mark.parametrize("text", ["重试", "再试一次", "需要", "好", "好的", "现在重试"])
def test_immediate_confirmation_resolves_owner_bound_source(
    db, auth_user_and_headers, text
):
    from app.services.agent_conversation_service import AgentConversationService

    user, _ = auth_user_and_headers
    service = AgentConversationService(db)
    conversation = service.get_or_create_conversation(
        user.id,
        None,
        title="写入恢复",
    )
    source, assistant = _save_failed_turn(service, user.id, conversation.id)

    recovery = resolve_retryable_turn_recovery(
        db,
        user_id=user.id,
        conversation_id=conversation.id,
        confirmation_text=text,
    )

    assert recovery is not None
    assert recovery.source_message_id == source.id
    assert recovery.root_source_message_id == source.id
    assert recovery.trigger_assistant_message_id == assistant.id
    assert recovery.message == "记录晚餐：牛排和蔬菜"
    assert recovery.image_urls == (
        "/api/v1/upload/files/chat/1/dinner.jpg",
    )


def test_retry_does_not_jump_over_intervening_user_message(
    db, auth_user_and_headers
):
    from app.services.agent_conversation_service import AgentConversationService

    user, _ = auth_user_and_headers
    service = AgentConversationService(db)
    conversation = service.get_or_create_conversation(user.id, None, title="顺序保护")
    _save_failed_turn(service, user.id, conversation.id)
    service.save_message(conversation.id, "user", "先不重试")

    assert resolve_retryable_turn_recovery(
        db,
        user_id=user.id,
        conversation_id=conversation.id,
        confirmation_text="需要",
    ) is None


def test_retry_is_rejected_for_another_user(
    db, auth_user_and_headers
):
    from app.models.user import User
    from app.services.agent_conversation_service import AgentConversationService

    user, _ = auth_user_and_headers
    service = AgentConversationService(db)
    conversation = service.get_or_create_conversation(user.id, None, title="所有权保护")
    _save_failed_turn(service, user.id, conversation.id)
    other = User(
        email="retry-other@example.com",
        username="retry-other",
        name="Retry Other",
        hashed_password="x",
        is_active=True,
    )
    db.add(other)
    db.commit()
    db.refresh(other)

    assert resolve_retryable_turn_recovery(
        db,
        user_id=other.id,
        conversation_id=conversation.id,
        confirmation_text="重试",
    ) is None


@pytest.mark.parametrize(
    "source_meta",
    [
        {"write_state": {"status": "in_flight"}},
        {"write_state": {"status": "uncertain"}},
        {"write_state": {"status": "verified"}},
        {"write_state": {"status": "mystery"}},
        {"write_operations": {"fp": {"status": "uncertain"}}},
        {
            "write_operations": {"fp": {"status": "planned"}},
            "write_plan": {
                "sealed": True,
                "fingerprints": ["fp", "missing"],
            },
        },
        {"write_receipts": {}},
        {"write_receipts": [{"resource_id": 9}]},
    ],
)
def test_retry_action_is_not_created_across_write_safety_barrier(source_meta):
    source = type("Source", (), {"id": 7, "meta": source_meta})()

    assert build_retry_source_action_if_safe(
        source_message=source,
        turn_outcome={
            "category": "execution_error",
            "reason_code": "completion_error",
            "retryable": True,
        },
        write_receipts=[],
        health_write_requested=True,
    ) is None


def test_retry_action_is_created_only_for_retryable_health_write():
    source = type("Source", (), {"id": 7, "meta": {}})()

    action = build_retry_source_action_if_safe(
        source_message=source,
        turn_outcome={
            "category": "execution_error",
            "reason_code": "completion_error",
            "retryable": True,
        },
        write_receipts=[],
        health_write_requested=True,
    )

    assert action is not None
    assert action["source_message_id"] == 7
    assert build_retry_source_action_if_safe(
        source_message=source,
        turn_outcome={
            "category": "execution_error",
            "reason_code": "completion_error",
            "retryable": True,
        },
        write_receipts=[],
        health_write_requested=False,
    ) is None


def test_retry_of_retry_resolves_original_business_turn(
    db, auth_user_and_headers
):
    from app.services.agent_conversation_service import AgentConversationService

    user, _ = auth_user_and_headers
    service = AgentConversationService(db)
    conversation = service.get_or_create_conversation(
        user.id,
        None,
        title="连续恢复",
    )
    original, first_assistant = _save_failed_turn(
        service,
        user.id,
        conversation.id,
        image_url=None,
    )
    first_recovery = resolve_retryable_turn_recovery(
        db,
        user_id=user.id,
        conversation_id=conversation.id,
        confirmation_text="需要",
    )
    assert first_recovery is not None

    retry_user, _ = service.save_user_message_once(
        conversation.id,
        user.id,
        "需要",
        client_turn_id="retry-turn",
        meta={
            "client_turn_id": "retry-turn",
            "retry_source": first_recovery.user_message_meta(),
        },
    )
    second_action = build_retry_source_action(
        source_message_id=retry_user.id,
        root_source_message_id=original.id,
        reason_code="completion_error",
    )
    second_assistant = service.save_message(
        conversation.id,
        "assistant",
        "系统仍未完成记录。",
        meta={
            "client_turn_finalized": True,
            "completion_status": "error",
            "write_receipts": [],
            "turn_outcome": {
                "category": "execution_error",
                "retryable": True,
            },
            "recovery_action": second_action,
        },
    )

    recovery = resolve_retryable_turn_recovery(
        db,
        user_id=user.id,
        conversation_id=conversation.id,
        confirmation_text="再试一次",
    )

    assert recovery is not None
    assert recovery.source_message_id == original.id
    assert recovery.root_source_message_id == original.id
    assert recovery.action_source_message_id == retry_user.id
    assert recovery.trigger_assistant_message_id == second_assistant.id
    assert recovery.message == original.content
    assert recovery.trigger_assistant_message_id != first_assistant.id


def test_persisted_retry_binding_rejects_mismatched_trigger_action(
    db, auth_user_and_headers
):
    from app.services.agent_conversation_service import AgentConversationService

    user, _ = auth_user_and_headers
    service = AgentConversationService(db)
    conversation = service.get_or_create_conversation(
        user.id,
        None,
        title="恢复绑定完整性",
    )
    source, assistant = _save_failed_turn(
        service,
        user.id,
        conversation.id,
        image_url=None,
    )
    retry_user, _ = service.save_user_message_once(
        conversation.id,
        user.id,
        "需要",
        client_turn_id="retry-integrity-turn",
        meta={
            "client_turn_id": "retry-integrity-turn",
            "retry_source": {
                "version": 1,
                "type": RETRY_SOURCE_ACTION_TYPE,
                "source_message_id": source.id,
                "root_source_message_id": source.id,
                "trigger_assistant_message_id": assistant.id,
            },
        },
    )
    assistant.meta = {
        **(assistant.meta or {}),
        "recovery_action": build_retry_source_action(
            source_message_id=source.id + 999,
            root_source_message_id=source.id + 999,
        ),
    }
    db.commit()

    assert restore_retryable_turn_recovery(
        db,
        user_id=user.id,
        user_message=retry_user,
    ) is None


def test_persisted_retry_binding_does_not_resume_after_conversation_advanced(
    db, auth_user_and_headers
):
    from app.services.agent_conversation_service import AgentConversationService

    user, _ = auth_user_and_headers
    service = AgentConversationService(db)
    conversation = service.get_or_create_conversation(
        user.id,
        None,
        title="过期恢复保护",
    )
    source, assistant = _save_failed_turn(
        service,
        user.id,
        conversation.id,
        image_url=None,
    )
    retry_user, _ = service.save_user_message_once(
        conversation.id,
        user.id,
        "需要",
        client_turn_id="retry-stale-turn",
        meta={
            "client_turn_id": "retry-stale-turn",
            "retry_source": {
                "version": 1,
                "type": RETRY_SOURCE_ACTION_TYPE,
                "source_message_id": source.id,
                "root_source_message_id": source.id,
                "trigger_assistant_message_id": assistant.id,
            },
        },
    )
    service.save_message(conversation.id, "user", "先处理另一个问题")

    assert restore_retryable_turn_recovery(
        db,
        user_id=user.id,
        user_message=retry_user,
    ) is None


def test_materialize_retry_images_uses_owner_scoped_reader(monkeypatch):
    from app.services.agent_turn_retry import RetryableTurnRecovery

    calls = []

    def fake_read_owned(relative_url, user_id):
        calls.append((relative_url, user_id))
        return "data:image/jpeg;base64,YQ=="

    monkeypatch.setattr(
        "app.services.chat_utils.read_owned_chat_image_data_uri",
        fake_read_owned,
    )
    recovery = RetryableTurnRecovery(
        source_message_id=8,
        root_source_message_id=8,
        action_source_message_id=8,
        trigger_assistant_message_id=9,
        conversation_id=3,
        message="记录晚餐",
        image_urls=("/api/v1/upload/files/chat/7/dinner.jpg",),
    )

    assert materialize_retryable_turn_images(recovery, user_id=7) == [
        {
            "base64": "data:image/jpeg;base64,YQ==",
            "type": "jpeg",
        }
    ]
    assert calls == [("/api/v1/upload/files/chat/7/dinner.jpg", 7)]


@pytest.mark.asyncio
async def test_executor_rehydrates_explicit_retry_before_running_turn(
    db, auth_user_and_headers, monkeypatch
):
    from app.services.agent_conversation_service import AgentConversationService
    from app.services.agent_executor import AgentExecutor

    user, _ = auth_user_and_headers
    service = AgentConversationService(db)
    conversation = service.get_or_create_conversation(
        user.id,
        None,
        title="执行器恢复",
    )
    source, _ = _save_failed_turn(
        service,
        user.id,
        conversation.id,
        image_url=None,
        message=(
            "记录晚餐：牛排和蔬菜，520千卡，蛋白质42克，"
            "碳水18克，脂肪30克，膳食纤维5克"
        ),
    )
    executor = AgentExecutor(db)
    captured = {}

    async def fake_run_stream_impl(**kwargs):
        captured.update(kwargs)
        yield {
            "event": "done",
            "data": {
                "conversation_id": conversation.id,
                "message_id": None,
                "completion_status": "complete",
            },
        }

    monkeypatch.setattr(executor, "_run_stream_impl", fake_run_stream_impl)

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="需要",
            conversation_id=conversation.id,
        )
    ]

    assert events[-1]["event"] == "done"
    assert captured["message"] == source.content
    assert captured["display_message"] == "需要"
    assert captured["retry_recovery"].source_message_id == source.id
    assert captured["persist_images"] == []


@pytest.mark.asyncio
async def test_executor_rehydrates_source_image_without_persisting_duplicate(
    db, auth_user_and_headers, monkeypatch
):
    from app.services.agent_conversation_service import AgentConversationService
    from app.services.agent_executor import AgentExecutor

    user, _ = auth_user_and_headers
    service = AgentConversationService(db)
    conversation = service.get_or_create_conversation(
        user.id,
        None,
        title="图片恢复",
    )
    source, _ = _save_failed_turn(
        service,
        user.id,
        conversation.id,
        image_url=json.dumps(
            [f"/api/v1/upload/files/chat/{user.id}/dinner.jpg"]
        ),
        message="记录这餐",
    )
    executor = AgentExecutor(db)
    captured = {}

    monkeypatch.setattr(
        "app.services.chat_utils.read_owned_chat_image_data_uri",
        lambda relative_url, owner_id: "data:image/jpeg;base64,YQ==",
    )

    async def fake_run_stream_impl(**kwargs):
        captured.update(kwargs)
        yield {
            "event": "done",
            "data": {
                "conversation_id": conversation.id,
                "message_id": None,
                "completion_status": "complete",
            },
        }

    monkeypatch.setattr(executor, "_run_stream_impl", fake_run_stream_impl)

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="重试",
            conversation_id=conversation.id,
        )
    ]

    assert events[-1]["event"] == "done"
    assert captured["message"] == source.content
    assert captured["images"] == [
        {
            "base64": "data:image/jpeg;base64,YQ==",
            "type": "jpeg",
        }
    ]
    assert captured["persist_images"] == []
    assert captured["retry_recovery"].image_urls == (
        f"/api/v1/upload/files/chat/{user.id}/dinner.jpg",
    )


@pytest.mark.asyncio
async def test_retry_executes_original_write_but_persists_user_confirmation(
    db, auth_user_and_headers, monkeypatch
):
    from app.services.agent_conversation_service import AgentConversationService
    from app.services.agent_executor import AgentExecutor

    user, _ = auth_user_and_headers
    service = AgentConversationService(db)
    conversation = service.get_or_create_conversation(
        user.id,
        None,
        title="恢复写入闭环",
    )
    source, _ = _save_failed_turn(
        service,
        user.id,
        conversation.id,
        image_url=None,
        message=(
            "记录晚餐：牛排和蔬菜，520千卡，蛋白质42克，"
            "碳水18克，脂肪30克，膳食纤维5克"
        ),
    )
    executor = AgentExecutor(db)
    llm_calls = 0
    dispatched = []

    async def fake_call_llm(messages, tools):
        nonlocal llm_calls
        llm_calls += 1
        current_user = next(
            item
            for item in reversed(messages)
            if item.get("role") == "user"
        )
        assert "记录晚餐：牛排和蔬菜" in str(current_user.get("content"))
        if llm_calls == 1:
            return {
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [{
                    "id": "retry-diet-write",
                    "function": {
                        "name": "health_record",
                        "arguments": json.dumps({
                            "record_type": "diet",
                            "data": {
                                "meal_type": "dinner",
                                "food_items": [
                                    {"name": "牛排"},
                                    {"name": "蔬菜"},
                                ],
                                "calories": 520,
                                "protein": 42,
                                "carbs": 18,
                                "fat": 30,
                                "fiber": 5,
                            },
                        }, ensure_ascii=False),
                    },
                }],
            }
        return {
            "content": "晚餐已记录。",
            "finish_reason": "stop",
        }

    async def fake_call_llm_stream(messages, tools):
        result = await fake_call_llm(messages, tools)
        if result.get("content"):
            yield {"type": "content", "text": result["content"]}
        if result.get("tool_calls"):
            yield {"type": "tool_calls", "tool_calls": result["tool_calls"]}
        yield {"type": "finish", "finish_reason": result.get("finish_reason")}

    async def fake_dispatch(request, user_token):
        dispatched.append((request.tool_name, request.arguments))
        return json.dumps(
            {
                "id": 951,
                "meal_type": "dinner",
                "calories": 520,
                "protein": 42,
                "carbs": 18,
                "fat": 30,
                "fiber": 5,
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(executor, "_call_llm", fake_call_llm)
    monkeypatch.setattr(executor, "_call_llm_stream", fake_call_llm_stream)
    monkeypatch.setattr(executor, "_dispatch_tool_request", fake_dispatch)

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="需要",
            conversation_id=conversation.id,
            client_turn_id="retry-success-turn",
            user_auth_token="test-token",
        )
    ]

    done = next(event for event in events if event.get("event") == "done")
    retry_user = service.find_user_message_by_client_turn(
        user.id,
        "retry-success-turn",
    )
    retry_assistant = service.find_assistant_message_by_client_turn(
        user.id,
        "retry-success-turn",
    )

    assert dispatched and dispatched[0][0] == "health_record"
    assert dispatched[0][1]["record_type"] == "diet"
    assert retry_user.content == "需要"
    assert retry_user.image_url is None
    assert retry_user.meta["retry_source"]["source_message_id"] == source.id
    assert done["data"]["write_receipts"]
    assert "recovery_action" not in done["data"]
    assert "recovery_action" not in retry_assistant.meta


def _mixed_retry_fixture():
    from datetime import datetime, timezone
    from app.services.intake_retry import build_intake_retry_plan
    text = '记录吃了两粒鱼油，喝了一杯豆浆'
    checkpoint = build_intake_retry_plan(
        source_text=text, owner_id=1, conversation_id=2, source_message_id=3,
        local_date='2026-10-24', timezone='Asia/Shanghai', item_fingerprints=['a', 'b'],
    )
    meta = {'intake_retry_plan': checkpoint,
            'write_plan': {'sealed': True, 'fingerprints': ['a', 'b']},
            'write_operations': {'a': {'status': 'verified', 'receipt_operation_id': 'r1'},
                                 'b': {'status': 'failed', 'no_side_effect': True}},
            'write_receipts': [{'operation_id': 'r1', 'verified': True}]}
    kwargs = dict(source_text=text, owner_id=1, conversation_id=2, source_message_id=3,
                  meta=meta, now=datetime(2026, 10, 24, 4, tzinfo=timezone.utc))
    return kwargs


def test_mixed_retry_selects_only_proven_unwritten_item():
    from app.services.intake_retry import resolve_intake_retry_selection
    result = resolve_intake_retry_selection(**_mixed_retry_fixture())
    assert result is not None
    assert result.item_indexes == (1,)
    assert '豆浆' in result.message and '鱼油' not in result.message


@pytest.mark.parametrize('mutation', [
    'owner', 'conversation', 'source_id', 'text', 'tomorrow', 'unknown',
    'no_proof', 'missing_receipt', 'extra_receipt', 'missing_operation',
    'duplicate_mapping', 'unsealed', 'extra_operation',
])
def test_mixed_retry_refuses_incomplete_or_drifted_proof(mutation):
    from datetime import timedelta
    from app.services.intake_retry import resolve_intake_retry_selection
    kw = _mixed_retry_fixture()
    meta = kw['meta']
    if mutation == 'owner': kw['owner_id'] = 9
    elif mutation == 'conversation': kw['conversation_id'] = 9
    elif mutation == 'source_id': kw['source_message_id'] = 9
    elif mutation == 'text': kw['source_text'] += '，还吃了一个苹果'
    elif mutation == 'tomorrow': kw['now'] += timedelta(days=1)
    elif mutation == 'unknown': meta['write_operations']['b']['status'] = 'uncertain'
    elif mutation == 'no_proof': meta['write_operations']['b'].pop('no_side_effect')
    elif mutation == 'missing_receipt': meta['write_receipts'] = []
    elif mutation == 'extra_receipt': meta['write_receipts'].append({'operation_id': 'r2'})
    elif mutation == 'missing_operation': del meta['write_operations']['b']
    elif mutation == 'duplicate_mapping': meta['intake_retry_plan']['items'][1]['fingerprint'] = 'a'
    elif mutation == 'unsealed': meta['intake_retry_plan']['sealed'] = False
    elif mutation == 'extra_operation': meta['write_operations']['c'] = {'status': 'planned'}
    assert resolve_intake_retry_selection(**kw) is None


def test_partial_intake_action_pins_selection_and_never_replays_success(db, auth_user_and_headers):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from app.services.agent_conversation_service import AgentConversationService
    from app.services.intake_retry import build_intake_retry_plan
    user, _ = auth_user_and_headers
    service = AgentConversationService(db)
    conversation = service.get_or_create_conversation(user.id, None, title='mixed retry')
    source, assistant = _save_failed_turn(service, user.id, conversation.id,
                                         message='记录吃了两粒鱼油，喝了一杯豆浆', image_url=None)
    meta = _mixed_retry_fixture()['meta']
    meta['intake_retry_plan'] = build_intake_retry_plan(
        source_text=source.content, owner_id=user.id, conversation_id=conversation.id,
        source_message_id=source.id, local_date=datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat(),
        timezone='Asia/Shanghai', item_fingerprints=['a', 'b'])
    source.meta = meta
    db.commit()
    action = build_retry_source_action_if_safe(source_message=source,
        turn_outcome={'retryable': True, 'category': 'tool_failed'},
        write_receipts=meta['write_receipts'], health_write_requested=True)
    assert action is not None
    assert action['scope'] == 'intake_pending_items'
    assert action['pending_item_indexes'] == [1]
    assistant.meta = {**assistant.meta, 'recovery_action': action}
    db.commit()
    recovery = resolve_retryable_turn_recovery(db, user_id=user.id,
        conversation_id=conversation.id, confirmation_text='重试')
    assert recovery is not None
    assert '豆浆' in recovery.message and '鱼油' not in recovery.message
    assert recovery.image_urls == ()
    assistant.meta = {**assistant.meta, 'recovery_action': {**action, 'pending_item_indexes': [0, 1]}}
    db.commit()
    assert resolve_retryable_turn_recovery(db, user_id=user.id,
        conversation_id=conversation.id, confirmation_text='重试') is None


def test_mixed_retry_multiple_pending_stays_parseable_and_requires_verified_receipt():
    from app.services.intake_plan import parse_intake_plan
    from app.services.intake_retry import build_intake_retry_plan, resolve_intake_retry_selection
    kw = _mixed_retry_fixture()
    kw['source_text'] = '记录吃了两粒鱼油，喝了一杯豆浆，喝了半杯牛奶'
    kw['meta']['intake_retry_plan'] = build_intake_retry_plan(
        source_text=kw['source_text'], owner_id=1, conversation_id=2, source_message_id=3,
        local_date='2026-10-24', timezone='Asia/Shanghai', item_fingerprints=['a', 'b', 'c'])
    kw['meta']['write_plan']['fingerprints'].append('c')
    kw['meta']['write_operations']['c'] = {'status': 'rejected', 'no_side_effect': True}
    result = resolve_intake_retry_selection(**kw)
    assert result is not None
    plan = parse_intake_plan(result.message)
    assert plan.status == 'complete' and len(plan.items) == 2
    kw['meta']['write_receipts'][0]['verified'] = False
    assert resolve_intake_retry_selection(**kw) is None


def test_mixed_retry_restore_keeps_selection_and_refuses_ambiguous_retry_dispatch(db, auth_user_and_headers):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from app.services.agent_conversation_service import AgentConversationService
    from app.services.intake_retry import build_intake_retry_plan
    user, _ = auth_user_and_headers
    service = AgentConversationService(db)
    conversation = service.get_or_create_conversation(user.id, None, title='mixed restore')
    source, assistant = _save_failed_turn(service, user.id, conversation.id,
                                         message='记录吃了两粒鱼油，喝了一杯豆浆', image_url=None)
    meta = _mixed_retry_fixture()['meta']
    meta['intake_retry_plan'] = build_intake_retry_plan(
        source_text=source.content, owner_id=user.id, conversation_id=conversation.id,
        source_message_id=source.id, local_date=datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat(),
        timezone='Asia/Shanghai', item_fingerprints=['a', 'b'])
    source.meta = meta
    db.commit()
    action = build_retry_source_action_if_safe(source_message=source,
        turn_outcome={'retryable': True, 'category': 'tool_failed'},
        write_receipts=meta['write_receipts'], health_write_requested=True)
    assistant.meta = {**assistant.meta, 'recovery_action': action}
    db.commit()
    recovery = resolve_retryable_turn_recovery(db, user_id=user.id,
        conversation_id=conversation.id, confirmation_text='重试')
    retry, _ = service.save_user_message_once(conversation.id, user.id, '重试',
        client_turn_id='mixed-retry', meta={'retry_source': recovery.user_message_meta()})
    restored = restore_retryable_turn_recovery(db, user_id=user.id, user_message=retry)
    assert restored is not None and restored.message == recovery.message
    retry.meta = {**retry.meta, 'write_operations': {'retry-fp': {'status': 'failed'}}}
    db.commit()
    assert restore_retryable_turn_recovery(db, user_id=user.id, user_message=retry) is None


@pytest.mark.parametrize('status,category,expected', [
    ('partial', 'action_not_executed', True),
    ('partial', 'tool_failed', True),
    ('partial', 'policy_blocked', False),
    ('blocked', 'action_not_executed', False),
    ('unknown', 'action_not_executed', False),
    ('failed', 'action_not_executed', False),
])
def test_partial_selection_does_not_require_global_resubmit_permission(status, category, expected):
    from types import SimpleNamespace
    kw = _mixed_retry_fixture()
    source = SimpleNamespace(id=3, conversation_id=2, content=kw['source_text'],
        conversation=SimpleNamespace(user_id=1), meta=kw['meta'], image_url=None)
    action = build_retry_source_action_if_safe(source_message=source,
        turn_outcome={'status': status, 'category': category, 'retryable': False},
        write_receipts=kw['meta']['write_receipts'], health_write_requested=True, now=kw['now'])
    assert (action is not None) is expected


def test_scoped_retry_carries_sealed_timezone_and_date(db, auth_user_and_headers):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from app.services.agent_conversation_service import AgentConversationService
    from app.services.intake_retry import build_intake_retry_plan
    user, _ = auth_user_and_headers
    service = AgentConversationService(db)
    conversation = service.get_or_create_conversation(user.id, None, title='date-bound retry')
    source, assistant = _save_failed_turn(service, user.id, conversation.id,
        message='记录吃了两粒鱼油，喝了一杯豆浆', image_url=None)
    local_date = datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()
    meta = _mixed_retry_fixture()['meta']
    meta['intake_retry_plan'] = build_intake_retry_plan(source_text=source.content,
        owner_id=user.id, conversation_id=conversation.id, source_message_id=source.id,
        local_date=local_date, timezone='Asia/Shanghai', item_fingerprints=['a', 'b'])
    source.meta = meta
    db.commit()
    action = build_retry_source_action_if_safe(source_message=source,
        turn_outcome={'status': 'partial', 'category': 'action_not_executed', 'retryable': False},
        write_receipts=meta['write_receipts'], health_write_requested=True)
    assistant.meta = {**assistant.meta, 'recovery_action': action}
    db.commit()
    recovery = resolve_retryable_turn_recovery(db, user_id=user.id,
        conversation_id=conversation.id, confirmation_text='重试')
    assert recovery.intake_local_date == local_date
    assert recovery.intake_timezone == 'Asia/Shanghai'
    retry, _ = service.save_user_message_once(conversation.id, user.id, '重试',
        client_turn_id='date-bound-retry', meta={'retry_source': recovery.user_message_meta()})
    restored = restore_retryable_turn_recovery(db, user_id=user.id, user_message=retry)
    assert restored.intake_local_date == local_date
    assert restored.intake_timezone == 'Asia/Shanghai'


def _prepare_intake_claim(service, user_id, conversation_id):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from app.services.intake_retry import build_intake_retry_plan
    source, assistant = _save_failed_turn(service, user_id, conversation_id,
        message='记录吃了两粒鱼油，喝了一杯豆浆', image_url=None)
    meta = _mixed_retry_fixture()['meta']
    meta['intake_retry_plan'] = build_intake_retry_plan(source_text=source.content,
        owner_id=user_id, conversation_id=conversation_id, source_message_id=source.id,
        local_date=datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat(),
        timezone='Asia/Shanghai', item_fingerprints=['a', 'b'])
    source.meta = meta
    service.db.commit()
    action = build_retry_source_action_if_safe(source_message=source,
        turn_outcome={'status': 'partial', 'category': 'action_not_executed', 'retryable': False},
        write_receipts=meta['write_receipts'], health_write_requested=True)
    assistant.meta = {**assistant.meta, 'recovery_action': action}
    service.db.commit()
    recovery = resolve_retryable_turn_recovery(service.db, user_id=user_id,
        conversation_id=conversation_id, confirmation_text='重试')
    retries = [service.save_user_message_once(conversation_id, user_id, '重试',
        client_turn_id=f'claim-{n}', meta={'retry_source': recovery.user_message_meta()})[0]
        for n in range(2)]
    return recovery, [m.id for m in retries]


def test_intake_claim_single_winner_same_message_resume(db, auth_user_and_headers):
    from app.services.agent_conversation_service import AgentConversationService
    from app.services.agent_turn_retry import claim_intake_retry_source
    from app.models.agent_conversation import AgentMessage
    user, _ = auth_user_and_headers
    service = AgentConversationService(db)
    conv = service.get_or_create_conversation(user.id, None, title='claim')
    recovery, ids = _prepare_intake_claim(service, user.id, conv.id)
    assert claim_intake_retry_source(db, user_id=user.id, recovery=recovery, retry_message_id=ids[0])
    assert claim_intake_retry_source(db, user_id=user.id, recovery=recovery, retry_message_id=ids[0])
    assert not claim_intake_retry_source(db, user_id=user.id, recovery=recovery, retry_message_id=ids[1])
    claim = db.get(AgentMessage, recovery.source_message_id).meta['intake_retry_claim']
    assert claim == {'version': 1, 'retry_message_id': ids[0],
                     'plan_digest': recovery.intake_plan_digest,
                     'pending_item_indexes': list(recovery.pending_item_indexes)}


def test_intake_claim_stale_two_session_compare_and_swap(db, auth_user_and_headers, monkeypatch):
    from sqlalchemy.orm import Session
    from sqlalchemy.sql.dml import Update
    from app.services.agent_conversation_service import AgentConversationService
    from app.services.agent_turn_retry import claim_intake_retry_source
    user, _ = auth_user_and_headers
    service = AgentConversationService(db)
    conv = service.get_or_create_conversation(user.id, None, title='claim race')
    recovery, ids = _prepare_intake_claim(service, user.id, conv.id)
    owner_id = user.id
    with Session(db.get_bind()) as rival:
        execute = rival.execute
        def interleave(statement, *args, **kwargs):
            if isinstance(statement, Update):
                assert claim_intake_retry_source(db, user_id=owner_id, recovery=recovery, retry_message_id=ids[0])
            return execute(statement, *args, **kwargs)
        monkeypatch.setattr(rival, 'execute', interleave)
        assert not claim_intake_retry_source(rival, user_id=owner_id, recovery=recovery, retry_message_id=ids[1])


def test_intake_claim_postgres_concurrent_winner(db, auth_user_and_headers, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    from sqlalchemy.orm import Session
    from sqlalchemy.sql.dml import Update
    from app.services.agent_conversation_service import AgentConversationService
    from app.services.agent_turn_retry import claim_intake_retry_source
    if db.get_bind().dialect.name != 'postgresql':
        pytest.skip('real PostgreSQL concurrency gate')
    user, _ = auth_user_and_headers
    service = AgentConversationService(db)
    conv = service.get_or_create_conversation(user.id, None, title='concurrent claim')
    recovery, ids = _prepare_intake_claim(service, user.id, conv.id)
    owner_id, engine = user.id, db.get_bind()
    barrier = threading.Barrier(2, timeout=10)
    execute = Session.execute
    def interleave(session, statement, *args, **kwargs):
        if isinstance(statement, Update):
            barrier.wait()
        return execute(session, statement, *args, **kwargs)
    monkeypatch.setattr(Session, 'execute', interleave)
    def claim(message_id):
        with Session(engine) as session:
            return claim_intake_retry_source(session, user_id=owner_id, recovery=recovery, retry_message_id=message_id)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, ids))
    assert sorted(results) == [False, True]


def test_intake_claim_propagates_database_error_without_claim(db, auth_user_and_headers, monkeypatch):
    from sqlalchemy.sql.dml import Update
    from app.services.agent_conversation_service import AgentConversationService
    from app.services.agent_turn_retry import claim_intake_retry_source
    from app.models.agent_conversation import AgentMessage
    user, _ = auth_user_and_headers
    service = AgentConversationService(db)
    conv = service.get_or_create_conversation(user.id, None, title='claim error')
    recovery, ids = _prepare_intake_claim(service, user.id, conv.id)
    execute = db.execute
    def fail(statement, *args, **kwargs):
        if isinstance(statement, Update):
            raise RuntimeError('synthetic database failure')
        return execute(statement, *args, **kwargs)
    monkeypatch.setattr(db, 'execute', fail)
    with pytest.raises(RuntimeError, match='synthetic database failure'):
        claim_intake_retry_source(db, user_id=user.id, recovery=recovery, retry_message_id=ids[0])
    assert 'intake_retry_claim' not in db.get(AgentMessage, recovery.source_message_id).meta


@pytest.mark.parametrize('mutation', ['owner', 'conversation', 'source', 'pending', 'retry_binding', 'retry_uncertain'])
def test_intake_claim_revalidates_scope_before_cas(db, auth_user_and_headers, mutation):
    from dataclasses import replace
    from app.services.agent_conversation_service import AgentConversationService
    from app.services.agent_turn_retry import claim_intake_retry_source
    from app.models.agent_conversation import AgentMessage
    user, _ = auth_user_and_headers
    service = AgentConversationService(db)
    conv = service.get_or_create_conversation(user.id, None, title='claim scope')
    recovery, ids = _prepare_intake_claim(service, user.id, conv.id)
    owner_id = user.id
    if mutation == 'owner': owner_id += 999
    elif mutation == 'conversation': recovery = replace(recovery, conversation_id=conv.id+999)
    elif mutation == 'source': recovery = replace(recovery, source_message_id=recovery.source_message_id+999)
    elif mutation == 'pending': recovery = replace(recovery, pending_item_indexes=(0, 1))
    else:
        retry = db.get(AgentMessage, ids[0])
        if mutation == 'retry_binding': retry.meta = {'retry_source': {}}
        else: retry.meta = {**retry.meta, 'write_operations': {'x': {'status': 'uncertain'}}}
        db.commit()
    assert not claim_intake_retry_source(db, user_id=owner_id, recovery=recovery, retry_message_id=ids[0])


@pytest.mark.parametrize("cached_message", ["source", "retry"])
def test_intake_claim_resume_refreshes_cached_source_proof(db, auth_user_and_headers, cached_message):
    from sqlalchemy import update
    from sqlalchemy.orm import Session
    from app.services.agent_conversation_service import AgentConversationService
    from app.services.agent_turn_retry import claim_intake_retry_source
    from app.models.agent_conversation import AgentMessage
    user, _ = auth_user_and_headers
    service = AgentConversationService(db)
    conv = service.get_or_create_conversation(user.id, None, title='stale claim proof')
    recovery, ids = _prepare_intake_claim(service, user.id, conv.id)
    assert claim_intake_retry_source(db, user_id=user.id, recovery=recovery, retry_message_id=ids[0])
    source = db.get(AgentMessage, recovery.source_message_id if cached_message == "source" else ids[0])
    original = source.meta
    changed = {**original, 'write_operations': {**original.get('write_operations', {}), 'b': {'status': 'uncertain'}}}
    with Session(db.get_bind()) as other:
        other.execute(update(AgentMessage).where(AgentMessage.id == source.id).values(meta=changed))
        other.commit()
    assert source.meta == original  # identity map still holds the old proof
    assert not claim_intake_retry_source(db, user_id=user.id, recovery=recovery, retry_message_id=ids[0])


def test_intake_claim_resume_checks_retry_metadata_at_cas(db, auth_user_and_headers, monkeypatch):
    from sqlalchemy import update
    from sqlalchemy.orm import Session
    from sqlalchemy.sql.dml import Update
    from app.services.agent_conversation_service import AgentConversationService
    from app.services.agent_turn_retry import claim_intake_retry_source
    from app.models.agent_conversation import AgentMessage
    user, _ = auth_user_and_headers
    service = AgentConversationService(db)
    conv = service.get_or_create_conversation(user.id, None, title='retry CAS drift')
    recovery, ids = _prepare_intake_claim(service, user.id, conv.id)
    assert claim_intake_retry_source(db, user_id=user.id, recovery=recovery, retry_message_id=ids[0])
    retry = db.get(AgentMessage, ids[0])
    changed = {**retry.meta, 'write_operations': {'x': {'status': 'in_flight'}}}
    execute = db.execute
    def interleave(statement, *args, **kwargs):
        if isinstance(statement, Update):
            with Session(db.get_bind()) as other:
                other.execute(update(AgentMessage).where(AgentMessage.id == ids[0]).values(meta=changed))
                other.commit()
        return execute(statement, *args, **kwargs)
    monkeypatch.setattr(db, 'execute', interleave)
    assert not claim_intake_retry_source(db, user_id=user.id, recovery=recovery, retry_message_id=ids[0])
