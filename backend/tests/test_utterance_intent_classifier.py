from datetime import datetime, timedelta, timezone
from inspect import getsource

import pytest

import app.services.utterance_intent_classifier as utterance_intent_classifier
from app.services.utterance_intent_classifier import classify_agent_utterance
from app.services import utterance_intent_lexicon as lexicon

BJ = timezone(timedelta(hours=8))


@pytest.mark.parametrize(
    ("text", "expected"),
    (
        (
            "删除用药记录么",
            ("mutate", "medication", "delete", "mutation_command", True, True),
        ),
        (
            "勿删除用药记录",
            ("mutate", "medication", "delete", "mutation_command", True, True),
        ),
        (
            "不再删除用药记录",
            ("mutate", "medication", "delete", "mutation_command", True, True),
        ),
        (
            "该不该记录今天腰痛6分",
            ("advice", "symptom", "analyze", "advice_frame", False, False),
        ),
        (
            "今天我没吃那么多，晚餐的两千大卡只有吃了四分之一",
            (
                "mutate",
                "diet",
                "update",
                "diet_quantity_correction",
                True,
                True,
            ),
        ),
    ),
)
def test_task_1b_keeps_legacy_classifier_contract(text, expected):
    intent = classify_agent_utterance(text)

    assert (
        intent.primary,
        intent.domain,
        intent.operation,
        intent.reason,
        intent.is_write,
        intent.requires_reliable_tool_model,
    ) == expected


def test_classifier_uses_exact_legacy_question_and_mutation_negation_views():
    assert lexicon.QUESTION_SIGNALS == (
        "?",
        "？",
        "多少",
        "什么",
        "啥",
        "哪些",
        "几",
        "有没有",
        "是不是",
        "是否",
        "吗",
        "呢",
        "如何",
        "怎么",
        "为什么",
        "多高",
        "多重",
        "多久",
        "高不高",
        "正常吗",
        "有问题吗",
        "能否",
        "可否",
        "可不可以",
        "怎么样",
    )
    assert lexicon.MUTATION_NEGATIONS == (
        "不要",
        "别",
        "不用",
        "无需",
        "不需要",
        "不想",
        "先别",
        "暂不",
        "不能",
        "不可",
        "禁止",
        "避免",
    )


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


SCREENSHOT_CLINICIAN_TEXT = (
    "医生诊断是大腿和臀部肌肉无力导致腰肌代偿进而导致腰肌痛"
)

CLINICIAN_INSTRUCTION_MESSAGES = (
    "医生让我记录每天腰痛情况",
    "医生叫我记录每天腰痛情况",
    "大夫交代我记录每天腰痛情况",
)

CLINICIAN_ROLE_REVERSAL_MESSAGES = (
    "我让医生记录每天腰痛情况",
    "家属叫医生记录每天腰痛情况",
)

CLINICIAN_POST_REPORT_INSTRUCTION_MESSAGES = (
    "医生说让我记录每天腰痛情况。请记录医生诊断：臀肌无力",
    "医生告诉我记录每天腰痛情况。请记录医生诊断：臀肌无力",
    "医生嘱咐你记录每天腰痛情况。请记录医生诊断：臀肌无力",
    "医生告诉我让我记录每天腰痛情况。请记录医生诊断：臀肌无力",
    "医生要求记录每天腰痛情况。请记录医生诊断：臀肌无力",
    "医生说请记录每天腰痛情况。请记录医生诊断：臀肌无力",
)

CLINICIAN_NEGATED_WRITE_CASES = (
    ("不要保存医生诊断", "negated_clinician_action"),
    ("不要写入医生反馈", "negated_clinician_action"),
    ("不需要保存医生诊断", "negated_clinician_action"),
    ("请先不要保存医生诊断", "negated_clinician_action"),
    ("请不要再保存医生诊断", "negated_clinician_action"),
    ("请不要帮我保存医生诊断", "negated_clinician_action"),
    ("不要写入医生体重", "unresolved_clinician_action"),
    ("不要不保存医生诊断", "unresolved_clinician_action"),
)

CLINICIAN_BASIS_NONWRITE_MESSAGES = (
    "根据医生诊断删除昨天用药记录",
    "依据医生意见调整用药剂量",
    "按照医生建议同步健康数据",
    "遵医嘱删除这条用药记录",
    "按医嘱停药并删除记录",
    "按照医嘱同步健康数据",
    "根据 医生 诊断 删除昨天用药记录",
    "根据医生诊断不要删除昨天用药记录",
    "根据医生诊断删除昨天用药记录并停药",
    "根据医 生诊断删除昨天用药记录",
    "按照医生建议同 步健康数据",
)

