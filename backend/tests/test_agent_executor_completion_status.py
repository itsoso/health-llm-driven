import json
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.agents.safety_guardian.schema import Alert, Severity
from app.models.blood_pressure import BloodPressureRecord
from app.models.user_profile import UserProfile
from app.models.agent_conversation import AgentMessage
from app.services.agent_executor import (
    INTERRUPTED_COMPLETION_NOTICE,
    AgentExecutor,
    _completion_status_from_finish_reason,
    _write_checkpoint_status_after_dispatch,
    _write_result_is_pre_dispatch_validation_error,
    _write_tool_completed,
)


# mobile/components/chat/cards/registry.tsx 的 ALLOWED_ACTIONS 客户端硬门:
# 卡片 action 不在此集合内会被客户端直接丢弃。后端发卡必须落在这个面里。
CLIENT_ACTION_ALLOWLIST = {
    "agenda.complete",
    "write_intent.confirm",
    "write_intent.dismiss",
    "route.open",
    "ui.inline.expand",
}


def _stream_from(fake_call_llm):
    """把旧式 fake_call_llm(messages, tools) -> dict 适配成 run_stream 现在用的
    _call_llm_stream(messages, tools) -> AsyncIterator[event]。

    run_stream 第一轮走 _call_llm_stream (真流式 seam); 空回复重试/兜底仍走
    _call_llm。共用同一个 fake_call_llm 保证调用计数序列不变。
    """
    async def fake_call_llm_stream(messages, tools):
        result = await fake_call_llm(messages, tools)
        if isinstance(result, dict):
            content = result.get("content") or ""
            if content:
                yield {"type": "content", "text": content}
            tool_calls = result.get("tool_calls")
            if tool_calls:
                yield {"type": "tool_calls", "tool_calls": tool_calls}
            yield {"type": "finish", "finish_reason": result.get("finish_reason")}
        else:
            text = str(result or "")
            if text:
                yield {"type": "content", "text": text}
            yield {"type": "finish", "finish_reason": "stop"}

    return fake_call_llm_stream


def test_completion_status_marks_length_finish_reason_as_interrupted():
    assert _completion_status_from_finish_reason("length") == "interrupted"


def test_completion_status_marks_stop_finish_reason_as_complete():
    assert _completion_status_from_finish_reason("stop") == "complete"


def test_completion_status_marks_error_finish_reason_as_error():
    assert _completion_status_from_finish_reason("error") == "error"


def test_local_write_validation_error_is_not_an_uncertain_dispatch():
    result = (
        "Error: sleep 记录必须提供 bedtime、wake_time、sleep_quality(1-5). "
        "缺少: bedtime, wake_time."
    )

    assert _write_result_is_pre_dispatch_validation_error(result) is True
    assert _write_checkpoint_status_after_dispatch(result, None) == "rejected"


def test_remote_write_error_remains_uncertain_after_dispatch():
    result = "Error: upstream returned 500 after request dispatch"

    assert _write_result_is_pre_dispatch_validation_error(result) is False
    assert _write_checkpoint_status_after_dispatch(result, None) == "uncertain"


@pytest.mark.parametrize("result", [
    "未找到活跃药物",
    "写入完成",
])
def test_unstructured_write_result_is_never_reported_as_completed(result):
    assert _write_tool_completed(
        "health_manage",
        {"operation": "update"},
        result,
    ) is False


def test_structured_write_result_with_resource_identity_is_completed():
    assert _write_tool_completed(
        "health_manage",
        {"record_type": "diet", "operation": "update"},
        '{"success":true,"id":42}',
    ) is True


def test_structured_write_result_without_resource_identity_is_not_completed():
    assert _write_tool_completed(
        "health_manage",
        {"record_type": "diet", "operation": "delete", "record_id": 42},
        '{"message":"Record deleted successfully"}',
    ) is False


@pytest.mark.asyncio
async def test_identityless_write_result_cannot_render_or_finish_as_success(
    db, auth_user_and_headers, monkeypatch
):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    calls = 0

    async def fake_call_llm(messages, tools):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [{
                    "id": "delete-1",
                    "function": {
                        "name": "health_manage",
                        "arguments": json.dumps({
                            "record_type": "diet",
                            "operation": "delete",
                            "record_id": 42,
                        }),
                    },
                }],
            }
        return {"content": "已经删除。", "finish_reason": "stop"}

    async def fake_execute_tool(name, args, token):
        return '{"message":"Record deleted successfully"}'

    monkeypatch.setattr(executor, "_build_system_prompt", lambda *args, **kwargs: "SYS")
    monkeypatch.setattr("app.services.agent_executor.get_health_tools", lambda subset=None: [])
    monkeypatch.setattr(executor, "_call_llm", fake_call_llm)
    monkeypatch.setattr(executor, "_call_llm_stream", _stream_from(fake_call_llm))
    monkeypatch.setattr(executor, "_execute_tool", fake_execute_tool)

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="删除记录 42",
            user_auth_token="test-token",
            client_turn_id="turn-delete-no-identity",
        )
    ]

    rendered = "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )
    assert "不能确认" in rendered
    assert "deleted successfully" not in rendered.lower()
    assert "已经删除" not in rendered
    done = next(event for event in events if event.get("event") == "done")
    assert done["data"]["completion_status"] == "error"
    assert done["data"]["write_receipts"] == []


@pytest.mark.asyncio
async def test_later_verified_same_write_clears_uncertain_checkpoint(
    db, auth_user_and_headers, monkeypatch
):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    calls = 0
    executions = 0

    async def fake_call_llm(messages, tools):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [
                    {
                        "id": "delete-no-receipt",
                        "function": {
                            "name": "health_manage",
                            "arguments": json.dumps({
                                "record_type": "diet",
                                "operation": "delete",
                                "record_id": 829,
                            }),
                        },
                    },
                    {
                        "id": "delete-with-receipt",
                        "function": {
                            "name": "health_manage",
                            "arguments": json.dumps({
                                "record_type": "diet",
                                "operation": "delete",
                                "record_id": 829,
                                "confirmed": True,
                            }),
                        },
                    },
                ],
            }
        return {"content": "已删除这条饮食记录。", "finish_reason": "stop"}

    async def fake_execute_tool(name, args, token):
        nonlocal executions
        executions += 1
        if executions == 1:
            return '{"message":"Record deleted successfully"}'
        return json.dumps(
            {
                "status": "verified",
                "success": True,
                "resource_type": "diet_record",
                "resource_id": "829",
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(executor, "_build_system_prompt", lambda *args, **kwargs: "SYS")
    monkeypatch.setattr("app.services.agent_executor.get_health_tools", lambda subset=None: [])
    monkeypatch.setattr(executor, "_call_llm", fake_call_llm)
    monkeypatch.setattr(executor, "_call_llm_stream", _stream_from(fake_call_llm))
    monkeypatch.setattr(executor, "_execute_tool", fake_execute_tool)

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="删除这条饮食记录",
            user_auth_token="test-token",
            client_turn_id="turn-delete-later-verified",
        )
    ]
    rendered = "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )

    assert "不能确认" not in rendered
    assert "已删除这条饮食记录" in rendered
    done = next(event for event in events if event.get("event") == "done")
    assert done["data"]["completion_status"] == "complete"
    assert done["data"]["write_receipts"][0]["resource_type"] == "diet_record"
    assert done["data"]["write_receipts"][0]["resource_id"] == "829"


