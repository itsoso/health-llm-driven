from app.services.agent_kernel.capability_policy import decide_tool_capability
from app.services.agent_kernel.intent_frame import build_intent_frame
from app.services.agent_kernel.types import (
    AgentEnvelope,
    ExecutionContext,
    ToolExecutionRequest,
    TurnSnapshot,
)


def _snapshot(text: str, channel: str = "chat") -> TurnSnapshot:
    envelope = AgentEnvelope(user_id=1, channel=channel, text=text)
    context = ExecutionContext.for_test(user_id=1, channel=channel)
    return TurnSnapshot(
        envelope=envelope,
        context=context,
        intent=build_intent_frame(envelope, context),
    )


def _request(name: str, args: dict) -> ToolExecutionRequest:
    return ToolExecutionRequest(tool_name=name, arguments=args, source="structured")


def test_read_turn_blocks_health_record_even_if_model_requests_it():
    decision = decide_tool_capability(
        _snapshot("今天我的饮食的记录，帮我列个表格出来。"),
        _request("health_record", {"record_type": "diet", "data": {"food_items": "米饭"}}),
    )

    assert decision.action == "block"
    assert decision.receipt_required is True
    assert decision.reason == "write_tool_without_write_intent"


def test_read_turn_allows_health_manage_list():
    decision = decide_tool_capability(
        _snapshot("列出今天饮食记录"),
        _request("health_manage", {"record_type": "diet", "operation": "list"}),
    )

    assert decision.action == "allow"
    assert decision.receipt_required is False


def test_read_turn_blocks_health_manage_update():
    decision = decide_tool_capability(
        _snapshot("列出今天饮食记录"),
        _request("health_manage", {"record_type": "diet", "operation": "update", "record_id": 1}),
    )

    assert decision.action == "block"
    assert decision.receipt_required is True
    assert decision.reason == "manage_write_without_mutate_intent"


def test_mutation_turn_allows_health_manage_delete_with_receipt():
    decision = decide_tool_capability(
        _snapshot("删除上一餐"),
        _request("health_manage", {"record_type": "diet", "operation": "delete", "record_id": 1}),
    )

    assert decision.action == "allow"
    assert decision.receipt_required is True


def test_write_turn_allows_health_record_with_receipt():
    decision = decide_tool_capability(
        _snapshot("记录午餐吃了牛肉面"),
        _request("health_record", {"record_type": "diet", "data": {"food_items": "牛肉面"}}),
    )

    assert decision.action == "allow"
    assert decision.receipt_required is True


def test_ambiguous_turn_blocks_health_record_even_when_arguments_look_valid():
    decision = decide_tool_capability(
        _snapshot("嗯"),
        _request("health_record", {"record_type": "water", "data": {"amount": 300}}),
    )

    assert decision.action == "block"
    assert decision.reason == "write_tool_without_write_intent"
    assert decision.receipt_required is True


def test_advice_turn_blocks_intervention_cycle_write():
    decision = decide_tool_capability(
        _snapshot("帮我分析下今天训练计划"),
        _request("intervention_cycle", {"action": "start", "name": "训练调整"}),
    )

    assert decision.action == "block"
    assert decision.reason == "intervention_write_without_mutation_intent"


def test_media_draft_is_a_receipted_write_capability_before_manual_provider_confirmation():
    snapshot = _snapshot("把这张早餐图片做成 5 秒竖屏短视频")
    decision = decide_tool_capability(
        snapshot,
        _request(
            "draft_aigc_media",
            {
                "kind": "image_to_video",
                "prompt": "做成晨间饮水提醒短视频",
                "purpose": "hydration_reminder",
            },
        ),
    )

    assert snapshot.intent.primary == "write"
    assert snapshot.intent.domain == "aigc_media"
    assert decision.action == "allow"
    assert decision.receipt_required is True


def test_media_advice_cannot_trigger_draft():
    decision = decide_tool_capability(
        _snapshot("AIGC 短视频怎么做？"),
        _request(
            "draft_aigc_media",
            {
                "kind": "text_to_video",
                "prompt": "晨间拉伸短视频",
                "purpose": "movement_routine",
            },
        ),
    )

    assert decision.action == "block"
    assert decision.reason == "aigc_media_without_explicit_draft_intent"


def test_media_draft_never_uses_model_controlled_provider_confirmation_flag():
    decision = decide_tool_capability(
        _snapshot("把这张早餐图片做成短视频"),
        _request(
            "draft_aigc_media",
            {
                "kind": "image_to_video",
                "prompt": "做成晨间饮水提醒短视频",
                "purpose": "hydration_reminder",
            },
        ),
    )

    assert decision.action == "allow"
    assert decision.reason == "explicit_aigc_media_draft"
