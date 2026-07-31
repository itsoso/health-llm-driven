from dataclasses import FrozenInstanceError
from inspect import getsource

import pytest

import app.services.utterance_action_evidence as utterance_action_evidence
import app.services.utterance_intent_classifier as utterance_intent_classifier
from app.services import utterance_intent_lexicon as lexicon
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
            "更新",
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
            (
                ("保存", "save", "clinician"),
                ("记录", "save", "user"),
            ),
        ),
        (
            "我想记录今天腰痛但医生说要保存检查结果",
            (("记录", "save", "user"), ("保存", "save", "clinician")),
        ),
        (
            "医生说要删除用药记录然后请记录今天腰痛6分",
            (
                ("删除", "delete", "clinician"),
                ("记录", "save", "user"),
            ),
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


def test_every_structured_save_row_uses_shared_stance_cues():
    rows = tuple(
        row
        for row in lexicon.EVIDENCE_ACTION_LEXICON
        if "save" in row.allowed_families
    )
    assert rows

    for row in rows:
        direct = parse_action_evidence(f"请{row.surface}今天腰痛")
        assert tuple(
            (action.action, action.polarity, action.modality)
            for action in direct.actions
        ) == (("save", "positive", "command"),), row

        for cue in lexicon.EVIDENCE_NEGATION_CUES:
            parsed = parse_action_evidence(
                f"{cue.surface}{row.surface}今天腰痛"
            )
            assert tuple(action.polarity for action in parsed.actions) == (
                "negative",
            ), (row, cue, parsed.actions)

        for cue in lexicon.EVIDENCE_QUESTION_CUES:
            text = (
                f"{cue.surface}{row.surface}今天腰痛"
                if cue.placement == "prefix"
                else f"{row.surface}今天腰痛{cue.surface}"
            )
            parsed = parse_action_evidence(text)
            assert tuple(action.modality for action in parsed.actions) == (
                "question",
            ), (row, cue, parsed.actions)


def test_every_structured_mutation_row_uses_shared_stance_cues():
    mutation_families = frozenset({"delete", "update", "sync"})
    target_by_family = {
        "delete": "用药记录",
        "update": "用药剂量",
        "sync": "健康数据",
    }
    rows = tuple(
        row
        for row in lexicon.EVIDENCE_ACTION_LEXICON
        if row.allowed_families & mutation_families
    )
    assert rows

    for row in rows:
        family = next(iter(row.allowed_families & mutation_families))
        target = target_by_family[family]
        direct = parse_action_evidence(f"请{row.surface}{target}")
        assert tuple(
            (action.action, action.polarity, action.modality)
            for action in direct.actions
        ) == ((family, "positive", "command"),), row

        for cue in lexicon.EVIDENCE_NEGATION_CUES:
            parsed = parse_action_evidence(
                f"{cue.surface}{row.surface}{target}"
            )
            assert tuple(action.polarity for action in parsed.actions) == (
                "negative",
            ), (row, cue, parsed.actions)

        for cue in lexicon.EVIDENCE_QUESTION_CUES:
            text = (
                f"{cue.surface}{row.surface}{target}"
                if cue.placement == "prefix"
                else f"{row.surface}{target}{cue.surface}"
            )
            parsed = parse_action_evidence(text)
            assert tuple(action.modality for action in parsed.actions) == (
                "question",
            ), (row, cue, parsed.actions)


def test_polarity_is_resolved_per_action_occurrence():
    text = "不要记录饮食但请保存诊断"

    parsed = parse_action_evidence(text)

    assert tuple(
        (action.action, action.polarity)
        for action in parsed.actions
    ) == (("save", "negative"), ("save", "positive"))


@pytest.mark.parametrize(
    ("text", "expected"),
    (
        (
            "医生说要保存诊断而我想记录今天腰痛",
            (("保存", "clinician"), ("记录", "user")),
        ),
        (
            "医生说要保存诊断接着请记录今天腰痛",
            (("保存", "clinician"), ("记录", "user")),
        ),
        (
            "医生说要保存诊断但是帮我记录今天腰痛",
            (("保存", "clinician"), ("记录", "user")),
        ),
        (
            "我想记录饮食而医生说要保存诊断",
            (("记录", "user"), ("保存", "clinician")),
        ),
    ),
)
def test_actor_uses_nearest_structural_evidence_per_occurrence(
    text,
    expected,
):
    parsed = parse_action_evidence(text)

    assert tuple(
        (text[action.start : action.end], action.actor)
        for action in parsed.actions
    ) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    (
        (
            "请删除用药记录后记录今天腰痛",
            (
                ("delete", "medication"),
                ("save", "symptom"),
            ),
        ),
        (
            "查看医生诊断记录后记录今天饮食",
            (
                ("read", "clinician_record"),
                ("save", "diet"),
            ),
        ),
        (
            "分析医生诊断记录然后记录体重71kg",
            (
                ("advice", "clinician_record"),
                ("save", "weight"),
            ),
        ),
        (
            "更新用药记录并记录今天腰痛",
            (
                ("update", "medication"),
                ("save", "symptom"),
            ),
        ),
    ),
)
def test_lexical_record_noun_span_does_not_swallow_later_save(
    text,
    expected,
):
    parsed = parse_action_evidence(text)

    assert tuple(
        (action.action, action.target)
        for action in parsed.actions
    ) == expected


