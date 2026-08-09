from dataclasses import replace
import json
from pathlib import Path
import re

import pytest

from app.services.agent_kernel import capability_policy as capability_policy_module
from app.services.agent_kernel.capability_policy import (
    capability_policy_contract_payload,
    capability_policy_digest,
    decide_tool_capability,
)
from app.services.agent_kernel.intent_frame import build_intent_frame
from app.services.agent_kernel.goal_spec import compile_goal_spec
from app.services.agent_kernel.write_safety import is_explicit_aigc_media_provider_veto
from app.services.agent_kernel.types import (
    ActionableReference,
    AgentEnvelope,
    ExecutionContext,
    ToolExecutionRequest,
    TurnSnapshot,
)


CLINICIAN_GUARD_FIXTURE = (
    Path(__file__).parent / "fixtures" / "clinician_provenance_guard_safety_cases.json"
)


def _snapshot(text: str, channel: str = "chat") -> TurnSnapshot:
    envelope = AgentEnvelope(user_id=1, channel=channel, text=text)
    context = ExecutionContext.for_test(user_id=1, channel=channel)
    return TurnSnapshot(
        envelope=envelope,
        context=context,
        intent=build_intent_frame(envelope, context),
    )


def _attachment_snapshot(text: str) -> TurnSnapshot:
    context = ExecutionContext.for_test(user_id=1, channel="chat")
    envelope = AgentEnvelope(
        user_id=1,
        channel="chat",
        text=text,
        media=({"kind": "image"},),
    )
    return TurnSnapshot(
        envelope=envelope,
        context=context,
        intent=build_intent_frame(envelope, context),
    )


@pytest.mark.parametrize(
    "message",
    (
        "记录口腔溃疡，算了吧不要记了",
        "记录口腔溃疡，不，还是别记录了",
        "记录口腔溃疡，先等等，别记了",
        "等我确诊后再记录感冒",
        "等以后如果我确诊感冒，再记录感冒",
        "确诊后再记录感冒",
        "请记录朋友的感冒",
        "帮我记录我妈妈的感冒",
        "记录我朋友感冒",
        "我朋友感冒了，记录一下",
        "记录妈妈感冒",
        "我妈妈感冒了，记录一下",
    ),
)
def test_non_authorizing_semantic_frames_block_health_record(message):
    decision = decide_tool_capability(
        _snapshot(message),
        _request(
            "health_record",
            {"record_type": "illness", "data": {"name": "感冒"}},
        ),
    )

    assert decision.action == "block"


def test_attachment_diet_authorization_still_binds_explicit_meal_slot():
    snapshot = _attachment_snapshot("记录早餐这餐")

    matching = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {
                "record_type": "diet",
                "data": {"meal_type": "breakfast", "food_items": "鸡蛋"},
            },
        ),
    )
    wrong_meal = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {
                "record_type": "diet",
                "data": {"meal_type": "dinner", "food_items": "鸡蛋"},
            },
        ),
    )

    assert matching.action == "allow"
    assert wrong_meal.action == "block"
    assert wrong_meal.reason == "health_record_target_mismatch"


def _request(
    name: str, args: dict, *, source: str = "structured"
) -> ToolExecutionRequest:
    return ToolExecutionRequest(tool_name=name, arguments=args, source=source)


def test_read_turn_blocks_health_record_even_if_model_requests_it():
    decision = decide_tool_capability(
        _snapshot("今天我的饮食的记录，帮我列个表格出来。"),
        _request(
            "health_record", {"record_type": "diet", "data": {"food_items": "米饭"}}
        ),
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
        "上次帮我记录口腔溃疡了吗？",
        "上回帮我记录口腔溃疡了吗？",
        "之前帮我记录口腔溃疡了吗？",
        "刚才帮我记录口腔溃疡了吗？",
        "你帮我保存口腔溃疡了吗？",
        "我想知道小巴能不能帮我记录口腔溃疡",
        "请告诉我小巴能否帮我记录口腔溃疡",
        "系统是否会帮我记录口腔溃疡？",
        "小巴会帮我记录口腔溃疡吗？",
        "这个功能支持帮我记录口腔溃疡吗？",
        "系统有没有帮我记录口腔溃疡的功能？",
        "请问能否记录口腔溃疡？",
        "无须让系统帮我记录口腔溃疡",
        "禁止帮我记录口腔溃疡",
        "我拒绝让系统帮我记录口腔溃疡",
        "请停止帮我记录口腔溃疡",
        "避免帮我记录口腔溃疡",
        "我不愿意让小巴帮我记录口腔溃疡",
        "我没有授权小巴帮我记录口腔溃疡",
        "未授权系统帮我记录口腔溃疡",
        "不一定要记录口腔溃疡",
        "不一定需要记录口腔溃疡",
        "不要执行：记录一下口腔溃疡",
        "请勿执行以下操作：记录一下今天晚餐",
        "禁止：记录口腔溃疡",
        "我从未同意系统帮我记录口腔溃疡",
        "我没有同意小巴帮我记录口腔溃疡",
        "我从没允许系统帮我记录口腔溃疡",
        "我没让系统帮我记录口腔溃疡",
        "我从没想过让系统帮我记录口腔溃疡",
        "我并没有要求系统帮我记录口腔溃疡",
        "我不乐意让小巴帮我记录口腔溃疡",
        "我无意让小巴帮我记录口腔溃疡",
        "我反对让系统帮我记录口腔溃疡",
        "未经我同意小巴帮我记录口腔溃疡",
        "严禁以下行为：记录口腔溃疡",
        "不要执行以下行为：记录口腔溃疡",
        "你帮我记录口腔溃疡没有",
        "你帮我保存口腔溃疡没有啊",
        "昨天帮我记录的口腔溃疡",
        "这个能帮我记录口腔溃疡吗？",
        "它能帮我记录口腔溃疡吗？",
        "请查询口腔溃疡记录",
        "请查看我的口腔溃疡记录",
        "请帮我确认有没有记录成功",
        "麻烦查查保存成功不成功",
        "帮我核对一下是否新增成功",
        "请查看口腔溃疡是否已录入",
        "客服说请记录口腔溃疡",
        "文档写着：帮我记录口腔溃疡",
        "他说记录一下口腔溃疡",
        "请转述这句话：记录口腔溃疡",
        "请复述“帮我记录口腔溃疡”",
        "请不必帮我记录口腔溃疡",
        "请杜绝系统自动记录口腔溃疡",
        "在没有得到我同意的情况下，记录口腔溃疡是不允许的",
        "记录口腔溃疡就免了",
        "记录口腔溃疡这件事作罢",
        "记录口腔溃疡未获授权",
        "记录口腔溃疡，还是算了",
        "记录口腔溃疡，取消吧",
        "不要做这件事：帮我记录口腔溃疡",
        "我从未叫你帮我记录口腔溃疡",
        "我可没让你帮我记录口腔溃疡",
        "未经我许可就帮我记录口腔溃疡",
        "我并不乐意让你帮我记录口腔溃疡",
        "请确认小巴具备记录健康数据的能力",
        "请说明小巴具不具备记录口腔溃疡的能力",
        "请确认它会自动记录口腔溃疡",
        "帮我看看昨天口腔溃疡是否已经记录",
        "请查一下上周那次口腔溃疡是否已保存",
        "请确认口腔溃疡是否已经成功写入数据库",
        "帮我核对口腔溃疡是否已经保存到病历中",
        "我只是举个例子：帮我记录口腔溃疡",
        "假设我说“帮我记录口腔溃疡”",
        "如果以后我说帮我记录口腔溃疡会怎样",
        "“帮我记录口腔溃疡”是什么意思",
        "文档写着：我午餐吃了米饭",
        "假设我午餐吃了米饭会怎样",
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
    ("message", "record_args"),
    (
        (
            "记录口腔溃疡，然后告诉我为什么会复发",
            {"record_type": "illness", "data": {"name": "口腔溃疡"}},
        ),
        (
            "记录口腔溃疡，再分析一下为什么会复发",
            {"record_type": "illness", "data": {"name": "口腔溃疡"}},
        ),
        (
            "记录午餐吃了牛肉面，再告诉我热量是多少",
            {
                "record_type": "diet",
                "data": {"meal_type": "lunch", "food_items": "牛肉面"},
            },
        ),
    ),
)
def test_explicit_record_with_followup_question_allows_health_record(
    message, record_args
):
    decision = decide_tool_capability(
        _snapshot(message),
        _request("health_record", record_args),
    )

    assert decision.action == "allow"
    assert decision.reason == "explicit_create_intent"


@pytest.mark.parametrize(
    "message",
    (
        "可不可以记录口腔溃疡？",
        "能不能帮我记录口腔溃疡？",
        "不需要分析，记录口腔溃疡",
        "不用录入昨天的但请录入今天的口腔溃疡",
        "不是不让你记录是请你记录口腔溃疡",
        "小巴你能帮我记录一下口腔溃疡吗",
        "小巴麻烦你记录口腔溃疡",
        "小巴请你记录口腔溃疡",
        "小巴替我记录口腔溃疡",
        "我想让你记录口腔溃疡",
        "请务必记录口腔溃疡",
        "把口腔溃疡记录下来",
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


@pytest.mark.parametrize(
    "message",
    (
        "我今天不舒服帮我记录一下",
        "这次不严重帮我记录下来",
        "这几天不想吃东西但请记录食欲下降",
        "我不能集中注意力但帮我记录一下",
        "这几天不想吃东西：请记录食欲下降",
        "这几天不想吃东西只是请记录食欲下降",
        "记录过敏反应",
        "请记录过量饮酒",
        "帮我记录过去三天的食欲下降",
    ),
)
def test_direct_but_different_health_fact_cannot_authorize_oral_ulcer(message):
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
        "请记录我上一次口腔溃疡，发作日期是7月1日",
        "把以前的口腔溃疡记录下来，开始日期是7月1日",
        "口腔溃疡上次发作日期是7月1日请记录一下",
    ),
)
def test_explicit_illness_backfill_binds_the_user_owned_start_date(message):
    matching = decide_tool_capability(
        _snapshot(message),
        _request(
            "health_record",
            {
                "record_type": "illness",
                "data": {"name": "口腔溃疡", "start_date": "2026-07-01"},
            },
        ),
    )
    missing_date = decide_tool_capability(
        _snapshot(message),
        _request(
            "health_record",
            {"record_type": "illness", "data": {"name": "口腔溃疡"}},
        ),
    )

    assert matching.action == "allow"
    assert missing_date.action == "block"


