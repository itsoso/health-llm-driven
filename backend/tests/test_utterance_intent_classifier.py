from datetime import datetime, timedelta, timezone
from inspect import getsource

import pytest

import app.services.utterance_intent_classifier as utterance_intent_classifier
from app.services.utterance_intent_classifier import classify_agent_utterance

BJ = timezone(timedelta(hours=8))


def test_read_only_diet_record_noun_is_not_a_write_intent():
    intent = classify_agent_utterance("今天我的饮食的记录，帮我列个表格出来。")

    assert intent.primary == "read"
    assert intent.domain == "diet"
    assert intent.operation == "list"
    assert intent.scope == {"date": datetime.now(BJ).date().isoformat()}
    assert intent.is_write is False


def test_contrastive_correction_stays_read_only():
    intent = classify_agent_utterance("不是记录，是列出我今天吃的所有东西。")

    assert intent.primary == "read"
    assert intent.domain == "diet"
    assert intent.operation == "list"
    assert intent.is_write is False


def test_real_record_command_is_write_intent():
    intent = classify_agent_utterance("记录午餐吃了牛肉面")

    assert intent.primary == "write"
    assert intent.domain == "diet"
    assert intent.operation == "create"
    assert intent.is_write is True


def test_clear_symptom_statement_is_write_intent():
    intent = classify_agent_utterance("还是有腰疼的症状。")

    assert intent.primary == "write"
    assert intent.domain == "symptom"
    assert intent.operation == "create"
    assert intent.is_write is True


def test_clinician_attributed_assessment_is_context_not_symptom_write():
    intent = classify_agent_utterance(
        "医生诊断是大腿和臀部肌肉无力导致腰肌代偿进而导致腰肌痛"
    )

    assert intent.primary == "chat"
    assert intent.domain == "clinical_context"
    assert intent.operation == "acknowledge"
    assert intent.is_write is False
    assert intent.requires_reliable_tool_model is True


def test_clinician_attributed_question_is_reliable_advice():
    intent = classify_agent_utterance(
        "医生认为是臀肌无力导致腰痛，我该怎么处理？"
    )

    assert intent.primary == "advice"
    assert intent.domain == "clinical_context"
    assert intent.operation == "analyze"
    assert intent.is_write is False
    assert intent.requires_reliable_tool_model is True


def test_explicit_clinician_feedback_save_is_reliable_write():
    intent = classify_agent_utterance(
        "请记录医生诊断：臀肌无力导致腰肌代偿"
    )

    assert intent.primary == "write"
    assert intent.domain == "clinical_context"
    assert intent.operation == "create"
    assert intent.is_write is True
    assert intent.requires_reliable_tool_model is True


@pytest.mark.parametrize(
    "message",
    (
        "医生说是臀肌无力。请记录医生诊断：臀肌无力导致腰痛",
        "医生说是臀肌无力，帮我记录一下",
        "医生说是臀肌无力！请记录医生诊断：臀肌无力导致腰痛",
        "医生说是臀肌无力\n请记录医生诊断：臀肌无力导致腰痛",
    ),
)
def test_adjacent_user_save_authorizes_clinician_feedback(message):
    intent = classify_agent_utterance(message)

    assert intent.primary == "write"
    assert intent.domain == "clinical_context"
    assert intent.operation == "create"
    assert intent.is_write is True
    assert intent.requires_reliable_tool_model is True


@pytest.mark.parametrize(
    "message",
    (
        "医生说请记录医生诊断",
        "医生说请把医生诊断记录下来",
        "医生说要记录每天疼痛情况",
        "康复师说请记录每天疼痛情况",
        "检查提示要记录每天疼痛情况",
    ),
)
def test_clinician_reported_record_instruction_is_not_user_authorization(message):
    intent = classify_agent_utterance(message)

    assert intent.primary == "chat"
    assert intent.domain == "clinical_context"
    assert intent.operation == "acknowledge"
    assert intent.is_write is False
    assert intent.requires_reliable_tool_model is True


@pytest.mark.parametrize(
    "message",
    (
        "我想记录医生诊断：臀肌无力导致腰痛",
        "医生诊断请帮我记录一下",
        "医生诊断，记一下",
        "医生的诊断帮我保存下来",
        "请把医生诊断记录下来",
        "请记录医生诊断记录",
    ),
)
def test_structural_user_command_authorizes_clinician_feedback_save(message):
    intent = classify_agent_utterance(message)

    assert intent.primary == "write"
    assert intent.domain == "clinical_context"
    assert intent.operation == "create"
    assert intent.is_write is True
    assert intent.requires_reliable_tool_model is True