@pytest.mark.asyncio
async def test_http_500_after_dispatched_write_is_uncertain_and_orphan_retry_does_not_reexecute(
    db, auth_user_and_headers, monkeypatch
):
    user, _ = auth_user_and_headers
    turn_id = "turn-write-committed-then-500"
    message = "记录午餐鸡胸肉"
    executor = AgentExecutor(db)

    async def first_llm_call(messages, tools):
        return {
            "content": "",
            "finish_reason": "tool_calls",
            "tool_calls": [{
                "id": "write-500",
                "function": {
                    "name": "health_record",
                    "arguments": json.dumps({
                        "record_type": "diet",
                        "data": {"food_items": "鸡胸肉", "meal_type": "lunch"},
                    }),
                },
            }],
        }

    async def committed_then_500(name, args, token):
        return "Error: upstream returned 500 after request dispatch"

    monkeypatch.setattr(executor, "_build_system_prompt", lambda *args, **kwargs: "SYS")
    monkeypatch.setattr("app.services.agent_executor.get_health_tools", lambda subset=None: [])
    monkeypatch.setattr(executor, "_call_llm", first_llm_call)
    monkeypatch.setattr(executor, "_call_llm_stream", _stream_from(first_llm_call))
    monkeypatch.setattr(executor, "_execute_tool", committed_then_500)

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message=message,
            user_auth_token="test-token",
            client_turn_id=turn_id,
        )
    ]
    assert next(event for event in events if event.get("event") == "done")["data"][
        "completion_status"
    ] == "error"

    user_message = db.query(AgentMessage).filter(
        AgentMessage.role == "user",
        AgentMessage.content == message,
    ).one()
    assert user_message.meta["write_state"]["status"] == "uncertain"

    for assistant in db.query(AgentMessage).filter(
        AgentMessage.role == "assistant",
        AgentMessage.conversation_id == user_message.conversation_id,
    ).all():
        db.delete(assistant)
    db.commit()

    retry_llm_calls = 0
    retry_executor = AgentExecutor(db)

    async def retry_llm_call(messages, tools):
        nonlocal retry_llm_calls
        retry_llm_calls += 1
        return {"content": "不应再次进入模型或写工具", "finish_reason": "stop"}

    monkeypatch.setattr(retry_executor, "_build_system_prompt", lambda *args, **kwargs: "SYS")
    monkeypatch.setattr(retry_executor, "_call_llm", retry_llm_call)
    monkeypatch.setattr(retry_executor, "_call_llm_stream", _stream_from(retry_llm_call))
    retry_events = [
        event
        async for event in retry_executor.run_stream(
            user_id=user.id,
            message=message,
            user_auth_token="test-token",
            client_turn_id=turn_id,
        )
    ]

    assert retry_llm_calls == 0
    recovered = "".join(
        event["data"].get("content", "")
        for event in retry_events
        if event.get("event") == "token"
    )
    assert "没有自动重试" in recovered


@pytest.mark.asyncio
async def test_pre_dispatch_sleep_validation_returns_to_model_without_unverified_write_claim(
    db, auth_user_and_headers, monkeypatch
):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    calls = 0
    validation_error = (
        "Error: sleep 记录必须提供 bedtime、wake_time、sleep_quality(1-5). "
        "缺少: bedtime, wake_time."
    )

    async def fake_call_llm(messages, tools):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [{
                    "id": "sleep-missing-times",
                    "function": {
                        "name": "health_record",
                        "arguments": json.dumps({
                            "record_type": "sleep",
                            "data": {"sleep_quality": 5},
                        }),
                    },
                }],
            }
        return {
            "content": "还缺少入睡时间和起床时间，请补充这两个时间。",
            "finish_reason": "stop",
        }

    async def fake_execute_tool(name, args, token):
        assert name == "health_record"
        return validation_error

    monkeypatch.setattr(executor, "_build_system_prompt", lambda *args, **kwargs: "SYS")
    monkeypatch.setattr("app.services.agent_executor.get_health_tools", lambda subset=None: [])
    monkeypatch.setattr(executor, "_call_llm", fake_call_llm)
    monkeypatch.setattr(executor, "_call_llm_stream", _stream_from(fake_call_llm))
    monkeypatch.setattr(executor, "_execute_tool", fake_execute_tool)

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="已经睡了十个小时，睡眠非常好，估计有九十五分",
            user_auth_token="test-token",
            client_turn_id="turn-sleep-validation-rejected",
        )
    ]

    rendered = "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )
    assert calls == 2
    assert "还缺少入睡时间和起床时间" in rendered
    assert "本次操作没有取得可验证" not in rendered
    done = next(event for event in events if event.get("event") == "done")
    assert done["data"]["completion_status"] == "complete"
    assert done["data"]["write_receipts"] == []

    user_message = db.query(AgentMessage).filter(
        AgentMessage.role == "user",
        AgentMessage.content == "已经睡了十个小时，睡眠非常好，估计有九十五分",
    ).one()
    assert user_message.meta["write_state"]["status"] == "rejected"


@pytest.mark.asyncio
async def test_duplicate_writes_in_one_model_response_execute_once(
    db, auth_user_and_headers, monkeypatch
):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    llm_calls = 0
    tool_calls = 0
    arguments = json.dumps({
        "record_type": "diet",
        "operation": "delete",
        "record_id": 900,
    })

    async def fake_llm_call(messages, tools):
        nonlocal llm_calls
        llm_calls += 1
        if llm_calls == 1:
            return {
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [
                    {"id": "duplicate-1", "function": {"name": "health_manage", "arguments": arguments}},
                    {"id": "duplicate-2", "function": {"name": "health_manage", "arguments": arguments}},
                ],
            }
        return {"content": "记录已删除。", "finish_reason": "stop"}

    async def fake_execute_tool(name, args, token):
        nonlocal tool_calls
        tool_calls += 1
        return json.dumps({
            "id": 900,
            "record_id": 900,
            "resource_type": "diet_record",
        })

    monkeypatch.setattr(executor, "_build_system_prompt", lambda *args, **kwargs: "SYS")
    monkeypatch.setattr("app.services.agent_executor.get_health_tools", lambda subset=None: [])
    monkeypatch.setattr(executor, "_call_llm", fake_llm_call)
    monkeypatch.setattr(executor, "_call_llm_stream", _stream_from(fake_llm_call))
    monkeypatch.setattr(executor, "_execute_tool", fake_execute_tool)

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="删除饮食记录 900",
            user_auth_token="test-token",
            client_turn_id="turn-duplicate-write",
        )
    ]

    assert tool_calls == 1
    tool_results = [
        event["data"]
        for event in events
        if event.get("event") == "tool_result"
    ]
    assert len(tool_results) == 2
    assert tool_results[1]["replayed"] is True
    done = next(event for event in events if event.get("event") == "done")
    assert len(done["data"]["write_receipts"]) == 1


@pytest.mark.asyncio
async def test_client_turn_lock_is_released_when_post_acquire_lookup_raises(
    db, auth_user_and_headers, monkeypatch
):
    from app.services.agent_conversation_service import AgentConversationService

    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    find_calls = 0
    releases = []

    def fake_find_user(self, user_id, client_turn_id):
        nonlocal find_calls
        find_calls += 1
        if find_calls == 1:
            return None
        raise RuntimeError("post-acquire lookup failed")

    monkeypatch.setattr(AgentConversationService, "find_user_message_by_client_turn", fake_find_user)
    monkeypatch.setattr(
        AgentConversationService,
        "find_assistant_message_by_client_turn",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        AgentConversationService,
        "try_acquire_client_turn_execution",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        AgentConversationService,
        "release_client_turn_execution",
        lambda self, user_id, client_turn_id: releases.append((user_id, client_turn_id)),
    )

    with pytest.raises(RuntimeError, match="post-acquire lookup failed"):
        [
            event
            async for event in executor.run_stream(
                user_id=user.id,
                message="测试锁释放",
                client_turn_id="turn-release-on-lookup-error",
            )
        ]

    assert releases == [(user.id, "turn-release-on-lookup-error")]


@pytest.mark.asyncio
async def test_recovery_reports_partial_when_one_of_multiple_writes_is_uncertain(
    db, auth_user_and_headers
):
    from app.services.agent_conversation_service import AgentConversationService

    user, _ = auth_user_and_headers
    service = AgentConversationService(db)
    conversation = service.get_or_create_conversation(user.id, None, title="多条写入")
    user_message, _ = service.save_user_message_once(
        conversation.id,
        user.id,
        "记录两项",
        client_turn_id="turn-partial-multi-write",
    )
    executor = AgentExecutor(db)
    executor._persist_turn_write_state(
        user_message,
        status="uncertain",
        tool_name="health_record",
        parsed_args={"record_type": "diet", "data": {"food_items": "A"}},
    )
    receipt = {
        "operation_id": "health_record:water_record:77",
        "status": "verified",
        "resource_type": "water_record",
        "resource_id": "77",
        "completed_at": "2026-07-10T12:00:00+00:00",
        "verified": True,
    }
    executor._persist_turn_write_state(
        user_message,
        status="verified",
        tool_name="health_record",
        parsed_args={"record_type": "water", "data": {"amount": 500}},
        receipt=receipt,
    )

    events = [
        event
        async for event in executor._recover_client_turn_write_checkpoint(
            service,
            user.id,
            user_message,
            "turn-partial-multi-write",
        )
    ]
    assert "部分写入获得回执" in next(
        event for event in events if event.get("event") == "token"
    )["data"]["content"]
    assert events[-1]["data"]["completion_status"] == "error"


