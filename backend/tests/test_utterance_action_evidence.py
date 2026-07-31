from dataclasses import FrozenInstanceError
from inspect import getsource

import pytest

import app.services.utterance_action_evidence as utterance_action_evidence
from app.services.utterance_action_evidence import (
    ActionEvidence,
    EvidenceParse,
    ProviderEvidence,
    parse_action_evidence,
)


def test_evidence_types_are_frozen_and_parse_starts_empty():
    parsed = parse_action_evidence("")

    assert parsed == EvidenceParse(
        text="",
        clinician_bearing=False,
        providers=(),
        actions=(),
    )
    with pytest.raises(FrozenInstanceError):
        parsed.text = "changed"

    provider = ProviderEvidence(
        start=0,
        end=2,
        provider="医生",
        relation="unresolved",
    )
    with pytest.raises(FrozenInstanceError):
        provider.relation = "report"

    action = ActionEvidence(
        start=0,
        end=2,
        action="save",
        actor="user",
        target="health_record",
        target_start=2,
        target_end=4,
        polarity="positive",
        modality="command",
        provenance="explicit_user_command",
    )
    with pytest.raises(FrozenInstanceError):
        action.actor = "clinician"


def _action(
    *,
    start=0,
    end=2,
    target="unknown",
    target_start=2,
    target_end=2,
):
    return ActionEvidence(
        start=start,
        end=end,
        action="save",
        actor="user",
        target=target,
        target_start=target_start,
        target_end=target_end,
        polarity="positive",
        modality="command",
        provenance="explicit_user_command",
    )


@pytest.mark.parametrize(
    "factory",
    (
        lambda: ProviderEvidence(
            start=0,
            end=0,
            provider="医生",
            relation="unresolved",
        ),
        lambda: ProviderEvidence(
            start=-1,
            end=1,
            provider="医生",
            relation="unresolved",
        ),
        lambda: ProviderEvidence(
            start=2,
            end=1,
            provider="医生",
            relation="unresolved",
        ),
        lambda: _action(start=0, end=0, target_start=0, target_end=0),
    ),
)
def test_source_and_action_spans_must_be_non_empty(factory):
    with pytest.raises(ValueError, match="non-empty"):
        factory()


def test_unknown_target_may_use_an_empty_anchor_span():
    evidence = _action(target_start=2, target_end=2)

    assert evidence.target == "unknown"
    assert evidence.target_start == evidence.target_end == 2


def test_known_target_span_must_be_non_empty():
    with pytest.raises(ValueError, match="target span"):
        _action(
            target="health_record",
            target_start=2,
            target_end=2,
        )


@pytest.mark.parametrize(
    "factory",
    (
        lambda: EvidenceParse(
            text="医生",
            clinician_bearing=False,
            providers=(
                ProviderEvidence(
                    start=0,
                    end=2,
                    provider="医生",
                    relation="unresolved",
                ),
            ),
            actions=(),
        ),
        lambda: EvidenceParse(
            text="没有医疗角色",
            clinician_bearing=True,
            providers=(),
            actions=(),
        ),
    ),
)
def test_clinician_bearing_must_match_provider_presence(factory):
    with pytest.raises(ValueError, match="clinician_bearing"):
        factory()


def test_evidence_parse_rejects_provider_span_outside_text():
    provider = ProviderEvidence(
        start=0,
        end=2,
        provider="医生",
        relation="unresolved",
    )

    with pytest.raises(ValueError, match="provider span"):
        EvidenceParse(
            text="医",
            clinician_bearing=True,
            providers=(provider,),
            actions=(),
        )


def test_evidence_parse_rejects_provider_raw_slice_mismatch():
    provider = ProviderEvidence(
        start=0,
        end=2,
        provider="医生",
        relation="unresolved",
    )

    with pytest.raises(ValueError, match="provider raw slice"):
        EvidenceParse(
            text="大夫",
            clinician_bearing=True,
            providers=(provider,),
            actions=(),
        )


def test_evidence_parse_rejects_action_or_target_span_outside_text():
    with pytest.raises(ValueError, match="action span"):
        EvidenceParse(
            text="记",
            clinician_bearing=False,
            providers=(),
            actions=(_action(),),
        )

    with pytest.raises(ValueError, match="target span"):
        EvidenceParse(
            text="记录",
            clinician_bearing=False,
            providers=(),
            actions=(
                _action(
                    target="health_record",
                    target_start=2,
                    target_end=3,
                ),
            ),
        )


