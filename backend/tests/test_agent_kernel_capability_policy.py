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
from app.services.agent_kernel.write_safety import is_explicit_aigc_media_provider_veto
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


@pytest.mark.parametrize(
    "message",
    (
        "记录过口腔溃疡吗？",
        "记录了几次口腔溃疡？",
        "记录口腔溃疡的历史有哪些？",
    ),
)
def test_historical_record_questions_never_authorize_health_record(message):
    decision = decide_tool_capability(
        _snapshot(message),
        _request(
            "health_record",
            {"record_type": "illness", "data": {"name": "口腔溃疡"}},
        ),
    )

    assert decision.action == "block"
    assert decision.reason == "write_tool_without_write_intent"


@pytest.mark.parametrize(
    "message",
    (
        "不要再帮我记录口腔溃疡",
        "请不要再帮我记录口腔溃疡",
        "别再帮忙记录口腔溃疡",
        "不用再替我保存体重",
    ),
)
def test_structurally_negated_requests_never_authorize_health_record(message):
    decision = decide_tool_capability(
        _snapshot(message),
        _request(
            "health_record",
            {"record_type": "illness", "data": {"name": "口腔溃疡"}},
        ),
    )

    assert decision.action == "block"
    assert decision.reason in {
        "explicit_write_cancellation",
        "write_tool_without_write_intent",
    }


@pytest.mark.parametrize(
    "message",
    (
        "勿帮我记录晚餐，分析一下热量",
        "甭帮我记录晚餐，分析一下热量",
        "请勿帮我记录口腔溃疡，分析一下原因",
        "这个功能可以帮我记录口腔溃疡吗？",
        "系统可以帮我记录口腔溃疡吗？",
        "小巴能帮我记录口腔溃疡吗？",
        "请问小巴能帮我记录口腔溃疡吗？",
        "请问系统可以帮我记录口腔溃疡吗？",
        "我想问这个功能可以帮我记录口腔溃疡吗？",
        "不用让小巴帮我记录口腔溃疡，分析一下原因",
        "不要让系统帮我记录口腔溃疡",
        "勿让小巴帮我记录晚餐，分析一下热量",
        "请不要主动帮我记录口腔溃疡",
        "不要默默帮我记录口腔溃疡",
        "别总是帮我记录口腔溃疡",
        "请勿擅自帮我记录口腔溃疡",
        "记录口腔溃疡历史",
        "记录列表",
        "记录汇总",
        "保存过口腔溃疡吗？",
        "录入过口腔溃疡吗？",
        "新增过口腔溃疡吗？",
        "写入过口腔溃疡吗？",
        "打卡过口腔溃疡吗？",
    ),
)
def test_negated_or_capability_questions_block_health_record(message):
    decision = decide_tool_capability(
        _snapshot(message),
        _request(
            "health_record",
            {"record_type": "illness", "data": {"name": "口腔溃疡"}},
        ),
    )

    assert decision.action == "block"


@pytest.mark.parametrize(
    "message",
    (
        "勿帮我记录晚餐，分析一下热量",
        "甭帮我记录晚餐，分析一下热量",
        "请勿帮我记录口腔溃疡，分析一下原因",
    ),
)
def test_negated_write_preserves_followup_advice_goal(message):
    snapshot = _snapshot(message)

    assert snapshot.intent.primary == "advice"
    assert snapshot.intent.operation == "analyze"
    assert snapshot.intent.is_write is False


@pytest.mark.parametrize(
    "message",
    (
        "记录口腔溃疡，然后告诉我为什么会复发",
        "记录口腔溃疡，再分析一下为什么会复发",
        "记录午餐吃了牛肉面，再告诉我热量是多少",
    ),
)
def test_explicit_record_with_followup_question_allows_health_record(message):
    decision = decide_tool_capability(
        _snapshot(message),
        _request(
            "health_record",
            {"record_type": "illness", "data": {"name": "口腔溃疡"}},
        ),
    )

    assert decision.action == "allow"
    assert decision.reason == "explicit_create_intent"


@pytest.mark.parametrize(
    "message",
    (
        "可不可以记录口腔溃疡？",
        "能不能帮我记录口腔溃疡？",
        "不需要分析，记录口腔溃疡",
        "我今天不舒服帮我记录一下",
        "这次不严重帮我记录下来",
        "不是很疼帮我记录一下",
    ),
)
def test_modal_or_later_clause_write_allows_health_record(message):
    decision = decide_tool_capability(
        _snapshot(message),
        _request(
            "health_record",
            {"record_type": "illness", "data": {"name": "口腔溃疡"}},
        ),
    )

    assert decision.action == "allow"


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