@pytest.mark.asyncio
async def test_recovery_reports_terminal_rejection_instead_of_unknown_write(
    db, auth_user_and_headers
):
    from app.services.agent_conversation_service import AgentConversationService

    user, _ = auth_user_and_headers
    service = AgentConversationService(db)
    conversation = service.get_or_create_conversation(user.id, None, title="拒绝写入恢复")
    user_message, _ = service.save_user_message_once(
        conversation.id,
        user.id,
        "记录睡眠",
        client_turn_id="turn-rejected-write-recovery",
    )
    executor = AgentExecutor(db)
    planned_args = {
        "record_type": "sleep",
        "data": {"sleep_quality": 5},
    }
    executor._persist_turn_expected_writes(
        user_message,
        [("health_record", planned_args)],
    )
    executor._persist_turn_write_state(
        user_message,
        status="rejected",
        tool_name="health_record",
        parsed_args=planned_args,
    )

    events = [
        event
        async for event in executor._recover_client_turn_write_checkpoint(
            service,
            user.id,
            user_message,
            "turn-rejected-write-recovery",
        )
    ]
    content = next(
        event for event in events if event.get("event") == "token"
    )["data"]["content"]

    assert "状态未知" not in content
    assert "未执行" in content or "拒绝" in content
    assert events[-1]["data"]["completion_status"] == "error"
    assert events[-1]["data"]["write_recovery"] == "write_checkpoint_rejected"


@pytest.mark.asyncio
async def test_legacy_verified_checkpoint_without_sealed_plan_never_reports_complete(
    db, auth_user_and_headers
):
    from app.services.agent_conversation_service import AgentConversationService

    user, _ = auth_user_and_headers
    service = AgentConversationService(db)
    conversation = service.get_or_create_conversation(
        user.id,
        None,
        title="旧版写入恢复",
    )
    user_message, _ = service.save_user_message_once(
        conversation.id,
        user.id,
        "删除两条旧记录",
        client_turn_id="turn-legacy-unsealed-write",
    )
    executor = AgentExecutor(db)
    executor._persist_turn_write_state(
        user_message,
        status="verified",
        tool_name="health_manage",
        parsed_args={
            "record_type": "diet",
            "operation": "delete",
            "record_id": 901,
        },
        receipt={
            "operation_id": "health_manage:diet_record:901",
            "status": "verified",
            "resource_type": "diet_record",
            "resource_id": "901",
            "completed_at": "2026-07-10T12:00:00+00:00",
            "verified": True,
        },
    )

    events = [
        event
        async for event in executor._recover_client_turn_write_checkpoint(
            service,
            user.id,
            user_message,
            "turn-legacy-unsealed-write",
        )
    ]

    assert events[-1]["data"]["completion_status"] == "error"
    assert "部分写入获得回执" in next(
        event for event in events if event.get("event") == "token"
    )["data"]["content"]


@pytest.mark.asyncio
async def test_sealed_planned_only_checkpoint_can_resume_before_any_dispatch(
    db, auth_user_and_headers, monkeypatch
):
    from app.services.agent_conversation_service import AgentConversationService

    user, _ = auth_user_and_headers
    service = AgentConversationService(db)
    conversation = service.get_or_create_conversation(
        user.id,
        None,
        title="安全恢复未执行写入",
    )
    user_message, _ = service.save_user_message_once(
        conversation.id,
        user.id,
        "删除这条记录",
        client_turn_id="turn-planned-before-dispatch",
    )
    write_args = {
        "record_type": "diet",
        "operation": "delete",
        "record_id": 902,
    }
    AgentExecutor(db)._persist_turn_expected_writes(
        user_message,
        [("health_manage", write_args)],
    )

    executor = AgentExecutor(db)
    llm_calls = 0
    tool_calls = 0

    async def fake_llm(messages, tools):
        nonlocal llm_calls
        llm_calls += 1
        if llm_calls == 1:
            return {
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [{
                    "id": "resume-write",
                    "function": {
                        "name": "health_manage",
                        "arguments": json.dumps(write_args),
                    },
                }],
            }
        return {"content": "已删除。", "finish_reason": "stop"}

    async def fake_execute_tool(name, args, token):
        nonlocal tool_calls
        tool_calls += 1
        return json.dumps({
            "id": 902,
            "record_id": 902,
            "resource_type": "diet_record",
        })

    monkeypatch.setattr(executor, "_build_system_prompt", lambda *args, **kwargs: "SYS")
    monkeypatch.setattr("app.services.agent_executor.get_health_tools", lambda subset=None: [])
    monkeypatch.setattr(executor, "_call_llm", fake_llm)
    monkeypatch.setattr(executor, "_call_llm_stream", _stream_from(fake_llm))
    monkeypatch.setattr(executor, "_execute_tool", fake_execute_tool)

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="删除这条记录",
            user_auth_token="test-token",
            client_turn_id="turn-planned-before-dispatch",
        )
    ]

    assert tool_calls == 1
    assert events[-1]["data"]["completion_status"] == "complete"


@pytest.mark.asyncio
async def test_all_planned_writes_are_checkpointed_before_first_dispatch(
    db, auth_user_and_headers, monkeypatch
):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    first_args = {
        "record_type": "diet",
        "operation": "delete",
        "record_id": 1001,
    }
    second_args = {
        "record_type": "diet",
        "operation": "delete",
        "record_id": 1002,
    }

    async def fake_llm_call(messages, tools):
        return {
            "content": "",
            "finish_reason": "tool_calls",
            "tool_calls": [
                {
                    "id": "write-a",
                    "function": {
                        "name": "health_manage",
                        "arguments": json.dumps(first_args),
                    },
                },
                {
                    "id": "write-b",
                    "function": {
                        "name": "health_manage",
                        "arguments": json.dumps(second_args),
                    },
                },
            ],
        }

    async def fake_execute_tool(name, args, token):
        parsed = json.loads(args)
        return json.dumps({
            "id": parsed["record_id"],
            "record_id": parsed["record_id"],
            "resource_type": "diet_record",
        })

    class WorkerCrashed(BaseException):
        pass

    original_persist = executor._persist_turn_write_state

    def crash_before_second_dispatch(user_message, **kwargs):
        if (
            kwargs["status"] == "in_flight"
            and kwargs["parsed_args"].get("record_id") == 1002
        ):
            raise WorkerCrashed()
        return original_persist(user_message, **kwargs)

    monkeypatch.setattr(executor, "_build_system_prompt", lambda *args, **kwargs: "SYS")
    monkeypatch.setattr("app.services.agent_executor.get_health_tools", lambda subset=None: [])
    monkeypatch.setattr(executor, "_call_llm", fake_llm_call)
    monkeypatch.setattr(executor, "_call_llm_stream", _stream_from(fake_llm_call))
    monkeypatch.setattr(executor, "_execute_tool", fake_execute_tool)
    monkeypatch.setattr(executor, "_persist_turn_write_state", crash_before_second_dispatch)

    with pytest.raises(WorkerCrashed):
        [
            event
            async for event in executor.run_stream(
                user_id=user.id,
                message="删除两条饮食记录",
                user_auth_token="test-token",
                client_turn_id="turn-two-planned-writes",
            )
        ]

    user_message = db.query(AgentMessage).filter(
        AgentMessage.role == "user",
        AgentMessage.content == "删除两条饮食记录",
    ).one()
    operations = user_message.meta["write_operations"]
    assert len(operations) == 2
    assert sorted(operation["status"] for operation in operations.values()) == [
        "planned",
        "verified",
    ]

    retry_executor = AgentExecutor(db)
    retry_llm_calls = 0

    async def retry_llm(messages, tools):
        nonlocal retry_llm_calls
        retry_llm_calls += 1
        return {"content": "不应重跑", "finish_reason": "stop"}

    monkeypatch.setattr(retry_executor, "_call_llm", retry_llm)
    monkeypatch.setattr(retry_executor, "_call_llm_stream", _stream_from(retry_llm))
    retry_events = [
        event
        async for event in retry_executor.run_stream(
            user_id=user.id,
            message="删除两条饮食记录",
            user_auth_token="test-token",
            client_turn_id="turn-two-planned-writes",
        )
    ]
    assert retry_llm_calls == 0
    assert "部分写入获得回执" in "".join(
        event["data"].get("content", "")
        for event in retry_events
        if event.get("event") == "token"
    )


