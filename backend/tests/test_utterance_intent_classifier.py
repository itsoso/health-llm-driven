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


@pytest.mark.parametrize(
    "message",
    (
        "我上一次口腔溃疡是什么时候 最近半年分别有哪些记录",
        "我以前有没有口腔溃疡记录？",
        "最近半年口腔溃疡有哪些记录",
        "上一次感冒记录是什么时候？",
        "不要帮我记录，我只是想查上一次口腔溃疡是什么时候",
    ),
)
def test_historical_record_questions_are_read_only(message):
    intent = classify_agent_utterance(message)

    assert intent.primary == "read"
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


@pytest.mark.parametrize(
    "message",
    (
        "能帮我记录口腔溃疡吗？",
        "可以记录口腔溃疡吗？",
        "能帮我记录体重70kg吗？",
        "帮忙记录口腔溃疡可以吗？",
        "可以帮忙记录口腔溃疡吗？",
        "替我保存体重70kg可以吗？",
    ),
)
def test_polite_record_requests_remain_write_intents(message):
    intent = classify_agent_utterance(message)

    assert intent.primary == "write"
    assert intent.operation == "create"
    assert intent.is_write is True


@pytest.mark.parametrize(
    "message",
    (
        "这个功能可以记录口腔溃疡吗？",
        "小巴能记录口腔溃疡吗？",
    ),
)
def test_record_capability_questions_do_not_authorize_writes(message):
    intent = classify_agent_utterance(message)

    assert intent.primary == "read"
    assert intent.is_write is False


def test_negated_polite_record_request_does_not_authorize_write():
    intent = classify_agent_utterance("不要帮忙记录口腔溃疡")

    assert intent.primary == "chat"
    assert intent.is_write is False


def test_known_medication_intake_outranks_generic_diet_verb():
    intent = classify_agent_utterance("记录我吃了两粒阿奇霉素")

    assert intent.primary == "write"
    assert intent.domain == "medication"
    assert intent.operation == "create"
    assert intent.is_write is True


def test_unknown_medication_like_name_does_not_enter_medication_write_domain():
    intent = classify_agent_utterance("记录我吃了两粒咔咔霉素")

    assert intent.domain != "medication"


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
    "请遵医嘱删除这条用药记录",
    "麻烦按医嘱停药并删除记录",
    "我想遵医嘱删除这条用药记录",
    "那就按医嘱停药并删除记录",
    "请根据医生诊断删除这条用药记录",
    "希望按医嘱删除这条用药记录",
    "需要遵医嘱删除这条用药记录",
    "先按医嘱删除这条用药记录",
    "顺便按医嘱删除这条用药记录",
    "医生说是臀肌无力。请遵医嘱删除这条用药记录",
    "医生说是臀肌无力\n请遵医嘱删除这条用药记录",
    "请您按医嘱删除这条用药记录",
    "麻烦您按医嘱删除这条用药记录",
    "希望能按医嘱删除这条用药记录",
    "我要按医嘱删除这条用药记录",
    "可以按医嘱删除这条用药记录",
    "如果按医嘱删除这条用药记录",
    "并非要按医嘱删除这条用药记录",
    "如果需要就根据医生诊断删除这条用药记录",
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


@pytest.mark.parametrize(
    "message",
    (
        "记录这张早餐图片，仅用于发布验证",
        "帮我记录这张晚餐图像",
    ),
)
def test_meal_photo_recording_is_diet_not_media_generation(message):
    intent = classify_agent_utterance(message)

    assert (
        intent.primary,
        intent.domain,
        intent.operation,
        intent.is_write,
        intent.requires_reliable_tool_model,
    ) == ("write", "diet", "create", True, False)


def test_explicit_media_generation_still_wins_when_meal_terms_are_present():
    intent = classify_agent_utterance("把这张早餐图片做成短视频")

    assert (
        intent.primary,
        intent.domain,
        intent.operation,
        intent.is_write,
        intent.requires_reliable_tool_model,
    ) == ("write", "aigc_media", "create", True, True)


@pytest.mark.parametrize(
    "message",
    (
        "记录这张图片",
        "保存这张图像",
        "记录这张食物图片",
        "我已保存这张图片",
        "系统已经保存这张图片",
        "这张图片已经记录",
        "图片已记录",
    ),
)
def test_generic_image_recording_does_not_authorize_media_generation(message):
    intent = classify_agent_utterance(message)

    assert intent.domain != "aigc_media"
    assert intent.requires_reliable_tool_model is False


