import json
from types import SimpleNamespace

import pytest

from app.services.agent_executor import AgentExecutor
from app.services.agent_kernel.intent_frame import build_intent_frame
from app.services.agent_kernel.tool_gateway import (
    ToolGateway,
    ToolPreflightError,
    blocked_tool_result,
)
from app.services.agent_kernel.types import AgentEnvelope, ExecutionContext, ToolExecutionRequest, TurnSnapshot


def _snapshot(text: str, *, policy_mode: str = "enforce") -> TurnSnapshot:
    envelope = AgentEnvelope(user_id=1, channel="chat", text=text)
    context = ExecutionContext.for_test(user_id=1, channel="chat")
    return TurnSnapshot(
        envelope=envelope,
        context=context,
        intent=build_intent_frame(envelope, context),
        policy_mode=policy_mode,
    )


def test_tool_gateway_blocks_recovered_health_record_in_read_turn():
    gateway = ToolGateway(_snapshot("今天我的饮食的记录，帮我列个表格出来。"))

    decision = gateway.preflight(
        ToolExecutionRequest(
            tool_name="health_record",
            arguments={"record_type": "diet", "data": {"food_items": "米饭"}},
            source="text_recovery",
        )
    )

    assert decision.action == "block"
    assert decision.reason == "write_tool_without_write_intent"
    assert decision.receipt_required is True


def test_blocked_tool_result_includes_a_recovery_instruction_for_the_agent():
    gateway = ToolGateway(_snapshot("今天我的饮食的记录，帮我列个表格出来。"))
    decision = gateway.preflight(
        ToolExecutionRequest(
            tool_name="health_record",
            arguments={"record_type": "diet", "data": {"food_items": "米饭"}},
            source="text_recovery",
        )
    )

    result = blocked_tool_result(decision)

    payload = json.loads(result)

    assert payload["status"] == "rejected"
    assert payload["dispatch_started"] is False
    assert payload["error_code"] == "write_tool_without_write_intent"
    assert payload["tool"] == "health_record"
    assert payload["message"].startswith("[NEEDS_CLARIFICATION]")
    assert "先澄清" in payload["recovery_guidance"]


@pytest.mark.asyncio
async def test_gateway_execute_dispatches_allowed_request_exactly_once():
    gateway = ToolGateway(_snapshot("记录午餐吃了牛肉面"))
    calls = []
    events = []
    request = ToolExecutionRequest(
        tool_name="health_record",
        arguments={"record_type": "diet", "data": {"food_items": "牛肉面"}},
    )

    async def dispatch(normalized_request):
        events.append("dispatch")
        calls.append(normalized_request)
        return '{"id": 1, "resource_type": "diet_record"}'

    result = await gateway.execute(
        request,
        dispatch,
        on_decision=lambda _decision: events.append("decision"),
    )

    assert len(calls) == 1
    assert events == ["decision", "dispatch"]
    assert calls[0].arguments == request.arguments
    assert result.content == '{"id": 1, "resource_type": "diet_record"}'
    assert result.decision is not None
    assert result.decision.action == "allow"


@pytest.mark.asyncio
async def test_gateway_decision_observer_failure_prevents_dispatch():
    gateway = ToolGateway(_snapshot("记录午餐吃了牛肉面"))
    dispatched = False
    request = ToolExecutionRequest(
        tool_name="health_record",
        arguments={"record_type": "diet", "data": {"food_items": "牛肉面"}},
    )

    async def dispatch(_request):
        nonlocal dispatched
        dispatched = True
        return "unexpected"

    def fail_before_dispatch(_decision):
        raise RuntimeError("private-health-payload")

    with pytest.raises(ToolPreflightError, match="tool_preflight_failed"):
        await gateway.execute(
            request,
            dispatch,
            on_decision=fail_before_dispatch,
        )

    assert dispatched is False