@pytest.mark.asyncio
async def test_health_query_blood_pressure_uses_existing_records_endpoint(db, monkeypatch):
    # D1(garmin-sync 治理 Wave 3)把 blood_pressure 读维度默认迁到进程内直读;本测试守的是
    # killswitch 关闭时的 HTTP 回退路径仍映射到正确的 records 端点(limit=10)。进程内路径的
    # 数据等价 + 默认零 HTTP 由 test_agent_executor_reads_in_process.py 覆盖。
    from app.config import settings

    monkeypatch.setattr(settings, "reads_in_process", False, raising=False)
    executor = AgentExecutor(db)
    captured_urls = []

    async def fake_api_get(url, headers):
        captured_urls.append(url)
        return "[]"

    executor._api_get = fake_api_get

    await executor._exec_health_query(
        "http://testserver/api/v1",
        {},
        {"dimension": "blood_pressure", "days": 7},
    )

    assert captured_urls == ["http://testserver/api/v1/blood-pressure/records/me?limit=10"]


@pytest.mark.asyncio
async def test_query_lab_indicators_bridges_blood_pressure_alias_to_standardized_vitals(
    db,
    auth_user_and_headers,
):
    user, _headers = auth_user_and_headers
    db.add_all([
        BloodPressureRecord(
            user_id=user.id,
            record_date=date.today(),
            systolic=119,
            diastolic=75,
            pulse=64,
        ),
        BloodPressureRecord(
            user_id=user.id,
            record_date=date.today() - timedelta(days=1),
            systolic=124,
            diastolic=78,
            pulse=66,
        ),
    ])
    db.commit()

    executor = AgentExecutor(db)
    executor._current_user_id = user.id

    result = await executor._exec_query_lab_indicators(
        "",
        {},
        {
            "name": "血压",
            "since": (date.today() - timedelta(days=30)).isoformat(),
            "limit": 10,
        },
    )
    payload = json.loads(result)

    assert payload["metric_key"] == "blood_pressure"
    assert payload["count"] == 2
    assert payload["items"][0]["name"] == "血压"
    assert payload["items"][0]["name_en"] == "BP"
    assert payload["items"][0]["value"] == "119/75"
    assert payload["items"][0]["unit"] == "mmHg"
    assert payload["items"][0]["systolic"] == 119
    assert payload["items"][0]["diastolic"] == 75
    assert payload["items"][0]["pulse"] == 64


@pytest.mark.asyncio
async def test_query_lab_indicators_severe_bp_appends_recheck_and_symptom_triage(
    db,
    auth_user_and_headers,
):
    user, _headers = auth_user_and_headers
    db.add(BloodPressureRecord(
        user_id=user.id,
        record_date=date.today(),
        systolic=185,
        diastolic=85,
    ))
    db.commit()

    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    result = await executor._exec_query_lab_indicators("", {}, {"name": "血压"})

    assert "⚠️ 安全提示" in result
    assert "复测" in result
    assert "胸痛" in result
    assert "高血压急症" not in result


@pytest.mark.asyncio
async def test_agent_call_llm_omits_empty_tools_for_commercial_retries(db, auth_user_and_headers, monkeypatch):
    """Empty no-tool retry must not send tools=[] to OpenAI-compatible gateways."""
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    captured_kwargs = []

    class FakeProvider:
        async def chat(self, **kwargs):
            captured_kwargs.append(kwargs)
            return {"content": "ok", "finish_reason": "stop"}

    monkeypatch.setattr(
        "app.services.llm.factory.create_provider_for_user",
        lambda _user_id, _db: FakeProvider(),
    )
    monkeypatch.setattr("app.services.agent_executor.settings.agent_base_url", None)
    monkeypatch.setattr("app.services.agent_executor.settings.agent_api_key", None)

    await executor._call_llm([{"role": "user", "content": "请直接回答"}], [])

    assert "tools" not in captured_kwargs[0]


@pytest.mark.asyncio
async def test_agent_call_llm_keeps_user_model_for_pure_record_turns(db, auth_user_and_headers, monkeypatch):
    """Pure record turns may use compact prompts, but must not override the user's model."""
    user, _headers = auth_user_and_headers
    db.add(UserProfile(user_id=user.id, llm_model_id="qwen3.6-plus"))
    db.commit()

    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    executor._prefer_fast_record_model = True
    created_model_ids = []
    created_user_provider_for = []
    captured_messages = []

    class FakeProvider:
        model = "qwen3.6-plus"

        async def chat(self, **kwargs):
            captured_messages.append(kwargs["messages"])
            return {"content": "ok", "finish_reason": "stop"}

    def fake_create_provider_for_model_id(model_id):
        created_model_ids.append(model_id)
        return FakeProvider()

    def fake_create_provider_for_user(user_id, _db):
        created_user_provider_for.append(user_id)
        return FakeProvider()

    monkeypatch.setattr(
        "app.services.llm.factory.create_provider_for_model_id",
        fake_create_provider_for_model_id,
    )
    monkeypatch.setattr(
        "app.services.llm.factory.create_provider_for_user",
        fake_create_provider_for_user,
    )
    monkeypatch.setattr("app.services.agent_executor.settings.agent_base_url", None)
    monkeypatch.setattr("app.services.agent_executor.settings.agent_api_key", None)

    await executor._call_llm([{"role": "user", "content": "记录晚餐牛肉饭"}], [])

    assert created_model_ids == []
    assert created_user_provider_for == [user.id]
    assert executor._last_provider_model_name == "qwen3.6-plus"
    assert len(captured_messages[0]) == 2
    assert "健康记录工具路由器" in captured_messages[0][0]["content"]
    assert captured_messages[0][1]["content"] == "记录晚餐牛肉饭"


@pytest.mark.asyncio
async def test_agent_stream_finishes_pure_record_turn_from_tool_result(db, auth_user_and_headers):
    """Pure record turns should not spend another LLM round synthesizing success text."""
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    calls = []

    async def fake_call_llm(messages, tools):
        calls.append({"messages": messages, "tool_count": len(tools or [])})
        return {
            "content": "",
            "finish_reason": "tool_calls",
            "tool_calls": [
                {
                    "id": "call_record_diet",
                    "type": "function",
                    "function": {
                        "name": "health_record",
                        "arguments": json.dumps({
                            "record_type": "diet",
                            "data": {
                                "meal_type": "dinner",
                                "food_items": "牛肉饭",
                            },
                        }, ensure_ascii=False),
                    },
                },
            ],
        }

    async def fake_execute_tool(tool_name, args_raw, user_token):
        assert tool_name == "health_record"
        return json.dumps({"id": 101, "message": "已记录晚餐：牛肉饭"}, ensure_ascii=False)

    executor._call_llm = fake_call_llm
    executor._call_llm_stream = _stream_from(fake_call_llm)
    executor._execute_tool = fake_execute_tool

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="记录晚餐牛肉饭",
            user_auth_token="test-token",
        )
    ]

    rendered = "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )

    assert len(calls) == 1
    # 饮食回复已压到 ≤2 句(确定性 quality 层): 无宏量数字 → 头条退化成 "已记录晚餐。",
    # 食材名/宏量由结构化卡承载,不再复述进文本(founder 截图的多段墙已收敛)。
    assert "已记录晚餐。" in rendered
    assert "牛肉饭" not in rendered  # 食材不再进文本
    assert events[-1]["event"] == "done"


@pytest.mark.asyncio
async def test_agent_stream_reports_tools_used_in_done_and_meta(db, auth_user_and_headers):
    """done 事件 + 持久化 meta 都暴露本轮调用过的工具名 (tools_used), 供 mac/mobile 展示。"""
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    calls = []

    async def fake_call_llm(messages, tools):
        calls.append({"messages": messages, "tool_count": len(tools or [])})
        # 第一轮发起一个 tool_call; 第二轮综合工具结果给出可见回复。
        if len(calls) == 1:
            return {
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [
                    {
                        "id": "call_query_hr",
                        "type": "function",
                        "function": {
                            "name": "health_query",
                            "arguments": json.dumps({"metric": "heart_rate"}, ensure_ascii=False),
                        },
                    },
                ],
            }
        return {"content": "你最近静息心率正常。", "finish_reason": "stop"}

    async def fake_execute_tool(tool_name, args_raw, user_token):
        assert tool_name == "health_query"
        return json.dumps({"resting_heart_rate": 60}, ensure_ascii=False)

    executor._call_llm = fake_call_llm
    executor._call_llm_stream = _stream_from(fake_call_llm)
    executor._execute_tool = fake_execute_tool

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="我的心率怎么样",
            user_auth_token="test-token",
        )
    ]

    done = events[-1]
    assert done["event"] == "done"
    assert done["data"]["tools_used"] == ["health_query"]
    # sources_used 与 tools_used 独立, 保留既有字段。
    assert "sources_used" in done["data"]

    # 持久化 meta 也要带 tools_used, 否则历史消息 reload 看不到。
    ai_msg = db.query(AgentMessage).filter_by(id=done["data"]["message_id"]).first()
    assert ai_msg is not None
    assert ai_msg.meta["tools_used"] == ["health_query"]


