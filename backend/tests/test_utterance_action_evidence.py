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
    assert parsed.actions == ()


@pytest.mark.parametrize(
    "text",
    (
        "医生说腰痛，：\n主治医生认为臀肌无力！：大夫建议复诊",
        "医生说腰痛,\n康复师认为臀肌无力!:理疗师建议复诊",
        "医生说腰痛康复师认为臀肌无力物理治疗师建议复诊",
    ),
)
def test_scanner_keeps_provider_offsets_across_delimiters_and_connections(text):
    parsed = parse_action_evidence(text)

    assert parsed.text == text
    assert tuple(
        text[evidence.start : evidence.end] for evidence in parsed.providers
    ) == tuple(evidence.provider for evidence in parsed.providers)
    assert tuple(evidence.start for evidence in parsed.providers) == tuple(
        sorted(evidence.start for evidence in parsed.providers)
    )
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


@pytest.mark.parametrize(
    "text",
    (
        "医生",
        "医生建议记录疼痛",
        "主治医生要求删除诊断记录",
    ),
)
def test_provider_evidence_is_independent_of_known_action_words(text):
    parsed = parse_action_evidence(text)

    assert parsed.clinician_bearing is True
    assert parsed.providers
    assert parsed.actions == ()


def test_non_clinician_text_has_no_provider_evidence():
    text = "请记录今天午餐吃了牛肉面"

    assert parse_action_evidence(text) == EvidenceParse(
        text=text,
        clinician_bearing=False,
        providers=(),
        actions=(),
    )


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
