import json
from types import SimpleNamespace

import pytest

from app.services.agent_executor import AgentExecutor
from app.services.agent_kernel.intent_frame import build_intent_frame
from app.services.agent_kernel.tool_gateway import ToolGateway, blocked_tool_result
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

    assert "下一步" in result
    assert "先澄清" in result


@pytest.mark.asyncio
async def test_gateway_execute_dispatches_allowed_request_exactly_once():
    gateway = ToolGateway(_snapshot("记录午餐吃了牛肉面"))
    calls = []
    request = ToolExecutionRequest(
        tool_name="health_record",
        arguments={"record_type": "diet", "data": {"food_items": "牛肉面"}},
    )

    async def dispatch(normalized_request):
        calls.append(normalized_request)
        return '{"id": 1, "resource_type": "diet_record"}'

    result = await gateway.execute(request, dispatch)

    assert len(calls) == 1
    assert calls[0].arguments == request.arguments
    assert result.content == '{"id": 1, "resource_type": "diet_record"}'
    assert result.decision is not None
    assert result.decision.action == "allow"


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
    assert "策略拦截" in result.content


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

    assert "策略拦截" in result
    assert "write_tool_without_write_intent" in result


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

    assert "策略拦截" in result
    assert "manage_write_without_mutate_intent" in result


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

    assert calls == [{"record_type": "diet", "data": {"food_items": "牛肉面"}}]
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

    assert calls == [{"record_type": "diet", "data": {"food_items": "牛肉面"}}]
    assert executor._agent_kernel_event_bus is not None
    assert "agent.tool_blocked" in [event.name for event in executor._agent_kernel_event_bus.events]


@pytest.mark.asyncio
async def test_agent_media_tool_uses_current_image_and_emits_manual_confirmation_card(db, monkeypatch):
    executor = AgentExecutor(db)
    executor._current_user_id = 1
    executor._current_turn_user_message = "确认把这张早餐图片发送给百炼，生成 5 秒竖屏短视频"
    executor._current_turn_source_message_id = 88
    executor._current_turn_image_urls = ["/api/v1/upload/files/chat/1/example.jpg"]

    class FakeMediaService:
        requested = None

        def __init__(self, _db):
            pass

        async def issue_confirmation(self, *, user_id, request):
            FakeMediaService.requested = (user_id, request)
            return SimpleNamespace(
                id="aigc_confirm_0123456789abcdef0123456789abcdef",
                kind=request.kind,
                source_message_id=request.source_message_id,
            )

    monkeypatch.setattr(
        "app.services.aigc_media_job_service.AIGCMediaJobService",
        FakeMediaService,
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
    assert executor._turn_aigc_media_cards == [{
        "type": "aigc_media_confirmation",
        "data": {
            "confirmation_id": "aigc_confirm_0123456789abcdef0123456789abcdef",
            "kind": "image_to_video",
            "title": "小巴创作草稿",
            "provider": "百炼 Wan",
            "source_attached": True,
            "status": "pending",
        },
        "actions": [{
            "id": "aigc_media.confirm:aigc_confirm_0123456789abcdef0123456789abcdef",
            "label": "发送给百炼并生成",
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
