from dataclasses import FrozenInstanceError
import importlib
import inspect
import json
from pathlib import Path

import pytest


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "clinician_provenance_guard_safety_cases.json"
)
PROVIDERS = {
    "医生",
    "医师",
    "大夫",
    "主治医生",
    "康复师",
    "物理治疗师",
}


def _module():
    try:
        return importlib.import_module(
            "app.services.clinician_provenance_guard"
        )
    except ModuleNotFoundError:
        pytest.fail("clinician_provenance_guard is not implemented yet")


def _slice(raw, start, end):
    if start is None or end is None:
        assert start is end is None
        return None
    return raw[start:end]


def _cases():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", _cases(), ids=lambda row: row["id"])
def test_fixed_safety_corpus(case):
    guard = _module()

    decision = guard.classify_clinician_turn(case["text"])

    assert decision.raw == case["text"]
    assert decision.kind == case["kind"]
    assert decision.reason_code == case["reason_code"]
    assert decision.authorizes_feedback_write is (
        case["kind"] == "explicit_doctor_feedback_write"
    )
    assert _slice(
        decision.raw,
        decision.provider_start,
        decision.provider_end,
    ) == case.get("provider")
    assert _slice(
        decision.raw,
        decision.content_start,
        decision.content_end,
    ) == case.get("content")
    assert _slice(
        decision.raw,
        decision.command_start,
        decision.command_end,
    ) == case.get("command")


def test_decision_is_frozen_and_only_explicit_kind_authorizes():
    guard = _module()
    explicit = guard.classify_clinician_turn(
        "请记录医生诊断：臀肌无力"
    )
    context = guard.classify_clinician_turn("医生说是臀肌无力")

    with pytest.raises(FrozenInstanceError):
        explicit.kind = "none"
    assert explicit.authorizes_feedback_write is True
    assert context.authorizes_feedback_write is False


@pytest.mark.parametrize(
    "text",
    (
        "查看医生告知记录",
        "医生告知记录",
        "家属向医生告知病情",
        "医生的广告知名度很高",
        "查看医生报告知情同意记录",
        "医生告知的记录",
        "医生告知的报告",
        "医生的告知内容",
        "医生的告知事项",
        "医生的告知信息",
        "医生的告知结果",
        "医生的告知证明",
        "医生的告知通知",
        "医生的告知单",
        "医生告知 ​的内容",
    ),
)
def test_false_notification_shapes_are_not_clinician_reports(text):
    guard = _module()
    segment = guard._Span(0, len(text))

    assert guard._find_report(text, segment, 0) is None
    decision = guard.classify_clinician_turn(text)
    assert decision.kind == "none"
    assert decision.authorizes_feedback_write is False
    assert _slice(
        decision.raw,
        decision.provider_start,
        decision.provider_end,
    ) == "医生"
    assert decision.content_start is None
    assert decision.content_end is None
    assert decision.command_start is None
    assert decision.command_end is None


@pytest.mark.parametrize(
    ("text", "provider", "content"),
    (
        ("大夫告知是臀肌无力导致腰痛", "大夫", "臀肌无力导致腰痛"),
        ("医生告知是臀肌无力导致腰痛", "医生", "臀肌无力导致腰痛"),
        ("医生告知的是臀肌无力导致腰痛", "医生", "臀肌无力导致腰痛"),
        ("大夫告知的为腰肌劳损", "大夫", "腰肌劳损"),
        (
            "医生告知 ​的 ⁠是 ​臀肌无力导致腰痛",
            "医生",
            "臀肌无力导致腰痛",
        ),
        ("大夫告知⁠的 ​为⁠ 腰肌劳损", "大夫", "腰肌劳损"),
        ("医生告知臀肌无力", "医生", "臀肌无力"),
    ),
)
def test_notification_reports_pin_provider_and_predicate_spans(
    text,
    provider,
    content,
):
    guard = _module()
    segment = guard._segments(text)[0]

    report = guard._find_report(text, segment, 0)

    assert report is not None
    assert text[report.provider.start : report.provider.end] == provider
    predicate = getattr(report, "predicate", None)
    assert predicate is not None
    assert text[predicate.start : predicate.end] == "告知"
    assert report.content is not None
    assert text[report.content.start : report.content.end] == content