@pytest.mark.asyncio
async def test_agent_stream_tools_used_empty_when_no_tool_call(db, auth_user_and_headers):
    """无 tool call 的纯问答轮, tools_used 为 []。"""
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)

    async def fake_call_llm(messages, tools):
        return {"content": "保持规律作息即可。", "finish_reason": "stop"}

    executor._call_llm = fake_call_llm
    executor._call_llm_stream = _stream_from(fake_call_llm)

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="给点睡眠建议",
            user_auth_token=None,
        )
    ]

    done = events[-1]
    assert done["event"] == "done"
    assert done["data"]["tools_used"] == []

    ai_msg = db.query(AgentMessage).filter_by(id=done["data"]["message_id"]).first()
    assert ai_msg is not None
    assert ai_msg.meta["tools_used"] == []


@pytest.mark.asyncio
async def test_agent_stream_auto_confirms_fast_record_tool_calls(db, auth_user_and_headers):
    """Fast record turns should complete simple logging without a second confirmation round."""
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    executed_args = []

    async def fake_call_llm(messages, tools):
        return {
            "content": "",
            "finish_reason": "tool_calls",
            "tool_calls": [
                {
                    "id": "call_record_water",
                    "type": "function",
                    "function": {
                        "name": "health_record",
                        "arguments": json.dumps({
                            "record_type": "water",
                            "data": {"amount": 1000},
                        }, ensure_ascii=False),
                    },
                },
            ],
        }

    async def fake_execute_tool(tool_name, args_raw, user_token):
        assert tool_name == "health_record"
        parsed = json.loads(args_raw)
        executed_args.append(parsed)
        if parsed.get("confirmed") is not True:
            return (
                "[NEEDS_CONFIRMATION] 我准备记录: 喝水 1000ml. "
                "请向用户复述并问一次'是这样吗？'"
            )
        return json.dumps({"id": 102, "message": "已记录饮水 1000ml"}, ensure_ascii=False)

    executor._call_llm = fake_call_llm
    executor._call_llm_stream = _stream_from(fake_call_llm)
    executor._execute_tool = fake_execute_tool

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="记录饮水1000",
            user_auth_token="test-token",
        )
    ]

    rendered = "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )

    assert executed_args[0]["confirmed"] is True
    assert executed_args[0]["data"]["confirmed"] is True
    assert "已记录饮水 1000ml" in rendered
    assert "NEEDS_CONFIRMATION" not in rendered
    assert "请向用户复述" not in rendered


@pytest.mark.asyncio
async def test_agent_stream_emits_record_card_after_fast_diet_record(db, auth_user_and_headers):
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)

    async def fake_call_llm(messages, tools):
        return {
            "content": "",
            "finish_reason": "tool_calls",
            "tool_calls": [
                {
                    "id": "call_record_diet",
                    "type": "function",
                    "function": {
                        "name": "health_record",
                        "arguments": json.dumps({
                            "record_type": "diet",
                            "data": {
                                "food_items": "两个鸡蛋,一杯牛奶",
                                "meal_type": "breakfast",
                            },
                        }, ensure_ascii=False),
                    },
                },
            ],
        }

    async def fake_execute_tool(tool_name, args_raw, user_token):
        assert tool_name == "health_record"
        parsed = json.loads(args_raw)
        assert parsed["confirmed"] is True
        return json.dumps({"id": 103, "message": "已记录早餐：两个鸡蛋,一杯牛奶"}, ensure_ascii=False)

    executor._call_llm = fake_call_llm
    executor._call_llm_stream = _stream_from(fake_call_llm)
    executor._execute_tool = fake_execute_tool

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="早饭吃了两个鸡蛋一杯牛奶",
            user_auth_token="test-token",
        )
    ]

    card_events = [event for event in events if event.get("event") == "card"]
    assert len(card_events) == 1
    card = card_events[0]["data"]["descriptor"]
    # post_record_quality 升级后, 饮食记录发结构化 record_quality 卡(带 actions/个性化字段),
    # 不再是扁平 record 卡。逐字段断言承重项, 不整卡盲等值(附加字段允许演进)。
    assert card["type"] == "record_quality"
    assert card["data"]["domain"] == "diet"
    assert card["data"]["title"] == "早餐已记录"
    assert card["data"]["summary"] == "两个鸡蛋,一杯牛奶"
    assert card["data"]["next_action"], "record_quality 卡必须带下一步行动"
    assert card["data"]["boundary"], "非诊断边界声明不允许缺失"
    actions = card.get("actions") or []
    assert actions, "record_quality 卡必须带 actions"
    for action in actions:
        assert action["action"] in CLIENT_ACTION_ALLOWLIST, f"客户端会丢弃越界 action: {action}"
        assert action.get("id") and action.get("label"), f"action 缺 id/label: {action}"
    assert card_events[0]["data"]["anchor"] == "post_record_quality"
    assert events.index(card_events[0]) > next(i for i, e in enumerate(events) if e.get("event") == "tool_result")
    done_idx = next(i for i, e in enumerate(events) if e.get("event") == "done")
    assert events.index(card_events[0]) < done_idx
    assert events[done_idx]["data"]["cards"] == [card]

    saved = db.query(AgentMessage).filter_by(id=events[done_idx]["data"]["message_id"]).first()
    assert saved is not None
    assert saved.meta["cards"] == [card]


@pytest.mark.asyncio
async def test_agent_stream_emits_safety_card_after_record_safety_alert(db, auth_user_and_headers, monkeypatch):
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)

    async def fake_call_llm(messages, tools):
        return {
            "content": "",
            "finish_reason": "tool_calls",
            "tool_calls": [
                {
                    "id": "call_record_diet",
                    "type": "function",
                    "function": {
                        "name": "health_record",
                        "arguments": json.dumps({
                            "record_type": "diet",
                            "data": {
                                "food_items": "牛肉面",
                                "meal_type": "dinner",
                            },
                        }, ensure_ascii=False),
                    },
                },
            ],
        }

    async def fake_execute_tool(tool_name, args_raw, user_token):
        assert tool_name == "health_record"
        parsed = json.loads(args_raw)
        assert parsed["confirmed"] is True
        return json.dumps({"id": 104, "message": "已记录晚餐：牛肉面"}, ensure_ascii=False)

    safety_alert = Alert(
        rule_id="training.high_intensity_not_recommended",
        category="training_load",
        severity=Severity.HIGH,
        title="今天不建议高强度训练",
        message="睡眠不足且 HRV 明显低于近期基线，建议把训练降级。",
        action="改为 20 分钟低强度步行或拉伸",
        requires_medical_attention=True,
    )
    monkeypatch.setattr("app.twin.builder.build_twin", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(
        "app.agents.safety_guardian.evaluate_safety",
        lambda _twin: SimpleNamespace(alerts=[safety_alert]),
    )

    executor._call_llm = fake_call_llm
    executor._call_llm_stream = _stream_from(fake_call_llm)
    executor._execute_tool = fake_execute_tool

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="记录晚餐牛肉面",
            user_auth_token="test-token",
        )
    ]

    card_events = [event for event in events if event.get("event") == "card"]
    assert len(card_events) == 2
    record_card = card_events[0]["data"]["descriptor"]
    safety_card = card_events[1]["data"]["descriptor"]

    # 记录卡升级为结构化 record_quality(post_record_quality 产出, 带 actions);
    # 承重字段逐一断言, 不整卡盲等值。
    assert record_card["type"] == "record_quality"
    assert record_card["data"]["domain"] == "diet"
    assert record_card["data"]["title"] == "晚餐已记录"
    assert record_card["data"]["summary"] == "牛肉面"
    assert record_card["data"]["boundary"], "非诊断边界声明不允许缺失"
    assert record_card.get("actions"), "record_quality 卡必须带 actions"
    for action in record_card["actions"]:
        assert action["action"] in CLIENT_ACTION_ALLOWLIST, f"客户端会丢弃越界 action: {action}"

    # 安全卡是确定性裁决输出 — 每个承重字段显式断言, 覆盖面不缩水(加层不减层)。
    assert safety_card["type"] == "safety"
    safety_data = safety_card["data"]
    assert safety_data["title"] == "今天不建议高强度训练"
    assert safety_data["severity"] == "high"
    assert safety_data["summary"] == "睡眠不足且 HRV 明显低于近期基线，建议把训练降级。"
    assert safety_data["recommendations"] == ["改为 20 分钟低强度步行或拉伸"]
    assert safety_data["boundary"] == "这不是诊断；如出现急性不适或持续症状，请及时就医。"
    assert safety_data["requires_medical_attention"] is True
    assert safety_data["rule_id"] == "training.high_intensity_not_recommended"
    assert safety_data["category"] == "training_load"
    for action in safety_card.get("actions") or []:
        assert action["action"] in CLIENT_ACTION_ALLOWLIST, f"客户端会丢弃越界 action: {action}"

    assert card_events[0]["data"]["anchor"] == "post_record_quality"
    assert card_events[1]["data"]["anchor"] == "safety_alert"

    done_idx = next(i for i, e in enumerate(events) if e.get("event") == "done")
    assert events[done_idx]["data"]["cards"] == [record_card, safety_card]

    saved = db.query(AgentMessage).filter_by(id=events[done_idx]["data"]["message_id"]).first()
    assert saved is not None
    assert saved.meta["cards"] == [record_card, safety_card]


