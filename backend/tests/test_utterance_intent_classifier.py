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


def test_clinician_attributed_assessment_is_context_not_symptom_write():
    intent = classify_agent_utterance(
        "医生诊断是大腿和臀部肌肉无力导致腰肌代偿进而导致腰肌痛"
    )

    assert intent.primary == "chat"
    assert intent.domain == "clinical_context"
    assert intent.operation == "acknowledge"
    assert intent.is_write is False
    assert intent.requires_reliable_tool_model is True


@pytest.mark.parametrize(
    "message",
    (
        "医生诊断：臀肌无力导致腰肌代偿",
        "主治医生诊断:臀肌无力导致腰痛",
        "大夫诊断：臀肌无力",
        "康复师诊断:臀肌无力",
    ),
)
def test_colon_diagnosis_introducer_is_clinician_context(message):
    intent = classify_agent_utterance(message)

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
        "医生说：臀肌无力。请记录一下",
        "医生告诉我：臀肌无力。帮我记录一下",
    ),
)
def test_colon_introduced_clinician_content_can_be_saved_by_adjacent_user_action(
    message,
):
    intent = classify_agent_utterance(message)

    assert intent.primary == "write"
    assert intent.domain == "clinical_context"
    assert intent.operation == "create"
    assert intent.is_write is True
    assert intent.requires_reliable_tool_model is True


@pytest.mark.parametrize(
    "message",
    (
        "医生说：臀肌无力",
        "医生告诉我：臀肌无力",
    ),
)
def test_colon_introduced_clinician_content_without_user_save_is_read_only(
    message,
):
    intent = classify_agent_utterance(message)

    assert intent.primary == "chat"
    assert intent.domain == "clinical_context"
    assert intent.operation == "acknowledge"
    assert intent.is_write is False
    assert intent.requires_reliable_tool_model is True


@pytest.mark.parametrize(
    "message",
    (
        "医生说：请记录每天疼痛情况",
        "医生说：臀肌无力。天气不错。请记录一下",
    ),
)
def test_colon_provenance_does_not_authorize_quoted_or_distant_save(message):
    intent = classify_agent_utterance(message)

    assert intent.primary == "chat"
    assert intent.domain == "clinical_context"
    assert intent.operation == "acknowledge"
    assert intent.is_write is False
    assert intent.requires_reliable_tool_model is True


@pytest.mark.parametrize(
    "message",
    (
        "医生说：康复师认为：删除医生诊断记录",
        "医生说：大夫建议：同步健康数据",
        "医生告诉我：康复师要求我：删除昨天用药记录",
    ),
)
def test_nested_clinician_introducers_keep_actions_clinician_owned(message):
    intent = classify_agent_utterance(message)

    assert intent.primary == "chat"
    assert intent.domain == "clinical_context"
    assert intent.operation == "acknowledge"
    assert intent.is_write is False
    assert intent.requires_reliable_tool_model is True


@pytest.mark.parametrize(
    "message",
    (
        "医生说，：删除医生诊断记录",
        "医生说！：删除医生诊断记录",
    ),
)
def test_delimiter_run_keeps_colon_provenance_fail_closed(message):
    intent = classify_agent_utterance(message)

    assert intent.primary == "chat"
    assert intent.domain == "clinical_context"
    assert intent.operation == "acknowledge"
    assert intent.is_write is False
    assert intent.requires_reliable_tool_model is True


@pytest.mark.parametrize(
    ("raw", "expected_separator", "has_colon", "has_question"),
    (
        ("医生说，：删除医生诊断记录", "，：", True, False),
        ("医生说！：删除医生诊断记录", "！：", True, False),
        ("医生说！？", "！？", False, True),
    ),
)
def test_clause_scanner_preserves_delimiter_run_metadata(
    raw,
    expected_separator,
    has_colon,
    has_question,
):
    first = utterance_intent_classifier._scan_clause_segments(raw)[0]

    assert first.separator_after == expected_separator
    assert first.has_colon is has_colon
    assert first.has_question is has_question


@pytest.mark.parametrize(
    ("message", "expected_primary", "expected_operation"),
    (
        ("不要保存医生诊断", "chat", "acknowledge"),
        ("不要写入医生反馈", "chat", "acknowledge"),
        ("先别把医生说的内容存下来", "chat", "acknowledge"),
        ("是否需要保存医生诊断？", "advice", "analyze"),
        ("需要记录医生诊断吗？", "advice", "analyze"),
        ("不用记录医生诊断", "chat", "acknowledge"),
        ("不需要保存医生诊断", "chat", "acknowledge"),
    ),
)
def test_clinician_save_requires_affirmative_non_question_clause(
    message,
    expected_primary,
    expected_operation,
):
    intent = classify_agent_utterance(message)

    assert intent.primary == expected_primary
    assert intent.domain == "clinical_context"
    assert intent.operation == expected_operation
    assert intent.is_write is False
    assert intent.requires_reliable_tool_model is True