def test_user_ba_construction_authorizes_clinician_feedback_save():
    intent = classify_agent_utterance("把医生说的内容保存下来")

    assert intent.primary == "write"
    assert intent.domain == "clinical_context"
    assert intent.operation == "create"
    assert intent.is_write is True
    assert intent.requires_reliable_tool_model is True


@pytest.mark.parametrize(
    "message",
    (
        "医生说要查看昨天用药记录",
        "医生说要记录每天疼痛情况",
        "医生说要调整用药",
        "医生建议删除昨天的用药记录",
        "医生说要同步最近的健康数据",
        "康复师说请记录每天的疼痛",
        "医生说请把医生诊断记录删除",
    ),
)
def test_clinician_reported_mutation_is_not_user_authorization(message):
    intent = classify_agent_utterance(message)

    assert intent.primary == "chat"
    assert intent.domain == "clinical_context"
    assert intent.operation == "acknowledge"
    assert intent.is_write is False
    assert intent.requires_reliable_tool_model is True


@pytest.mark.parametrize(
    "message",
    (
        "医生告诉我是臀肌无力导致腰痛",
        "主治医生告诉我是臀肌无力导致腰痛",
        "大夫告知是臀肌无力导致腰痛",
    ),
)
def test_clinician_disclosure_is_attribution_not_agent_read(message):
    intent = classify_agent_utterance(message)

    assert intent.primary == "chat"
    assert intent.domain == "clinical_context"
    assert intent.operation == "acknowledge"
    assert intent.is_write is False
    assert intent.requires_reliable_tool_model is True


@pytest.mark.parametrize(
    ("message", "expected"),
    (
        (
            "医生说要记录每天疼痛情况",
            ("clinician_quote", "save", "clinician", "clinician_content"),
        ),
        (
            "请记录医生诊断",
            ("user", "save", "user", "clinician_record"),
        ),
        (
            "把医生说的内容保存下来",
            ("clinician_quote", "save", "user", "clinician_content"),
        ),
    ),
)
def test_clause_frame_resolves_action_actor_and_object(message, expected):
    frame = utterance_intent_classifier._classify_clause(message)

    assert (frame.source, frame.action, frame.actor, frame.object_kind) == expected


@pytest.mark.parametrize(
    "message",
    (
        "医生说是臀肌无力。请删除",
        "医生说是臀肌无力。请调整",
        "医生说是臀肌无力。请同步",
    ),
)
def test_non_save_action_cannot_inherit_previous_clinician_object(message):
    intent = classify_agent_utterance(message)

    assert intent.primary == "chat"
    assert intent.domain == "clinical_context"
    assert intent.operation == "acknowledge"
    assert intent.is_write is False
    assert intent.requires_reliable_tool_model is True


@pytest.mark.parametrize(
    "message",
    (
        "请记录医生诊断，不要记录",
        "医生说是臀肌无力。不要删除医生诊断记录",
        "医生说是臀肌无力。不要调整医生诊断记录",
        "医生说是臀肌无力。不要同步医生诊断记录",
    ),
)
def test_clinician_clause_authorization_respects_negation(message):
    intent = classify_agent_utterance(message)

    assert intent.is_write is False
    assert intent.primary not in {"write", "mutate"}


def test_direct_user_medication_mutation_remains_authorized():
    intent = classify_agent_utterance("把用药剂量调整为每天两次")

    assert intent.primary == "mutate"
    assert intent.domain == "medication"
    assert intent.operation == "update"
    assert intent.is_write is True
    assert intent.requires_reliable_tool_model is True


@pytest.mark.parametrize(
    ("message", "expected_primary", "expected_operation", "expected_is_write"),
    (
        ("查看医生诊断记录", "read", "list", False),
        ("医生诊断记录有哪些？", "read", "ask", False),
        ("删除医生诊断记录", "mutate", "delete", True),
    ),
)
def test_clinician_record_reference_keeps_explicit_record_operation(
    message,
    expected_primary,
    expected_operation,
    expected_is_write,
):
    intent = classify_agent_utterance(message)

    assert intent.primary == expected_primary
    assert intent.operation == expected_operation
    assert intent.is_write is expected_is_write


def test_clinician_record_noun_phrase_is_not_promoted_to_a_write():
    intent = classify_agent_utterance("医生诊断记录")

    assert intent.primary == "unknown"
    assert intent.operation == "none"
    assert intent.is_write is False


@pytest.mark.parametrize(
    "message",
    (
        "医生的诊断是臀肌无力导致腰痛",
        "检查提示腰肌劳损导致疼痛",
        "大夫说是臀肌无力导致腰痛",
    ),
)
def test_common_clinician_attribution_variants_are_non_write_context(message):
    intent = classify_agent_utterance(message)

    assert intent.primary == "chat"
    assert intent.domain == "clinical_context"
    assert intent.operation == "acknowledge"
    assert intent.is_write is False
    assert intent.requires_reliable_tool_model is True