@pytest.mark.parametrize(
    ("message", "record_args"),
    (
        (
            "请记录过程中的头痛",
            {
                "record_type": "symptom",
                "data": {"body_part": "head", "description": "头痛"},
            },
        ),
        (
            "帮我保存既往感冒记录，起病日期是6月3日",
            {
                "record_type": "illness",
                "data": {"name": "感冒", "start_date": "2026-06-03"},
            },
        ),
    ),
)
def test_direct_write_authorization_allows_only_its_semantic_target(
    message, record_args
):
    decision = decide_tool_capability(
        _snapshot(message),
        _request("health_record", record_args),
    )

    assert decision.action == "allow"


@pytest.mark.parametrize(
    "message",
    (
        "请分别记录早餐和午餐",
        "不要记录口腔溃疡但记录今天晚餐",
        "别保存早餐而是记录午餐",
        "帮我把今天午餐记录下来",
    ),
)
def test_meal_slot_without_food_requires_clarification(message):
    decision = decide_tool_capability(
        _snapshot(message),
        _request(
            "health_record",
            {
                "record_type": "diet",
                "data": {"meal_type": "lunch", "food_items": "未指定"},
            },
        ),
    )

    assert decision.action == "block"


def test_positive_contrast_clause_cannot_authorize_the_denied_target():
    snapshot = _snapshot("不要记录口腔溃疡但记录今天晚餐吃米饭")
    goal = compile_goal_spec(
        envelope=snapshot.envelope,
        context=snapshot.context,
        intent=snapshot.intent,
    )
    snapshot = replace(snapshot, goal=goal)

    denied_target = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {"record_type": "illness", "data": {"name": "口腔溃疡"}},
        ),
    )
    authorized_target = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {
                "record_type": "diet",
                "data": {"meal_type": "dinner", "food_items": "米饭"},
            },
        ),
    )

    assert goal is not None
    assert goal.domain == "diet"
    assert denied_target.action == "block"
    assert denied_target.reason == "health_record_target_mismatch"
    assert authorized_target.action == "allow"


@pytest.mark.parametrize(
    ("message", "denied_args", "authorized_args"),
    (
        (
            "不要记录口腔溃疡但记录体重71kg",
            {"record_type": "illness", "data": {"name": "口腔溃疡"}},
            {"record_type": "weight", "data": {"weight": 71, "unit": "kg"}},
        ),
        (
            "不要记录午餐但记录晚餐吃了米饭",
            {
                "record_type": "diet",
                "data": {"meal_type": "lunch", "food_items": "米饭"},
            },
            {
                "record_type": "diet",
                "data": {"meal_type": "dinner", "food_items": "米饭"},
            },
        ),
        (
            "不要记录喝水300ml但记录晚餐吃了米饭",
            {"record_type": "water", "data": {"amount_ml": 300}},
            {
                "record_type": "diet",
                "data": {"meal_type": "dinner", "food_items": "米饭"},
            },
        ),
    ),
)
def test_health_record_authorization_binds_the_final_positive_clause_target(
    message, denied_args, authorized_args
):
    snapshot = _snapshot(message)

    denied = decide_tool_capability(snapshot, _request("health_record", denied_args))
    authorized = decide_tool_capability(
        snapshot, _request("health_record", authorized_args)
    )

    assert denied.action == "block"
    assert denied.reason == "health_record_target_mismatch"
    assert authorized.action == "allow"


def test_direct_metric_authorization_cannot_be_reused_for_an_illness_write():
    snapshot = _snapshot("记录体重71kg")

    mismatch = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {"record_type": "illness", "data": {"name": "口腔溃疡"}},
        ),
    )
    matching = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {"record_type": "weight", "data": {"weight": 71, "unit": "kg"}},
        ),
    )
    wrong_value = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {"record_type": "weight", "data": {"weight": 72, "unit": "kg"}},
        ),
    )

    assert mismatch.action == "block"
    assert mismatch.reason == "health_record_target_mismatch"
    assert matching.action == "allow"
    assert wrong_value.action == "block"
    assert wrong_value.reason == "health_record_target_mismatch"


def test_illness_authorization_cannot_be_reused_for_another_illness_name():
    snapshot = _snapshot("记录口腔溃疡")

    mismatch = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {"record_type": "illness", "data": {"name": "感冒"}},
        ),
    )
    matching = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {"record_type": "illness", "data": {"name": "口腔溃疡"}},
        ),
    )

    assert mismatch.action == "block"
    assert mismatch.reason == "health_record_target_mismatch"
    assert matching.action == "allow"


def test_one_direct_clause_can_authorize_each_explicit_metric_target():
    snapshot = _snapshot("记录体重71kg和血压120/80")

    weight = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {"record_type": "weight", "data": {"weight": 71}},
        ),
    )
    blood_pressure = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {
                "record_type": "blood_pressure",
                "data": {"systolic": 120, "diastolic": 80},
            },
        ),
    )
    unrelated = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {"record_type": "illness", "data": {"name": "口腔溃疡"}},
        ),
    )

    assert weight.action == "allow"
    assert blood_pressure.action == "allow"
    assert unrelated.action == "block"
    assert unrelated.reason == "health_record_target_mismatch"


@pytest.mark.parametrize(
    ("message", "record_args"),
    (
        ("记录体重71kg", {"record_type": "weight", "weight": 72}),
        ("记录体重71kg", {"record_type": "weight", "value": 72}),
        (
            "记录体重71kg",
            {"record_type": "weight", "data": {"weight_kg": 72}},
        ),
        ("记录喝水300ml", {"record_type": "water", "amount": 500}),
        (
            "记录血压120/80",
            {
                "record_type": "blood_pressure",
                "systolic": 130,
                "diastolic": 90,
            },
        ),
        ("记录腰围80cm", {"record_type": "waist", "waist": 90}),
        (
            "记录腰围80cm",
            {"record_type": "waist", "data": {"value": 90}},
        ),
        ("记录口腔溃疡", {"record_type": "illness", "name": "感冒"}),
    ),
)
def test_health_record_target_binding_checks_every_executor_value_alias(
    message, record_args
):
    decision = decide_tool_capability(
        _snapshot(message),
        _request("health_record", record_args),
    )

    assert decision.action == "block"
    assert decision.reason == "health_record_target_mismatch"


@pytest.mark.parametrize(
    ("message", "record_args"),
    (
        (
            "记录午餐吃米饭",
            {"record_type": "diet", "data": {"food_items": "米饭"}},
        ),
        (
            "不要记录晚餐面包但记录晚餐米饭",
            {
                "record_type": "diet",
                "data": {"meal_type": "dinner", "food_items": "面包"},
            },
        ),
        (
            "不要记录昨天晚餐但记录今天晚餐吃米饭",
            {
                "record_type": "diet",
                "data": {
                    "record_date": "2026-07-16",
                    "meal_type": "dinner",
                    "food_items": "米饭",
                },
            },
        ),
    ),
)
def test_diet_authorization_binds_meal_food_and_date(message, record_args):
    decision = decide_tool_capability(
        _snapshot(message),
        _request("health_record", record_args),
    )

    assert decision.action == "block"
    assert decision.reason == "health_record_target_mismatch"


@pytest.mark.parametrize(
    ("message", "record_args"),
    (
        (
            "记录体重71kg，然后记录血压120/80",
            {"record_type": "weight", "data": {"weight": 71}},
        ),
        (
            "记录体重71kg，然后记录血压120/80",
            {
                "record_type": "blood_pressure",
                "data": {"systolic": 120, "diastolic": 80},
            },
        ),
        (
            "我喝了300ml水，午餐吃了米饭",
            {"record_type": "water", "data": {"amount": 300}},
        ),
        (
            "我喝了300ml水，午餐吃了米饭",
            {
                "record_type": "diet",
                "data": {"meal_type": "lunch", "food_items": "米饭"},
            },
        ),
    ),
)
def test_each_direct_positive_clause_owns_an_independent_authorized_target(
    message, record_args
):
    decision = decide_tool_capability(
        _snapshot(message),
        _request("health_record", record_args),
    )

    assert decision.action == "allow"


def test_reported_context_does_not_poison_a_later_direct_contrast_request():
    decision = decide_tool_capability(
        _snapshot("朋友说我胖了，但请记录体重71kg"),
        _request(
            "health_record",
            {"record_type": "weight", "data": {"weight": 71}},
        ),
    )

    assert decision.action == "allow"


@pytest.mark.parametrize(
    "message",
    (
        "朋友说，今天下午，帮我记录口腔溃疡",
        "转告我：帮我记录口腔溃疡",
    ),
)
def test_reported_context_spans_neutral_clauses_and_never_authorizes(message):
    decision = decide_tool_capability(
        _snapshot(message),
        _request(
            "health_record",
            {"record_type": "illness", "data": {"name": "口腔溃疡"}},
        ),
    )

    assert decision.action == "block"


@pytest.mark.parametrize(
    ("message", "record_args"),
    (
        (
            "如果我喝了300ml水",
            {"record_type": "water", "data": {"amount": 300}},
        ),
        (
            "假如我体重71kg",
            {"record_type": "weight", "data": {"weight": 71}},
        ),
        (
            "假如帮我记录口腔溃疡",
            {"record_type": "illness", "data": {"name": "口腔溃疡"}},
        ),
    ),
)
def test_hypothetical_fact_or_command_never_authorizes_a_write(message, record_args):
    decision = decide_tool_capability(
        _snapshot(message),
        _request("health_record", record_args),
    )

    assert decision.action == "block"


@pytest.mark.parametrize(
    "message",
    (
        "记录体重71kg，先不记了",
        "记录体重71kg，还是别记了",
        "记录体重71kg，取消刚才的请求",
        "记录体重71kg，稍后再说",
    ),
)
def test_common_trailing_revocations_remove_write_authority(message):
    decision = decide_tool_capability(
        _snapshot(message),
        _request(
            "health_record",
            {"record_type": "weight", "data": {"weight": 71}},
        ),
    )

    assert decision.action == "block"


def test_arbitrary_illness_name_is_bound_instead_of_failing_open():
    snapshot = _snapshot("记录胃炎")

    matching = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {"record_type": "illness", "data": {"name": "胃炎"}},
        ),
    )
    mismatch = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {"record_type": "illness", "data": {"name": "高血压"}},
        ),
    )

    assert matching.action == "allow"
    assert mismatch.action == "block"
    assert mismatch.reason == "health_record_target_mismatch"


def test_same_clause_correction_authorizes_only_the_corrected_value():
    snapshot = _snapshot("记录体重71kg改记录72kg")

    superseded = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {"record_type": "weight", "data": {"weight": 71}},
        ),
    )
    corrected = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {"record_type": "weight", "data": {"weight": 72}},
        ),
    )

    assert superseded.action == "block"
    assert corrected.action == "allow"