@pytest.mark.parametrize(
    ("message", "operation"),
    (
        ("遵医嘱删除这条用药记录", "delete"),
        ("按医嘱停药并删除记录", "delete"),
        ("请遵医嘱删除这条用药记录", "delete"),
        ("麻烦按医嘱停药并删除记录", "delete"),
        ("我想遵医嘱删除这条用药记录", "delete"),
        ("那就按医嘱停药并删除记录", "delete"),
        ("请根据医生诊断删除这条用药记录", "delete"),
        ("希望按医嘱删除这条用药记录", "delete"),
        ("需要遵医嘱删除这条用药记录", "delete"),
        ("先按医嘱删除这条用药记录", "delete"),
        ("顺便按医嘱删除这条用药记录", "delete"),
        ("请您按医嘱删除这条用药记录", "delete"),
        ("麻烦您按医嘱删除这条用药记录", "delete"),
        ("希望能按医嘱删除这条用药记录", "delete"),
        ("我要按医嘱删除这条用药记录", "delete"),
        ("可以按医嘱删除这条用药记录", "delete"),
        ("如果按医嘱删除这条用药记录", "delete"),
        ("并非要按医嘱删除这条用药记录", "delete"),
        ("如果需要就根据医生诊断删除这条用药记录", "delete"),
        ("请您遵照医嘱删除昨天的用药记录", "delete"),
        ("请您依照医嘱删除昨天的用药记录", "delete"),
        ("请您照医嘱删除昨天的用药记录", "delete"),
        ("请您按着医嘱删除昨天的用药记录", "delete"),
        ("请您按，医嘱删除昨天的用药记录", "delete"),
        ("请您按/医嘱删除昨天的用药记录", "delete"),
        ("请您按医，嘱删除昨天的用药记录", "delete"),
        ("请您照着医嘱删除昨天的用药记录", "delete"),
        ("请您听从医嘱删除昨天的用药记录", "delete"),
        ("请您遵循医嘱删除昨天的用药记录", "delete"),
        ("请您医嘱删除昨天的用药记录", "delete"),
        ("请按医\ufe0f嘱删除记录", "delete"),
        ("请按医\u034f嘱删除记录", "delete"),
        ("请按医🩺嘱删除记录", "delete"),
        ("请按医★嘱删除记录", "delete"),
        ("请按医\u0007嘱删除记录", "delete"),
        ("请按医\u007f嘱删除记录", "delete"),
        ("请按医\u0080嘱删除记录", "delete"),
        ("请按医\ue000嘱删除记录", "delete"),
        ("请按医\ufdd0嘱删除记录", "delete"),
        ("请按醫囑删除记录", "delete"),
        ("请遵嘱删除记录", "delete"),
        ("请依嘱删除记录", "delete"),
        (
            "请记录医生意见：按医嘱调整训练强度，然后按医嘱删除昨天用药记录",
            "delete",
        ),
        (
            "请记录医生意见：按医嘱调整训练强度，然后按照医生意见同步健康数据",
            "delete",
        ),
        (
            "按医嘱调整剂量有什么风险吗，顺便记录早餐",
            "delete",
        ),
        (
            "按医嘱调整剂量有什么风险吗，并创建一个提醒",
            "delete",
        ),
        ("按医嘱调整剂量有什么风险吗，查询昨天的体重", "delete"),
        (
            "请比较按医嘱调整剂量和自行调整剂量的风险并记录早餐",
            "delete",
        ),
        ("“说明”按医嘱删除记录是什么意思“结尾”？", "delete"),
        ("我想了解按医嘱调整剂量的风险，查询昨天体重", "delete"),
        ("分析按医嘱调整剂量的副作用并记录早餐", "delete"),
        ("解释“按医嘱删除记录”的意思并创建提醒", "delete"),
        ("按医嘱调整剂量的风险并生成图片", "delete"),
        ("按医嘱调整剂量的风险并制定计划", "delete"),
        ("可以按醫囑删除记录吗？", "delete"),
        (
            "我想了解按医嘱删除这条记录并记录早餐有什么风险？",
            "delete",
        ),
        (
            "我想了解按医嘱删除这条记录并★记录早餐有什么风险？",
            "delete",
        ),
        ("我想了解按医嘱调整剂量并★查询昨天体重有什么风险？", "delete"),
        ("分析按医嘱调整剂量并🩺创建提醒的副作用", "delete"),
        ("分析按医嘱调整剂量后记录早餐的副作用", "delete"),
        ("分析按医嘱调整剂量之后制定计划的副作用", "delete"),
        ("按医嘱调整剂量而生成图片的风险", "delete"),
        ("分析按医嘱调整剂量接下来查询体重的副作用", "delete"),
        ("分析按医嘱调整剂量并立即记录早餐的副作用", "delete"),
        ("分析按医嘱调整剂量接下来记录早餐的副作用", "delete"),
        ("分析按医嘱调整剂量然后去记录早餐的副作用", "delete"),
        ("分析按医嘱调整剂量然后去设置闹钟的副作用", "delete"),
        ("分析按医嘱调整剂量接下来生成图片的副作用", "delete"),
        ("分析按医嘱调整剂量随后开始制定计划的副作用", "delete"),
    ),
)
def test_medical_instruction_basis_cannot_authorize_destructive_manage(
    message,
    operation,
):
    snapshot = _snapshot(message)
    decision = decide_tool_capability(
        snapshot,
        _request(
            "health_manage",
            {
                "record_type": "medication",
                "operation": operation,
                "record_id": 1,
            },
        ),
    )

    assert (
        snapshot.intent.primary,
        snapshot.intent.domain,
        snapshot.intent.operation,
        snapshot.intent.is_write,
    ) == ("chat", "clinical_context", "acknowledge", False)
    assert decision.action == "block"
    assert decision.reason == "manage_write_without_mutate_intent"
    assert decision.receipt_required is True