@pytest.mark.asyncio
async def test_gateway_execute_blocks_enforced_denial_without_dispatch():
    gateway = ToolGateway(_snapshot("列出今天的饮食记录"))
    dispatched = False
    request = ToolExecutionRequest(
        tool_name="health_record",
        arguments={"record_type": "diet", "data": {"food_items": "牛肉面"}},
    )

    async def dispatch(_request):
        nonlocal dispatched
        dispatched = True
        return "unexpected"

    result = await gateway.execute(request, dispatch)

    assert dispatched is False
    assert result.decision is not None
    assert result.decision.action == "block"
    payload = json.loads(result.content)
    assert payload["status"] == "rejected"
    assert payload["dispatch_started"] is False
    assert "工具调用未执行" in payload["message"]


@pytest.mark.asyncio
async def test_gateway_execute_shadow_denial_still_dispatches_once():
    gateway = ToolGateway(_snapshot("列出今天的饮食记录", policy_mode="shadow"))
    calls = []
    request = ToolExecutionRequest(
        tool_name="health_record",
        arguments={"record_type": "diet", "data": {"food_items": "牛肉面"}},
    )

    async def dispatch(normalized_request):
        calls.append(normalized_request)
        return '{"id": 2, "resource_type": "diet_record"}'

    result = await gateway.execute(request, dispatch)

    assert len(calls) == 1
    assert result.decision is not None
    assert result.decision.action == "block"
    assert '"id": 2' in result.content


@pytest.mark.asyncio
async def test_execute_tool_blocks_policy_denied_health_record_before_dispatch(db, monkeypatch):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = "今天我的饮食的记录，帮我列个表格出来。"

    monkeypatch.setattr(
        "app.services.llm.tool_validator.validate_tool_call",
        lambda tool_name, args, db, user_id, reference_now=None: {"error": None, "data": args},
    )

    async def should_not_run(*args, **kwargs):
        raise AssertionError("_exec_health_record should not run")

    monkeypatch.setattr(executor, "_exec_health_record", should_not_run)

    result = await executor._execute_tool(
        "health_record",
        json.dumps({"record_type": "diet", "data": {"food_items": "米饭"}}, ensure_ascii=False),
        None,
    )

    payload = json.loads(result)
    assert payload["status"] == "rejected"
    assert payload["dispatch_started"] is False
    assert payload["error_code"] == "write_tool_without_write_intent"

    assert executor._agent_kernel_event_bus is not None
    tool_result = next(
        event
        for event in executor._agent_kernel_event_bus.events
        if event.name == "agent.tool_result"
    )
    assert tool_result.data["success"] is False


@pytest.mark.asyncio
async def test_execute_tool_decision_failure_is_structured_pre_dispatch_rejection(
    db,
    monkeypatch,
):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = "记录午餐吃了牛肉面"
    dispatched = False

    monkeypatch.setattr(
        "app.services.llm.tool_validator.validate_tool_call",
        lambda tool_name, args, db, user_id, reference_now=None: {
            "error": None,
            "data": args,
        },
    )

    def fail_decision_recording(_tool_name, _decision):
        raise RuntimeError("private-health-payload")

    async def dispatch_should_not_run(_request, _token):
        nonlocal dispatched
        dispatched = True
        return '{"id": 1, "resource_type": "diet_record"}'

    monkeypatch.setattr(
        executor,
        "_agent_kernel_record_capability_decision",
        fail_decision_recording,
    )
    monkeypatch.setattr(executor, "_dispatch_tool_request", dispatch_should_not_run)

    result = await executor._execute_tool(
        "health_record",
        {"record_type": "diet", "data": {"food_items": "牛肉面"}},
        None,
    )

    payload = json.loads(result)
    assert dispatched is False
    assert payload["status"] == "rejected"
    assert payload["dispatch_started"] is False
    assert payload["error_code"] == "policy_check_failed"


@pytest.mark.asyncio
async def test_structured_successful_read_result_remains_successful_in_telemetry(
    db,
    monkeypatch,
):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = "查询今天的饮水记录"

    monkeypatch.setattr(
        "app.services.llm.tool_validator.validate_tool_call",
        lambda tool_name, args, db, user_id, reference_now=None: {
            "error": None,
            "data": args,
        },
    )

    async def read_success(_base_url, _headers, _args):
        return '{"status":"success","records":[]}'

    monkeypatch.setattr(executor, "_exec_health_query", read_success)

    result = await executor._execute_tool(
        "health_query",
        {"query_type": "water", "date": "today"},
        None,
    )

    assert json.loads(result)["status"] == "success"
    assert executor._agent_kernel_event_bus is not None
    tool_result = next(
        event
        for event in executor._agent_kernel_event_bus.events
        if event.name == "agent.tool_result"
    )
    assert tool_result.data["success"] is True