@pytest.mark.parametrize(
    ("message", "superseded_args", "corrected_args"),
    (
        (
            "记录体重71kg，不对，改成70kg",
            {"record_type": "weight", "data": {"weight": 71}},
            {"record_type": "weight", "data": {"weight": 70}},
        ),
        (
            "记录口腔溃疡，不对，应该是感冒",
            {"record_type": "illness", "data": {"name": "口腔溃疡"}},
            {"record_type": "illness", "data": {"name": "感冒"}},
        ),
    ),
)
def test_followup_correction_replaces_prior_target(
    message, superseded_args, corrected_args
):
    snapshot = _snapshot(message)

    superseded = decide_tool_capability(
        snapshot, _request("health_record", superseded_args)
    )
    corrected = decide_tool_capability(
        snapshot, _request("health_record", corrected_args)
    )

    assert superseded.action == "block"
    assert corrected.action == "allow"


def test_observed_water_amount_is_bound_to_the_dispatched_value():
    snapshot = _snapshot("我喝了300ml水")

    mismatch = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {"record_type": "water", "data": {"amount": 400}},
        ),
    )
    matching = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {"record_type": "water", "data": {"amount": 300}},
        ),
    )

    assert mismatch.action == "block"
    assert matching.action == "allow"


@pytest.mark.parametrize(
    ("message", "record_args"),
    (
        (
            "记录喝水300ml和晚餐吃了米饭",
            {"record_type": "water", "data": {"amount": 300}},
        ),
        (
            "记录喝水300ml和晚餐吃了米饭",
            {
                "record_type": "diet",
                "data": {"meal_type": "dinner", "food_items": "米饭"},
            },
        ),
        (
            "记录口腔溃疡和湿疹",
            {"record_type": "illness", "data": {"name": "口腔溃疡"}},
        ),
        (
            "记录口腔溃疡和湿疹",
            {"record_type": "illness", "data": {"name": "湿疹"}},
        ),
        (
            "不要记录午餐面包只记录晚餐米饭",
            {
                "record_type": "diet",
                "data": {"meal_type": "dinner", "food_items": "米饭"},
            },
        ),
    ),
)
def test_multi_target_and_limiting_language_preserves_each_final_target(
    message, record_args
):
    decision = decide_tool_capability(
        _snapshot(message),
        _request("health_record", record_args),
    )

    assert decision.action == "allow"


@pytest.mark.parametrize(
    "message",
    (
        "帮我记录口腔溃疡，这是朋友说的例句",
        "“我喝了300ml水",
    ),
)
def test_post_attribution_or_unclosed_quote_never_authorizes_health_write(message):
    decision = decide_tool_capability(
        _snapshot(message),
        _request(
            "health_record",
            {"record_type": "illness", "data": {"name": "口腔溃疡"}},
        ),
    )

    assert decision.action == "block"


@pytest.mark.parametrize(
    ("message", "record_args"),
    (
        (
            "记录心情3分",
            {"record_type": "illness", "data": {"name": "感冒"}},
        ),
        (
            "记录排便一次",
            {"record_type": "illness", "data": {"name": "感冒"}},
        ),
        (
            "记录提醒明早8点喝水",
            {"record_type": "illness", "data": {"name": "感冒"}},
        ),
        (
            "记录我吃了感冒药",
            {"record_type": "illness", "data": {"name": "感冒"}},
        ),
        (
            "记录跑步30分钟",
            {"record_type": "illness", "data": {"name": "感冒"}},
        ),
    ),
)
def test_non_illness_target_never_fails_open_to_an_illness_write(message, record_args):
    decision = decide_tool_capability(
        _snapshot(message),
        _request("health_record", record_args),
    )

    assert decision.action == "block"


def test_supplement_authorization_binds_the_named_supplement():
    snapshot = _snapshot("记录鱼油")

    matching = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {"record_type": "supplement", "data": {"supplement_name": "鱼油"}},
        ),
    )
    mismatch = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {
                "record_type": "supplement",
                "data": {"supplement_name": "维生素D"},
            },
        ),
    )

    assert matching.action == "allow"
    assert mismatch.action == "block"


def test_supplement_authorization_preserves_the_full_named_supplement():
    snapshot = _snapshot("记录甘氨酸镁")

    matching = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {
                "record_type": "supplement",
                "data": {"supplement_name": "甘氨酸镁"},
            },
        ),
    )
    shorter_alias = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {"record_type": "supplement", "data": {"supplement_name": "镁"}},
        ),
    )

    assert matching.action == "allow"
    assert shorter_alias.action == "block"


def test_medication_authorization_binds_name_and_dosage():
    snapshot = _snapshot("记录阿奇霉素2粒")

    matching = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {
                "record_type": "medication",
                "data": {
                    "medication_name": "阿奇霉素",
                    "actual_dosage": "2粒",
                },
            },
        ),
    )
    wrong_dose = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {
                "record_type": "medication",
                "data": {
                    "medication_name": "阿奇霉素",
                    "actual_dosage": "1粒",
                },
            },
        ),
    )

    assert matching.action == "allow"
    assert wrong_dose.action == "block"
    assert wrong_dose.reason == "health_record_target_mismatch"


@pytest.mark.parametrize(
    "conflicting_args",
    (
        {
            "record_type": "medication",
            "data": {
                "medication_name": "阿奇霉素",
                "actual_dosage": "2粒",
                "dose": "10粒",
            },
        },
        {
            "record_type": "medication",
            "data": {
                "medication_name": "阿奇霉素",
                "dosage": "2粒",
            },
            "dose": "10粒",
        },
    ),
)
def test_medication_authorization_rejects_conflicting_execution_aliases(
    conflicting_args,
):
    decision = decide_tool_capability(
        _snapshot("记录我吃了阿奇霉素2粒"),
        _request("health_record", conflicting_args),
    )

    assert decision.action == "block"
    assert decision.reason == "health_record_target_mismatch"


def test_record_date_alias_is_canonicalized_before_the_gateway_dispatches():
    decision = decide_tool_capability(
        _snapshot("记录昨天体重70kg"),
        _request(
            "health_record",
            {
                "record_type": "weight",
                "data": {"weight": 70, "date": "2026-07-16"},
            },
        ),
    )

    assert decision.action == "allow"
    assert decision.normalized_args["data"]["record_date"] == "2026-07-16"


def test_record_date_alias_cannot_move_a_historical_write_to_today():
    decision = decide_tool_capability(
        _snapshot("记录昨天体重70kg"),
        _request(
            "health_record",
            {
                "record_type": "weight",
                "data": {"weight": 70, "date": "2026-07-17"},
            },
        ),
    )

    assert decision.action == "block"
    assert decision.reason == "health_record_target_mismatch"


@pytest.mark.parametrize(
    "extra_data",
    (
        {"status": "resolved"},
        {"end_date": "2026-07-17"},
    ),
)
def test_illness_create_rejects_model_invented_health_fields(extra_data):
    decision = decide_tool_capability(
        _snapshot("记录口腔溃疡"),
        _request(
            "health_record",
            {
                "record_type": "illness",
                "data": {"name": "口腔溃疡", **extra_data},
            },
        ),
    )

    assert decision.action == "block"
    assert decision.reason == "health_record_target_mismatch"


@pytest.mark.parametrize("record_type", ("illness", "symptom"))
def test_unmentioned_model_severity_is_removed_from_normalized_dispatch(
    record_type,
):
    if record_type == "illness":
        message = "记录口腔溃疡"
        data = {"name": "口腔溃疡", "severity": 5}
    else:
        message = "记录头痛"
        data = {
            "body_part": "head",
            "description": "头痛",
            "severity": 5,
        }

    decision = decide_tool_capability(
        _snapshot(message),
        _request(
            "health_record",
            {"record_type": record_type, "severity": 5, "data": data},
        ),
    )

    assert decision.action == "allow"
    assert "severity" not in decision.normalized_args
    assert "severity" not in decision.normalized_args["data"]


def test_illness_create_allows_safe_active_default_and_explicit_severity():
    decision = decide_tool_capability(
        _snapshot("记录口腔溃疡严重度6分"),
        _request(
            "health_record",
            {
                "record_type": "illness",
                "data": {
                    "name": "口腔溃疡",
                    "severity": 6,
                    "status": "active",
                },
            },
        ),
    )

    assert decision.action == "allow"


@pytest.mark.parametrize(
    "message",
    (
        "记录口腔溃疡严重度6级",
        "记录口腔溃疡，严重度6分",
    ),
)
def test_illness_explicit_severity_variants_survive_projection(message):
    decision = decide_tool_capability(
        _snapshot(message),
        _request(
            "health_record",
            {
                "record_type": "illness",
                "data": {"name": "口腔溃疡", "severity": 6},
            },
        ),
    )

    assert decision.action == "allow"
    assert decision.normalized_args["data"]["severity"] == 6


def test_illness_create_binds_explicit_notes_and_rejects_invented_notes():
    snapshot = _snapshot("记录口腔溃疡，备注舌尖疼")

    matching = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {
                "record_type": "illness",
                "data": {"name": "口腔溃疡", "notes": "舌尖疼"},
            },
        ),
    )
    invented = decide_tool_capability(
        _snapshot("记录口腔溃疡"),
        _request(
            "health_record",
            {
                "record_type": "illness",
                "data": {"name": "口腔溃疡", "notes": "舌尖疼"},
            },
        ),
    )

    assert matching.action == "allow"
    assert invented.action == "block"
    assert invented.reason == "health_record_target_mismatch"


def test_illness_explicit_status_alias_is_canonicalized_for_dispatch():
    decision = decide_tool_capability(
        _snapshot("记录已经痊愈的感冒"),
        _request(
            "health_record",
            {
                "record_type": "illness",
                "status": "resolved",
                "data": {"name": "感冒"},
            },
        ),
    )

    assert decision.action == "allow"
    assert decision.normalized_args["data"]["status"] == "resolved"


def test_medication_authorization_binds_observed_strength_separately_from_dosage():
    snapshot = _snapshot("记录阿奇霉素2粒每粒250mg")

    matching = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {
                "record_type": "medication",
                "data": {
                    "medication_name": "阿奇霉素",
                    "actual_dosage": "2粒",
                    "observed_strength": "250mg",
                },
            },
        ),
    )
    wrong_strength = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {
                "record_type": "medication",
                "data": {
                    "medication_name": "阿奇霉素",
                    "actual_dosage": "2粒",
                    "observed_strength": "500mg",
                },
            },
        ),
    )

    assert matching.action == "allow"
    assert wrong_strength.action == "block"
    assert wrong_strength.reason == "health_record_target_mismatch"


