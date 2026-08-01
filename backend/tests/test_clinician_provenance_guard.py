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


@pytest.mark.parametrize(
    "text",
    (
        "我让医生记录每天腰痛情况",
        "家属叫医生记录每天腰痛情况",
    ),
)
def test_role_reversed_instructions_do_not_make_clinician_the_agent(text):
    guard = _module()

    decision = guard.classify_clinician_turn(text)

    assert decision.kind == "ambiguous_clinician_action"
    assert decision.reason_code == "unresolved_clinician_action"
    assert decision.authorizes_feedback_write is False
    assert decision.content_start is None
    assert decision.content_end is None
    assert decision.command_start is None
    assert decision.command_end is None


def test_bare_instruction_verbs_do_not_join_global_report_predicates():
    lexicon = importlib.import_module(
        "app.services.utterance_intent_lexicon"
    )

    assert "让" not in lexicon.CLINICIAN_REPORT_PREDICATES
    assert "叫" not in lexicon.CLINICIAN_REPORT_PREDICATES


_FAIL_CLOSED_3C_IDS = frozenset(
    {
        "user_instructs_doctor_role_reversal",
        "family_instructs_doctor_role_reversal",
        "give_doctor_record_role_reversal",
        "ask_doctor_to_record_role_reversal",
        "patient_requires_doctor_to_record_role_reversal",
        "post_report_nested_instruction_blocks_write",
        "post_report_patient_instruction_blocks_write",
        "post_report_tell_instruction_blocks_write",
        "post_report_you_instruction_blocks_write",
        "post_report_outer_recipient_instruction_blocks_write",
        "post_report_direct_action_instruction_blocks_write",
        "post_report_command_instruction_blocks_write",
        "temporarily_prefixed_negated_clinician_write",
        "now_prefixed_negated_clinician_write",
        "first_prefixed_negated_clinician_write",
        "again_wrapped_negated_clinician_write",
        "help_me_wrapped_negated_clinician_write",
        "immediately_wrapped_negated_clinician_write",
        "negated_write_without_feedback_object_is_fail_closed",
        "negated_write_with_wrong_measurement_object",
        "conflicting_double_negation_is_fail_closed",
    }
)

_OBFUSCATED_CLINICIAN_ACTION_IDS = frozenset(
    {
        "split_provider_in_negated_write",
        "split_write_root_in_negated_write",
        "split_provider_in_instruction",
        "split_write_root_in_explicit_feedback",
        "fullwidth_space_split_provider",
        "word_joiner_split_provider",
        "fullwidth_space_split_write_root",
        "word_joiner_split_write_root",
        "zero_width_space_split_feedback_object",
        "fullwidth_space_split_feedback_object",
        "duplicated_provider_does_not_mask_split_provider",
        "duplicated_root_does_not_mask_split_root",
        "duplicated_object_does_not_mask_split_object",
    }
)

_CLINICIAN_BASIS_CONTROL_IDS = frozenset(
    {
        "diagnosis_basis_delete_control",
        "opinion_basis_update_control",
        "advice_basis_sync_control",
        "spaced_clinician_basis_control",
        "conjoined_dates_remain_a_single_basis_target",
        "conjoined_nouns_remain_a_single_basis_target",
        "conjoined_objects_remain_a_single_basis_target",
        "comorbidity_record_remains_a_basis_target",
        "gender_record_remains_a_basis_target",
        "immune_plan_remains_a_basis_target",
        "invalid_record_remains_a_basis_target",
        "meal_remains_a_basis_target",
        "weight_remains_a_basis_target",
        "health_data_record_remains_a_basis_target",
        "medication_info_record_remains_a_basis_target",
        "exercise_goal_record_remains_a_basis_target",
        "heart_rate_remains_a_basis_target",
        "medication_remains_a_basis_target",
        "dose_adjustment_record_remains_a_basis_target",
        "immune_plan_execution_record_remains_a_basis_target",
        "merged_record_remains_a_basis_target",
    }
)