@pytest.mark.parametrize(
    "message",
    ("请您删除这条用药记录", "请您删除这条用药记录🩺"),
)
def test_ordinary_delete_without_clinician_basis_keeps_manage_capability(
    message,
):
    snapshot = _snapshot(message)
    decision = decide_tool_capability(
        snapshot,
        _request(
            "health_manage",
            {
                "record_type": "medication",
                "operation": "delete",
                "record_id": 1,
            },
        ),
    )

    assert (
        snapshot.intent.primary,
        snapshot.intent.domain,
        snapshot.intent.operation,
        snapshot.intent.is_write,
    ) == ("mutate", "medication", "delete", True)
    assert decision.action == "allow"
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


@pytest.mark.parametrize(
    "message",
    (
        "请记录医生医嘱：减少负重训练",
        "请记录医生意见：按医嘱调整训练强度",
        "请记录医生医嘱：患者需要按医嘱调整用药剂量",
        "请记录医生意见：根据医生建议调整训练强度",
        "请记录医生意见：按医🩺嘱调整训练强度",
    ),
)
def test_doctor_feedback_tool_allows_explicit_doctor_instruction_save_only(
    message,
):
    snapshot = _snapshot(message)
    decision = decide_tool_capability(
        snapshot,
        _request("record_doctor_feedback", {"assessment": "减少负重训练"}),
    )

    assert (
        snapshot.intent.primary,
        snapshot.intent.domain,
        snapshot.intent.operation,
        snapshot.intent.is_write,
    ) == ("write", "clinical_context", "create", True)
    assert decision.action == "allow"
    assert decision.reason == "explicit_doctor_feedback_write"


@pytest.mark.parametrize(
    "message",
    (
        "按医嘱调整用药剂量会有什么风险？",
        "医生说按医嘱调整剂量会有副作用吗？",
        "为什么要按医嘱调整剂量？",
        "请比较按医嘱调整剂量和自行调整剂量的风险",
        "“按医嘱删除记录”是什么意思？",
        "搜索“按医嘱删除记录”的法律含义",
        "照着医嘱调整剂量会有什么风险？",
        "“听从医嘱删除记录”是什么意思？",
        "我想了解按医嘱调整剂量的风险",
        "分析按医嘱调整剂量的副作用",
        "解释“按医嘱删除记录”的意思",
        "按医嘱调整剂量的风险",
        "我想了解按医嘱删除记录的风险",
        "我想了解按医嘱删除这条用药记录的风险",
        "按医嘱同步数据有什么风险？",
        "分析按医\ufe0f嘱调整剂量的风险",
        "解释“按医★嘱删除记录”的意思",
    ),
)
def test_medical_basis_analysis_allows_reads_but_not_mutations(message):
    snapshot = _snapshot(message)
    mutation = decide_tool_capability(
        snapshot,
        _request(
            "health_manage",
            {
                "record_type": "medication",
                "operation": "delete",
                "record_id": 1,
            },
        ),
    )
    read = decide_tool_capability(
        snapshot,
        _request("knowledge_search", {"query": message}),
    )

    assert (
        snapshot.intent.primary,
        snapshot.intent.domain,
        snapshot.intent.operation,
        snapshot.intent.is_write,
    ) == ("advice", "clinical_context", "analyze", False)
    assert mutation.action == "block"
    assert mutation.reason == "manage_write_without_mutate_intent"
    assert read.action == "allow"
    assert read.reason == "read_only_tool"


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


def test_complex_source_image_provider_confirmation_allows_model_selected_draft():
    snapshot = _snapshot("确认把这张早餐图片发送给百炼，生成 5 秒竖屏短视频")
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
    assert snapshot.intent.operation == "create"
    assert decision.action == "allow"
    assert decision.reason == "explicit_aigc_media_draft"