def test_medication_legacy_dosage_is_canonicalized_to_exact_consumed_field():
    unmentioned_dose = decide_tool_capability(
        _snapshot("记录阿莫西林"),
        _request(
            "health_record",
            {
                "record_type": "medication",
                "data": {"medication_name": "阿莫西林", "dosage": "10ml"},
            },
        ),
    )
    unmentioned_strength = decide_tool_capability(
        _snapshot("记录我吃了阿奇霉素2粒"),
        _request(
            "health_record",
            {
                "record_type": "medication",
                "data": {
                    "medication_name": "阿奇霉素",
                    "actual_dosage": "2粒",
                    "dosage": "250mg",
                },
            },
        ),
    )
    explicit_strength = decide_tool_capability(
        _snapshot("记录阿奇霉素2粒每粒250mg"),
        _request(
            "health_record",
            {
                "record_type": "medication",
                "data": {
                    "medication_name": "阿奇霉素",
                    "actual_dosage": "2粒",
                    "dosage": "250mg",
                },
            },
        ),
    )

    assert unmentioned_dose.action == "block"
    assert unmentioned_strength.action == "block"
    assert explicit_strength.action == "allow"
    assert explicit_strength.normalized_args["data"] == {
        "medication_name": "阿奇霉素",
        "actual_dosage": "2粒",
        "observed_strength": "250mg",
    }


def test_executor_medication_plan_uses_the_same_canonical_alias_parser():
    from app.services.agent_executor import AgentExecutor

    item, error = AgentExecutor._medication_item_from_health_record_args(
        {
            "record_type": "medication",
            "data": {
                "medication_name": "阿奇霉素",
                "actual_dosage": "2粒",
                "dosage": "250mg",
            },
        }
    )
    conflict_item, conflict_error = (
        AgentExecutor._medication_item_from_health_record_args(
            {
                "record_type": "medication",
                "data": {
                    "medication_name": "阿奇霉素",
                    "actual_dosage": "2粒",
                    "dose": "10粒",
                },
            }
        )
    )
    legacy_count_conflict_item, legacy_count_conflict_error = (
        AgentExecutor._medication_item_from_health_record_args(
            {
                "record_type": "medication",
                "data": {
                    "medication_name": "阿奇霉素",
                    "actual_dosage": "2粒",
                    "dosage": "10粒",
                },
            }
        )
    )

    assert error is None
    assert item == {
        "medication_name": "阿奇霉素",
        "actual_dosage": "2粒",
        "observed_strength": "250mg",
    }
    assert conflict_item is None
    assert "冲突" in str(conflict_error)
    assert legacy_count_conflict_item is None
    assert "冲突" in str(legacy_count_conflict_error)


def test_medication_legacy_count_alias_cannot_override_actual_dosage():
    decision = decide_tool_capability(
        _snapshot("记录我吃了阿奇霉素2粒"),
        _request(
            "health_record",
            {
                "record_type": "medication",
                "data": {
                    "medication_name": "阿奇霉素",
                    "actual_dosage": "2粒",
                    "dosage": "10粒",
                },
            },
        ),
    )

    assert decision.action == "block"
    assert decision.reason == "health_record_target_mismatch"


def test_date_aliases_canonicalize_to_one_stable_dispatch_payload():
    snapshot = _snapshot("记录昨天体重70kg")
    via_alias = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {
                "record_type": "weight",
                "data": {"weight": 70, "date": "2026-07-16"},
            },
        ),
    )
    via_canonical = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {
                "record_type": "weight",
                "data": {"weight": 70, "record_date": "2026-07-16"},
            },
        ),
    )

    assert via_alias.action == "allow"
    assert via_alias.normalized_args == via_canonical.normalized_args
    assert via_alias.normalized_args["data"] == {
        "weight": 70,
        "record_date": "2026-07-16",
    }


def test_date_only_symptom_projects_model_timestamp_to_server_owned_date():
    decision = decide_tool_capability(
        _snapshot("记录昨天头痛"),
        _request(
            "health_record",
            {
                "record_type": "symptom",
                "data": {
                    "body_part": "head",
                    "description": "头痛",
                    "occurred_at": "2026-07-16T23:59:59-12:00",
                },
            },
        ),
    )

    assert decision.action == "allow"
    assert decision.normalized_args["data"] == {
        "body_part": "head",
        "description": "头痛",
        "record_date": "2026-07-16",
    }


def test_explicit_symptom_clock_is_canonicalized_in_user_timezone():
    decision = decide_tool_capability(
        _snapshot("记录昨天9点头痛"),
        _request(
            "health_record",
            {
                "record_type": "symptom",
                "data": {
                    "body_part": "head",
                    "description": "头痛",
                    "occurred_at": "2026-07-16T09:00:00-12:00",
                },
            },
        ),
    )

    assert decision.action == "allow"
    assert decision.normalized_args["data"]["occurred_at"] == (
        "2026-07-16T09:00:00+08:00"
    )


def test_unmentioned_supplement_definition_fields_are_projected_out():
    decision = decide_tool_capability(
        _snapshot("记录鱼油"),
        _request(
            "health_record",
            {
                "record_type": "supplement",
                "data": {
                    "supplement_name": "鱼油",
                    "dosage": "4粒",
                    "timing": "bedtime",
                    "category": "药物",
                    "description": "治疗高血压",
                },
            },
        ),
    )

    assert decision.action == "allow"
    assert decision.normalized_args["data"] == {"supplement_name": "鱼油"}


def test_explicit_supplement_definition_fields_are_bound_and_preserved():
    snapshot = _snapshot("记录鱼油，剂量2粒，晚上吃")
    matching = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {
                "record_type": "supplement",
                "data": {
                    "supplement_name": "鱼油",
                    "dosage": "2粒",
                    "timing": "evening",
                    "category": "invented",
                },
            },
        ),
    )
    wrong = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {
                "record_type": "supplement",
                "data": {
                    "supplement_name": "鱼油",
                    "dosage": "4粒",
                    "timing": "morning",
                },
            },
        ),
    )

    assert matching.action == "allow"
    assert matching.normalized_args["data"] == {
        "supplement_name": "鱼油",
        "dosage": "2粒",
        "timing": "evening",
    }
    assert wrong.action == "block"


@pytest.mark.parametrize(
    "message",
    (
        "记录鱼油，每次2粒，晚上吃",
        "记录鱼油2粒晚上吃",
    ),
)
def test_compact_supplement_name_dosage_and_timing_are_bound(message):
    decision = decide_tool_capability(
        _snapshot(message),
        _request(
            "health_record",
            {
                "record_type": "supplement",
                "data": {
                    "supplement_name": "鱼油",
                    "dosage": "2粒",
                    "timing": "evening",
                },
            },
        ),
    )

    assert decision.action == "allow"
    assert decision.normalized_args["data"] == {
        "supplement_name": "鱼油",
        "dosage": "2粒",
        "timing": "evening",
    }


def test_food_conjunction_does_not_collapse_wagyu_lexeme():
    decision = decide_tool_capability(
        _snapshot("记录早餐米饭和和牛200g"),
        _request(
            "health_record",
            {
                "record_type": "diet",
                "data": {
                    "meal_type": "breakfast",
                    "food_items": "米饭和牛200g",
                },
            },
        ),
    )

    assert decision.action == "block"
    assert decision.reason == "health_record_target_mismatch"


@pytest.mark.parametrize(
    ("message", "food_items"),
    (
        ("记录晚餐，吃了日式和风沙拉", "日式和风沙拉"),
        ("记录早餐米饭和牛肉", "米饭、牛肉"),
        ("记录早餐米饭和和牛200g", "米饭、和牛200g"),
    ),
)
def test_food_conjunction_parser_distinguishes_lexemes_from_item_boundaries(
    message, food_items
):
    decision = decide_tool_capability(
        _snapshot(message),
        _request(
            "health_record",
            {
                "record_type": "diet",
                "data": {
                    "meal_type": "dinner" if "晚餐" in message else "breakfast",
                    "food_items": food_items,
                },
            },
        ),
    )

    assert decision.action == "allow"


@pytest.mark.parametrize(
    ("message", "matching_args", "wrong_severity_args"),
    (
        (
            "记录头痛程度6分",
            {
                "record_type": "symptom",
                "data": {
                    "body_part": "head",
                    "description": "头痛程度6分",
                    "severity": 6,
                },
            },
            {
                "record_type": "symptom",
                "data": {
                    "body_part": "head",
                    "description": "头痛程度6分",
                    "severity": 3,
                },
            },
        ),
        (
            "记录口腔溃疡严重程度5分",
            {
                "record_type": "illness",
                "data": {"name": "口腔溃疡", "severity": 5},
            },
            {
                "record_type": "illness",
                "data": {"name": "口腔溃疡", "severity": 2},
            },
        ),
    ),
)
def test_health_authorization_binds_explicit_severity(
    message, matching_args, wrong_severity_args
):
    snapshot = _snapshot(message)

    matching = decide_tool_capability(
        snapshot,
        _request("health_record", matching_args),
    )
    wrong = decide_tool_capability(
        snapshot,
        _request("health_record", wrong_severity_args),
    )

    assert matching.action == "allow"
    assert wrong.action == "block"
    assert wrong.reason == "health_record_target_mismatch"


@pytest.mark.parametrize(
    "record_args",
    (
        {"record_type": "water", "data": {"amount": 300}},
        {"record_type": "water", "data": {"amount_ml": 300}},
        {"record_type": "water", "amount": 300},
    ),
)
def test_water_aliases_produce_one_executor_consumable_payload(record_args):
    decision = decide_tool_capability(
        _snapshot("记录饮水300ml"),
        _request("health_record", record_args),
    )

    assert decision.action == "allow"
    assert decision.normalized_args == {
        "record_type": "water",
        "data": {"amount": 300},
    }


def test_unmentioned_water_type_is_projected_out():
    decision = decide_tool_capability(
        _snapshot("记录饮水300ml"),
        _request(
            "health_record",
            {
                "record_type": "water",
                "data": {"amount": 300, "drink_type": "烈酒"},
            },
        ),
    )

    assert decision.action == "allow"
    assert decision.normalized_args["data"] == {"amount": 300}


def test_conflicting_water_aliases_fail_closed():
    decision = decide_tool_capability(
        _snapshot("记录饮水300ml"),
        _request(
            "health_record",
            {
                "record_type": "water",
                "amount": 300,
                "data": {"amount_ml": 500},
            },
        ),
    )

    assert decision.action == "block"
    assert decision.reason == "health_record_target_mismatch"


def test_conflicting_record_type_aliases_fail_closed_before_projection():
    decision = decide_tool_capability(
        _snapshot("记录饮水300ml"),
        _request(
            "health_record",
            {
                "record_type": "water",
                "data": {"record_type": "weight", "amount": 300},
            },
        ),
    )

    assert decision.action == "block"
    assert decision.reason == "health_record_target_mismatch"