def test_evidence_parse_rejects_non_monotonic_provider_sequence():
    text = "医生大夫"
    doctor = ProviderEvidence(
        start=0,
        end=2,
        provider="医生",
        relation="unresolved",
    )
    doctor_alt = ProviderEvidence(
        start=2,
        end=4,
        provider="大夫",
        relation="unresolved",
    )

    with pytest.raises(ValueError, match="providers must be ordered"):
        EvidenceParse(
            text=text,
            clinician_bearing=True,
            providers=(doctor_alt, doctor),
            actions=(),
        )


def test_evidence_parse_rejects_non_monotonic_action_sequence():
    with pytest.raises(ValueError, match="actions must be ordered"):
        EvidenceParse(
            text="记录删除",
            clinician_bearing=False,
            providers=(),
            actions=(
                _action(start=2, end=4, target_start=4, target_end=4),
                _action(start=0, end=2, target_start=2, target_end=2),
            ),
        )


def test_evidence_parse_rejects_duplicate_start_offsets():
    doctor = ProviderEvidence(
        start=0,
        end=2,
        provider="医生",
        relation="unresolved",
    )
    with pytest.raises(ValueError, match="providers must be ordered"):
        EvidenceParse(
            text="医生",
            clinician_bearing=True,
            providers=(doctor, doctor),
            actions=(),
        )

    action = _action()
    with pytest.raises(ValueError, match="actions must be ordered"):
        EvidenceParse(
            text="记录",
            clinician_bearing=False,
            providers=(),
            actions=(action, action),
        )


def test_evidence_parse_rejects_overlapping_provider_source_spans():
    with pytest.raises(ValueError, match="providers.*non-overlapping"):
        EvidenceParse(
            text="主治医生",
            clinician_bearing=True,
            providers=(
                ProviderEvidence(0, 4, "主治医生", "report"),
                ProviderEvidence(2, 4, "医生", "report"),
            ),
            actions=(),
        )


def test_evidence_parse_rejects_overlapping_action_source_spans():
    with pytest.raises(ValueError, match="actions.*non-overlapping"):
        EvidenceParse(
            text="记录保存",
            clinician_bearing=False,
            providers=(),
            actions=(
                _action(start=0, end=3, target_start=3, target_end=3),
                _action(start=2, end=4, target_start=4, target_end=4),
            ),
        )


def test_action_target_spans_may_overlap_other_action_sources_and_targets():
    first = _action(
        start=0,
        end=2,
        target="diet",
        target_start=2,
        target_end=4,
    )
    second = _action(
        start=4,
        end=6,
        target="diet",
        target_start=2,
        target_end=4,
    )

    parsed = EvidenceParse(
        text="记录饮食保存",
        clinician_bearing=False,
        providers=(),
        actions=(first, second),
    )

    assert parsed.actions == (first, second)


@pytest.mark.parametrize(
    ("text", "provider", "relation"),
    (
        ("医生诊断：臀肌无力", "医生", "report"),
        ("主治医生说腰痛", "主治医生", "report"),
        ("大夫认为需要休息", "大夫", "report"),
        ("医师表示先观察", "医师", "report"),
        ("康复师建议加强训练", "康复师", "report"),
        ("物理治疗师判断是代偿", "物理治疗师", "report"),
        ("理疗师告诉我要拉伸", "理疗师", "report"),
        ("根据医生建议调整训练", "医生", "basis"),
        ("依据物理治疗师评估减少负重", "物理治疗师", "basis"),
        ("按照理疗师方案练习", "理疗师", "basis"),
        ("昨天见了医师", "医师", "unresolved"),
    ),
)
def test_provider_evidence_preserves_raw_span_and_relation(
    text,
    provider,
    relation,
):
    parsed = parse_action_evidence(text)

    assert parsed.text == text
    assert parsed.clinician_bearing is True
    assert len(parsed.providers) == 1
    evidence = parsed.providers[0]
    assert text[evidence.start : evidence.end] == provider
    assert evidence.provider == provider
    assert evidence.relation == relation