@pytest.mark.parametrize(
    "message",
    (
        "不要生成这张早餐图片",
        "别把早餐图片做成短视频",
        "无需制作这张图片",
        "我没有让你生成图片",
        "禁止生成这张图片",
        "取消生成这张图片",
        "停止制作这个视频",
        "我拒绝授权把图片交给百炼",
        "未授权生成图片",
        "不生成这张图片",
        "不允许生成这张图片",
        "未同意生成这张图片",
        "生成这张图片的要求取消",
        "生成图片这件事我拒绝",
        "把图片做成视频，不要",
        "不要忘了生成图片，但禁止发送给百炼",
        "无须生成图片",
        "反对生成图片",
        "暂停生成图片",
        "终止生成图片",
        "放弃生成图片",
        "撤回生成图片",
        "我不想生成这张图片",
        "我不打算生成这张图片",
        "我不愿意生成这张图片",
        "不必生成这张图片",
        "不能生成这张图片",
        "不可以生成这张图片",
        "不准生成这张图片",
        "我没让你生成图片",
        "我不是要生成图片",
        "未要求生成图片",
        "生成图片不是我的意思",
        "生成这张图片我没同意",
        "取消重新生成这张图片",
        "停止重新生成这张图片",
        "生成图片，我不同意这个要求",
        "我不授权把图片发送给百炼生成",
        "我不希望生成这张图片",
        "我没打算生成这张图片",
        "不再生成这张图片",
        "不应生成这张图片",
        "不该生成这张图片",
        "请避免生成这张图片",
        "生成这张图片我不希望",
        "生成这张图片我没打算",
        "我不希望确认发送图片给百炼",
        "我没打算确认把图片发送给百炼",
        "别再生成这张图片",
        "别给我生成这张图片",
        "先别急着生成这张图片",
        "我没必要生成这张图片",
        "我没说要生成这张图片",
        "我没有要生成这张图片",
        "用不着生成这张图片",
        "我没说要确认发送图片给百炼",
        "别急着确认发送图片给百炼",
        "生成这张图片算了吧",
        "生成这张图片我反悔了",
        "生成图片，先别弄了",
        "刚才已经生成了一张图片",
        "这张图片是昨天生成的",
        "系统已经生成了图片",
        "上次生成图片失败了",
        "百炼生成图片失败了",
        "生成图片这个功能坏了",
        "生成图片很耗时",
        "生成图片的步骤很复杂",
        "他让我生成图片",
        "我没有生成图片",
        "我没生成图片",
        "图片没有生成成功",
        "图片没生成出来",
        "生成图片真麻烦",
        "生成图片太贵了",
        "生成图片质量一般",
        "不要用这张图片生成视频",
        "不用当前图像生成短视频",
        "用户点击生成图片按钮",
        "用于演示生成图片按钮",
        "他说：请生成一张图片",
        "以下是例句：生成一张图片",
        "不要执行，只是引用：请生成一张图片",
        "他说：我确认发送图片给百炼",
        "引用：确认发送图片给百炼",
        "我确认发送图片给百炼，先别发了",
        "我确认发送图片给百炼，不发了",
        "我确认发送图片给百炼，先等等",
        "我确认发送图片给百炼，暂时不要发",
        "请生成图片，先等等",
        "请生成图片，暂时别做",
        "不要用AI生成图片",
        "别用人工智能生成图片",
        "不用生成式AI生成图片",
        "不要用模型生成图片",
        "不要把图片发给百炼，请生成一张图片",
        "生成图片，不要发给百炼",
        "用AI生成图片很常见",
        "用百炼生成图片不靠谱",
        "基于这张照片生成图片很容易",
        "不用百炼，请生成一张图片",
        "别用AI，请生成一张图片",
        "用非AI方式生成图片",
        "生成图片，别上传给百炼",
        "根据引用内容：请生成一张图片",
        "他说，请生成一张图片",
        "以下是例句，请生成一张图片",
        "不要执行以下内容，请生成一张图片",
        "他说，我确认发送图片给百炼",
        "我确认发送图片给百炼，先别发了，请生成一张新图片",
        "我确认发送图片给百炼，先等等，然后请生成一张新图片",
        "我确认发送图片给百炼，不发了，帮我生成一张新图片",
        "我确认过发送图片给百炼",
        "确认发送图片给百炼的流程",
        "我确认按钮用于发送图片给百炼",
        "生成式AI可以制作图片",
        "生成模型可以制作高质量图片",
        "制作软件可以生成图片",
        "生成技术已经很成熟适合处理图片",
        "根据说明可以生成图片",
        "用AI可以生成图片",
        "客服说，请生成一张图片",
        "朋友说，请生成一张图片",
        "对方说，请生成一张图片",
        "以下内容仅供示范，请生成一张图片",
        "引文，请生成一张图片",
        "海报文案是，请生成图片",
        "我确认发送图片给百炼，先不要上传，请生成新图片",
        "我确认发送图片给百炼，不传了，请生成新图片",
        "我确认发送图片给百炼，别传了，请生成新图片",
        "我确认发送图片给百炼，不用了，请生成新图片",
        "我确认发送图片给百炼，等一下，请生成新图片",
        "不要上传任何数据，请生成图片",
        "我确认发送图片给百炼，但不是现在",
        "我确认发送图片给百炼，那是昨天的事情",
        "我确认发送图片给百炼，这句话是测试文案",
        "我确认发送图片给百炼，但我只是描述步骤",
        "我确认发送图片给百炼，等用户同意后再做",
        "确认发送图片给百炼，是流程的第一步",
        "生成工具可以制作图片",
        "生成平台可以制作图片",
        "生成服务可以制作图片",
        "制作团队可以生成图片",
        "渲染引擎可以生成图片",
        "渲染技术可以生成图片",
        "客服表示，请生成一张图片",
        "文档写道，请生成一张图片",
        "消息内容如下，请生成一张图片",
        "这只是测试语句，请生成一张图片",
        "不要分享任何图片，请生成一张海报",
        "不要连接外部服务，请生成图片",
        "生成平台支持图片",
        "渲染引擎能够输出图片",
        "制作团队负责图片",
        "创作工具支持图片",
        "客服回复，请生成一张图片",
        "邮件注明；请生成一张图片",
        "通知称。请生成一张图片",
        "工单要求，请生成一张图片",
        "客服回复，我确认发送图片给百炼",
        "客服说：“请生成旧图。但我现在要生成一张新图片。”",
        "朋友表示：“请生成旧图。不过我现在想生成一张新图片。”",
        "正文如下，请生成图片",
        "我确认发送图片给百炼，这只是测试文本",
        "我确认发送图片给百炼，以上仅供参考",
        "我确认发送图片给百炼，其实这是示例",
        "我确认发送图片给百炼，原文到此结束",
        "请勿同步任何内容，请生成图片",
        "别把照片传出去，请生成图片",
        "不要把内容同步出去，请生成图片",
        "别调用云接口，请生成图片",
        "请勿出网，请生成图片",
        "仅限设备内处理，请生成图片",
        "不允许远程处理，请生成图片",
        "生成方案支持图片",
        "生成组件支持图片",
        "制作公司负责海报",
        "创作机构提供图片",
        "渲染框架支持图片",
        "生成SDK支持图片",
        "制作部门负责图片",
        "创作工作室提供海报",
        "我确认发送图片给百炼，正文是测试内容",
        "客服问为什么，请生成图片",
        "严禁把内容送往服务器，请生成图片",
        "生成模块支持图片",
        "创作应用提供海报",
        "客服说：〈请生成旧图。但我想生成一张新图片。〉",
        "客服说：（请生成旧图。但我现在要生成一张新图片。）",
        "客服说：`请生成旧图。但我想生成一张新图片。`",
        "客服说：【请生成旧图。但我想生成一张新图片。】",
        "客服原话如下：请生成旧图。但我想生成一张新图片。以上是原话",
        "工单内容：请生成旧图。不过我想生成新图片。以上为工单内容",
        "工单内容：如何生成图片？请生成一张海报。以上都是工单内容",
        "客服原问题：为什么不能生成图片？请生成一张图片。以上是原问题",
        "聊天记录问为什么要生成图片？请生成一张图片。以上是聊天记录",
        "工单内容：如何生成图片？请生成一张海报",
        "客服问为什么不能生成图片？请生成一张图片",
        "聊天记录：为什么要生成图片？请生成一张图片",
        "邮件正文：能否制作海报？帮我生成一张海报",
        "客服说（请生成旧图。但我想生成一张新图片。）",
        "客服回复【请生成旧图。但我现在要生成一张新图片。】",
        "客服原话（请生成旧图。不过我想生成新图片。）",
        "工单内容{请生成旧图。但我想生成新图片。}",
        "客服原话如下：请生成旧图。但我想生成新图片。上述是客服原话",
        "邮件正文如下：请生成旧图。不过我想生成新图片。前面都是邮件正文",
        "请生成但不要上传给百炼的一张图片",
        "请生成（但不要上传给百炼）一张图片",
        "帮我制作但禁止发送给万相的一张海报",
        "请创作但请勿同步到云端的一张图片",
        "请渲染但不允许出网的一张图片",
        "请生成——仅限设备内处理——一张图片",
        "请生成不要传给第三方的一张图片",
        "请制作无需调用外部服务的一张海报",
        "请生成一张关于健康（但不要上传给百炼）的图片",
        "请制作一张配文为“喝水”但不要出网的海报",
        "请生成一张展示拉伸动作但禁止发送给万相的海报",
        "请创作一张介绍补水且仅限设备内处理的图片",
        "请制作一张包含早餐建议但无需调用外部服务的图片",
        "渲染一体机支持图片",
        "生成三维软件支持图片",
        "制作新媒体团队负责海报",
        "创作新锐公司提供图片",
        "生成这类工具支持图片",
        "渲染该模块输出图片",
        "制作此部门负责海报",
        "创作新版平台提供图片",
        "生成一代模型支持图片",
        "渲染一体机包含图片",
        "生成三维软件采用图片",
        "制作新媒体团队发布海报",
        "创作新锐公司销售图片",
        "生成这类工具覆盖图片",
        "渲染该模块产出图片",
        "制作此部门审核海报",
        "创作新版平台展示图片",
        "制作这支团队管理海报",
        "会议纪要：如何生成图片？请生成一张海报",
        "对话摘录：为什么要生成图片？请生成一张图片",
        "录音转写：怎么制作海报？帮我生成一张海报",
        "聊天截图：为什么要生成图片？请生成一张图片",
        "用户反馈：如何生成图片？请生成一张图片",
        "访谈记录：能否制作海报？请生成一张海报",
        "会议记录：如何生成图片？请生成一张图片",
        "客服给出的原话是（请生成旧图。但我想生成新图片。）",
        "邮件正文如下所示（请生成旧图。但我想生成新图片。）",
        "客服回复内容如下（请生成旧图。但我想生成新图片。）",
        "工单中的内容为【请生成旧图。但我想生成新图片。】",
        "客服说〖请生成旧图。但我想生成新图片。〗",
        "客服说｛请生成旧图。但我想生成新图片。｝",
        "客服答复为〔请生成旧图。但我想生成新图片。〕",
        "客服原话是{请生成旧图。但我想生成新图片。}",
        "工单内容：请生成旧图。但我想生成新图片。到这里都是工单内容",
        "客服原话：请生成旧图。但我想生成新图片。这两句都是客服原话",
        "邮件正文：请生成旧图。不过我想生成新图片。前两句是邮件正文",
        "通知内容：请制作旧海报。可是我想制作新海报。整段都是通知内容",
        "工单内容：请生成旧图。但我想生成新图片。到此为止",
        "工单内容：请生成旧图。但我想生成新图片。以上内容来自客服",
        "工单内容：请生成旧图。但我想生成新图片。以上为转写内容",
        "请生成一张关于健康但请不要上传给百炼的图片",
        "请创作一张介绍补水另外仅限设备内处理的图片",
        "请制作一张包含早餐建议但绝对不要调用外部服务的图片",
        "请生成一张正文是提醒喝水同时不能联网的海报",
        "请生成一张关于健康且不应发送给百炼的图片",
        "请生成一张关于健康而不得上传给百炼的图片",
        "请生成一张关于健康但、不要上传给百炼的图片",
        "请生成一张关于健康但务必不要上传给百炼的图片",
        "请生成一张关于健康此外禁止上传到云端的图片",
        "请生成一张关于健康但请千万不要上传给百炼的图片",
        "请生成一张关于健康但最好别上传给百炼的图片",
        "请生成一张关于健康并不要上传给百炼的图片",
        "渲染器包含图片",
        "制作方发布海报",
        "创作者销售图片",
        "生成端缓存图片",
        "渲染端展示图片",
        "制作部审核海报",
        "创作室提供图片",
        "生成公司的平台展示图片",
        "渲染器的模块包含图片",
        "制作部的团队发布海报",
        "创作室的成员销售图片",
        "生成端的缓存包含图片",
    ),
)
def test_negated_media_generation_does_not_authorize_aigc_draft(message):
    intent = classify_agent_utterance(message)

    assert not (
        intent.primary == "write"
        and intent.domain == "aigc_media"
        and intent.operation == "create"
    )