def test_fractional_severity_is_explicit_and_bound():
    snapshot = _snapshot("记录口腔溃疡，严重程度7/10")
    matching = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {"record_type": "illness", "data": {"name": "口腔溃疡", "severity": 7}},
        ),
    )
    wrong = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {"record_type": "illness", "data": {"name": "口腔溃疡", "severity": 5}},
        ),
    )

    assert matching.action == "allow"
    assert wrong.action == "block"


def test_medication_count_is_actual_dosage_and_mass_is_strength():
    snapshot = _snapshot("记录阿奇霉素250mg两片")
    matching = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {
                "record_type": "medication",
                "data": {
                    "medication_name": "阿奇霉素",
                    "actual_dosage": "2片",
                    "observed_strength": "250mg",
                },
            },
        ),
    )
    wrong = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {
                "record_type": "medication",
                "data": {"medication_name": "阿奇霉素", "actual_dosage": "250mg"},
            },
        ),
    )

    assert matching.action == "allow"
    assert wrong.action == "block"


def test_medication_authorization_supports_multiple_explicit_targets():
    snapshot = _snapshot("记录伊托必利1粒，记录替普瑞酮1粒")

    for name in ("伊托必利", "替普瑞酮"):
        decision = decide_tool_capability(
            snapshot,
            _request(
                "health_record",
                {
                    "record_type": "medication",
                    "data": {
                        "medication_name": name,
                        "actual_dosage": "1粒",
                    },
                },
            ),
        )
        assert decision.action == "allow"

    invented = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {
                "record_type": "medication",
                "data": {
                    "medication_name": "阿奇霉素",
                    "actual_dosage": "1粒",
                },
            },
        ),
    )
    assert invented.action == "block"


@pytest.mark.parametrize(
    ("message", "matching_args", "mismatching_args"),
    (
        (
            "记录心情4分",
            {"record_type": "mood", "data": {"mood_score": 4}},
            {"record_type": "mood", "data": {"mood_score": 2}},
        ),
        (
            "记录排便一次",
            {"record_type": "excretion", "data": {"type": "bowel"}},
            {"record_type": "excretion", "data": {"type": "diarrhea"}},
        ),
        (
            "记录昨晚23点入睡今天7点起床睡眠质量4分",
            {
                "record_type": "sleep",
                "data": {
                    "bedtime": "2026-07-16T23:00:00+08:00",
                    "wake_time": "2026-07-17T07:00:00+08:00",
                    "sleep_quality": 4,
                },
            },
            {
                "record_type": "sleep",
                "data": {
                    "bedtime": "2026-07-16T22:00:00+08:00",
                    "wake_time": "2026-07-17T07:00:00+08:00",
                    "sleep_quality": 4,
                },
            },
        ),
        (
            "创建目标：每日体重降到70kg",
            {
                "record_type": "goal",
                "data": {
                    "title": "每日体重降到70kg",
                    "goal_type": "weight",
                    "goal_period": "daily",
                    "target_value": 70,
                    "target_unit": "kg",
                },
            },
            {
                "record_type": "goal",
                "data": {
                    "title": "每日体重降到80kg",
                    "goal_type": "weight",
                    "goal_period": "daily",
                    "target_value": 80,
                    "target_unit": "kg",
                },
            },
        ),
        (
            "设置每天10:30臀中肌训练提醒",
            {
                "record_type": "reminder",
                "data": {
                    "title": "臀中肌训练",
                    "time": "10:30",
                    "recurrence": "daily",
                },
            },
            {
                "record_type": "reminder",
                "data": {
                    "title": "臀中肌训练",
                    "time": "11:30",
                    "recurrence": "daily",
                },
            },
        ),
    ),
)
def test_standard_health_writes_bind_every_semantic_selector(
    message, matching_args, mismatching_args
):
    snapshot = _snapshot(message)

    matching = decide_tool_capability(
        snapshot,
        _request("health_record", matching_args),
    )
    mismatching = decide_tool_capability(
        snapshot,
        _request("health_record", mismatching_args),
    )

    assert matching.action == "allow"
    assert mismatching.action == "block"
    assert mismatching.reason == "health_record_target_mismatch"


@pytest.mark.parametrize(
    ("message", "arguments", "expected_data"),
    (
        (
            "记录跑步30分钟",
            {
                "record_type": "exercise",
                "data": {
                    "exercise_type": "跑步",
                    "duration": 30,
                    "distance": 100,
                    "calories_burned": 4999,
                    "notes": "model invented",
                },
            },
            {
                "exercise_type": "跑步",
                "duration": 30,
            },
        ),
        (
            "记录头痛",
            {
                "record_type": "symptom",
                "data": {
                    "body_part": "head",
                    "description": "头痛",
                    "triggers": ["熬夜"],
                    "duration_minutes": 600,
                    "notes": "model invented",
                    "source": "siri",
                },
            },
            {
                "body_part": "head",
                "description": "头痛",
                "record_date": "2026-07-17",
            },
        ),
        (
            "记录排便一次",
            {
                "record_type": "excretion",
                "data": {
                    "type": "bowel",
                    "stool_type": 7,
                    "blood_present": True,
                    "pain_level": 5,
                    "notes": "model invented",
                },
            },
            {"type": "bowel"},
        ),
        (
            "设置每天10:30臀中肌训练提醒",
            {
                "record_type": "reminder",
                "data": {
                    "title": "臀中肌训练",
                    "time": "10:30",
                    "recurrence": "daily",
                    "message": "model invented",
                    "priority": "urgent",
                },
            },
            {
                "title": "臀中肌训练",
                "time": "10:30",
                "recurrence": "daily",
            },
        ),
    ),
)
def test_health_write_projection_drops_model_invented_persisted_fields(
    message,
    arguments,
    expected_data,
):
    decision = decide_tool_capability(
        _snapshot(message),
        _request("health_record", arguments),
    )

    assert decision.action == "allow"
    assert decision.normalized_args == {
        "record_type": arguments["record_type"],
        "data": expected_data,
    }


def test_mood_label_without_explicit_score_cannot_use_model_invented_required_value():
    decision = decide_tool_capability(
        _snapshot("记录心情平静"),
        _request(
            "health_record",
            {
                "record_type": "mood",
                "data": {"mood": "calm", "mood_score": 5},
            },
        ),
    )

    assert decision.action == "block"
    assert decision.reason == "health_record_authorization_target_unresolved"


def test_goal_without_explicit_type_and_period_cannot_persist_model_defaults():
    decision = decide_tool_capability(
        _snapshot("创建目标：90天把腰围降到82cm"),
        _request(
            "health_record",
            {
                "record_type": "goal",
                "data": {
                    "title": "90天把腰围降到82cm",
                    "goal_type": "weight",
                    "goal_period": "daily",
                    "target_value": 82,
                    "target_unit": "cm",
                },
            },
        ),
    )

    assert decision.action == "block"
    assert decision.reason == "health_record_authorization_target_unresolved"


def test_sleep_start_projects_out_model_invented_time_and_notes():
    decision = decide_tool_capability(
        _snapshot("准备开始睡觉了"),
        _request(
            "health_record",
            {
                "record_type": "sleep",
                "data": {
                    "bedtime": "2099-01-01T23:59:00+08:00",
                    "notes": "model invented",
                },
            },
        ),
    )

    assert decision.action == "allow"
    assert decision.normalized_args == {
        "record_type": "sleep",
        "data": {"title": "准备开始睡觉"},
    }


def test_reminder_window_is_rebuilt_from_explicit_user_schedule():
    decision = decide_tool_capability(
        _snapshot("设置定时饮水提醒每天9点到20点每隔1.5小时一次"),
        _request(
            "health_record",
            {
                "record_type": "reminder",
                "data": {
                    "title": "定时饮水",
                    "message": "model invented",
                    "start_time": "09:00",
                    "end_time": "20:00",
                    "interval_minutes": 90,
                    "recurrence": "daily",
                    "priority": "urgent",
                },
            },
        ),
    )

    assert decision.action == "allow"
    assert decision.normalized_args == {
        "record_type": "reminder",
        "data": {
            "title": "定时饮水",
            "start_time": "09:00",
            "end_time": "20:00",
            "interval_minutes": 90,
            "recurrence": "daily",
        },
    }


def test_diet_write_keeps_food_continuation_after_meal_comma():
    snapshot = _snapshot("记录早餐，一个包子和一个茶叶蛋")

    matching = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {
                "record_type": "diet",
                "data": {
                    "meal_type": "breakfast",
                    "food_items": "一个包子和一个茶叶蛋",
                },
            },
        ),
    )
    invented = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {
                "record_type": "diet",
                "data": {"meal_type": "breakfast", "food_items": "一碗粥"},
            },
        ),
    )

    assert matching.action == "allow"
    assert invented.action == "block"


def test_diet_write_keeps_declarative_food_continuation_after_meal_comma():
    snapshot = _snapshot(
        "记录早餐，吃了一个包子、一个茶叶蛋、一碗粥，计算热量和营养成分。"
    )

    decision = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {
                "record_type": "diet",
                "data": {
                    "meal_type": "breakfast",
                    "food_items": "一个包子、一个茶叶蛋、一碗粥",
                },
            },
        ),
    )

    assert decision.action == "allow"


def test_diet_write_does_not_absorb_medication_as_food_continuation():
    snapshot = _snapshot("记录早餐，吃了二甲双胍")

    decision = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {
                "record_type": "diet",
                "data": {
                    "meal_type": "breakfast",
                    "food_items": "二甲双胍",
                },
            },
        ),
    )

    assert decision.action == "block"


def test_diet_write_matches_structured_food_item_names():
    snapshot = _snapshot("记录晚餐：牛排和蔬菜")

    decision = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {
                "record_type": "diet",
                "data": {
                    "meal_type": "dinner",
                    "food_items": [{"name": "牛排"}, {"name": "蔬菜"}],
                },
            },
        ),
    )

    assert decision.action == "allow"


def test_diet_write_normalizes_equivalent_food_quantities_and_separators():
    snapshot = _snapshot("记录早餐，吃了一个包子、一碗粥")

    decision = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {
                "record_type": "diet",
                "data": {
                    "meal_type": "breakfast",
                    "food_items": "包子 1个 + 粥 1碗",
                },
            },
        ),
    )

    assert decision.action == "allow"


def test_compound_diet_write_preserves_food_names_that_start_with_conjunction_character():
    snapshot = _snapshot("记录早餐和牛200g，并记录喝水300ml")

    matching = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {
                "record_type": "diet",
                "data": {"meal_type": "breakfast", "food_items": "和牛200g"},
            },
        ),
    )
    truncated = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {
                "record_type": "diet",
                "data": {"meal_type": "breakfast", "food_items": "牛200g"},
            },
        ),
    )

    assert matching.action == "allow"
    assert truncated.action == "block"
    assert truncated.reason == "health_record_target_mismatch"