@pytest.mark.parametrize(
    ("message", "expected_primary", "expected_operation"),
    (
        ("医生诊断记录？", "read", "ask"),
        ("医生说是腰肌劳损？", "advice", "analyze"),
        ("医生说得对吗？", "advice", "analyze"),
        ("医生诊断是什么？", "advice", "analyze"),
    ),
)
def test_terminal_question_is_owned_by_user_speech_act(
    message,
    expected_primary,
    expected_operation,
):
    intent = classify_agent_utterance(message)

    assert intent.primary == expected_primary
    assert intent.operation == expected_operation
    assert intent.is_write is False
    if "医生诊断记录" not in message:
        assert intent.domain == "clinical_context"
        assert intent.requires_reliable_tool_model is True


def test_negated_unrelated_clause_does_not_poison_adjacent_clinician_save():
    intent = classify_agent_utterance(
        "别记录今天的饮食。医生说是臀肌无力，帮我记录一下"
    )

    assert intent.primary == "write"
    assert intent.domain == "clinical_context"
    assert intent.operation == "create"
    assert intent.is_write is True
    assert intent.requires_reliable_tool_model is True


@pytest.mark.parametrize(
    "message",
    (
        "医生让我记录每天腰痛情况",
        "医生要求我删除昨天用药记录",
        "医生嘱咐我同步健康数据",
        "大夫交代我调整用药",
    ),
)
def test_provider_before_action_without_user_command_proof_fails_closed(message):
    intent = classify_agent_utterance(message)

    assert intent.primary == "chat"
    assert intent.domain == "clinical_context"
    assert intent.operation == "acknowledge"
    assert intent.is_write is False
    assert intent.requires_reliable_tool_model is True


@pytest.mark.parametrize(
    ("message", "expected_domain", "expected_operation"),
    (
        ("根据医生诊断删除昨天用药记录", "medication", "delete"),
        ("依据医生意见调整用药剂量", "medication", "update"),
        ("删除根据医生诊断生成的用药记录", "medication", "delete"),
        ("调整医生诊断中提到的用药剂量", "medication", "update"),
    ),
)
def test_clinician_basis_does_not_override_action_target(
    message,
    expected_domain,
    expected_operation,
):
    intent = classify_agent_utterance(message)

    assert intent.primary == "mutate"
    assert intent.domain == expected_domain
    assert intent.operation == expected_operation
    assert intent.is_write is True
    assert intent.requires_reliable_tool_model is True


@pytest.mark.parametrize(
    "message",
    (
        "记录根据医生诊断出现的今天腰痛6分",
        "根据医生诊断记录今天腰痛6分",
    ),
)
def test_clinician_basis_does_not_override_health_save_target(message):
    frame = utterance_intent_classifier._classify_clause(message)
    intent = classify_agent_utterance(message)

    assert frame.target_kind == "health_record"
    assert intent.primary == "write"
    assert intent.domain == "symptom"
    assert intent.operation == "create"
    assert intent.is_write is True


@pytest.mark.parametrize(
    "message",
    (
        "医生诊断记录意味着什么？",
        "分析医生诊断记录的风险",
    ),
)
def test_unowned_clinician_record_analysis_falls_back_to_general_advice(message):
    intent = classify_agent_utterance(message)

    assert intent.primary == "advice"
    assert intent.domain == "clinical_context"
    assert intent.operation == "analyze"
    assert intent.is_write is False
    assert intent.requires_reliable_tool_model is True


def test_clinician_record_media_generation_preserves_general_media_contract():
    intent = classify_agent_utterance("生成医生诊断记录的图片")

    assert intent.primary == "write"
    assert intent.domain == "aigc_media"
    assert intent.operation == "create"
    assert intent.is_write is True
    assert intent.requires_reliable_tool_model is True


def test_explicit_symptom_save_after_clinician_context_keeps_symptom_write():
    intent = classify_agent_utterance(
        "医生说是臀肌无力。记录今天腰痛6分"
    )

    assert intent.primary == "write"
    assert intent.domain == "symptom"
    assert intent.operation == "create"
    assert intent.is_write is True


def test_clinician_basis_does_not_override_explicit_symptom_save_target():
    intent = classify_agent_utterance(
        "根据医生诊断记录今天腰痛6分"
    )

    assert intent.primary == "write"
    assert intent.domain == "symptom"
    assert intent.operation == "create"
    assert intent.is_write is True


@pytest.mark.parametrize(
    "message",
    (
        "医生说要删除昨天用药记录。记录今天腰痛6分",
        "医生说要同步健康数据。记录今天腰痛6分",
        "医生要求我调整用药。记录今天腰痛6分",
    ),
)
def test_clinician_clause_never_authorizes_whole_text_fallback(message):
    intent = classify_agent_utterance(message)

    assert intent.primary == "write"
    assert intent.domain == "symptom"
    assert intent.operation == "create"
    assert intent.is_write is True