@pytest.mark.asyncio
async def test_structured_pending_read_result_is_not_a_tool_failure(
    db,
    monkeypatch,
):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = "查询今天的饮水记录"

    monkeypatch.setattr(
        "app.services.llm.tool_validator.validate_tool_call",
        lambda tool_name, args, db, user_id, reference_now=None: {
            "error": None,
            "data": args,
        },
    )

    async def read_pending(_base_url, _headers, _args):
        return '{"status":"pending","records":[]}'

    monkeypatch.setattr(executor, "_exec_health_query", read_pending)

    await executor._execute_tool(
        "health_query",
        {"query_type": "water", "date": "today"},
        None,
    )

    assert executor._agent_kernel_event_bus is not None
    tool_result = next(
        event
        for event in executor._agent_kernel_event_bus.events
        if event.name == "agent.tool_result"
    )
    assert tool_result.data["success"] is True
    assert "health_query" not in executor._agent_kernel_tool_failure_tools


@pytest.mark.asyncio
async def test_execute_tool_blocks_health_manage_update_in_read_turn(db, monkeypatch):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = "列出今天的饮食记录"

    monkeypatch.setattr(
        "app.services.llm.tool_validator.validate_tool_call",
        lambda tool_name, args, db, user_id, reference_now=None: {"error": None, "data": args},
    )

    async def should_not_run(*args, **kwargs):
        raise AssertionError("_exec_health_manage should not run")

    monkeypatch.setattr(executor, "_exec_health_manage", should_not_run)

    result = await executor._execute_tool(
        "health_manage",
        {"record_type": "diet", "operation": "update", "record_id": 1, "data": {"meal_type": "lunch"}},
        None,
    )

    payload = json.loads(result)
    assert payload["status"] == "rejected"
    assert payload["dispatch_started"] is False
    assert payload["error_code"] == "manage_write_without_mutate_intent"


@pytest.mark.asyncio
async def test_execute_tool_blocks_health_manage_delete_in_update_turn(db, monkeypatch):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = "把刚才 300ml 改成 350ml"

    monkeypatch.setattr(
        "app.services.llm.tool_validator.validate_tool_call",
        lambda tool_name, args, db, user_id, reference_now=None: {"error": None, "data": args},
    )

    async def should_not_run(*args, **kwargs):
        raise AssertionError("_exec_health_manage should not run")

    monkeypatch.setattr(executor, "_exec_health_manage", should_not_run)

    result = await executor._execute_tool(
        "health_manage",
        {"record_type": "water", "operation": "delete", "record_id": 718},
        None,
    )

    payload = json.loads(result)
    assert payload["status"] == "rejected"
    assert payload["dispatch_started"] is False
    assert payload["error_code"] == "manage_operation_mismatch"
    assert "保留现有记录" in payload["recovery_guidance"]
    assert "用户明确要求的操作" in payload["recovery_guidance"]


@pytest.mark.asyncio
async def test_execute_tool_blocks_field_removal_from_deleting_record(db, monkeypatch):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = "把上一条饮水记录的备注去掉"

    monkeypatch.setattr(
        "app.services.llm.tool_validator.validate_tool_call",
        lambda tool_name, args, db, user_id, reference_now=None: {"error": None, "data": args},
    )

    async def should_not_run(*args, **kwargs):
        raise AssertionError("_exec_health_manage should not run")

    monkeypatch.setattr(executor, "_exec_health_manage", should_not_run)

    result = await executor._execute_tool(
        "health_manage",
        {"record_type": "water", "operation": "delete", "record_id": 718},
        None,
    )

    payload = json.loads(result)
    assert payload["status"] == "rejected"
    assert payload["dispatch_started"] is False
    assert payload["error_code"] == "delete_requires_explicit_whole_record_intent"
    assert "保留整条记录" in payload["recovery_guidance"]
    assert "仅移除字段" in payload["recovery_guidance"]