@pytest.mark.parametrize(
    ("message", "data"),
    (
        (
            "明天9点吃药提醒",
            {
                "title": "吃药",
                "remind_at": "2026-07-18T09:00:00+08:00",
            },
        ),
        (
            "每天9点提醒我吃药",
            {"title": "吃药", "time": "09:00", "recurrence": "daily"},
        ),
    ),
)
def test_reminder_binding_supports_scheduled_date_and_post_marker_title(message, data):
    decision = decide_tool_capability(
        _snapshot(message),
        _request("health_record", {"record_type": "reminder", "data": data}),
    )

    assert decision.action == "allow"


def test_recurring_reminder_binds_explicit_start_date():
    snapshot = _snapshot("从明天开始每天9点提醒我吃药")

    matching = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {
                "record_type": "reminder",
                "data": {
                    "title": "吃药",
                    "remind_at": "2026-07-18T09:00:00+08:00",
                    "recurrence": "daily",
                },
            },
        ),
    )
    wrong_start = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {
                "record_type": "reminder",
                "data": {
                    "title": "吃药",
                    "remind_at": "2026-07-19T09:00:00+08:00",
                    "recurrence": "daily",
                },
            },
        ),
    )

    assert matching.action == "allow"
    assert wrong_start.action == "block"
    assert wrong_start.reason == "health_record_target_mismatch"


def test_contextual_goal_target_remains_authoritative_when_clause_is_deictic():
    snapshot = _snapshot("记录这个")
    fallback_goal = compile_goal_spec(
        envelope=snapshot.envelope,
        context=snapshot.context,
        intent=snapshot.intent,
    )
    snapshot = replace(
        snapshot,
        goal=replace(
            fallback_goal,
            target_record_type="weight",
            target_values=(("weight", "71"),),
        ),
    )

    mismatch = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {"record_type": "illness", "data": {"name": "口腔溃疡"}},
        ),
    )
    matching = decide_tool_capability(
        snapshot,
        _request(
            "health_record",
            {"record_type": "weight", "data": {"weight": 71}},
        ),
    )

    assert mismatch.action == "block"
    assert mismatch.reason == "health_record_target_mismatch"
    assert matching.action == "allow"


@pytest.mark.parametrize(
    ("message", "arguments", "expected_data"),
    (
        (
            "记一下我鞋码42.5",
            {
                "record_type": "remember",
                "data": {
                    "predicate": "鞋码",
                    "object_value": "42.5",
                    "subject": "张三",
                    "is_sensitive": True,
                },
            },
            {"subject": "用户", "predicate": "鞋码", "object_value": "42.5"},
        ),
        (
            "记录生活事件：落地北京",
            {
                "record_type": "event",
                "data": {"title": "落地北京", "notes": "MODEL"},
            },
            {"title": "落地北京"},
        ),
        (
            "早上的补剂都吃了，记录一下",
            {
                "record_type": "supplement_group",
                "data": {"timing": "morning", "notes": "MODEL"},
            },
            {"timing": "morning"},
        ),
        (
            "记录跑步30分钟5公里",
            {
                "record_type": "exercise",
                "data": {
                    "exercise_type": "跑步",
                    "duration": 30,
                    "distance": 5,
                    "calories_burned": 9999,
                },
            },
            {"exercise_type": "跑步", "duration": 30, "distance": 5},
        ),
        (
            "记录俯卧撑10个做3组",
            {
                "record_type": "exercise",
                "data": {
                    "exercise_type": "俯卧撑",
                    "reps": 10,
                    "sets": 3,
                    "notes": "MODEL",
                },
            },
            {"exercise_type": "俯卧撑", "reps": 10, "sets": 3},
        ),
    ),
)
def test_supported_record_families_project_only_user_evidenced_fields(
    message,
    arguments,
    expected_data,
):
    decision = decide_tool_capability(
        _snapshot(message),
        _request("health_record", arguments),
    )

    assert decision.action == "allow"
    assert decision.normalized_args == {
        "record_type": arguments["record_type"],
        "data": expected_data,
    }


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
        _request(
            "health_manage",
            {"record_type": "diet", "operation": "update", "record_id": 1},
        ),
    )

    assert decision.action == "block"
    assert decision.receipt_required is True
    assert decision.reason == "manage_write_without_mutate_intent"


def test_mutation_turn_allows_health_manage_delete_with_receipt():
    decision = decide_tool_capability(
        _snapshot("删除饮食记录 1"),
        _request(
            "health_manage",
            {"record_type": "diet", "operation": "delete", "record_id": 1},
        ),
    )

    assert decision.action == "allow"
    assert decision.reason == "explicit_mutation_intent"
    assert decision.receipt_required is True


def test_update_turn_blocks_health_manage_delete_with_receipt():
    decision = decide_tool_capability(
        _snapshot("把刚才 300ml 改成 350ml"),
        _request(
            "health_manage",
            {"record_type": "water", "operation": "delete", "record_id": 718},
        ),
    )

    assert decision.action == "block"
    assert decision.reason == "manage_operation_mismatch"
    assert decision.receipt_required is True


@pytest.mark.parametrize(
    "message",
    (
        "把刚才 300ml 改成 350ml",
        "把饮水记录718（300ml）改成350ml",
        "把饮水记录718改成350ml",
        "把饮水记录718：300ml改成350ml",
        "请把饮水记录718（300ml）修改为350ml",
        "请把我的饮水记录718改成350ml",
        "请把我自己的饮水记录718改成350ml",
        "麻烦帮我把刚才300ml改成350ml",
        "请你帮我把刚才300ml改成350ml",
    ),
)
def test_update_turn_allows_health_manage_update_with_receipt(message):
    snapshot = replace(
        _snapshot(message),
        actionable_references=(
            ActionableReference(
                kind="owner_scoped_health_manage_list",
                data={
                    "record_type": "water",
                    "records": ({"id": 718, "amount": 300},),
                },
            ),
        ),
    )
    decision = decide_tool_capability(
        snapshot,
        _request(
            "health_manage",
            {
                "record_type": "water",
                "operation": "update",
                "record_id": 718,
                "data": {"amount": 350},
            },
        ),
    )

    assert decision.action == "allow"
    assert decision.reason == "explicit_mutation_intent"
    assert decision.normalized_args == {
        "record_type": "water",
        "operation": "update",
        "record_id": 718,
        "data": {"amount": 350},
    }
    assert decision.receipt_required is True


@pytest.mark.parametrize(
    "arguments",
    (
        {
            "record_type": "illness",
            "operation": "update",
            "record_id": 999999,
            "data": {"status": "resolved"},
        },
        {
            "record_type": "water",
            "operation": "update",
            "record_id": 719,
            "data": {"amount": 350},
        },
        {
            "record_type": "water",
            "operation": "update",
            "record_id": 718,
            "data": {"amount": 999},
        },
    ),
)
def test_update_requires_owner_scoped_identity_and_exact_user_patch(arguments):
    snapshot = replace(
        _snapshot("把刚才 300ml 改成 350ml"),
        actionable_references=(
            ActionableReference(
                kind="owner_scoped_health_manage_list",
                data={
                    "record_type": "water",
                    "records": ({"id": 718, "amount": 300},),
                },
            ),
        ),
    )

    decision = decide_tool_capability(
        snapshot,
        _request("health_manage", arguments),
    )

    assert decision.action == "block"
    assert decision.reason == "update_requires_exact_target_evidence"


def test_update_without_owner_scoped_list_or_explicit_id_is_blocked():
    decision = decide_tool_capability(
        _snapshot("把刚才 300ml 改成 350ml"),
        _request(
            "health_manage",
            {
                "record_type": "water",
                "operation": "update",
                "record_id": 718,
                "data": {"amount": 350},
            },
        ),
    )

    assert decision.action == "block"
    assert decision.reason == "update_requires_exact_target_evidence"


@pytest.mark.parametrize(
    "message",
    (
        "小明让我把刚才300ml改成350ml",
        "假设把刚才300ml改成350ml",
        "我说“把刚才300ml改成350ml”只是举例",
        "把刚才300ml改成350ml，这是小明的",
        "把刚才300ml改成350ml，不是我的，是小明的",
    ),
)
def test_update_requires_direct_current_user_semantic_authority(message):
    snapshot = replace(
        _snapshot(message),
        actionable_references=(
            ActionableReference(
                kind="owner_scoped_health_manage_list",
                data={
                    "record_type": "water",
                    "records": ({"id": 718, "amount": 300},),
                },
            ),
        ),
    )
    decision = decide_tool_capability(
        snapshot,
        _request(
            "health_manage",
            {
                "record_type": "water",
                "operation": "update",
                "record_id": 718,
                "data": {"amount": 350},
            },
        ),
    )

    assert decision.action == "block"
    assert decision.reason == "update_requires_exact_target_evidence"


def test_explicit_update_id_still_requires_owner_scoped_candidate():
    decision = decide_tool_capability(
        _snapshot("把饮水记录999999的300ml改成350ml"),
        _request(
            "health_manage",
            {
                "record_type": "water",
                "operation": "update",
                "record_id": 999999,
                "data": {"amount": 350},
            },
        ),
    )

    assert decision.action == "block"
    assert decision.reason == "update_requires_exact_target_evidence"


def test_illness_resolution_binds_owner_scoped_record_and_exact_patch():
    snapshot = replace(
        _snapshot("舌尖溃疡昨天好了，修改记录"),
        actionable_references=(
            ActionableReference(
                kind="owner_scoped_health_manage_list",
                data={
                    "record_type": "illness",
                    "records": ({"id": 71, "name": "舌尖溃疡", "status": "active"},),
                },
            ),
        ),
    )

    decision = decide_tool_capability(
        snapshot,
        _request(
            "health_manage",
            {
                "record_type": "illness",
                "operation": "update",
                "record_id": 71,
                "data": {
                    "status": "resolved",
                    "end_date": "2026-07-16",
                },
            },
        ),
    )

    assert decision.action == "allow"
    assert decision.normalized_args == {
        "record_type": "illness",
        "operation": "update",
        "record_id": 71,
        "data": {"status": "resolved", "end_date": "2026-07-16"},
    }


@pytest.mark.parametrize(
    "arguments",
    (
        {
            "record_type": "illness",
            "operation": "update",
            "record_id": 999999,
            "data": {"status": "resolved", "end_date": "2026-07-16"},
        },
        {
            "record_type": "illness",
            "operation": "update",
            "record_id": 71,
            "data": {
                "status": "resolved",
                "end_date": "2026-07-16",
                "severity": 1,
            },
        },
    ),
)
def test_illness_resolution_rejects_wrong_identity_or_invented_patch(arguments):
    snapshot = replace(
        _snapshot("舌尖溃疡昨天好了，修改记录"),
        actionable_references=(
            ActionableReference(
                kind="owner_scoped_health_manage_list",
                data={
                    "record_type": "illness",
                    "records": ({"id": 71, "name": "舌尖溃疡", "status": "active"},),
                },
            ),
        ),
    )

    decision = decide_tool_capability(
        snapshot,
        _request("health_manage", arguments),
    )

    assert decision.action == "block"
    assert decision.reason == "update_requires_exact_target_evidence"