_ACTOR_MATRIX_PROVIDERS = (
    "医生",
    "大夫",
    "医师",
    "康复师",
    "物理治疗师",
)
_REPORT_CONNECTIVE_STRUCTURES = (
    "对我说要",
    "跟我说要",
    "叫我",
    "指示我",
    "给我的要求是",
    "希望我",
    "要求我",
)


@pytest.mark.parametrize("provider", _ACTOR_MATRIX_PROVIDERS)
@pytest.mark.parametrize("connective", _REPORT_CONNECTIVE_STRUCTURES)
def test_provider_and_report_connective_cross_product_never_authorizes_user(
    provider,
    connective,
):
    text = f"{provider}{connective}删除昨天用药记录"

    parsed = parse_action_evidence(text)

    assert len(parsed.actions) == 1
    assert parsed.actions[0].actor in {"clinician", "ambiguous"}


@pytest.mark.parametrize("provider", _ACTOR_MATRIX_PROVIDERS)
@pytest.mark.parametrize("basis", ("根据", "依据", "按照"))
def test_basis_and_provider_cross_product_keeps_user_authority(
    provider,
    basis,
):
    text = f"{basis}{provider}建议删除昨天用药记录"

    parsed = parse_action_evidence(text)

    assert len(parsed.actions) == 1
    assert parsed.actions[0].actor == "user"


@pytest.mark.parametrize(
    "text",
    (
        "医生说请记录每天腰痛",
        "医生说帮我删除用药记录",
        "医生建议请调整用药",
        "医生要求帮我同步健康数据",
    ),
)
def test_user_cue_inside_provider_report_does_not_steal_authority(text):
    parsed = parse_action_evidence(text)

    assert len(parsed.actions) == 1
    assert parsed.actions[0].actor in {"clinician", "ambiguous"}