def test_notification_diagnosis_question_is_advice_not_a_report():
    guard = _module()
    text = "大夫告知的诊断靠谱吗？"
    segment = guard._segments(text)[0]

    assert guard._find_report(text, segment, 0) is None
    decision = guard.classify_clinician_turn(text)
    assert decision.kind == "clinician_advice"
    assert decision.reason_code == "clinician_question"
    assert _slice(
        decision.raw,
        decision.provider_start,
        decision.provider_end,
    ) == "大夫"
    assert decision.content_start is None
    assert decision.content_end is None
    assert decision.command_start is None
    assert decision.command_end is None


def test_non_writes_never_expose_an_authorizing_command_span():
    guard = _module()

    for case in _cases():
        decision = guard.classify_clinician_turn(case["text"])
        if case["kind"] != "explicit_doctor_feedback_write":
            assert decision.command_start is None
            assert decision.command_end is None


def test_provider_vocabulary_is_covered_by_handwritten_corpus():
    covered = {case.get("provider") for case in _cases()}

    assert PROVIDERS <= covered


def test_guard_is_deterministic_and_does_not_use_regex_or_llm():
    guard = _module()
    source = inspect.getsource(guard)
    text = "医生说是臀肌无力。请记录医生诊断：臀肌无力"

    assert guard.classify_clinician_turn(text) == guard.classify_clinician_turn(
        text
    )
    assert "import re" not in source
    assert "re.compile" not in source
    assert "llm" not in source.lower()


def test_guard_does_not_grow_a_general_action_taxonomy():
    guard = _module()
    source = inspect.getsource(guard)

    for forbidden in (
        "ActionKind",
        "delete_actions",
        "update_actions",
        "sync_actions",
        "plan_actions",
        "reminder_actions",
        "media_actions",
    ):
        assert forbidden not in source


def test_guard_deny_roots_cover_shared_legacy_action_lexicon():
    guard = _module()
    lexicon = importlib.import_module(
        "app.services.utterance_intent_lexicon"
    )
    expected = {
        *lexicon.READ_ACTIONS,
        *lexicon.WRITE_ACTIONS,
        *lexicon.MEDIA_CREATE_ACTIONS,
        *lexicon.PLAN_CREATE_ACTIONS,
        *lexicon.PLAN_UPDATE_ACTIONS,
        *lexicon.REMINDER_CREATE_ACTIONS,
        *lexicon.CLINICIAN_CONTEXT_WRITE_ACTIONS,
        *(
            root
            for roots in lexicon.MUTATE_ACTIONS.values()
            for root in roots
        ),
    }

    assert expected <= set(guard._DENY_ONLY_ACTION_ROOTS)


@pytest.mark.parametrize(
    ("kind", "reason_code"),
    (
        ("unknown", "no_clinician_signal"),
        ("explicit_doctor_feedback_write", "clinician_report"),
        ("clinician_context", "explicit_feedback_write"),
        ("none", "coordinated_clinician_action"),
    ),
)
def test_decision_rejects_invalid_kind_reason_combinations(
    kind,
    reason_code,
):
    guard = _module()

    with pytest.raises(ValueError, match="kind|reason"):
        guard.ClinicianTurnDecision(
            raw="",
            kind=kind,
            provider_start=None,
            provider_end=None,
            content_start=None,
            content_end=None,
            command_start=None,
            command_end=None,
            reason_code=reason_code,
        )


@pytest.mark.parametrize(
    "offsets",
    (
        {
            "provider_start": 8,
            "provider_end": 10,
            "content_start": 12,
            "content_end": 16,
            "command_start": 0,
            "command_end": 7,
        },
        {
            "provider_start": 3,
            "provider_end": 5,
            "content_start": 0,
            "content_end": 2,
            "command_start": 2,
            "command_end": 7,
        },
        {
            "provider_start": 3,
            "provider_end": 5,
            "content_start": 4,
            "content_end": 8,
            "command_start": 0,
            "command_end": 7,
        },
    ),
)
def test_explicit_decision_rejects_invalid_span_relationships(offsets):
    guard = _module()

    with pytest.raises(ValueError, match="provider|command|content|span"):
        guard.ClinicianTurnDecision(
            raw="请记录医生诊断：臀肌无力",
            kind="explicit_doctor_feedback_write",
            reason_code="explicit_feedback_write",
            **offsets,
        )