@pytest.mark.parametrize(
    "phrase",
    (
        "好了点",
        "好了一些",
        "好了一半",
        "好了一丢丢",
        "好了一小点",
        "快好了",
        "基本好了",
        "一点点好了",
        "稍微好了",
        "有点好了",
        "算是好了",
        "差点好了",
    ),
)
def test_illness_partial_recovery_is_improving_not_resolved(phrase):
    snapshot = replace(
        _snapshot(f"舌尖溃疡昨天{phrase}，修改记录"),
        actionable_references=(
            ActionableReference(
                kind="owner_scoped_health_manage_list",
                data={
                    "record_type": "illness",
                    "records": ({"id": 71, "name": "舌尖溃疡", "status": "active"},),
                },
            ),
        ),
    )
    improving = decide_tool_capability(
        snapshot,
        _request(
            "health_manage",
            {
                "record_type": "illness",
                "operation": "update",
                "record_id": 71,
                "data": {"status": "improving"},
            },
        ),
    )
    resolved = decide_tool_capability(
        snapshot,
        _request(
            "health_manage",
            {
                "record_type": "illness",
                "operation": "update",
                "record_id": 71,
                "data": {"status": "resolved", "end_date": "2026-07-16"},
            },
        ),
    )

    assert improving.action == "allow"
    assert improving.normalized_args["data"] == {"status": "improving"}
    assert resolved.action == "block"


@pytest.mark.parametrize(
    "phrase",
    ("可能好了", "似乎好了", "好像好了", "大约好了"),
)
@pytest.mark.parametrize("status", ("improving", "resolved"))
def test_uncertain_illness_recovery_requires_clarification(phrase, status):
    snapshot = replace(
        _snapshot(f"舌尖溃疡昨天{phrase}，修改记录"),
        actionable_references=(
            ActionableReference(
                kind="owner_scoped_health_manage_list",
                data={
                    "record_type": "illness",
                    "records": ({"id": 71, "name": "舌尖溃疡", "status": "active"},),
                },
            ),
        ),
    )
    data = {"status": status}
    if status == "resolved":
        data["end_date"] = "2026-07-16"

    decision = decide_tool_capability(
        snapshot,
        _request(
            "health_manage",
            {
                "record_type": "illness",
                "operation": "update",
                "record_id": 71,
                "data": data,
            },
        ),
    )

    assert decision.action == "block"
    assert decision.reason == "update_requires_exact_target_evidence"


@pytest.mark.parametrize("status", ("active", "improving", "resolved"))
def test_illness_relapse_phrase_requires_clarification_instead_of_guessing(status):
    snapshot = replace(
        _snapshot("舌尖溃疡昨天一度好了又复发，修改记录"),
        actionable_references=(
            ActionableReference(
                kind="owner_scoped_health_manage_list",
                data={
                    "record_type": "illness",
                    "records": ({"id": 71, "name": "舌尖溃疡", "status": "active"},),
                },
            ),
        ),
    )
    data = {"status": status}
    if status == "resolved":
        data["end_date"] = "2026-07-16"

    decision = decide_tool_capability(
        snapshot,
        _request(
            "health_manage",
            {
                "record_type": "illness",
                "operation": "update",
                "record_id": 71,
                "data": data,
            },
        ),
    )

    assert decision.action == "block"
    assert decision.reason == "update_requires_exact_target_evidence"


@pytest.mark.parametrize(
    "phrase",
    (
        "并没有好转",
        "还没好转",
        "看起来好了其实没有",
    ),
)
@pytest.mark.parametrize("status", ("active", "improving", "resolved"))
def test_negated_illness_recovery_requires_clarification_instead_of_guessing(
    phrase,
    status,
):
    snapshot = replace(
        _snapshot(f"舌尖溃疡昨天{phrase}，修改记录"),
        actionable_references=(
            ActionableReference(
                kind="owner_scoped_health_manage_list",
                data={
                    "record_type": "illness",
                    "records": ({"id": 71, "name": "舌尖溃疡", "status": "active"},),
                },
            ),
        ),
    )
    data = {"status": status}
    if status == "resolved":
        data["end_date"] = "2026-07-16"

    decision = decide_tool_capability(
        snapshot,
        _request(
            "health_manage",
            {
                "record_type": "illness",
                "operation": "update",
                "record_id": 71,
                "data": data,
            },
        ),
    )

    assert decision.action == "block"
    assert decision.reason == "update_requires_exact_target_evidence"


@pytest.mark.parametrize(
    "phrase",
    (
        "并非好转",
        "不算好转",
        "毫无好转",
        "好转但今天加重了",
        "好了又发作了",
        "痊愈后今天复发",
        "并无好转",
        "尚无好转",
        "绝非好转",
        "算不上好转",
        "好转不了",
        "看不出好转",
        "似乎好转",
        "好了今天又犯了",
        "好转同时今天更严重了",
        "没有证据表明已经康复",
        "未见好转",
        "没有出现好转",
        "康复尚未证实",
        "没有理由认为已经康复",
        "并非还在发作中",
        "可能还没好",
        "大概正在逐步好转",
        "不代表已经好转",
        "好了今天又疼了",
        "尚未观察到好转",
        "不能说明已经康复",
        "据说已经好转",
        "好转存疑",
        "还没好只是猜测",
        "正在发作中尚未确认",
        "未能确认已经康复",
        "康复还无法确定",
        "好转与否还不确定",
        "看似在好转",
        "好转是假象",
        "估计已经好转了",
        "未必已经好转",
        "大概快好了",
        "估计还没好",
        "未必还在发作中",
        "昨天好了今天又长出来了",
        "昨天好了但今天疼得更厉害",
        "不一定已经康复",
        "好转尚待观察",
        "多半已经好转",
        "不排除已经好转",
        "昨天好了今天再疼起来",
        "昨天好了今天症状回来了",
        "昨天好了今天又溃疡了",
        "昨天好了今天再次长出了",
        "昨天好了但同一处又红了",
    ),
)
@pytest.mark.parametrize("status", ("active", "improving", "resolved"))
def test_negated_worsening_or_recurrent_illness_never_compiles_a_patch(
    phrase,
    status,
):
    snapshot = replace(
        _snapshot(f"舌尖溃疡昨天{phrase}，修改记录"),
        actionable_references=(
            ActionableReference(
                kind="owner_scoped_health_manage_list",
                data={
                    "record_type": "illness",
                    "records": ({"id": 71, "name": "舌尖溃疡", "status": "active"},),
                },
            ),
        ),
    )
    data = {"status": status}
    if status == "resolved":
        data["end_date"] = "2026-07-16"

    decision = decide_tool_capability(
        snapshot,
        _request(
            "health_manage",
            {
                "record_type": "illness",
                "operation": "update",
                "record_id": 71,
                "data": data,
            },
        ),
    )

    assert decision.action == "block"
    if phrase == "不能说明已经康复":
        assert decision.reason in {
            "manage_write_without_mutate_intent",
            "update_requires_exact_target_evidence",
        }
    else:
        assert decision.reason == "update_requires_exact_target_evidence"


def test_clear_active_illness_state_remains_a_supported_update():
    snapshot = replace(
        _snapshot("舌尖溃疡还没好，修改记录"),
        actionable_references=(
            ActionableReference(
                kind="owner_scoped_health_manage_list",
                data={
                    "record_type": "illness",
                    "records": ({"id": 71, "name": "舌尖溃疡", "status": "improving"},),
                },
            ),
        ),
    )

    decision = decide_tool_capability(
        snapshot,
        _request(
            "health_manage",
            {
                "record_type": "illness",
                "operation": "update",
                "record_id": 71,
                "data": {"status": "active"},
            },
        ),
    )

    assert decision.action == "allow"
    assert decision.normalized_args["data"] == {"status": "active"}


@pytest.mark.parametrize(
    "message",
    (
        "舌尖溃疡已经明显改善，修改记录",
        "舌尖溃疡未用药就好转，修改记录",
        "舌尖溃疡没有加重反而明显改善，修改记录",
        "舌尖溃疡没有出现加重反而明显改善，修改记录",
    ),
)
def test_clear_illness_improvement_paraphrase_remains_supported(message):
    snapshot = replace(
        _snapshot(message),
        actionable_references=(
            ActionableReference(
                kind="owner_scoped_health_manage_list",
                data={
                    "record_type": "illness",
                    "records": ({"id": 71, "name": "舌尖溃疡", "status": "active"},),
                },
            ),
        ),
    )

    decision = decide_tool_capability(
        snapshot,
        _request(
            "health_manage",
            {
                "record_type": "illness",
                "operation": "update",
                "record_id": 71,
                "data": {"status": "improving"},
            },
        ),
    )

    assert decision.action == "allow"
    assert decision.normalized_args["data"] == {"status": "improving"}


@pytest.mark.parametrize(
    "message",
    (
        "舌尖溃疡记录999昨天好了，修改记录",
        "舌尖溃疡条目999昨天好了，修改记录",
        "舌尖溃疡的疾病记录999昨天好了，修改记录",
        "舌尖溃疡记录编号999昨天好了，修改记录",
        "舌尖溃疡记录ID999昨天好了，修改记录",
        "舌尖溃疡记录编号：999昨天好了，修改记录",
        "舌尖溃疡第999号记录昨天好了，修改记录",
        "舌尖溃疡记录编号为999昨天好了，修改记录",
        "舌尖溃疡第999条疾病记录昨天好了，修改记录",
        "舌尖溃疡疾病记录第999号昨天好了，修改记录",
        "舌尖溃疡ID999昨天好转了，修改记录",
        "舌尖溃疡疾病记录（ID999）昨天好了，修改记录",
        "舌尖溃疡第999个疾病记录昨天好了，修改记录",
        "舌尖溃疡ID=999昨天好转了，修改记录",
        "舌尖溃疡ID为999昨天好转了，修改记录",
        "舌尖溃疡ID是999昨天好转了，修改记录",
        "舌尖溃疡编号999昨天好转了，修改记录",
        "舌尖溃疡#999昨天好转了，修改记录",
    ),
)
def test_visible_illness_record_id_cannot_fall_back_to_a_different_named_record(
    message,
):
    snapshot = replace(
        _snapshot(message),
        actionable_references=(
            ActionableReference(
                kind="owner_scoped_health_manage_list",
                data={
                    "record_type": "illness",
                    "records": ({"id": 71, "name": "舌尖溃疡", "status": "active"},),
                },
            ),
        ),
    )

    decision = decide_tool_capability(
        snapshot,
        _request(
            "health_manage",
            {
                "record_type": "illness",
                "operation": "update",
                "record_id": 71,
                "data": {"status": "improving"},
            },
        ),
    )

    assert decision.action == "block"
    assert decision.reason == "update_requires_exact_target_evidence"