@pytest.mark.parametrize(
    ("text", "expected"),
    (
        (
            "医生说要保存诊断但是帮我记录今天腰痛",
            (("save", "clinician"), ("save", "user")),
        ),
        (
            "医生说要保存诊断接着请记录今天腰痛",
            (("save", "clinician"), ("save", "user")),
        ),
        (
            "医生说是腰肌劳损。请记录医生诊断",
            (("save", "clinician"),),
        ),
    ),
)
def test_previous_action_or_hard_boundary_resets_to_user_authority(
    text,
    expected,
):
    parsed = parse_action_evidence(text)

    assert tuple(
        (action.action, action.actor)
        for action in parsed.actions
    ) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    (
        (
            "医生说：“先删除旧记录，然后请记录每天腰痛”",
            (("delete", "clinician"), ("save", "clinician")),
        ),
        (
            "医生说先保存诊断然后请删除用药记录",
            (("save", "clinician"), ("delete", "user")),
        ),
        (
            "医生说要保存诊断但请记录今天腰痛",
            (("save", "clinician"), ("save", "user")),
        ),
        (
            "根据医生说：“请删除用药记录”",
            (("delete", "clinician"),),
        ),
    ),
)
def test_provider_report_scope_owns_every_nested_action(
    text,
    expected,
):
    parsed = parse_action_evidence(text)

    assert tuple(
        (action.action, action.actor) for action in parsed.actions
    ) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    (
        (
            "医生说要保存诊断。但我想记录今天腰痛",
            (("save", "clinician"), ("save", "user")),
        ),
        (
            "医生说要保存诊断然后我想记录今天腰痛",
            (("save", "clinician"), ("save", "user")),
        ),
        (
            "医生说要保存诊断。我要记录今天腰痛",
            (("save", "clinician"), ("save", "user")),
        ),
        (
            "医生说要保存诊断。请帮我记录今天腰痛",
            (("save", "clinician"), ("save", "user")),
        ),
    ),
)
def test_explicit_user_subject_or_hard_reset_ends_report_scope(
    text,
    expected,
):
    parsed = parse_action_evidence(text)

    assert tuple(
        (action.action, action.actor)
        for action in parsed.actions
    ) == expected


