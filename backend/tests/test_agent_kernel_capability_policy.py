from dataclasses import replace
import json
from pathlib import Path
import re

import pytest

from app.services.agent_kernel.capability_policy import (
    capability_policy_contract_payload,
    capability_policy_digest,
    decide_tool_capability,
)
from app.services.agent_kernel.intent_frame import build_intent_frame
from app.services.agent_kernel.goal_spec import compile_goal_spec
from app.services.agent_kernel.types import (
    AgentEnvelope,
    ExecutionContext,
    ToolExecutionRequest,
    TurnSnapshot,
)


CLINICIAN_GUARD_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "clinician_provenance_guard_safety_cases.json"
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


@pytest.mark.parametrize(
    ("message", "expected_primary", "expected_operation"),
    (
        (
            "医生诊断是臀肌无力导致腰肌代偿",
            "chat",
            "acknowledge",
        ),
        (
            "医生认为是臀肌无力，我该怎么办？",
            "advice",
            "analyze",
        ),
        (
            "医生建议休息然后请保存诊断记录",
            "chat",
            "acknowledge",
        ),
        (
            "根据医生诊断删除昨天用药记录",
            "chat",
            "acknowledge",
        ),
    ),
)
def test_doctor_feedback_tool_blocks_non_authorizing_clinician_frames(
    message,
    expected_primary,
    expected_operation,
):
    snapshot = _snapshot(message)
    decision = decide_tool_capability(
        snapshot,
        _request("record_doctor_feedback", {"assessment": "模型生成的反馈摘要"}),
    )

    assert snapshot.intent.primary == expected_primary
    assert snapshot.intent.domain == "clinical_context"
    assert snapshot.intent.operation == expected_operation
    assert snapshot.intent.is_write is False
    assert decision.action == "block"
    assert decision.reason == "doctor_feedback_without_explicit_clinician_write"
    assert decision.receipt_required is True


def test_doctor_feedback_tool_allows_only_guard_authorized_explicit_save():
    snapshot = _snapshot("请记录医生诊断：臀肌无力导致腰肌代偿")
    decision = decide_tool_capability(
        snapshot,
        _request("record_doctor_feedback", {"assessment": "臀肌无力导致腰肌代偿"}),
    )

    assert (
        snapshot.intent.primary,
        snapshot.intent.domain,
        snapshot.intent.operation,
        snapshot.intent.is_write,
    ) == ("write", "clinical_context", "create", True)
    assert decision.action == "allow"
    assert decision.reason == "explicit_doctor_feedback_write"
    assert decision.receipt_required is True


def test_doctor_feedback_tool_allows_explicit_save_after_clinician_report():
    snapshot = _snapshot(
        "医生说是臀肌无力。请记录医生诊断：臀肌无力导致腰痛"
    )
    decision = decide_tool_capability(
        snapshot,
        _request("record_doctor_feedback", {"assessment": "臀肌无力导致腰痛"}),
    )

    assert (
        snapshot.intent.primary,
        snapshot.intent.domain,
        snapshot.intent.operation,
        snapshot.intent.is_write,
    ) == ("write", "clinical_context", "create", True)
    assert "classifier:explicit_feedback_write_after_report" in snapshot.intent.evidence
    assert decision.action == "allow"
    assert decision.reason == "explicit_doctor_feedback_write"


@pytest.mark.parametrize(
    "text",
    (
        "医生诊断是臀肌无力导致腰肌代偿",
        "记录体重71公斤",
    ),
)
def test_forged_clinical_write_frame_cannot_override_raw_guard_decision(text):
    base = _snapshot(text)
    forged = replace(
        base,
        intent=replace(
            base.intent,
            primary="write",
            domain="clinical_context",
            operation="create",
            is_write=True,
            evidence=("classifier:explicit_feedback_write",),
        ),
    )

    decision = decide_tool_capability(
        forged,
        _request("record_doctor_feedback", {"assessment": "不应写入"}),
    )

    assert decision.action == "block"
    assert decision.reason == "doctor_feedback_without_explicit_clinician_write"