def test_clinician_bearing_turn_never_enters_whole_text_authorizers(
    monkeypatch,
):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("whole-text authorizer was entered")

    monkeypatch.setattr(
        utterance_intent_classifier,
        "_mutation_operation",
        fail_if_called,
    )
    monkeypatch.setattr(
        utterance_intent_classifier,
        "_plan_operation",
        fail_if_called,
    )
    monkeypatch.setattr(
        utterance_intent_classifier,
        "_reminder_operation",
        fail_if_called,
    )

    intent = classify_agent_utterance(
        "医生说要删除昨天用药记录。记录今天腰痛6分"
    )

    assert intent.primary == "write"
    assert intent.domain == "symptom"
    assert intent.operation == "create"


@pytest.mark.parametrize(
    "message",
    (
        "医生对我说要删除昨天用药记录",
        "医生跟我说要同步健康数据",
        "医生叫我记录每天腰痛情况",
        "医生指示我删除昨天用药记录",
        "医生的建议是删除昨天记录",
        "物理治疗师要求我记录每天疼痛",
    ),
)
def test_provider_before_action_without_user_proof_is_ambiguous(message):
    frame = utterance_intent_classifier._classify_clause(message)
    intent = classify_agent_utterance(message)

    assert frame.actor == "ambiguous"
    assert intent.primary == "chat"
    assert intent.domain == "clinical_context"
    assert intent.operation == "acknowledge"
    assert intent.is_write is False
    assert intent.requires_reliable_tool_model is True


@pytest.mark.parametrize(
    ("message", "expected_actor"),
    (
        ("根据医生诊断删除昨天用药记录", "user"),
        ("依据医生意见调整用药剂量", "user"),
        ("按照医生诊断删除昨天用药记录", "user"),
        ("医生诊断请帮我删除昨天用药记录", "user"),
        ("把医生诊断记录删除", "user"),
        ("医生对我说要删除昨天用药记录", "ambiguous"),
        ("医生叫我记录每天腰痛情况", "ambiguous"),
    ),
)
def test_provider_before_action_actor_is_structural(
    message,
    expected_actor,
):
    frame = utterance_intent_classifier._classify_clause(message)

    assert frame.actor == expected_actor


@pytest.mark.parametrize(
    "save_action",
    (
        "记录",
        "记一下",
        "记下",
        "录入",
        "保存",
        "写入",
        "存下来",
    ),
)
def test_clinician_save_question_stance_never_authorizes(save_action):
    intent = classify_agent_utterance(
        f"要不要{save_action}医生诊断？"
    )

    assert intent.primary == "advice"
    assert intent.domain == "clinical_context"
    assert intent.operation == "analyze"
    assert intent.is_write is False
    assert intent.requires_reliable_tool_model is True


@pytest.mark.parametrize(
    "message",
    (
        "不想保存医生诊断",
        "没有必要写入医生诊断",
        "不用记录医生诊断",
        "无需保存医生诊断",
        "不要记录医生诊断",
        "先别记录医生诊断",
    ),
)
def test_clinician_save_negative_stance_never_authorizes(message):
    intent = classify_agent_utterance(message)

    assert intent.primary == "chat"
    assert intent.domain == "clinical_context"
    assert intent.operation == "acknowledge"
    assert intent.is_write is False
    assert intent.requires_reliable_tool_model is True


@pytest.mark.parametrize(
    "message",
    (
        "请记录医生诊断。算了，不要保存",
        "请记录医生诊断。等等，不要记录",
        "请记录医生诊断。不过，不要记录",
        "别忘了记录饮食但不要保存医生诊断",
    ),
)
def test_later_negative_save_stance_cancels_earlier_positive(message):
    intent = classify_agent_utterance(message)

    assert intent.primary not in {"write", "mutate"}
    assert intent.domain == "clinical_context"
    assert intent.is_write is False
    assert intent.requires_reliable_tool_model is True


@pytest.mark.parametrize(
    ("message", "expected_domain"),
    (
        (
            "记录今天腰痛6分并分析医生诊断记录的风险",
            "symptom",
        ),
        (
            "请记录饮食然后分析医生诊断记录的风险",
            "diet",
        ),
        (
            "把今天腰痛记录下来并分析医生诊断记录的风险",
            "symptom",
        ),
        (
            "需要记录饮食然后分析医生诊断记录的风险",
            "diet",
        ),
        (
            "别忘了记录饮食然后分析医生诊断记录的风险",
            "diet",
        ),
    ),
)
def test_later_record_noun_is_not_a_second_save_stance(
    message,
    expected_domain,
):
    frame = utterance_intent_classifier._classify_clause(message)
    stances = utterance_intent_classifier._collect_save_stances((frame,))
    intent = classify_agent_utterance(message)

    assert len(stances) == 1
    assert intent.primary == "write"
    assert intent.domain == expected_domain
    assert intent.operation == "create"


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