@pytest.mark.parametrize(
    "text",
    (
        "医生诊断记录",
        "医生建议清单",
    ),
)
def test_report_like_provider_noun_phrase_is_unresolved(text):
    parsed = parse_action_evidence(text)

    assert parsed.providers[0].relation == "unresolved"


@pytest.mark.parametrize(
    "text",
    (
        "医生诊断的记录",
        "医生建议的清单",
    ),
)
def test_linked_provider_noun_phrase_is_unresolved(text):
    parsed = parse_action_evidence(text)

    assert parsed.providers[0].relation == "unresolved"


@pytest.mark.parametrize(
    "text",
    (
        "医生诊断是腰肌劳损",
        "医生建议每天拉伸",
    ),
)
def test_provider_report_predicate_with_content_is_report(text):
    parsed = parse_action_evidence(text)

    assert parsed.providers[0].relation == "report"


@pytest.mark.parametrize(
    ("text", "expected"),
    (
        (
            "医生说腰痛，：\n主治医生认为臀肌无力！：大夫建议复诊",
            (
                ProviderEvidence(0, 2, "医生", "report"),
                ProviderEvidence(8, 12, "主治医生", "report"),
                ProviderEvidence(20, 22, "大夫", "report"),
            ),
        ),
        (
            "医生说腰痛,\n康复师认为臀肌无力!:理疗师建议复诊",
            (
                ProviderEvidence(0, 2, "医生", "report"),
                ProviderEvidence(7, 10, "康复师", "report"),
                ProviderEvidence(18, 21, "理疗师", "report"),
            ),
        ),
        (
            "医生说腰痛康复师认为臀肌无力物理治疗师建议复诊",
            (
                ProviderEvidence(0, 2, "医生", "report"),
                ProviderEvidence(5, 8, "康复师", "report"),
                ProviderEvidence(14, 19, "物理治疗师", "report"),
            ),
        ),
    ),
)
def test_scanner_keeps_provider_offsets_across_delimiters_and_connections(
    text,
    expected,
):
    parsed = parse_action_evidence(text)

    assert parsed.text == text
    assert parsed.providers == expected
    assert parsed.actions == ()


def test_longest_provider_match_does_not_duplicate_nested_doctor_term():
    text = "主治医生说先观察"

    parsed = parse_action_evidence(text)

    assert parsed.providers == (
        ProviderEvidence(
            start=0,
            end=len("主治医生"),
            provider="主治医生",
            relation="report",
        ),
    )


def test_repeated_provider_is_returned_at_each_raw_offset():
    text = "医生说腰痛医生建议拉伸"

    parsed = parse_action_evidence(text)

    assert parsed.providers == (
        ProviderEvidence(0, 2, "医生", "report"),
        ProviderEvidence(5, 7, "医生", "report"),
    )


def test_provider_at_end_preserves_exact_offset():
    text = "复诊时问医生"

    parsed = parse_action_evidence(text)

    assert parsed.providers == (
        ProviderEvidence(4, 6, "医生", "unresolved"),
    )


def test_provider_after_emoji_and_combining_unicode_preserves_exact_offset():
    prefix = "🧑🏽‍⚕️e\u0301"
    text = f"{prefix}医生说先观察"

    parsed = parse_action_evidence(text)

    assert parsed.providers == (
        ProviderEvidence(
            len(prefix),
            len(prefix) + len("医生"),
            "医生",
            "report",
        ),
    )


@pytest.mark.parametrize(
    ("text", "expected_action"),
    (
        ("医生", None),
        ("医生建议记录疼痛", "save"),
        ("主治医生要求删除诊断记录", "delete"),
    ),
)
def test_provider_evidence_is_independent_of_known_action_words(
    text,
    expected_action,
):
    parsed = parse_action_evidence(text)

    assert parsed.clinician_bearing is True
    assert parsed.providers
    assert tuple(action.action for action in parsed.actions) == (
        () if expected_action is None else (expected_action,)
    )


def test_non_clinician_text_has_no_provider_evidence():
    text = "请记录今天午餐吃了牛肉面"

    parsed = parse_action_evidence(text)

    assert parsed.text == text
    assert parsed.clinician_bearing is False
    assert parsed.providers == ()
    assert len(parsed.actions) == 1
    assert parsed.actions[0].action == "save"