@pytest.mark.asyncio
async def test_execute_tool_allows_explicit_health_record_write(db, monkeypatch):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = "记录午餐吃了牛肉面"
    calls = []

    monkeypatch.setattr(
        "app.services.llm.tool_validator.validate_tool_call",
        lambda tool_name, args, db, user_id, reference_now=None: {"error": None, "data": args},
    )

    async def fake_exec(base, headers, args):
        calls.append(args)
        return '{"id": 1, "resource_type": "diet_record", "food_items": "牛肉面"}'

    monkeypatch.setattr(executor, "_exec_health_record", fake_exec)

    result = await executor._execute_tool(
        "health_record",
        {"record_type": "diet", "data": {"food_items": "牛肉面"}},
        None,
    )

    assert calls == [{
        "record_type": "diet",
        "data": {"food_items": "牛肉面", "source": "agent_text"},
    }]
    assert '"id": 1' in result


@pytest.mark.asyncio
async def test_execute_tool_emits_receipt_for_json_encoded_write_arguments(db, monkeypatch):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = "记录午餐吃了牛肉面"

    monkeypatch.setattr(
        "app.services.llm.tool_validator.validate_tool_call",
        lambda tool_name, args, db, user_id, reference_now=None: {"error": None, "data": args},
    )

    async def fake_exec(base, headers, args):
        return '{"id": 9, "resource_type": "diet_record", "food_items": "牛肉面"}'

    monkeypatch.setattr(executor, "_exec_health_record", fake_exec)

    await executor._execute_tool(
        "health_record",
        json.dumps({"record_type": "diet", "data": {"food_items": "牛肉面"}}, ensure_ascii=False),
        None,
    )

    assert executor._agent_kernel_event_bus is not None
    events = executor._agent_kernel_event_bus.events
    receipt = next(event for event in events if event.name == "agent.write_receipt_verified")
    assert receipt.data["operation_id"] == "health_record:diet_record:9"
    assert receipt.data["resource_id"] == "9"


@pytest.mark.asyncio
async def test_recorded_health_write_with_verified_receipt_is_telemetry_success(
    db,
    monkeypatch,
):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = "记录午餐吃了牛肉面"

    monkeypatch.setattr(
        "app.services.llm.tool_validator.validate_tool_call",
        lambda tool_name, args, db, user_id, reference_now=None: {
            "error": None,
            "data": args,
        },
    )

    async def fake_exec(_base, _headers, _args):
        return (
            '{"status":"recorded","id":42,'
            '"resource_type":"diet_record","food_items":"牛肉面"}'
        )

    monkeypatch.setattr(executor, "_exec_health_record", fake_exec)

    await executor._execute_tool(
        "health_record",
        {"record_type": "diet", "data": {"food_items": "牛肉面"}},
        None,
    )

    assert executor._agent_kernel_event_bus is not None
    tool_result = next(
        event
        for event in executor._agent_kernel_event_bus.events
        if event.name == "agent.tool_result"
    )
    assert tool_result.data["success"] is True
    assert "health_record" not in executor._agent_kernel_tool_failure_tools


@pytest.mark.asyncio
async def test_shadow_policy_observes_denied_write_without_blocking_dispatch(db, monkeypatch):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = "列出今天的饮食记录"
    calls = []
    monkeypatch.setattr("app.services.agent_executor.settings.agent_kernel_policy_mode", "shadow")
    monkeypatch.setattr(
        "app.services.llm.tool_validator.validate_tool_call",
        lambda tool_name, args, db, user_id, reference_now=None: {"error": None, "data": args},
    )

    async def fake_exec(base, headers, args):
        calls.append(args)
        return '{"id": 10, "resource_type": "diet_record"}'

    monkeypatch.setattr(executor, "_exec_health_record", fake_exec)

    await executor._execute_tool(
        "health_record",
        {"record_type": "diet", "data": {"food_items": "牛肉面"}},
        None,
    )

    assert calls == [{
        "record_type": "diet",
        "data": {"food_items": "牛肉面", "source": "agent_text"},
    }]
    assert executor._agent_kernel_event_bus is not None
    assert "agent.tool_blocked" in [event.name for event in executor._agent_kernel_event_bus.events]