CLINICIAN_BASIS_OBFUSCATED_NONWRITE_MESSAGES = (
    "根据医，生诊断删除昨天用药记录",
    "根据医：生诊断调整体重",
    "依据医、师意见同步健康数据",
    "按照物理治，疗师建议删除记录",
    "根据医,生诊断删除昨天用药记录",
    "依据医/师意见同步健康数据",
    "按照物理治.疗师建议删除记录",
)

CLINICIAN_FALLBACK_NONWRITE_MESSAGES = (
    *CLINICIAN_INSTRUCTION_MESSAGES,
    *CLINICIAN_ROLE_REVERSAL_MESSAGES,
    *CLINICIAN_POST_REPORT_INSTRUCTION_MESSAGES,
    *(message for message, _reason in CLINICIAN_NEGATED_WRITE_CASES),
    *CLINICIAN_BASIS_NONWRITE_MESSAGES,
    *CLINICIAN_BASIS_OBFUSCATED_NONWRITE_MESSAGES,
)


@pytest.mark.parametrize(
    ("message", "expected"),
    (
        (
            SCREENSHOT_CLINICIAN_TEXT,
            (
                "chat",
                "clinical_context",
                "acknowledge",
                "clinician_report",
                False,
                True,
            ),
        ),
        (
            "大夫告知是臀肌无力导致腰痛",
            (
                "chat",
                "clinical_context",
                "acknowledge",
                "clinician_report",
                False,
                True,
            ),
        ),
        (
            "医生认为是臀肌无力导致腰痛，我该怎么处理？",
            (
                "advice",
                "clinical_context",
                "analyze",
                "clinician_question",
                False,
                True,
            ),
        ),
        (
            "请记录医生诊断：臀肌无力导致腰肌代偿",
            (
                "write",
                "clinical_context",
                "create",
                "explicit_feedback_write",
                True,
                True,
            ),
        ),
        (
            "请记录医生诊断：臀肌无力并删除旧记录",
            (
                "chat",
                "clinical_context",
                "acknowledge",
                "coordinated_clinician_action",
                False,
                True,
            ),
        ),
    ),
)
def test_clinician_guard_maps_to_public_intent_before_legacy_classifier(
    message,
    expected,
):
    intent = classify_agent_utterance(message)

    assert (
        intent.primary,
        intent.domain,
        intent.operation,
        intent.reason,
        intent.is_write,
        intent.requires_reliable_tool_model,
    ) == expected


@pytest.mark.parametrize("message", CLINICIAN_INSTRUCTION_MESSAGES)
def test_clinician_instructions_are_reliable_nonwrite_advice(message):
    intent = classify_agent_utterance(message)

    assert (
        intent.primary,
        intent.domain,
        intent.operation,
        intent.reason,
        intent.is_write,
        intent.requires_reliable_tool_model,
    ) == (
        "advice",
        "clinical_context",
        "analyze",
        "clinician_instruction",
        False,
        True,
    )


@pytest.mark.parametrize("message", CLINICIAN_ROLE_REVERSAL_MESSAGES)
def test_clinician_role_reversals_fail_closed_as_reliable_chat(message):
    intent = classify_agent_utterance(message)

    assert (
        intent.primary,
        intent.domain,
        intent.operation,
        intent.reason,
        intent.is_write,
        intent.requires_reliable_tool_model,
    ) == (
        "chat",
        "clinical_context",
        "acknowledge",
        "unresolved_clinician_action",
        False,
        True,
    )


@pytest.mark.parametrize("message", CLINICIAN_POST_REPORT_INSTRUCTION_MESSAGES)
def test_clinician_instruction_then_explicit_write_fails_closed(message):
    intent = classify_agent_utterance(message)

    assert (
        intent.primary,
        intent.domain,
        intent.operation,
        intent.reason,
        intent.is_write,
        intent.requires_reliable_tool_model,
    ) == (
        "chat",
        "clinical_context",
        "acknowledge",
        "coordinated_clinician_action",
        False,
        True,
    )


@pytest.mark.parametrize(("message", "expected_reason"), CLINICIAN_NEGATED_WRITE_CASES)
def test_negated_clinician_writes_fail_closed_without_record_recovery(
    message,
    expected_reason,
):
    intent = classify_agent_utterance(message)

    assert (
        intent.primary,
        intent.domain,
        intent.operation,
        intent.reason,
        intent.is_write,
        intent.requires_reliable_tool_model,
    ) == (
        "chat",
        "clinical_context",
        "acknowledge",
        expected_reason,
        False,
        True,
    )