def test_reported_clinician_medication_statement_is_not_a_save_command():
    intent = classify_agent_utterance("医生说我吃了药")

    assert intent.primary == "chat"
    assert intent.domain == "clinical_context"
    assert intent.operation == "acknowledge"
    assert intent.is_write is False
    assert intent.requires_reliable_tool_model is True


@pytest.mark.parametrize(
    ("raw", "expected"),
    (
        (
            "医生说是臀肌无力。请记录医生诊断：臀肌无力导致腰痛",
            ("医生说是臀肌无力", "请记录医生诊断", "臀肌无力导致腰痛"),
        ),
        ("甲，乙,丙；丁;戊：己:庚", ("甲", "乙", "丙", "丁", "戊", "己", "庚")),
        ("甲！乙?丙？丁\n戊", ("甲", "乙", "丙", "丁", "戊")),
        ("  甲！？\n，。；乙  ", ("甲", "乙")),
        ("，。！？\n", ()),
        ("", ()),
    ),
)
def test_split_clauses_preserves_non_empty_order_across_boundaries(raw, expected):
    assert utterance_intent_classifier._split_clauses(raw) == expected


def test_current_symptom_with_severity_remains_a_symptom_write():
    intent = classify_agent_utterance("今天腰痛 6 分")

    assert intent.primary == "write"
    assert intent.domain == "symptom"
    assert intent.operation == "create"
    assert intent.is_write is True


def test_natural_sneeze_recording_is_symptom_write_intent():
    intent = classify_agent_utterance("记录下来刚才打了一个喷嚏。")

    assert intent.primary == "write"
    assert intent.domain == "symptom"
    assert intent.operation == "create"
    assert intent.is_write is True


def test_symptom_question_stays_advice():
    intent = classify_agent_utterance("腰疼怎么办？")

    assert intent.primary == "advice"
    assert intent.is_write is False


def test_compound_record_and_analysis_keeps_write_capability():
    intent = classify_agent_utterance(
        "记录晚餐牛肉面，帮我分析今天的热量和蛋白质"
    )

    assert intent.primary == "write"
    assert intent.operation == "create"
    assert intent.is_write is True


def test_diet_nutrition_request_with_carbs_is_not_misrouted_to_water():
    intent = classify_agent_utterance(
        "记录晚餐吃了沙拉，同时计算这餐的热量、蛋白质、碳水、脂肪和膳食纤维"
    )

    assert intent.primary == "write"
    assert intent.domain == "diet"
    assert intent.operation == "create"


@pytest.mark.parametrize(
    "message",
    (
        "喝水300ml",
        "喝了250ml水",
        "记录饮水半升",
        "喝了一杯水",
        "记录一杯水",
        "记录500ml水",
        "记下两瓶水",
        "今天水喝少了",
        "喝了一杯水准备睡觉",
        "记录一杯水然后吃饭",
    ),
)
def test_explicit_water_intake_stays_in_water_domain(message):
    intent = classify_agent_utterance(message)

    assert intent.domain == "water"


def test_water_character_inside_food_name_is_not_a_water_intent():
    intent = classify_agent_utterance("记录午餐吃了十个水饺")

    assert intent.domain == "diet"


@pytest.mark.parametrize(
    "message",
    (
        "记录早餐一杯水果茶",
        "记录加餐一瓶水果汁",
        "记录午餐一些水果沙拉",
        "记录早餐吃了一些水晶虾饺",
        "记录早餐吃了一些水煎包",
        "记录早餐白水煮鸡蛋和小米粥",
        "记录早餐温水煮蛋和一个包子",
    ),
)
def test_water_container_substrings_inside_fruit_foods_are_not_hydration(message):
    intent = classify_agent_utterance(message)

    assert intent.domain == "diet"


def test_analysis_using_record_as_evidence_does_not_become_a_write():
    intent = classify_agent_utterance(
        "从我的基因、生活习惯、睡眠、心率、HRV 记录出发，推断一下我胃溃疡的根因。"
    )

    assert intent.primary == "advice"
    assert intent.operation == "analyze"
    assert intent.is_write is False


def test_medication_side_effect_question_does_not_become_a_write():
    intent = classify_agent_utterance("吃了布洛芬后胃不舒服怎么办？")

    assert intent.primary == "advice"
    assert intent.is_write is False