@pytest.mark.parametrize(
    "message",
    (
        "我确认把图片 发送给万相",
        "我确认把图片\t发送给万相",
        "我确认把图片\n发送给万相",
    ),
)
def test_provider_confirmation_whitespace_cannot_authorize_model_selected_draft(message):
    snapshot = _snapshot(message)
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

    assert snapshot.intent.primary != "write"
    assert decision.action == "block"
    assert decision.reason == "aigc_media_without_explicit_draft_intent"


@pytest.mark.parametrize(
    "message",
    (
        "确认发送图片但取消上传到百炼",
        "确认把这张早餐图片发送给百炼，但不要上传",
        "基于这张照片生成短视频，只限本地处理",
        "基于这张照片生成短视频，必须断网处理",
        "基于这张照片生成短视频，只在手机上处理",
        "基于这张照片生成短视频，不得交由服务商处理",
        "基于这张照片生成短视频，禁止传到云上",
        "基于这张照片生成短视频，请勿出网",
        "基于这张照片生成短视频，不允许远程处理",
        "基于这张照片生成短视频，别调用云接口",
        "基于这张照片生成短视频，严禁把内容送往服务器",
        "基于这张照片生成短视频，不要把内容同步出去",
        "基于这张照片生成短视频，别把照片传出去",
        "基于这张照片生成短视频，无需调用外部服务",
        "基于这张照片生成短视频，必须留在本机",
        "基于这张照片生成短视频，不得送到线上处理",
        "基于这张照片生成短视频，只许在终端侧运行",
        "基于这张照片生成短视频，只能在本地运行",
        "基于这张照片生成短视频，仅能在本地运行",
        "基于这张照片生成短视频，只可在设备内处理",
        "基于这张照片生成短视频，仅可在手机上处理",
        "基于这张照片生成短视频，限定在本机完成",
        "基于这张照片生成短视频，照片留在本地就好",
        "基于这张照片生成短视频，全程本地完成",
        "基于这张照片生成短视频，全程离线完成",
        "基于这张照片生成短视频，在本机完成",
        "基于这张照片生成短视频，在设备端完成",
        "基于这张照片生成短视频，在端侧处理",
        "基于这张照片生成短视频，只能在端侧运行",
        "基于这张照片生成短视频，仅限端上处理",
        "基于这张照片生成短视频，本地生成即可",
        "基于这张照片生成短视频，离线生成即可",
        "基于这张照片生成短视频，不准上传",
        "基于这张照片生成短视频，不许上传",
        "基于这张照片生成短视频，不让照片离开手机",
        "基于这张照片生成短视频，照片不能离开本机",
        "基于这张照片生成短视频，照片不离开设备",
        "基于这张照片生成短视频，全部在手机本地做",
        "基于这张照片生成短视频，只在手机端做",
        "基于这张照片生成短视频，在本地做就行",
        "基于这张照片生成短视频，离线做即可",
        "基于这张照片生成短视频，不要把照片发出去",
        "基于这张照片生成短视频，别把照片发出去",
        "基于这张照片生成短视频，不要外发",
        "基于这张照片生成短视频，禁止外发",
        "基于这张照片生成短视频，请不要上云",
        "基于这张照片生成短视频，禁止上云",
        "基于这张照片生成短视频，不得使用云服务",
        "基于这张照片生成短视频，只用手机处理",
        "基于这张照片生成短视频，仅用当前设备处理",
        "基于这张照片生成短视频，在当前设备完成",
        "基于这张照片生成短视频，仅限当前设备处理",
        "基于这张照片生成短视频，端内完成",
        "基于这张照片生成短视频，只在端内做",
        "基于这张照片生成短视频，本端处理",
        "基于这张照片生成短视频，设备本身完成",
        "基于这张照片生成短视频，手机自身处理",
        "基于这张照片生成短视频，只用本机模型",
        "请生成图片，local only",
        "请生成图片，offline only",
        "请生成图片，on-device only",
        "请生成图片，do not upload",
        "请生成图片，don't upload",
        "请生成图片，keep it on my phone",
        "请生成图片，no cloud processing",
    ),
)
def test_media_provider_veto_blocks_model_selected_draft(message):
    assert is_explicit_aigc_media_provider_veto(message) is True
    decision = decide_tool_capability(
        _snapshot(message),
        _request(
            "draft_aigc_media",
            {
                "kind": "image_to_video",
                "prompt": "做成晨间饮水提醒短视频",
                "purpose": "hydration_reminder",
            },
        ),
    )

    assert decision.action == "block"
    assert decision.reason == "explicit_aigc_media_provider_veto"


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