@pytest.mark.parametrize(
    ("kwargs", "message"),
    (
        (
            {
                "start": -1,
                "end": 1,
                "target_start": 1,
                "target_end": 2,
            },
            "action span",
        ),
        (
            {
                "start": 2,
                "end": 1,
                "target_start": 1,
                "target_end": 2,
            },
            "action span",
        ),
        (
            {
                "start": 0,
                "end": 1,
                "target_start": 3,
                "target_end": 2,
            },
            "target span",
        ),
    ),
)
def test_action_evidence_rejects_invalid_spans(kwargs, message):
    with pytest.raises(ValueError, match=message):
        ActionEvidence(
            action="save",
            actor="user",
            target="health_record",
            polarity="positive",
            modality="command",
            provenance="explicit_user_command",
            **kwargs,
        )


def test_module_does_not_use_regular_expressions():
    source = getsource(utterance_action_evidence)

    assert "import re" not in source
    assert "re." not in source
    assert "re.compile" not in source


def _assert_raw_action_spans(text, actions):
    for action in actions:
        assert text[action.start : action.end]
        assert text[action.start : action.end] in {
            "记录",
            "记一下",
            "记下",
            "录入",
            "保存",
            "写入",
            "存下来",
            "查看",
            "删除",
            "调整",
            "同步",
            "分析",
            "生成",
            "创建",
            "制定",
        }


@pytest.mark.parametrize(
    ("text", "expected"),
    (
        (
            "我想记录饮食但医生说要保存诊断",
            (("记录", "save", "user"), ("保存", "save", "clinician")),
        ),
        (
            "医生说要保存诊断但请记录今天腰痛6分",
            (("保存", "save", "clinician"), ("记录", "save", "user")),
        ),
        (
            "我想记录今天腰痛但医生说要保存检查结果",
            (("记录", "save", "user"), ("保存", "save", "clinician")),
        ),
        (
            "医生说要删除用药记录然后请记录今天腰痛6分",
            (("删除", "delete", "clinician"), ("记录", "save", "user")),
        ),
    ),
)
def test_action_occurrences_resolve_actor_independently(text, expected):
    parsed = parse_action_evidence(text)

    assert tuple(
        (text[item.start : item.end], item.action, item.actor)
        for item in parsed.actions
    ) == expected
    _assert_raw_action_spans(text, parsed.actions)


@pytest.mark.parametrize(
    ("text", "expected"),
    (
        ("医生诊断记录", ()),
        ("查看医生诊断记录", (("查看", "read"),)),
        ("把医生诊断记录删除", (("删除", "delete"),)),
        (
            "请记录饮食然后需要查看医生诊断记录",
            (("记录", "save"), ("查看", "read")),
        ),
        (
            "请记录今天腰痛随后需要分析医生诊断记录",
            (("记录", "save"), ("分析", "advice")),
        ),
    ),
)
def test_record_noun_spans_do_not_create_save_evidence(text, expected):
    parsed = parse_action_evidence(text)

    assert tuple(
        (text[item.start : item.end], item.action)
        for item in parsed.actions
    ) == expected
    _assert_raw_action_spans(text, parsed.actions)


@pytest.mark.parametrize(
    "text",
    (
        "医生对我说要删除昨天用药记录",
        "医生跟我说要同步健康数据",
        "医生叫我记录每天腰痛情况",
        "医生指示我删除昨天用药记录",
        "医生的建议是删除昨天记录",
        "医生给我的要求是记录每天腰痛",
        "医生希望我保存检查结果",
        "物理治疗师要求我记录每天疼痛",
        "理疗师让我删除健康记录",
        "医师嘱咐我同步健康数据",
    ),
)
def test_provider_governed_action_is_never_user_authorized(text):
    parsed = parse_action_evidence(text)

    assert len(parsed.actions) == 1
    assert parsed.actions[0].actor in {"clinician", "ambiguous"}
    _assert_raw_action_spans(text, parsed.actions)