@pytest.mark.asyncio
async def test_agent_stream_keeps_safety_text_visible_for_old_clients(db, auth_user_and_headers, monkeypatch):
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)

    async def fake_call_llm(messages, tools):
        return {
            "content": "",
            "finish_reason": "tool_calls",
            "tool_calls": [
                {
                    "id": "call_record_diet",
                    "type": "function",
                    "function": {
                        "name": "health_record",
                        "arguments": json.dumps({
                            "record_type": "diet",
                            "data": {
                                "food_items": "牛肉面",
                                "meal_type": "dinner",
                            },
                        }, ensure_ascii=False),
                    },
                },
            ],
        }

    async def fake_execute_tool(tool_name, args_raw, user_token):
        assert tool_name == "health_record"
        return json.dumps(
            {"id": 105, "message": "已记录晚餐：" + ("牛肉面" * 80)},
            ensure_ascii=False,
        )

    safety_alert = Alert(
        rule_id="training.high_intensity_not_recommended",
        category="training_load",
        severity=Severity.HIGH,
        title="今天不建议高强度训练",
        message="睡眠不足且 HRV 明显低于近期基线，建议把训练降级。",
        action="改为 20 分钟低强度步行或拉伸",
    )
    monkeypatch.setattr("app.twin.builder.build_twin", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(
        "app.agents.safety_guardian.evaluate_safety",
        lambda _twin: SimpleNamespace(alerts=[safety_alert]),
    )

    executor._call_llm = fake_call_llm
    executor._call_llm_stream = _stream_from(fake_call_llm)
    executor._execute_tool = fake_execute_tool

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="记录晚餐牛肉面",
            user_auth_token="test-token",
        )
    ]
    rendered = "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )

    assert "⚠️ 安全提示" in rendered
    assert "今天不建议高强度训练" in rendered


@pytest.mark.asyncio
async def test_agent_stream_marks_length_limited_answer_as_interrupted(db, auth_user_and_headers):
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)

    async def fake_call_llm(messages, tools):
        return {
            "content": "## 检查计划\n| 时间 | 行动 |\n| **报",
            "finish_reason": "length",
        }

    executor._call_llm = fake_call_llm
    executor._call_llm_stream = _stream_from(fake_call_llm)
    executor._build_system_knowledge_evidence_card = lambda *args, **kwargs: {
        "type": "system_knowledge_evidence",
        "data": {"entity": {"title": "不完整证据"}, "claims": []},
        "actions": [{
            "id": "unsafe-open",
            "label": "继续操作",
            "action": "route.open",
            "payload": {"route": "/knowledge"},
        }],
    }

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="给我一份完整检查计划",
            user_auth_token=None,
        )
    ]

    rendered = "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )
    done = events[-1]
    saved = db.query(AgentMessage).filter_by(role="assistant").one()

    assert INTERRUPTED_COMPLETION_NOTICE in rendered
    assert done["event"] == "done"
    assert done["data"]["completion_status"] == "interrupted"
    assert done["data"]["finish_reason"] == "length"
    assert done["data"]["cards"] == []
    assert saved.meta["completion_status"] == "interrupted"
    assert saved.meta["finish_reason"] == "length"
    assert saved.meta["cards"] == []


@pytest.mark.asyncio
async def test_agent_stream_retries_when_model_returns_empty_visible_reply(db, auth_user_and_headers):
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    calls = []

    async def fake_call_llm(messages, tools):
        calls.append({"messages": messages, "tool_count": len(tools or [])})
        if len(calls) == 1:
            return {"content": "", "finish_reason": "stop"}
        return {"content": "补发回答：基于 9p21 和运动数据，先保持二区有氧。", "finish_reason": "stop"}

    executor._call_llm = fake_call_llm
    executor._call_llm_stream = _stream_from(fake_call_llm)

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="针对我的 9p21 基因，给我未来 30 天方案",
            user_auth_token=None,
        )
    ]

    rendered = "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )

    assert "补发回答" in rendered
    assert calls[-1]["tool_count"] == 0
    assert events[-1]["event"] == "done"


@pytest.mark.asyncio
async def test_agent_stream_injects_mac_desktop_markdown_instruction(db, auth_user_and_headers, monkeypatch):
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    calls = []

    monkeypatch.setattr(executor, "_build_system_prompt", lambda *_args, **_kwargs: "你是健康助理。")
    monkeypatch.setattr(executor, "_build_system_knowledge_prompt_context", lambda *_args, **_kwargs: "")

    async def fake_call_llm(messages, tools):
        calls.append({"messages": messages, "tool_count": len(tools or [])})
        return {"content": "## 关键结论\n\n- 已按桌面端 Markdown 输出。", "finish_reason": "stop"}

    executor._call_llm = fake_call_llm
    executor._call_llm_stream = _stream_from(fake_call_llm)

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="分析最近饮食趋势",
            user_auth_token=None,
            extra_context=json.dumps({
                "client": "mac",
                "desktop_markdown_response_instruction": "请用 Markdown 分段，不要输出密集长段落。",
            }),
        )
    ]

    # rank #6 (prefix-cache layout): the mac desktop markdown instruction is
    # turn-scoped → last user message, not the byte-stable system prompt.
    msgs = calls[0]["messages"]
    system_prompt = msgs[0]["content"]
    last_user = next(m["content"] for m in reversed(msgs) if m.get("role") == "user")
    assert "## 桌面端回复格式要求" not in system_prompt
    assert "## 桌面端回复格式要求" in last_user
    assert "请用 Markdown 分段" in last_user
    assert events[-1]["event"] == "done"


@pytest.mark.asyncio
async def test_agent_stream_compacts_context_after_repeated_empty_visible_reply(db, auth_user_and_headers, monkeypatch):
    """Commercial gateways can return stop+empty for long system prompts."""
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    calls = []

    monkeypatch.setattr(
        executor,
        "_build_system_prompt",
        lambda *_args, **_kwargs: (
            "你是健康助理。\n"
            "## 用户健康档案\n"
            + ("睡眠、血压、运动、饮食和基因风险需要综合评估。\n" * 260)
        ),
    )
    monkeypatch.setattr(executor, "_build_system_knowledge_prompt_context", lambda *_args, **_kwargs: "")

    async def fake_call_llm(messages, tools):
        calls.append({"messages": messages, "tool_count": len(tools or [])})
        if len(calls) <= 2:
            return {"content": "", "finish_reason": "stop"}
        return {"content": "压缩上下文后回答：先关注睡眠、血压和今天的第一项任务。", "finish_reason": "stop"}

    executor._call_llm = fake_call_llm
    executor._call_llm_stream = _stream_from(fake_call_llm)

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="为什么今天优先这五件任务？",
            user_auth_token=None,
        )
    ]

    rendered = "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )

    assert "压缩上下文后回答" in rendered
    assert len(calls) == 3
    assert calls[2]["tool_count"] == 0
    assert len(calls[2]["messages"][0]["content"]) < len(calls[0]["messages"][0]["content"])
    assert "## 用户健康档案" in calls[2]["messages"][0]["content"]