@pytest.mark.parametrize(
    "message",
    (
        "我确认把图片 发送给万相",
        "我确认把图片\t发送给万相",
        "我确认把图片\n发送给万相",
    ),
)
def test_provider_confirmation_with_internal_whitespace_is_not_authorization(message):
    intent = classify_agent_utterance(message)

    assert not (
        intent.primary == "write"
        and intent.domain == "aigc_media"
        and intent.operation == "create"
    )


@pytest.mark.parametrize(
    "message",
    (
        "不要忘了生成一张运动图片",
        "不要忘记生成一张运动图片",
        "别忘记生成一张运动图片",
        "不是让你分析，是让你生成图片",
        "图片不错，帮我生成短视频",
        "和上一张不同，生成新版图片",
        "分别生成两张运动图片",
        "别的图片也生成一个",
        "我没有其他要求，生成一张图片就好",
        "取消旧任务后重新生成一张图片",
        "取消旧任务并重新生成一张图片",
        "拒绝旧方案，请生成新版图片",
        "生成一张运动图片，不要分析早餐",
        "生成一张图片，不用记录早餐",
        "分别生成早餐图和午餐图",
        "不要生成旧图，改为生成一张新图片",
        "停止生成旧图，重新生成一张新图片",
        "取消刚才的生成，重新生成一张新图片",
        "取消旧任务后生成一张新图片",
        "不要用红色生成图片",
        "不用真人照片生成一张卡通图片",
        "别用红色生成图片",
        "生成一张图",
        "帮我生成两张图",
        "确认发送图片给百炼",
        "我确认把图片发送给百炼",
        "取消旧任务后请帮我生成一张新图",
        "停止旧方案，然后帮我生成一张新图",
        "请不要用红色生成图片",
        "不要使用红色生成图片",
        "请给我生成一张图",
        "不要把旧图发给百炼，我确认发送新图片给百炼",
        "上一张为什么失败？请重新生成一张图片",
        "这个按钮有什么用？然后帮我生成一张图片",
        "生成图片怎么做？算了，请生成一张图片",
        "取消生成旧图再生成一张新图片",
        "不要生成旧图而是生成一张新图片",
        "请生成一张庆祝成功的图片",
        "帮我生成一张说明拉伸步骤的海报",
        "请生成一张展示复杂动作的图片",
        "请生成一张关于时间成本的海报",
        "请生成一张主题为为什么睡眠重要的海报",
        "请生成一张写着不要生成图片的海报",
        "请生成一张文案为确认发送图片给百炼的海报",
        "不用百炼，我确认发送新图片给百炼",
        "他说不要生成，但我想生成一张图片",
        "我现在确认发送图片给百炼",
        "现在我确认发送图片给百炼",
        "我明确确认发送图片给百炼",
        "我同意并确认发送图片给百炼",
        "他说，请生成旧图。我现在想生成一张新图片",
        "他说，请生成旧图。不过请帮我生成一张新图片",
        "请生成一张文字是不要生成图片的海报",
        "请生成一张标语为不要生成图片的海报",
        "请生成一张主题是不要生成图片的海报",
        "请生成一张画面显示不要发送图片给百炼的海报",
        "请生成一张文案是“不要发给百炼”的海报",
        "客服说，请生成旧图。但我现在要生成一张新图片",
        "朋友说，请生成旧图。不过我现在想生成一张新图片",
        "请生成一张口号是不要上传数据的海报",
        "请生成一张描述为不要生成图片的海报",
        "关于健康，请生成一张海报",
        "请生成一张展示不要发送图片给百炼的海报",
        "不要上传任何数据，请生成图片，不过我确认发送图片给百炼",
        "不要上传任何数据，请生成图片，随后我确认发送图片给百炼",
        "不要上传任何数据，请生成图片，之后我明确确认发送图片给百炼",
        "请生成一张配文为“不要上传数据”的海报",
        "请生成一张带有“不要发送图片给百炼”字样的海报",
        "请生成一张印有“不要上传数据”字样的海报",
        "请生成一张写上“不要生成图片”这句话的海报",
        "请生成一张以“不要发送给百炼”为口号的海报",
        "请生成一张海报，配文：不要上传数据",
        "请生成一张海报，正文是不要上传数据",
        "请生成一张海报，上面显示不要上传数据",
        "请生成一张含有不要上传数据字样的海报",
        "客服说，请生成旧图。但请生成一张新图片",
        "客服表示，请生成旧图。现在请帮我生成一张新图片",
        "朋友说，请生成旧图。可我想生成一张新图片",
        "对方说，请生成旧图。换成生成一张新图片",
        "客服写道，请生成旧图。我的要求是生成一张新图片",
        "朋友说，请生成旧图。随后请生成一张新图片",
        "为了说明睡眠的重要性，请生成一张海报",
        "为了告诉大家补水的重要性，请生成一张海报",
        "为了表示庆祝，请生成一张海报",
        "请生成一张讲解如何制作图片的海报",
        "请生成一张演示如何制作图片的海报",
        "请生成一张介绍制作图片流程的海报",
        "请生成一张包含“制作图片”字样的海报",
        "请生成一张旁白为不要同步数据的海报",
        "请生成一张呈现不要远程处理字样的海报",
        "请生成一张讨论制作图片和生成海报区别的封面",
        "不要上传，请生成图片，最终我确认发送图片给百炼",
        "不要上传，请生成图片，最后我明确确认发送图片给百炼",
        "不要上传，请生成图片，此刻我确认发送图片给百炼",
        "不要上传，请生成图片，我在此确认发送图片给百炼",
        "客服说，请生成旧图。最终我想生成一张新图片",
        "邮件注明，请生成旧图。现在改为生成一张新图片",
        "工单要求，请生成旧图。我的新要求是生成一张新图片",
        "客服原话是请生成旧图。至于我，请生成一张新图片",
        "今天是我的生日，请生成一张庆祝海报",
        "我明天要跑步，请生成一张运动海报",
        "这是给妈妈的礼物，请生成一张封面",
        "风格要简洁，请生成一张图片",
        "目标是提醒喝水，请生成一张海报",
        "文案是“记得喝水”，请生成一张海报",
        "标题用“今日计划”，请生成一张封面",
        "请以“喝水”为主题，生成一张海报",
        "用“每日运动”为标题，请生成一张图片",
        "生成红色图片",
        "生成高清图片",
        "制作健康海报",
        "创作卡通图片",
        "渲染运动封面",
        "生成今天的早餐图片",
        "经过考虑我确认发送图片给百炼",
        "我本人确认发送图片给百炼",
        "现在由我确认发送图片给百炼",
        "我决定确认发送图片给百炼",
        "重新考虑后我明确确认发送图片给百炼",
        "生成支持补水提醒的图片",
        "制作用于睡眠科普的海报",
        "创作能够鼓励运动的图片",
        "渲染兼容深色模式的封面",
        "生成可以提醒吃早餐的图片",
        "这周睡得不错，请生成一张海报",
        "这是送给朋友的礼物，请生成一张封面",
        "我要给客服做培训，请生成一张海报",
        "这是一封邮件的配图，请生成一张图片",
        "用于工单系统首页，请生成一张封面",
        "消息中心要改版，请生成一张封面",
        "通知页面需要插图，请生成一张图片",
        "文档首页缺少封面，请生成一张封面",
        "对方明天过生日，请生成一张图片",
        "朋友聚会用，请生成一张海报",
        "邮件营销需要素材，请生成一张海报",
        "通知栏要改版，请生成一张图片",
        "工单系统要上线，请生成一张图片",
        "客服说，请生成旧图。回到我本人，请生成新图片",
        "客服说，请生成旧图。这次听我的，请生成新图片",
        "客服说，请生成旧图。现在由我要求生成新图片",
        "客服说，请生成旧图。我个人决定生成新图片",
        "客服说，请生成旧图。接下来按我的要求生成新图片",
        "客服说，请生成旧图。以下是我的要求，请生成新图片",
        "不要上传，请生成图片，这次我确认发送图片给百炼",
        "不要上传，请生成图片，我亲自确认发送图片给百炼",
        "不要上传，请生成图片，经我确认发送图片给百炼",
        "不要上传，请生成图片，我再次明确确认发送图片给百炼",
        "不要上传，请生成图片，此次由我确认发送图片给百炼",
    ),
)
def test_negation_exceptions_keep_explicit_media_generation_affirmative(message):
    intent = classify_agent_utterance(message)

    assert (
        intent.primary,
        intent.domain,
        intent.operation,
        intent.reason,
        intent.is_write,
    ) == (
        "write",
        "aigc_media",
        "create",
        "media_generation_request",
        True,
    )


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