_INVALID_CLINICIAN_BASIS_IDS = frozenset(
    {
        "negated_clinician_basis_is_not_released",
        "second_subject_clinician_basis_is_not_released",
        "coordinated_clinician_basis_is_not_released",
        "empty_target_clinician_basis_is_not_released",
        "unable_suffix_clinician_basis_is_not_released",
        "cannot_suffix_clinician_basis_is_not_released",
        "prohibited_suffix_clinician_basis_is_not_released",
        "avoid_suffix_clinician_basis_is_not_released",
        "unknown_coordinated_verb_basis_is_not_released",
        "not_yet_authorized_basis_is_not_released",
        "not_allowed_basis_is_not_released",
        "not_possible_basis_is_not_released",
        "not_viable_basis_is_not_released",
        "without_permission_basis_is_not_released",
        "must_not_execute_basis_is_not_released",
        "should_not_execute_basis_is_not_released",
        "stop_medication_coordination_basis_is_not_released",
        "reduce_dose_coordination_basis_is_not_released",
        "switch_medication_coordination_basis_is_not_released",
        "weak_and_stop_medication_basis_is_not_released",
        "weak_with_reduce_dose_basis_is_not_released",
        "weak_also_switch_medication_basis_is_not_released",
        "weak_and_abort_medication_basis_is_not_released",
        "refuse_execution_basis_is_not_released",
        "void_basis_is_not_released",
        "known_second_root_basis_is_not_released",
        "noun_terminated_stop_plan_basis_is_not_released",
        "noun_terminated_keep_backup_basis_is_not_released",
        "noun_terminated_refusal_plan_basis_is_not_released",
        "unanchored_clinician_advice_is_not_basis_control",
    }
)


@pytest.mark.parametrize(
    "case",
    tuple(case for case in _cases() if case["id"] in _FAIL_CLOSED_3C_IDS),
    ids=lambda row: row["id"],
)
def test_fail_closed_clinician_actions_never_authorize_or_expose_command(case):
    guard = _module()

    decision = guard.classify_clinician_turn(case["text"])

    assert decision.kind != "explicit_doctor_feedback_write"
    assert decision.authorizes_feedback_write is False
    assert decision.command_start is None
    assert decision.command_end is None


@pytest.mark.parametrize(
    "case",
    tuple(
        case
        for case in _cases()
        if case["id"] in _OBFUSCATED_CLINICIAN_ACTION_IDS
    ),
    ids=lambda row: row["id"],
)
def test_obfuscated_clinician_actions_fail_closed_without_raw_spans(case):
    guard = _module()

    decision = guard.classify_clinician_turn(case["text"])

    assert decision.kind == "ambiguous_clinician_action"
    assert decision.reason_code == "obfuscated_clinician_action"
    assert decision.authorizes_feedback_write is False
    assert decision.provider_start is decision.provider_end is None
    assert decision.content_start is decision.content_end is None
    assert decision.command_start is decision.command_end is None


@pytest.mark.parametrize(
    "case",
    tuple(
        case
        for case in _cases()
        if case["id"] in _CLINICIAN_BASIS_CONTROL_IDS
    ),
    ids=lambda row: row["id"],
)
def test_clinician_basis_controls_reach_legacy_mutation(case):
    guard = _module()
    classifier = importlib.import_module(
        "app.services.utterance_intent_classifier"
    )

    decision = guard.classify_clinician_turn(case["text"])
    intent = classifier.classify_agent_utterance(case["text"])

    assert decision.kind == "none"
    assert decision.reason_code == "clinician_basis_user_action"
    assert decision.authorizes_feedback_write is False
    assert intent.primary == "mutate"
    assert intent.operation == case["public_operation"]
    assert intent.is_write is True


@pytest.mark.parametrize(
    "case",
    tuple(
        case
        for case in _cases()
        if case["id"] in _INVALID_CLINICIAN_BASIS_IDS
    ),
    ids=lambda row: row["id"],
)
def test_invalid_clinician_basis_shapes_are_never_released(case):
    guard = _module()
    classifier = importlib.import_module(
        "app.services.utterance_intent_classifier"
    )

    decision = guard.classify_clinician_turn(case["text"])
    intent = classifier.classify_agent_utterance(case["text"])

    assert decision.reason_code != "clinician_basis_user_action"
    assert decision.authorizes_feedback_write is False
    assert intent.is_write is False


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
        ("clinician_context", "clinician_instruction"),
        ("clinician_advice", "negated_clinician_action"),
        ("none", "unresolved_clinician_action"),
        ("clinician_context", "clinician_basis_user_action"),
        ("none", "obfuscated_clinician_action"),
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