def test_illness_update_does_not_bind_generic_list_name_to_specific_user_entity():
    snapshot = replace(
        _snapshot("舌尖溃疡昨天好了，修改记录"),
        actionable_references=(
            ActionableReference(
                kind="owner_scoped_health_manage_list",
                data={
                    "record_type": "illness",
                    "records": ({"id": 71, "name": "溃疡", "status": "active"},),
                },
            ),
        ),
    )
    decision = decide_tool_capability(
        snapshot,
        _request(
            "health_manage",
            {
                "record_type": "illness",
                "operation": "update",
                "record_id": 71,
                "data": {"status": "resolved", "end_date": "2026-07-16"},
            },
        ),
    )

    assert decision.action == "block"
    assert decision.reason == "update_requires_exact_target_evidence"


@pytest.mark.parametrize(
    "message",
    (
        "把上一条饮水记录的备注去掉",
        "把上一条饮水记录里的备注去掉",
        "把上一条饮水记录备注删掉",
        "把上一条饮水记录内的饮水量删掉",
        "把上一条饮水记录上面的说明删掉",
        "把备注从上一条饮水记录里去掉",
        "从上一条饮水记录里把备注去掉",
        "从上一条饮水记录中把说明删掉",
        "从上一条饮食记录里将热量删除",
        "把上一条体重记录这个体重字段删掉",
        "删除上一条饮食记录热量",
        "把备注在上一条饮水记录里去掉",
        "把上一条饮水记录里的单位去掉",
        "把上一条运动记录里的距离去掉",
        "把来源从上一条饮水记录里删除",
        "把上一条运动记录中的速度删掉",
        "撤销刚才对饮水记录的修改",
        "删除上一条饮水记录并改成 350ml",
        "删除饮水记录",
        "删除第一条记录",
        "删除两条饮水记录",
        "删除上一条饮水记录",
        "删除上一条体重记录",
        "请帮我删除上一条体重记录",
        "把上一条饮食记录删了",
        "清掉记录 718",
        "删除上一餐",
        "我要删除上一条饮水记录",
        "删除刚才的饮水记录",
        "给我删除上一条饮水记录",
        "确认删除上一条饮水记录",
        "删除上一条不是饮水的记录",
        "删除上一条饮水以外的记录",
        "删除上一条非饮水记录",
        "删除上一条除饮水外的记录",
        "删除上一条不含饮水的记录",
        "删除饮水或用药记录 718",
        "删除饮水用药记录 718",
        "删除第1条或第2条饮水记录",
        "删除所有饮水记录 718",
        "删除饮水记录 718 和 719",
        "删除饮水记录 718-719",
        "删除饮水记录 718 的备注",
        "撤销删除饮水记录 718",
        "删除饮水记录 718 并改成 350ml",
    ),
)
def test_delete_requires_explicit_whole_record_intent(message):
    decision = decide_tool_capability(
        _snapshot(message),
        _request(
            "health_manage",
            {"record_type": "water", "operation": "delete", "record_id": 718},
        ),
    )

    assert decision.action == "block"
    assert decision.reason == "delete_requires_explicit_whole_record_intent"
    assert decision.receipt_required is True


@pytest.mark.parametrize(
    ("message", "record_type"),
    (
        ("删除饮水记录 718", "water"),
        ("请帮我删除体重记录 718", "weight"),
        ("把饮食记录 718 删了", "diet"),
        ("我要删除饮水记录 718", "water"),
        ("给我删除饮水记录 718", "water"),
        ("确认删除饮水记录 718", "water"),
        ("删除 bp 记录 718", "blood_pressure"),
        ("删除 blood_pressure 记录 718", "blood_pressure"),
        ("删除 medication 记录 718", "medication"),
        ("删除用药记录 718", "medication"),
        ("删除 meal 记录 718", "diet"),
        ("删除饮食记录 718", "diet"),
    ),
)
def test_explicit_whole_record_delete_remains_allowed(message, record_type):
    decision = decide_tool_capability(
        _snapshot(message),
        _request(
            "health_manage",
            {
                "record_type": record_type,
                "operation": "delete",
                "record_id": 718,
            },
        ),
    )

    assert decision.action == "allow"
    assert decision.reason == "explicit_mutation_intent"
    assert decision.receipt_required is True


@pytest.mark.parametrize(
    ("message", "record_type", "record_id"),
    (
        ("删除上一条饮水记录", "medication", 718),
        ("删除上一条饮水记录", "water", 718),
        ("清掉记录 718", "medication", 718),
        ("清掉记录 718", "water", 718),
        ("清掉记录 718", "water", 719),
        ("删除饮水记录 718", "weight", 718),
        ("删除饮水记录 718", "water", 719),
        ("删除第一条记录", "water", 718),
        ("删除两条饮水记录", "water", 718),
        ("删除饮水或用药记录 718", "water", 718),
        ("删除饮水用药记录 718", "water", 718),
        ("删除第1条或第2条饮水记录", "water", 718),
        ("删除所有饮水记录 718", "water", 718),
        ("删除上一条非饮水记录", "water", 718),
        ("删除上一条除饮水外的记录", "water", 718),
        ("删除上一条不含饮水的记录", "water", 718),
    ),
)
def test_delete_evidence_must_bind_to_requested_target(
    message,
    record_type,
    record_id,
):
    decision = decide_tool_capability(
        _snapshot(message),
        _request(
            "health_manage",
            {
                "record_type": record_type,
                "operation": "delete",
                "record_id": record_id,
            },
        ),
    )

    assert decision.action == "block"
    assert decision.reason == "delete_requires_explicit_whole_record_intent"
    assert decision.receipt_required is True


@pytest.mark.parametrize("record_id", (718, "718", 718.0))
def test_explicit_delete_id_accepts_canonical_positive_integer_forms(record_id):
    decision = decide_tool_capability(
        _snapshot("清掉饮水记录 718"),
        _request(
            "health_manage",
            {
                "record_type": "water",
                "operation": "delete",
                "record_id": record_id,
            },
        ),
    )

    assert decision.action == "allow"


@pytest.mark.parametrize(
    "record_id",
    (None, False, 0, -1, 718.5, "718.0", "718.5", "invalid"),
)
def test_explicit_delete_id_rejects_noncanonical_or_nonpositive_values(record_id):
    decision = decide_tool_capability(
        _snapshot("清掉饮水记录 718"),
        _request(
            "health_manage",
            {
                "record_type": "water",
                "operation": "delete",
                "record_id": record_id,
            },
        ),
    )

    assert decision.action == "block"
    assert decision.reason == "delete_requires_explicit_whole_record_intent"


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        (718, 718),
        ("718", 718),
        (718.0, 718),
        (None, None),
        (False, None),
        (0, None),
        (-1, None),
        (718.5, None),
        ("718.0", None),
        ("invalid", None),
    ),
)
def test_health_manage_record_id_canonicalization_is_strict(value, expected):
    assert capability_policy_module.canonical_health_manage_record_id(value) == expected


def test_write_turn_allows_health_record_with_receipt():
    decision = decide_tool_capability(
        _snapshot("记录午餐吃了牛肉面"),
        _request(
            "health_record",
            {
                "record_type": "diet",
                "data": {"meal_type": "lunch", "food_items": "牛肉面"},
            },
        ),
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
    ("请您删除用药记录 1", "请您删除用药记录 1🩺"),
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
    snapshot = _snapshot("医生说是臀肌无力。请记录医生诊断：臀肌无力导致腰痛")
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
    food_items = message.removeprefix("记录午餐")
    decision = decide_tool_capability(
        _snapshot(message),
        _request(
            "health_record",
            {
                "record_type": "diet",
                "data": {"meal_type": "lunch", "food_items": food_items},
            },
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
        _request(
            "health_record", {"record_type": "diet", "data": {"food_items": "米饭"}}
        ),
    )

    assert decision.action == "block"
    assert decision.reason == "aigc_media_turn_disallows_health_write"
    assert decision.receipt_required is True


def test_compound_write_and_analysis_turn_allows_health_record():
    decision = decide_tool_capability(
        _snapshot("记录晚餐牛肉面，帮我分析今天的热量和蛋白质"),
        _request(
            "health_record",
            {
                "record_type": "diet",
                "data": {"meal_type": "dinner", "food_items": "牛肉面"},
            },
        ),
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


def test_health_query_policy_projects_only_public_schema_fields():
    decision = decide_tool_capability(
        _snapshot("查一下我近半年睡眠的记录"),
        _request(
            "health_query",
            {
                "dimension": "sleep",
                "days": 183,
                "record_type": "symptom",
                "data": {"description": "模型自造字段"},
            },
        ),
    )

    assert decision.action == "allow"
    assert decision.normalized_args == {"dimension": "sleep", "days": 183}


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
def test_recipe_replay_source_cannot_authorize_persistent_or_external_record_types(
    record_type,
):
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
def test_provider_confirmation_whitespace_cannot_authorize_model_selected_draft(
    message,
):
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
    decision = decide_tool_capability(
        _snapshot("帮我分析一下最近的健康情况"), _request(tool_name, args)
    )

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
    decision = decide_tool_capability(
        _snapshot("分析一下我的睡眠"), _request("future_tool", {})
    )

    assert decision.action == "block"
    assert decision.reason == "unknown_tool"


def test_capability_policy_digest_is_deterministic_content_free_sha256():
    first = capability_policy_digest()
    second = capability_policy_digest()
    payload = capability_policy_contract_payload()

    assert first == second
    assert re.fullmatch(r"[0-9a-f]{64}", first)
    assert payload["contract_version"] == "agent-capability-policy-v27"
    assert payload["health_record_target_binding"] == {
        "version": "authorized-target-set-v23",
        "domain_types": {
            "diet": "diet",
            "exercise": "exercise",
            "medication": "medication",
            "mood": "mood",
            "reminder": "reminder",
            "sleep": "sleep",
            "supplement": "supplement",
            "symptom": "symptom",
            "water": "water",
        },
    }
    assert (
        payload["whole_record_delete_evidence_version"] == "record-delete-evidence-v2"
    )
    assert (
        payload["health_manage_update_evidence_version"] == "record-update-evidence-v18"
    )
    assert payload["known_tools"]
    assert payload["recipe_record_types"]
    serialized = repr(payload).lower()
    assert "prompt" not in serialized
    assert "user_id" not in serialized
    assert "health_value" not in serialized