@pytest.mark.parametrize("message", CLINICIAN_BASIS_NONWRITE_MESSAGES)
def test_clinician_basis_mutations_require_a_separate_command(message):
    intent = classify_agent_utterance(message)

    assert (
        intent.primary,
        intent.domain,
        intent.operation,
        intent.reason,
        intent.is_write,
        intent.requires_reliable_tool_model,
    ) == (
        "chat",
        "clinical_context",
        "acknowledge",
        "clinician_basis_action_requires_separate_command",
        False,
        True,
    )


@pytest.mark.parametrize(
    "message",
    CLINICIAN_BASIS_OBFUSCATED_NONWRITE_MESSAGES,
)
def test_punctuated_clinician_basis_mutations_fail_closed(message):
    intent = classify_agent_utterance(message)

    assert (
        intent.primary,
        intent.domain,
        intent.operation,
        intent.reason,
        intent.is_write,
        intent.requires_reliable_tool_model,
    ) == (
        "chat",
        "clinical_context",
        "acknowledge",
        "obfuscated_clinician_action",
        False,
        True,
    )


@pytest.mark.parametrize(
    ("message", "expected"),
    (
        ("记录午餐吃了牛肉面", ("write", "diet", "create", True, False)),
        ("今天腰痛6分", ("write", "symptom", "create", True, False)),
        (
            "记录服药二甲双胍一片",
            ("write", "medication", "create", True, False),
        ),
        (
            "生成一张运动图片",
            ("write", "aigc_media", "create", True, True),
        ),
        ("制定康复计划", ("write", "plan", "create", True, True)),
        ("提醒我明天复查", ("write", "reminder", "create", True, True)),
        (
            "查看医生诊断记录",
            ("read", "clinical_context", "list", False, True),
        ),
        (
            "删除医生诊断记录",
            ("mutate", "clinical_context", "delete", True, True),
        ),
        (
            "删除昨天用药记录",
            ("mutate", "medication", "delete", True, True),
        ),
        ("调整体重", ("mutate", "metric", "update", True, True)),
        ("同步健康数据", ("mutate", "unknown", "sync", True, True)),
    ),
)
def test_guard_none_conserves_legacy_public_intents(message, expected):
    intent = classify_agent_utterance(message)

    assert (
        intent.primary,
        intent.domain,
        intent.operation,
        intent.is_write,
        intent.requires_reliable_tool_model,
    ) == expected


def test_every_clinician_guard_decision_bypasses_legacy_authorizers(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("legacy whole-text authorizer was entered")

    for helper in (
        "_has_explicit_write_command",
        "_mutation_operation",
        "_plan_operation",
        "_reminder_operation",
        "_is_media_generation_request",
        "_has_explicit_observation_write",
        "_has_explicit_symptom_observation",
        "_has_explicit_event_write",
    ):
        monkeypatch.setattr(
            utterance_intent_classifier,
            helper,
            fail_if_called,
        )

    for message in (
        SCREENSHOT_CLINICIAN_TEXT,
        "医生认为是臀肌无力导致腰痛，我该怎么处理？",
        "请记录医生诊断：臀肌无力导致腰肌代偿",
        "请记录医生诊断：臀肌无力并删除旧记录",
        *CLINICIAN_FALLBACK_NONWRITE_MESSAGES,
    ):
        intent = classify_agent_utterance(message)
        assert intent.domain == "clinical_context", message


@pytest.mark.parametrize(
    ("helper_name", "message", "expected"),
    (
        (
            "_has_explicit_write_command",
            "记录午餐吃了牛肉面",
            ("write", "diet"),
        ),
        ("_mutation_operation", "删除午餐记录", ("mutate", "diet")),
        ("_plan_operation", "制定康复计划", ("write", "plan")),
        ("_reminder_operation", "提醒我明天复查", ("write", "reminder")),
        (
            "_is_media_generation_request",
            "生成一张运动图片",
            ("write", "aigc_media"),
        ),
    ),
)
def test_guard_none_still_reaches_legacy_authorizers(
    monkeypatch,
    helper_name,
    message,
    expected,
):
    called = False
    original = getattr(utterance_intent_classifier, helper_name)

    def observe_authorizer(*args, **kwargs):
        nonlocal called
        called = True
        return original(*args, **kwargs)

    monkeypatch.setattr(
        utterance_intent_classifier,
        helper_name,
        observe_authorizer,
    )

    intent = classify_agent_utterance(message)

    assert called is True
    assert (intent.primary, intent.domain) == expected


def test_direct_user_medication_mutation_remains_authorized():
    intent = classify_agent_utterance("把用药剂量调整为每天两次")

    assert intent.primary == "mutate"
    assert intent.domain == "medication"
    assert intent.operation == "update"
    assert intent.is_write is True
    assert intent.requires_reliable_tool_model is True


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