@pytest.mark.parametrize(
    ("text", "expected_action", "expected_polarity", "expected_modality"),
    (
        (
            "根据医生建议不要再删除用药记录",
            "delete",
            "negative",
            "command",
        ),
        (
            "删除用药记录吗？",
            "delete",
            "positive",
            "question",
        ),
        (
            "你觉得要不要帮我删除用药记录",
            "delete",
            "positive",
            "question",
        ),
        (
            "不要帮我删除用药记录",
            "delete",
            "negative",
            "command",
        ),
        (
            "不再保存诊断",
            "save",
            "negative",
            "command",
        ),
        (
            "不要删除用药记录吗？",
            "delete",
            "negative",
            "question",
        ),
    ),
)
def test_occurrence_scope_resolves_negation_and_question_with_fillers(
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


def test_question_scope_applies_to_all_actions_in_the_question():
    text = "是否需要删除用药记录并保存诊断？"

    parsed = parse_action_evidence(text)

    assert tuple(action.action for action in parsed.actions) == (
        "delete",
        "save",
    )
    assert all(action.modality == "question" for action in parsed.actions)
    assert all(action.polarity == "positive" for action in parsed.actions)


@pytest.mark.parametrize(
    ("text", "expected_actions"),
    (
        (
            "根据医生建议我已经记录了今天腰痛",
            ("save",),
        ),
        (
            "我刚刚删除了用药记录，医生说这样可以",
            ("delete",),
        ),
        (
            "根据医生建议查看已经删除的用药记录",
            ("read", "delete"),
        ),
        (
            "根据医生建议查看需要保存的诊断记录",
            ("read", "save"),
        ),
        (
            "我昨天记录过腰痛",
            ("save",),
        ),
    ),
)
def test_completed_and_relative_actions_are_statements(
    text,
    expected_actions,
):
    parsed = parse_action_evidence(text)

    assert tuple(action.action for action in parsed.actions) == expected_actions
    assert parsed.actions[-1].modality == "statement"


@pytest.mark.parametrize(
    ("text", "expected_target"),
    (
        ("根据医生建议查看已经删除的用药记录", "medication"),
        ("根据医生建议查看需要保存的诊断记录", "clinician_record"),
    ),
)
def test_outer_read_and_relative_action_share_the_governed_target(
    text,
    expected_target,
):
    parsed = parse_action_evidence(text)

    assert tuple(action.target for action in parsed.actions) == (
        expected_target,
        expected_target,
    )


@pytest.mark.parametrize(
    ("target_text", "expected_target"),
    (
        ("饮食记录", "diet"),
        ("旧记录", "health_record"),
        ("疼痛记录", "symptom"),
        ("运动记录", "health_record"),
        ("体重记录", "weight"),
    ),
)
def test_open_record_noun_target_does_not_create_save_action(
    target_text,
    expected_target,
):
    text = f"根据医生建议查看{target_text}"

    parsed = parse_action_evidence(text)

    assert tuple(action.action for action in parsed.actions) == ("read",)
    assert parsed.actions[0].target == expected_target


@pytest.mark.parametrize(
    ("text", "expected_target"),
    (
        ("记录饮食", "diet"),
        ("记录体重", "weight"),
    ),
)
def test_record_before_health_object_remains_a_save_action(
    text,
    expected_target,
):
    parsed = parse_action_evidence(text)

    assert len(parsed.actions) == 1
    assert parsed.actions[0].action == "save"
    assert parsed.actions[0].target == expected_target


def test_create_without_a_known_target_fails_closed():
    parsed = parse_action_evidence("请创建一个东西")

    assert parsed.actions == ()


@pytest.mark.parametrize(
    ("text", "expected_action", "expected_target"),
    (
        ("用药记录和诊断记录都删除", "delete", "unknown"),
        (
            "删除根据医生诊断生成的用药记录",
            "delete",
            "medication",
        ),
        (
            "根据医生建议查看饮食记录",
            "read",
            "diet",
        ),
    ),
)
def test_target_scope_prefers_governed_target_or_fails_closed_on_conflict(
    text,
    expected_action,
    expected_target,
):
    parsed = parse_action_evidence(text)

    assert len(parsed.actions) == 1
    assert parsed.actions[0].action == expected_action
    assert parsed.actions[0].target == expected_target


def test_classifier_and_action_evidence_share_one_intent_lexicon():
    shared_names = (
        "QUESTION_SIGNALS",
        "WRITE_ACTIONS",
        "WRITE_NEGATIONS",
        "WRITE_NEGATION_EXCEPTIONS",
        "MUTATE_ACTIONS",
        "MUTATION_NEGATIONS",
        "MUTATION_NEGATION_EXCEPTIONS",
        "MEDIA_TERMS",
        "MEDIA_CREATE_ACTIONS",
        "PLAN_TERMS",
        "PLAN_CREATE_ACTIONS",
        "PLAN_UPDATE_ACTIONS",
        "REMINDER_TERMS",
        "REMINDER_CREATE_ACTIONS",
        "CLINICIAN_CONTEXT_WRITE_ACTIONS",
    )
    classifier_source = getsource(utterance_intent_classifier)
    for name in shared_names:
        assert getattr(utterance_intent_classifier, name) is getattr(
            lexicon,
            name,
        )
        assert f"\n{name} =" not in classifier_source

    action_verbs = {
        verb
        for verb, _ in utterance_action_evidence._ACTION_VOCABULARY
    }
    assert action_verbs == {
        row.surface for row in lexicon.EVIDENCE_ACTION_LEXICON
    }

    assert {
        "不需要",
        "暂不",
        "不能",
        "不可",
        "禁止",
        "避免",
    } <= {cue.surface for cue in lexicon.EVIDENCE_NEGATION_CUES}
    assert {
        "能否",
        "可不可以",
        "是不是",
        "怎么",
        "吗",
        "是否",
    } <= {cue.surface for cue in lexicon.EVIDENCE_QUESTION_CUES}


@pytest.mark.parametrize(
    "text",
    (
        "根据医生建议「请删除用药记录」",
        "依据医生诊断：“请保存诊断记录”",
        "按照医生认为‘请同步健康数据’",
        '根据医生判断"请调整用药剂量"',
    ),
)
def test_quoted_clinician_report_overrides_basis_relation(text):
    parsed = parse_action_evidence(text)

    assert len(parsed.actions) == 1
    assert parsed.actions[0].actor == "clinician"
    assert parsed.actions[0].provenance == "clinician_reported_action"


def test_question_particle_does_not_match_inside_declarative_word():
    parsed = parse_action_evidence("删除那么多用药记录")

    assert len(parsed.actions) == 1
    assert parsed.actions[0].modality == "command"


def test_prefix_question_cue_after_action_does_not_retroactively_scope_it():
    parsed = parse_action_evidence("删除用药记录后怎么处理")

    assert tuple(action.modality for action in parsed.actions) == (
        "command",
    )


@pytest.mark.parametrize(
    ("text", "expected_polarities", "expected_modalities"),
    (
        (
            "不要删除或保存任何用药记录",
            ("negative", "negative"),
            ("command", "command"),
        ),
        (
            "是否需要删除并保存用药记录",
            ("positive", "positive"),
            ("question", "question"),
        ),
        (
            "是否删除用药记录，但我想保存诊断记录",
            ("positive", "positive"),
            ("question", "command"),
        ),
        (
            "我已经删除旧记录，现在我要保存诊断记录",
            ("positive", "positive"),
            ("statement", "command"),
        ),
    ),
)
def test_each_occurrence_has_its_own_polarity_and_modality_scope(
    text,
    expected_polarities,
    expected_modalities,
):
    parsed = parse_action_evidence(text)

    assert tuple(action.polarity for action in parsed.actions) == (
        expected_polarities
    )
    assert tuple(action.modality for action in parsed.actions) == (
        expected_modalities
    )


@pytest.mark.parametrize(
    "text",
    (
        "我已删除用药记录",
        "我已经删除用药记录",
        "我刚删除了用药记录",
        "我刚刚删除了用药记录",
        "我刚才删除了用药记录",
        "我早就删除了用药记录",
        "我之前删除过用药记录",
        "我曾经删除过用药记录",
        "我删除了用药记录",
        "我删除过用药记录",
    ),
)
def test_completed_aspect_actions_default_to_statement(text):
    parsed = parse_action_evidence(text)

    assert len(parsed.actions) == 1
    assert parsed.actions[0].modality == "statement"


@pytest.mark.parametrize(
    ("text", "inner_action"),
    (
        ("查看删除后的用药记录", "delete"),
        ("保存调整后的用药剂量", "update"),
        ("分析更新后的用药记录", "update"),
        ("查看删除过的用药记录", "delete"),
    ),
)
def test_relative_action_occurrence_is_statement(text, inner_action):
    parsed = parse_action_evidence(text)

    inner = next(action for action in parsed.actions if action.action == inner_action)
    assert inner.modality == "statement"


@pytest.mark.parametrize(
    ("text", "expected_action", "expected_target"),
    (
        ("把饮食记录保存下来", "save", "diet"),
        ("把诊断记录存下来", "save", "clinician_record"),
        ("把运动记录删除", "delete", "health_record"),
        ("查看疼痛记录", "read", "symptom"),
    ),
)
def test_structural_record_noun_is_not_an_extra_save_occurrence(
    text,
    expected_action,
    expected_target,
):
    parsed = parse_action_evidence(text)

    assert len(parsed.actions) == 1
    assert parsed.actions[0].action == expected_action
    assert parsed.actions[0].target == expected_target


def test_basis_modifier_excludes_all_nested_targets_before_resolution():
    parsed = parse_action_evidence(
        "删除根据医生对用药的建议形成的诊断记录"
    )

    assert len(parsed.actions) == 1
    assert parsed.actions[0].action == "delete"
    assert parsed.actions[0].target == "clinician_record"


def test_occurrence_extractor_preserves_task_1a_raw_spans():
    source = getsource(utterance_action_evidence)

    assert "enumerate(raw_candidates)" in source
    assert "enumerate(resolved_candidates)" in source
    assert ".index(" not in source

    text = "医生说请删除用药记录，然后我想保存诊断记录"
    parsed = parse_action_evidence(text)
    assert tuple(text[action.start : action.end] for action in parsed.actions) == (
        "删除",
        "保存",
    )


def test_structured_action_candidates_exactly_cover_shared_lexicon():
    rows = lexicon.EVIDENCE_ACTION_LEXICON
    expected_surfaces = {row.surface for row in rows}
    actual_surfaces = {
        surface
        for surface, _allowed_families in utterance_action_evidence._ACTION_VOCABULARY
    }

    assert actual_surfaces == expected_surfaces
    assert set(lexicon.READ_ACTIONS) <= expected_surfaces
    assert all(row.allowed_families for row in rows)


def test_structured_create_lexicon_conserves_each_allowed_family():
    target_by_family = {
        "media": "康复图片",
        "plan": "康复计划",
        "reminder": "复查提醒",
    }
    create_families = frozenset(target_by_family)

    for row in lexicon.EVIDENCE_ACTION_LEXICON:
        allowed_create_families = row.allowed_families & create_families
        if not allowed_create_families:
            continue
        for family in allowed_create_families:
            parsed = parse_action_evidence(
                f"请{row.surface}{target_by_family[family]}"
            )
            assert tuple(
                (action.action, action.target)
                for action in parsed.actions
            ) == ((family, family),)


def test_structured_create_lexicon_rejects_every_unlisted_family():
    target_by_family = {
        "media": "康复图片",
        "plan": "康复计划",
        "reminder": "复查提醒",
    }
    create_families = frozenset(target_by_family)

    for row in lexicon.EVIDENCE_ACTION_LEXICON:
        allowed_create_families = row.allowed_families & create_families
        if not allowed_create_families:
            continue
        for family in create_families - allowed_create_families:
            parsed = parse_action_evidence(
                f"请{row.surface}{target_by_family[family]}"
            )
            assert parsed.actions == (), (
                row.surface,
                family,
                parsed.actions,
            )


@pytest.mark.parametrize(
    ("text", "expected"),
    (
        ("保存康复计划", (("保存", "plan"),)),
        ("保存诊断记录", (("保存", "save"),)),
        ("生成康复图片", (("生成", "media"),)),
        ("生成康复计划", (("生成", "plan"),)),
        ("生成复查提醒", ()),
        ("设置康复计划", ()),
        ("制作复查提醒", ()),
        ("创建康复图片", ()),
    ),
)
def test_create_family_overlap_is_constrained_and_cannot_be_laundered(
    text,
    expected,
):
    parsed = parse_action_evidence(text)

    assert tuple(
        (text[action.start : action.end], action.action)
        for action in parsed.actions
    ) == expected


@pytest.mark.parametrize(
    "text",
    (
        "保存康复图片和康复计划",
        "保存复查提醒和诊断记录",
    ),
)
def test_conflicting_create_targets_cannot_fall_back_to_save(text):
    parsed = parse_action_evidence(text)

    assert parsed.actions == ()


def test_plan_update_actions_are_complete_shared_longest_match_rows():
    rows_by_surface = {
        row.surface: row for row in lexicon.EVIDENCE_ACTION_LEXICON
    }

    for surface in lexicon.PLAN_UPDATE_ACTIONS:
        row = rows_by_surface[surface]
        assert "plan" in row.allowed_families
        target = "" if "计划" in surface else "康复计划"
        text = f"请{surface}{target}"
        parsed = parse_action_evidence(text)
        assert tuple(
            (text[action.start : action.end], action.action, action.target)
            for action in parsed.actions
        ) == ((surface, "plan", "plan"),), (surface, parsed.actions)


def test_actor_scope_transitions_require_shared_strict_user_cues():
    for transition in lexicon.EVIDENCE_ACTOR_TRANSITION_CUES:
        for cue in lexicon.EVIDENCE_STRICT_USER_COMMAND_CUES:
            text = (
                f"医生说要保存诊断{transition.surface}"
                f"{cue.surface}记录今天腰痛6分"
            )
            parsed = parse_action_evidence(text)
            assert tuple(action.actor for action in parsed.actions) == (
                "clinician",
                "user",
            ), (transition, cue, parsed.actions)


def test_hard_boundary_transitions_require_shared_strict_user_cues():
    for boundary in lexicon.EVIDENCE_HARD_BOUNDARIES:
        for cue in lexicon.EVIDENCE_STRICT_USER_COMMAND_CUES:
            text = (
                f"医生说要保存诊断{boundary.surface}"
                f"{cue.surface}记录今天腰痛6分"
            )
            parsed = parse_action_evidence(text)
            assert tuple(action.actor for action in parsed.actions) == (
                "clinician",
                "user",
            ), (boundary, cue, parsed.actions)


def test_provider_owned_quote_has_priority_over_every_user_command_cue():
    for quote in lexicon.EVIDENCE_QUOTE_PAIRS:
        for cue in (
            *lexicon.EVIDENCE_STRICT_USER_COMMAND_CUES,
            *lexicon.EVIDENCE_USER_SUBJECT_CUES,
        ):
            text = (
                f"医生说{quote.opener}{cue.surface}记录腰痛"
                f"{quote.closer}"
            )
            parsed = parse_action_evidence(text)
            assert tuple(action.actor for action in parsed.actions) == (
                "clinician",
            ), (quote, cue, parsed.actions)


@pytest.mark.parametrize(
    "text",
    (
        "医生说要保存诊断。但我想「记录腰痛」",
        "医生说要保存诊断。请「记录腰痛」",
    ),
)
def test_hard_boundary_user_reset_owns_following_quote(text):
    parsed = parse_action_evidence(text)

    assert tuple(action.actor for action in parsed.actions) == (
        "clinician",
        "user",
    )


@pytest.mark.parametrize(
    "text",
    (
        "医生说要保存诊断但请「记录腰痛」",
        "医生说要保存诊断然后帮我“记录腰痛”",
        "医生说要保存诊断接着我想‘记录腰痛’",
    ),
)
def test_top_level_transition_user_reset_owns_following_quote(text):
    parsed = parse_action_evidence(text)

    assert tuple(action.actor for action in parsed.actions) == (
        "clinician",
        "user",
    )


def test_quote_internal_user_cues_do_not_reset_consumed_report_scope():
    for quote in lexicon.EVIDENCE_QUOTE_PAIRS:
        for cue in (
            *lexicon.EVIDENCE_STRICT_USER_COMMAND_CUES,
            *lexicon.EVIDENCE_USER_SUBJECT_CUES,
        ):
            text = (
                f"医生说要保存诊断但{quote.opener}"
                f"{cue.surface}记录腰痛{quote.closer}"
            )
            parsed = parse_action_evidence(text)
            assert tuple(action.actor for action in parsed.actions) == (
                "clinician",
                "clinician",
            ), (quote, cue, parsed.actions)


@pytest.mark.parametrize(
    ("text", "expected"),
    (
        (
            "医生说要保存诊断但请记录今天腰痛6分",
            (("保存", "clinician"), ("记录", "user")),
        ),
        (
            "医生说要删除用药记录然后请记录今天腰痛6分",
            (("删除", "clinician"), ("记录", "user")),
        ),
        ("医生说请记录腰痛", (("记录", "clinician"),)),
        (
            "医生说要删除并保存记录",
            (("删除", "clinician"), ("保存", "clinician")),
        ),
        (
            "医生说要保存诊断但「请记录腰痛」",
            (("保存", "clinician"), ("记录", "clinician")),
        ),
        (
            "医生说要保存诊断。请记录腰痛",
            (("保存", "clinician"), ("记录", "user")),
        ),
        (
            "医生说要保存诊断但我想记录腰痛",
            (("保存", "clinician"), ("记录", "user")),
        ),
    ),
)
def test_linear_actor_scope_assigns_each_action_once(text, expected):
    parsed = parse_action_evidence(text)

    assert tuple(
        (text[action.start : action.end], action.actor)
        for action in parsed.actions
    ) == expected


def test_rejected_family_candidate_cannot_open_a_user_scope_transition():
    text = "医生说要生成复查提醒但请记录腰痛"

    parsed = parse_action_evidence(text)

    assert tuple(
        (text[action.start : action.end], action.actor)
        for action in parsed.actions
    ) == (("记录", "clinician"),)


def test_negation_exceptions_are_driven_by_shared_positioned_cues():
    for cue in lexicon.EVIDENCE_NEGATION_EXCEPTION_CUES:
        parsed = parse_action_evidence(f"{cue.surface}删除用药记录")
        assert tuple(action.polarity for action in parsed.actions) == (
            "positive",
        ), cue