@pytest.mark.parametrize(
    "text",
    (
        "根据医生建议删除昨天用药记录",
        "依据医生建议调整用药剂量",
        "按照医生建议同步健康数据",
        "请依据医生说的内容调整用药",
        "根据医生诊断生成一张康复图片",
    ),
)
def test_clinician_basis_keeps_user_as_action_authority(text):
    parsed = parse_action_evidence(text)

    assert len(parsed.actions) == 1
    assert parsed.actions[0].actor == "user"
    _assert_raw_action_spans(text, parsed.actions)


def test_give_me_substring_does_not_grant_user_authority():
    text = "医生给我的要求是记录每天腰痛"

    parsed = parse_action_evidence(text)

    assert parsed.actions[0].actor != "user"


@pytest.mark.parametrize(
    ("text", "expected_action", "expected_target"),
    (
        ("删除根据医生诊断生成的用药记录", "delete", "medication"),
        ("调整医生诊断中提到的用药剂量", "update", "medication"),
        ("记录根据医生诊断出现的今天腰痛6分", "save", "symptom"),
        ("根据医生诊断记录今天腰痛6分", "save", "symptom"),
        ("根据医生诊断生成一张康复图片", "media", "media"),
        ("根据医生诊断创建明天复查提醒", "reminder", "reminder"),
        ("根据医生诊断制定一个康复计划", "plan", "plan"),
    ),
)
def test_specific_action_target_wins_over_clinician_basis(
    text,
    expected_action,
    expected_target,
):
    parsed = parse_action_evidence(text)

    assert len(parsed.actions) == 1
    action = parsed.actions[0]
    assert action.action == expected_action
    assert action.target == expected_target
    assert text[action.target_start : action.target_end]


_SAVE_SYNONYMS = (
    "记录",
    "记一下",
    "记下",
    "录入",
    "保存",
    "写入",
    "存下来",
)


@pytest.mark.parametrize("verb", _SAVE_SYNONYMS)
@pytest.mark.parametrize(
    ("template", "expected_polarity", "expected_modality"),
    (
        ("请{verb}今天腰痛", "positive", "command"),
        ("要不要{verb}今天腰痛？", "positive", "question"),
        ("是否需要{verb}今天腰痛？", "positive", "question"),
        ("不要{verb}今天腰痛", "negative", "command"),
        ("不用{verb}今天腰痛", "negative", "command"),
        ("无需{verb}今天腰痛", "negative", "command"),
        ("先别{verb}今天腰痛", "negative", "command"),
        ("不想{verb}今天腰痛", "negative", "command"),
        ("没有必要{verb}今天腰痛", "negative", "command"),
    ),
)
def test_save_occurrence_has_local_polarity_and_modality(
    verb,
    template,
    expected_polarity,
    expected_modality,
):
    text = template.format(verb=verb)

    parsed = parse_action_evidence(text)

    assert len(parsed.actions) == 1
    action = parsed.actions[0]
    assert text[action.start : action.end] == verb
    assert action.action == "save"
    assert action.actor == "user"
    assert action.polarity == expected_polarity
    assert action.modality == expected_modality


@pytest.mark.parametrize(
    ("text", "expected_action", "expected_polarity", "expected_modality"),
    (
        ("请删除昨天用药记录", "delete", "positive", "command"),
        ("不要删除昨天用药记录", "delete", "negative", "command"),
        ("要不要删除昨天用药记录？", "delete", "positive", "question"),
        ("请调整用药剂量", "update", "positive", "command"),
        ("无需调整用药剂量", "update", "negative", "command"),
        ("是否需要调整用药剂量？", "update", "positive", "question"),
        ("请同步健康数据", "sync", "positive", "command"),
        ("先别同步健康数据", "sync", "negative", "command"),
        ("要不要同步健康数据？", "sync", "positive", "question"),
    ),
)
def test_non_save_occurrence_has_local_polarity_and_modality(
    text,
    expected_action,
    expected_polarity,
    expected_modality,
):
    parsed = parse_action_evidence(text)

    assert len(parsed.actions) == 1
    action = parsed.actions[0]
    assert action.action == expected_action
    assert action.polarity == expected_polarity
    assert action.modality == expected_modality


def test_polarity_is_resolved_per_action_occurrence():
    text = "不要记录饮食但请保存诊断"

    parsed = parse_action_evidence(text)

    assert tuple(
        (action.action, action.polarity)
        for action in parsed.actions
    ) == (("save", "negative"), ("save", "positive"))