@pytest.mark.asyncio
async def test_agent_stream_falls_back_to_stable_provider_when_compact_retry_is_empty(db, auth_user_and_headers, monkeypatch):
    """If the selected commercial model keeps returning empty, use a stable fallback."""
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    calls = []
    fallback_calls = []

    monkeypatch.setattr(
        executor,
        "_build_system_prompt",
        lambda *_args, **_kwargs: (
            "你是健康助理。\n"
            "## 用户健康档案\n"
            + ("睡眠、血压、运动、饮食和基因风险需要综合评估。\n" * 260)
        ),
    )
    monkeypatch.setattr(executor, "_build_system_knowledge_prompt_context", lambda *_args, **_kwargs: "")

    async def fake_call_llm(messages, tools):
        calls.append({"messages": messages, "tool_count": len(tools or [])})
        return {"content": "", "finish_reason": "stop"}

    async def fake_fallback(messages):
        fallback_calls.append(messages)
        return {"content": "稳定模型兜底回答：先处理血压、睡眠和低风险运动。", "finish_reason": "stop"}

    executor._call_llm = fake_call_llm
    executor._call_llm_stream = _stream_from(fake_call_llm)
    executor._call_llm_fallback_provider = fake_fallback

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="为什么今天优先这五件任务？",
            user_auth_token=None,
        )
    ]

    rendered = "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )

    assert "稳定模型兜底回答" in rendered
    assert len(calls) == 3
    assert len(fallback_calls) == 1
    assert fallback_calls[0][0]["role"] == "system"


@pytest.mark.asyncio
async def test_agent_stream_executes_inline_tool_json_instead_of_rendering_it(db, auth_user_and_headers):
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    calls = []
    executed = []

    async def fake_call_llm(messages, tools):
        calls.append({"messages": messages, "tool_count": len(tools or [])})
        if len(calls) == 1:
            return {
                "content": (
                    "好的，我来帮你删除最后一条饮食记录。\n"
                    '{"name":"health_manage","parameters":{"record_type":"diet","operation":"delete","record_id":625}}'
                ),
                "finish_reason": "stop",
            }
        return {"content": "已删除最后一条饮食记录。", "finish_reason": "stop"}

    async def fake_execute_tool(tool_name, args_raw, user_token):
        executed.append((tool_name, args_raw, user_token))
        return '{"message":"已删除最后一条饮食记录","record_id":625}'

    executor._call_llm = fake_call_llm
    executor._call_llm_stream = _stream_from(fake_call_llm)
    executor._execute_tool = fake_execute_tool

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="删除最后一条饮食记录",
            user_auth_token="test-token",
        )
    ]

    rendered = "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )

    assert executed == [
        ("health_manage", '{"record_type": "diet", "operation": "delete", "record_id": 625}', "test-token")
    ]
    assert any(event.get("event") == "tool_call" and event["data"]["tool"] == "health_manage" for event in events)
    assert "已删除最后一条饮食记录" in rendered
    assert '"name":"health_manage"' not in rendered


@pytest.mark.asyncio
async def test_agent_stream_executes_inline_diet_record_json_with_nutrition(db, auth_user_and_headers):
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    executed = []

    async def fake_call_llm(messages, tools):
        if not executed:
            return {
                "content": (
                    "我先识别并记录这顿饭。\n"
                    '{"name":"health_record","parameters":{"record_type":"diet","data":{'
                    '"meal_type":"dinner","food_items":"鳕鱼 100g + 米饭 150g + 青菜 100g",'
                    '"calories":520,"protein":32,"carbs":58,"fat":14,"fiber":5}}}'
                ),
                "finish_reason": "stop",
            }
        return {"content": "已记录晚餐：约 520 kcal，蛋白质 32g。", "finish_reason": "stop"}

    async def fake_execute_tool(tool_name, args_raw, user_token):
        args = json.loads(args_raw)
        executed.append((tool_name, args))
        # Real health_record returns a `message` the fast-record path renders.
        return (
            '{"id":701,"message":"已记录晚餐：约 520 kcal，蛋白质 32g",'
            '"food_items":"鳕鱼 100g + 米饭 150g + 青菜 100g","calories":520}'
        )

    executor._call_llm = fake_call_llm
    executor._call_llm_stream = _stream_from(fake_call_llm)
    executor._execute_tool = fake_execute_tool

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="计算热量和营养并记录饮食",
            user_auth_token="test-token",
        )
    ]

    rendered = "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )

    assert executed[0][0] == "health_record"
    assert executed[0][1]["record_type"] == "diet"
    assert executed[0][1]["data"]["protein"] == 32
    assert any(
        event.get("event") == "tool_result"
        and event["data"]["record_type"] == "diet"
        and event["data"]["record_data"]["calories"] == 520
        and event["data"]["write_completed"] is True
        and event["data"]["receipt"]["resource_type"] == "diet_record"
        and event["data"]["receipt"]["resource_id"] == "701"
        and event["data"]["receipt"]["verified"] is True
        and event["data"]["result"] == (
            '{"id":701,"message":"已记录晚餐：约 520 kcal，蛋白质 32g",'
            '"food_items":"鳕鱼 100g + 米饭 150g + 青菜 100g","calories":520}'
        )
        for event in events
    )
    done = next(event for event in events if event.get("event") == "done")
    assert done["data"]["write_receipts"] == [
        {
            "operation_id": "health_record:diet_record:701",
            "status": "verified",
            "resource_type": "diet_record",
            "resource_id": "701",
            "completed_at": done["data"]["write_receipts"][0]["completed_at"],
            "verified": True,
        }
    ]
    from app.models.agent_conversation import AgentMessage

    saved_assistant = (
        db.query(AgentMessage)
        .filter(AgentMessage.role == "assistant")
        .order_by(AgentMessage.id.desc())
        .first()
    )
    assert saved_assistant.meta["write_receipts"] == done["data"]["write_receipts"]
    assert "已记录晚餐" in rendered
    assert '"name":"health_record"' not in rendered


@pytest.mark.asyncio
async def test_agent_stream_executes_founder_sneeze_tool_code_and_returns_receipt(
    db, auth_user_and_headers
):
    """Founder 2026-07-16: Python-style pseudo tool call must become a real write."""
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    executed = []

    async def fake_call_llm(messages, tools):
        if not executed:
            return {
                "content": (
                    "<tool_code>\n"
                    "print(health_record(record_type='symptom', "
                    "data={'description': '打喷嚏', 'body_part': 'respiratory'}))\n"
                    "</tool_code>"
                ),
                "finish_reason": "stop",
            }
        return {"content": "已记录症状：打喷嚏。", "finish_reason": "stop"}

    async def fake_execute_tool(tool_name, args_raw, user_token):
        executed.append((tool_name, json.loads(args_raw), user_token))
        return json.dumps(
            {
                "id": 75,
                "body_part": "respiratory",
                "description": "打喷嚏",
                "severity": 1,
            },
            ensure_ascii=False,
        )

    executor._call_llm = fake_call_llm
    executor._call_llm_stream = _stream_from(fake_call_llm)
    executor._execute_tool = fake_execute_tool

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="我准备睡觉了，记录刚才我打了一个喷嚏。",
            user_auth_token="test-token",
            extra_context=json.dumps({"client": "mobile"}),
            channel="typed",
        )
    ]
    rendered = "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )

    assert executed[0][0] == "health_record"
    assert executed[0][1]["record_type"] == "symptom"
    assert executed[0][1]["data"]["description"] == "打喷嚏"
    assert executed[0][2] == "test-token"
    assert "<tool_code>" not in rendered and "print(health_record" not in rendered
    assert "已记录症状：打喷嚏" in rendered
    done = next(event for event in events if event.get("event") == "done")
    assert done["data"]["write_receipts"][0]["resource_type"] == "symptom_record"
    assert done["data"]["write_receipts"][0]["resource_id"] == "75"
    assert done["data"]["write_receipts"][0]["verified"] is True


