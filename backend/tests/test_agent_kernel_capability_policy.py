import pytest

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


def _request(name: str, args: dict, *, source: str = "structured") -> ToolExecutionRequest:
    return ToolExecutionRequest(tool_name=name, arguments=args, source=source)


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


def test_compound_write_and_analysis_turn_allows_health_record():
    decision = decide_tool_capability(
        _snapshot("记录晚餐牛肉面，帮我分析今天的热量和蛋白质"),
        _request("health_record", {"record_type": "diet", "data": {"food_items": "牛肉面"}}),
    )

    assert decision.action == "allow"
    assert decision.reason == "explicit_create_intent"
    assert decision.receipt_required is True


def test_ambiguous_turn_blocks_health_record_even_when_arguments_look_valid():
    decision = decide_tool_capability(
        _snapshot("嗯"),
        _request("health_record", {"record_type": "water", "data": {"amount": 300}}),
    )

    assert decision.action == "block"
    assert decision.reason == "ambiguous_intent_requires_clarification"
    assert decision.receipt_required is True


def test_ambiguous_health_observation_requires_clarification_before_write():
    snapshot = _snapshot("我昨晚睡了十个小时，睡眠很好")
    decision = decide_tool_capability(
        snapshot,
        _request("health_record", {"record_type": "sleep", "data": {"duration": 10}}),
    )

    assert snapshot.intent.primary == "unknown"
    assert decision.action == "block"
    assert decision.reason == "ambiguous_intent_requires_clarification"
    assert decision.receipt_required is True


def test_ambiguous_health_observation_can_still_use_read_only_tools():
    decision = decide_tool_capability(
        _snapshot("我昨晚睡了十个小时，睡眠很好"),
        _request("health_query", {"dimension": "sleep", "days": 1}),
    )

    assert decision.action == "allow"
    assert decision.reason == "read_only_tool"


def test_exact_recipe_replay_allows_only_prevalidated_record_step():
    """已保存、精确命中的配方可在短语本身不含“记录”时重放 AUTO 步骤。"""
    decision = decide_tool_capability(
        _snapshot("晨间套餐", channel="typed"),
        _request(
            "health_record",
            {"record_type": "water", "data": {"amount": 250, "confirmed": True}},
            source="procedure_recipe_replay",
        ),
    )

    assert decision.action == "allow"
    assert decision.reason == "prevalidated_recipe_replay"
    assert decision.receipt_required is True


def test_recipe_replay_source_cannot_authorize_other_write_tools():
    decision = decide_tool_capability(
        _snapshot("晨间套餐", channel="typed"),
        _request(
            "health_manage",
            {"record_type": "diet", "operation": "delete", "record_id": 1},
            source="procedure_recipe_replay",
        ),
    )

    assert decision.action == "block"
    assert decision.reason == "recipe_replay_tool_not_allowed"


@pytest.mark.parametrize("record_type", ["reminder", "goal", "garmin_sync", "remember"])
def test_recipe_replay_source_cannot_authorize_persistent_or_external_record_types(record_type):
    """精确短语只授权日常健康记录，不能创建长期副作用。"""
    decision = decide_tool_capability(
        _snapshot("晨间套餐", channel="typed"),
        _request(
            "health_record",
            {"record_type": record_type, "data": {"title": "不应执行"}},
            source="procedure_recipe_replay",
        ),
    )

    assert decision.action == "block"
    assert decision.reason == "recipe_replay_record_type_not_allowed"


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


@pytest.mark.parametrize(
    ("tool_name", "args"),
    [
        ("manage_plan", {"action": "save_to_card", "data": {"title": "计划"}}),
        ("upload_genetic_txt", {"txt_content": "rsid\tchromosome\tposition\tgenotype"}),
        ("upload_medical_exam_text", {"text": "LDL 3.8 mmol/L"}),
    ],
)
def test_mutating_tools_are_blocked_without_explicit_write_intent(tool_name, args):
    decision = decide_tool_capability(_snapshot("帮我分析一下最近的健康情况"), _request(tool_name, args))

    assert decision.action == "block"
    assert decision.receipt_required is True
    assert decision.reason == "write_tool_without_write_intent"


@pytest.mark.parametrize(
    ("text", "tool_name", "args"),
    [
        (
            "保存这份基因原始数据",
            "upload_genetic_txt",
            {"txt_content": "rsid\tchromosome\tposition\tgenotype"},
        ),
        (
            "记录这次体检结果 LDL 3.8",
            "upload_medical_exam_text",
            {"text": "LDL 3.8 mmol/L"},
        ),
        (
            "保存这个健康计划到首页",
            "manage_plan",
            {"action": "save_to_card", "data": {"title": "计划"}},
        ),
    ],
)
def test_mutating_tools_allow_explicit_write_intent(text, tool_name, args):
    decision = decide_tool_capability(_snapshot(text), _request(tool_name, args))

    assert decision.action == "allow"
    assert decision.receipt_required is True


def test_intervention_cycle_unknown_action_is_blocked_fail_closed():
    decision = decide_tool_capability(
        _snapshot("帮我看看干预周期"),
        _request("intervention_cycle", {"action": "future_action"}),
    )

    assert decision.action == "block"
    assert decision.reason == "unknown_intervention_action"


def test_unknown_tool_is_blocked_fail_closed():
    decision = decide_tool_capability(_snapshot("分析一下我的睡眠"), _request("future_tool", {}))

    assert decision.action == "block"
    assert decision.reason == "unknown_tool"