@pytest.mark.asyncio
async def test_agent_media_tool_uses_current_image_and_emits_manual_confirmation_card(db, monkeypatch):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = "确认把这张早餐图片发送给百炼，生成 5 秒竖屏短视频"
    executor._current_turn_source_message_id = 88
    executor._current_turn_image_urls = ["/api/v1/upload/files/chat/1/example.jpg"]
    executor._current_turn_conversation_id = 42

    class FakeMediaService:
        requested = None

        def __init__(self, _db):
            pass

        async def issue_confirmation(self, *, user_id, request, conversation_id=None):
            FakeMediaService.requested = (user_id, request, conversation_id)
            return SimpleNamespace(
                id="aigc_confirm_0123456789abcdef0123456789abcdef",
                kind=request.kind,
                source_message_id=request.source_message_id,
                model="happyhorse-1.1-i2v",
                duration_seconds=request.duration_seconds,
                ratio=request.ratio,
            )

    monkeypatch.setattr(
        "app.services.aigc_media_job_service.AIGCMediaJobService",
        FakeMediaService,
    )
    # This focused adapter test uses a synthetic source id instead of a durable
    # AgentMessage. Dispatch checkpoint behavior is covered by executor status
    # tests with a real source row.
    monkeypatch.setattr(
        executor,
        "_persist_current_turn_write_dispatch_started",
        lambda **_kwargs: None,
    )

    result = await executor._execute_tool(
        "draft_aigc_media",
        {
            "kind": "image_to_video",
            "prompt": "做成晨间饮水提醒短视频",
            "duration_seconds": 5,
            "ratio": "9:16",
            "purpose": "hydration_reminder",
        },
        None,
    )

    assert json.loads(result)["resource_type"] == "aigc_media_confirmation"
    assert FakeMediaService.requested[0] == 1
    assert FakeMediaService.requested[1].source_message_id == 88
    assert FakeMediaService.requested[2] == 42
    assert executor._turn_aigc_media_cards == [{
        "type": "aigc_media_confirmation",
        "data": {
            "confirmation_id": "aigc_confirm_0123456789abcdef0123456789abcdef",
            "kind": "image_to_video",
            "title": "短视频草稿",
            "provider": "百炼 HappyHorse",
            "source_attached": True,
            "status": "pending",
            "content_summary": "围绕补水生成健康行动短视频",
            "content_topics": ["补水"],
            "duration_seconds": 5,
            "duration_options": [5, 8, 15],
            "ratio": "9:16",
            "resolution": "720P",
            "generates_audio": True,
        },
        "actions": [{
            "id": "aigc_media.confirm:aigc_confirm_0123456789abcdef0123456789abcdef",
            "label": "确认并生成",
            "action": "aigc_media.confirm",
            "endpoint": "/aigc/media/confirmations/aigc_confirm_0123456789abcdef0123456789abcdef/confirm",
            "requires_manual_confirm": True,
            "capability_id": "aigc_media_confirmation.v1",
            "required_receipt": True,
            "autonomy_tier": "manual_confirm",
            "policy_reason": "manual_confirm_write",
        }],
    }]
    assert executor._agent_kernel_event_bus is not None
    receipt = next(
        event for event in executor._agent_kernel_event_bus.events
        if event.name == "agent.write_receipt_verified"
    )
    assert receipt.data["resource_id"] == (
        "aigc_confirm_0123456789abcdef0123456789abcdef"
    )
    tool_result = next(
        event
        for event in executor._agent_kernel_event_bus.events
        if event.name == "agent.tool_result"
    )
    assert tool_result.data["success"] is True
    assert "draft_aigc_media" not in executor._agent_kernel_tool_failure_tools


def test_aigc_media_preview_exposes_categories_without_raw_health_details():
    from app.services.agent_executor import _aigc_media_content_preview

    preview = _aigc_media_content_preview(
        kind="text_to_video",
        prompt="用今天 95 分睡眠、8200 步和晚餐 580 kcal 生成回顾视频",
    )

    assert preview == {
        "content_summary": "围绕活动、饮食和睡眠生成健康行动短视频",
        "content_topics": ["活动", "饮食", "睡眠"],
    }
    assert "95" not in preview["content_summary"]
    assert "8200" not in preview["content_summary"]
    assert "580" not in preview["content_summary"]