@pytest.mark.asyncio
async def test_agent_stream_strips_leading_inline_tool_json_then_prose(db, auth_user_and_headers):
    """Regression: weaker fast-record models emit the tool-call JSON FIRST and a
    human-readable confirmation/analysis AFTER it. Previously the inline extractor
    bailed on any trailing text, so the raw JSON leaked to the user AND the tool
    never ran (the '已记录' was a hallucination, data not saved). Now the call must
    be recovered+executed and the JSON must never render."""
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    calls = []
    executed = []

    async def fake_call_llm(messages, tools):
        calls.append(1)
        if len(calls) == 1:
            # JSON first, then prose (mirrors the reported voice-chat screenshot).
            return {
                "content": (
                    '{"name":"health_record","parameters":{"record_type":"symptom","data":{'
                    '"symptom":"口腔溃疡","location":"右嘴角 + 上颚外嘴唇连接处","count":2,'
                    '"severity":4}}} '
                    "已记录：口腔溃疡 ×2（右嘴角、上颚外嘴唇连接处）\n\n原因分析（结合你的基因+近况）..."
                ),
                "finish_reason": "stop",
            }
        # Any follow-up synthesis turn (non-fast-record path) returns clean text.
        return {"content": "已记录：口腔溃疡 ×2。", "finish_reason": "stop"}

    async def fake_execute_tool(tool_name, args_raw, user_token):
        executed.append((tool_name, json.loads(args_raw)))
        return json.dumps(
            {"id": 106, "message": "已记录：口腔溃疡 ×2", "record_type": "symptom"},
            ensure_ascii=False,
        )

    executor._call_llm = fake_call_llm
    executor._call_llm_stream = _stream_from(fake_call_llm)
    executor._execute_tool = fake_execute_tool

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="右嘴角有口腔溃疡然后上颚外嘴唇连接处有口腔溃疡",
            user_auth_token="test-token",
        )
    ]

    rendered = "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )

    # 1) the tool actually executed → data persisted (not a hallucinated 已记录)
    assert executed and executed[0][0] == "health_record"
    assert executed[0][1]["record_type"] == "symptom"
    # 2) the raw tool-call JSON never leaks into the visible reply
    assert '"name":"health_record"' not in rendered
    assert '"parameters"' not in rendered
    assert "record_type" not in rendered
    # 3) the user still sees a confirmation
    assert "已记录" in rendered


@pytest.mark.asyncio
async def test_record_intent_with_no_tool_executed_is_flagged(db, auth_user_and_headers):
    """#3 guard: a record-intent turn where the model only SAYS '已记录' but calls no
    tool must be flagged (record_intent_no_tool=True) so silent data loss is observable
    instead of looking like success."""
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    executed = []

    async def fake_call_llm(messages, tools):
        # No tool_calls, no inline JSON — the model hallucinates a successful record.
        return {"content": "已记录晚餐：牛肉饭。", "finish_reason": "stop"}

    async def fake_execute_tool(tool_name, args_raw, user_token):
        executed.append(tool_name)
        return "{}"

    executor._call_llm = fake_call_llm
    executor._call_llm_stream = _stream_from(fake_call_llm)
    executor._execute_tool = fake_execute_tool

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id, message="记录晚餐 牛肉饭", user_auth_token="test-token",
        )
    ]

    done = [e for e in events if e.get("event") == "done"]
    assert done, "should yield a done event"
    assert done[0]["data"]["record_intent_no_tool"] is True
    assert executed == []  # confirms no tool ran — the flag caught real silent loss


@pytest.mark.asyncio
async def test_negated_mutation_read_only_turn_completes_without_tool_failure(
    db, auth_user_and_headers
):
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    executed = []

    async def fake_call_llm(messages, tools):
        return {"content": "只读验证完成。", "finish_reason": "stop"}

    async def fake_execute_tool(tool_name, args_raw, user_token):
        executed.append(tool_name)
        return "{}"

    executor._call_llm = fake_call_llm
    executor._call_llm_stream = _stream_from(fake_call_llm)
    executor._execute_tool = fake_execute_tool

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message=(
                "这是内部只读运行验证。请只回复一句简短确认，"
                "不要调用工具，也不要记录或修改任何数据。"
            ),
            user_auth_token="test-token",
            client_turn_id="turn-negated-mutation-read-only",
        )
    ]

    done = [event for event in events if event.get("event") == "done"]
    assert done
    assert done[0]["data"]["record_intent_no_tool"] is False
    assert done[0]["data"]["turn_outcome"]["category"] == "success"
    assert executed == []


@pytest.mark.asyncio
async def test_record_intent_with_tool_executed_is_not_flagged(db, auth_user_and_headers):
    """Counterpart: when a record turn actually executes a write tool, the guard stays
    off (record_intent_no_tool=False)."""
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    calls = []

    async def fake_call_llm(messages, tools):
        calls.append(1)
        if len(calls) == 1:
            return {
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [{
                    "id": "c1",
                    "type": "function",
                    "function": {
                        "name": "health_record",
                        "arguments": json.dumps(
                            {"record_type": "diet", "data": {"meal_type": "dinner", "food_items": "牛肉饭"}},
                            ensure_ascii=False,
                        ),
                    },
                }],
            }
        return {"content": "已记录晚餐。", "finish_reason": "stop"}

    async def fake_execute_tool(tool_name, args_raw, user_token):
        return json.dumps({"id": 107, "message": "已记录晚餐：牛肉饭"}, ensure_ascii=False)

    executor._call_llm = fake_call_llm
    executor._call_llm_stream = _stream_from(fake_call_llm)
    executor._execute_tool = fake_execute_tool

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id, message="记录晚餐 牛肉饭", user_auth_token="test-token",
        )
    ]

    done = [e for e in events if e.get("event") == "done"]
    assert done and done[0]["data"]["record_intent_no_tool"] is False


@pytest.mark.asyncio
async def test_agent_stream_falls_back_to_tool_result_when_model_synthesis_is_empty(db, auth_user_and_headers):
    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    calls = []

    async def fake_call_llm(messages, tools):
        calls.append({"messages": messages, "tool_count": len(tools or [])})
        if len(calls) == 1:
            return {
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [
                    {
                        "id": "call_record_diet",
                        "type": "function",
                        "function": {
                            "name": "health_record",
                            "arguments": json.dumps({
                                "record_type": "diet",
                                "data": {
                                    "meal_type": "breakfast",
                                    "food_items": "两个豆腐包子",
                                },
                            }, ensure_ascii=False),
                        },
                    },
                ],
            }
        return {"content": "", "finish_reason": "stop"}

    async def fake_execute_tool(tool_name, args_raw, user_token):
        args = json.loads(args_raw)
        assert tool_name == "health_record"
        return json.dumps({
            "id": 108,
            "message": "已记录早餐：两个豆腐包子",
            "record_type": args["record_type"],
            "food_items": args["data"]["food_items"],
        }, ensure_ascii=False)

    executor._call_llm = fake_call_llm
    executor._call_llm_stream = _stream_from(fake_call_llm)
    executor._execute_tool = fake_execute_tool

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="记录饮食 早餐两个豆腐包子",
            user_auth_token="test-token",
        )
    ]

    rendered = "".join(
        event["data"].get("content", "")
        for event in events
        if event.get("event") == "token"
    )

    # 2 轮综合为空 → 回退到确定性 quality 回复(非空)。饮食回复已压到 ≤2 句:
    # 无宏量 → "已记录早餐。" + 一句备注;食材名由结构化卡承载,不再进文本。
    assert "已记录早餐。" in rendered
    assert "两个豆腐包子" not in rendered  # 食材不再进文本
    assert "没有收到模型的有效回复" not in rendered
    assert events[-1]["event"] == "done"


@pytest.mark.asyncio
async def test_langbridge_commercial_model_receives_raw_image_parts(db, auth_user_and_headers):
    user, _headers = auth_user_and_headers
    db.add(UserProfile(user_id=user.id, llm_model_id="gemini-3.1-pro"))
    db.commit()

    executor = AgentExecutor(db)
    captured_messages = []

    async def fake_medical_import(_user_id, _images):
        return None

    async def fake_vision_preprocess(_message, _images):
        return "视觉预处理文本，不应该替代 LangBridge 原图。"

    async def fake_call_llm(messages, tools):
        captured_messages.append(messages)
        return {
            "content": "我看到了图片。",
            "finish_reason": "stop",
        }

    executor._try_import_medical_report_images = fake_medical_import
    executor._analyze_image_with_vision = fake_vision_preprocess
    executor._call_llm = fake_call_llm
    executor._call_llm_stream = _stream_from(fake_call_llm)

    events = [
        event
        async for event in executor.run_stream(
            user_id=user.id,
            message="这张照片里是什么建筑？",
            images=[{"base64": "YWJjMTIz", "type": "jpeg"}],
            user_auth_token=None,
        )
    ]

    assert events[-1]["event"] == "done"
    first_call = captured_messages[0]
    last_user = next(msg for msg in reversed(first_call) if msg.get("role") == "user")
    assert isinstance(last_user["content"], list)
    assert last_user["content"][0] == {"type": "text", "text": "这张照片里是什么建筑？"}
    assert last_user["content"][1]["type"] == "image_url"
    assert last_user["content"][1]["image_url"]["url"] == "data:image/jpeg;base64,YWJjMTIz"