def test_sleep_observation_without_a_request_is_not_misread_as_a_query():
    intent = classify_agent_utterance("我昨晚睡了十个小时，睡眠很好")

    assert intent.primary == "unknown"
    assert intent.operation == "none"
    assert intent.is_write is False


def test_negated_record_command_is_not_write_intent():
    intent = classify_agent_utterance("这个不用记录")

    assert intent.is_write is False
    assert intent.primary != "write"


def test_repeated_negation_uses_the_one_nearest_to_mutation():
    intent = classify_agent_utterance(
        "这是内部只读运行验证。请只回复一句简短确认，"
        "不要调用工具，也不要记录或修改任何数据。"
    )

    assert intent.primary == "chat"
    assert intent.operation == "none"
    assert intent.is_write is False


def test_shared_negation_covers_parallel_record_and_delete_actions():
    intent = classify_agent_utterance(
        "不要调用工具，也不要记录、删除或修改任何数据。"
    )

    assert intent.primary == "chat"
    assert intent.operation == "none"
    assert intent.is_write is False


def test_mutation_question_is_read_not_a_mutation_command():
    intent = classify_agent_utterance("我删除早餐了吗?")

    assert intent.primary == "read"
    assert intent.operation == "ask"
    assert intent.requires_reliable_tool_model is False


def test_destructive_command_requires_reliable_tool_model():
    intent = classify_agent_utterance("删除早餐 1")

    assert intent.primary == "mutate"
    assert intent.operation == "delete"
    assert intent.requires_reliable_tool_model is True


def test_analysis_adjustment_is_advice_not_mutation_command():
    intent = classify_agent_utterance("综合分析我最近的睡眠趋势，我该怎么调整")

    assert intent.primary == "advice"
    assert intent.operation == "analyze"
    assert intent.requires_reliable_tool_model is False


def test_destructive_command_after_analysis_preface_stays_mutation():
    intent = classify_agent_utterance("分析后帮我删除重复早餐")

    assert intent.primary == "mutate"
    assert intent.operation == "delete"
    assert intent.requires_reliable_tool_model is True


def test_plan_generation_is_a_write_intent():
    intent = classify_agent_utterance("生成本周健康计划")

    assert intent.primary == "write"
    assert intent.domain == "plan"
    assert intent.operation == "create"
    assert intent.is_write is True


def test_explicit_reminder_creation_is_not_misrouted_to_water_or_medication():
    intent = classify_agent_utterance(
        "创建一个一次性测试提醒，2099-01-01 09:00 提醒我喝水，不要现在执行"
    )

    assert intent.primary == "write"
    assert intent.domain == "reminder"
    assert intent.operation == "create"
    assert intent.is_write is True
    assert intent.requires_reliable_tool_model is True


@pytest.mark.parametrize(
    "message",
    [
        "明天早上8点提醒我喝水",
        "每天9点提醒我吃药",
    ],
)
def test_reminder_creation_outranks_embedded_health_target(message):
    intent = classify_agent_utterance(message)

    assert intent.primary == "write"
    assert intent.domain == "reminder"
    assert intent.operation == "create"
    assert intent.is_write is True


def test_plan_item_completion_is_a_mutation_intent():
    intent = classify_agent_utterance("完成今天的计划项")

    assert intent.primary == "mutate"
    assert intent.domain == "plan"
    assert intent.operation == "update"
    assert intent.is_write is True


def test_intervention_status_question_is_read_intent():
    intent = classify_agent_utterance("帮我看看干预周期")

    assert intent.primary == "read"
    assert intent.domain == "plan"
    assert intent.operation == "list"
    assert intent.is_write is False


@pytest.mark.parametrize(
    "message",
    [
        "今天我没吃那么多，晚餐的两千大卡只有吃了四分之一",
        "晚饭实际只吃了一半，帮我按实际摄入修正",
        "午餐没有全吃完，只吃了三分之一",
    ],
)
def test_partial_meal_statement_is_an_existing_diet_correction(message):
    intent = classify_agent_utterance(message)

    assert intent.primary == "mutate"
    assert intent.domain == "diet"
    assert intent.operation == "update"
    assert intent.scope["meal_type"] in {"lunch", "dinner"}
    assert intent.is_write is True
    assert intent.requires_reliable_tool_model is True


def test_partial_meal_advice_question_does_not_mutate_a_record():
    intent = classify_agent_utterance("晚餐只吃四分之一会不会饿？")

    assert intent.primary in {"read", "advice"}
    assert intent.domain == "diet"
    assert intent.is_write is False


def test_classifier_surface_does_not_use_regex():
    source = getsource(utterance_intent_classifier)

    assert "import re" not in source
    assert "re." not in source
    assert "re.compile" not in source
