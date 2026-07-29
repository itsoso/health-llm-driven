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