@pytest.mark.parametrize(
    "case",
    json.loads(CLINICIAN_GUARD_FIXTURE.read_text(encoding="utf-8")),
    ids=lambda row: row["id"],
)
def test_doctor_feedback_policy_matches_full_clinician_guard_corpus(case):
    from app.services.clinician_provenance_guard import classify_clinician_turn

    guard_decision = classify_clinician_turn(case["text"])
    snapshot = _snapshot(case["text"])
    decision = decide_tool_capability(
        snapshot,
        _request("record_doctor_feedback", {"assessment": "固定测试内容"}),
    )
    expected_allowed = case["kind"] == "explicit_doctor_feedback_write"

    assert guard_decision.authorizes_feedback_write is expected_allowed
    assert decision.action == ("allow" if expected_allowed else "block")
    if expected_allowed:
        assert (
            snapshot.intent.primary,
            snapshot.intent.domain,
            snapshot.intent.operation,
            snapshot.intent.is_write,
        ) == ("write", "clinical_context", "create", True)


def test_another_domain_write_frame_cannot_authorize_doctor_feedback_tool():
    snapshot = _snapshot("记录体重71公斤")
    decision = decide_tool_capability(
        snapshot,
        _request("record_doctor_feedback", {"summary": "不应写入"}),
    )

    assert snapshot.intent.is_write is True
    assert snapshot.intent.domain != "clinical_context"
    assert decision.action == "block"
    assert decision.reason == "doctor_feedback_without_explicit_clinician_write"
    assert decision.receipt_required is True


@pytest.mark.parametrize(
    "message",
    (
        "不要记录午餐牛肉面",
        "先别保存午餐牛肉面",
        "暂不录入午餐牛肉面",
    ),
)
def test_explicit_record_cancellation_blocks_health_record(message):
    snapshot = _snapshot(message)
    decision = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {"record_type": "diet", "data": {"food_items": "牛肉面"}},
        ),
    )

    assert snapshot.intent.is_write is False
    assert decision.action == "block"
    assert decision.reason == "explicit_write_cancellation"


@pytest.mark.parametrize(
    "message",
    (
        "记录午餐牛肉面不要辣",
        "记录午餐牛肉面别放香菜",
        "记录午餐牛肉面需要少盐",
    ),
)
def test_food_preferences_do_not_cancel_health_record(message):
    decision = decide_tool_capability(
        _snapshot(message),
        _request(
            "health_record",
            {"record_type": "diet", "data": {"food_items": message}},
        ),
    )

    assert decision.action == "allow"
    assert decision.reason == "explicit_create_intent"


@pytest.mark.parametrize(
    "message",
    (
        "记录2026-02-30午餐牛肉面",
        "记录2月30日午餐牛肉面",
    ),
)
def test_invalid_explicit_date_goal_blocks_health_record(message):
    base = _snapshot(message)
    goal = compile_goal_spec(
        envelope=base.envelope,
        context=base.context,
        intent=base.intent,
    )
    snapshot = TurnSnapshot(
        envelope=base.envelope,
        context=base.context,
        intent=base.intent,
        goal=goal,
    )

    decision = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {"record_type": "diet", "data": {"food_items": "牛肉面"}},
        ),
    )

    assert goal.requires_clarification is True
    assert decision.action == "block"
    assert decision.reason == "goal_requires_clarification"


def test_explicit_aigc_photo_turn_blocks_health_record_even_if_model_requests_it():
    decision = decide_tool_capability(
        _snapshot("基于这张照片生成今天活动的短视频，以此照片为开头。"),
        _request("health_record", {"record_type": "diet", "data": {"food_items": "米饭"}}),
    )

    assert decision.action == "block"
    assert decision.reason == "aigc_media_turn_disallows_health_write"
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


def test_capability_policy_digest_is_deterministic_content_free_sha256():
    first = capability_policy_digest()
    second = capability_policy_digest()
    payload = capability_policy_contract_payload()

    assert first == second
    assert re.fullmatch(r"[0-9a-f]{64}", first)
    assert payload["contract_version"] == "agent-capability-policy-v1"
    assert payload["known_tools"]
    assert payload["recipe_record_types"]
    serialized = repr(payload).lower()
    assert "prompt" not in serialized
    assert "user_id" not in serialized
    assert "health_value" not in serialized
