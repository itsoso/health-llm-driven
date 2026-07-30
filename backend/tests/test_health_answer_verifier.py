"""Deterministic final-text gate for health-evidence answers."""

import pytest

from app.services.health_evidence.verifier import verify_health_answer


BASE = {
    "risk_level": "medium",
    "sufficiency": "clarify",
    "allowed_claim_ids": {
        "claim:c_low_back_emergency_neurologic_red_flags",
        "claim:c_low_back_self_management_activity_boundary",
    },
    "authority_organizations": {"NICE", "NHS"},
    "grounded_claims": {
        "claim:c_low_back_emergency_neurologic_red_flags": (
            "腰痛合并新的膀胱或肠道功能改变、会阴感觉改变或双腿明显无力时，"
            "应立即急诊评估；这是筛查边界，不是诊断。"
        ),
        "claim:c_low_back_self_management_activity_boundary": (
            "警示征象筛查未发现异常后，可在耐受范围内维持日常活动并避免长期卧床。"
        ),
    },
    "context_categories": {"symptom", "medication"},
    "missing_discriminators": (
        {
            "id": "low_back.cauda_equina",
            "question": "是否有排尿困难、大小便失控或会阴麻木？",
            "priority": "emergency",
        },
    ),
}


def _verify(text: str, **overrides):
    return verify_health_answer(text, **{**BASE, **overrides})


def test_clarify_answer_is_deterministically_rendered_from_policy():
    result = _verify(
        "先确认是否有大小便功能改变或会阴麻木；若有请立即急诊。"
        "若没有这些警示征象，可在耐受范围内维持活动，避免长期卧床。"
        "这不是诊断，持续或加重请就医评估。"
        "依据 [claim:c_low_back_emergency_neurologic_red_flags]。"
    )

    assert result.verdict == "repair"
    assert result.reasons == ("clarification_safe_render_required",)
    assert "为了安全分流" in result.text
    assert "立即" in result.text
    assert "长期卧床" not in result.text


def test_red_flag_downgrade_is_blocked_and_replaced_before_output():
    result = _verify(
        "你有腰痛、会阴麻木和排不出尿，但先在家观察，不用就医。",
        risk_level="emergency",
        sufficiency="safe_fallback",
    )

    assert result.verdict == "block"
    assert "red_flag_downgrade" in result.reasons
    assert "立即" in result.text
    assert "先在家观察" not in result.text


def test_diagnostic_overclaim_is_blocked_but_negated_diagnostic_language_is_safe():
    blocked = _verify("这已经确诊为腰椎间盘突出，不需要医生确认。")
    safe = _verify("仅凭聊天不能确诊，也不能替代医生评估。")

    assert blocked.verdict == "block"
    assert "diagnostic_overclaim" in blocked.reasons
    assert safe.verdict in {"pass", "repair"}


def test_self_directed_medication_change_is_blocked_but_warning_is_safe():
    blocked = _verify("把止痛药加倍，并把现有处方药停掉。")
    safe = _verify("不要自行停药或加量；如需调整请先联系医生。")

    assert blocked.verdict == "block"
    assert "self_medication_change" in blocked.reasons
    assert safe.verdict in {"pass", "repair"}


@pytest.mark.parametrize(
    "answer",
    [
        "建议口服布洛芬400mg，每6小时一次。",
        "你可以开始服用布洛芬，每次400mg。",
    ],
)
def test_new_medication_or_specific_regimen_is_blocked(answer):
    result = _verify(answer)

    assert result.verdict == "block"
    assert "medication_prescribing" in result.reasons
    assert "布洛芬400mg" not in result.text


def test_medication_safety_boundary_without_a_regimen_is_not_prescribing():
    result = _verify(
        "不要自行开始、停用或调整药物；如需止痛药，请先让医生或药师结合"
        "你的过敏史和现有用药判断。"
    )

    assert "medication_prescribing" not in result.reasons


def test_safe_fallback_never_releases_arbitrary_model_treatment_text():
    result = _verify(
        "做三组高强度硬拉就能恢复。",
        sufficiency="safe_fallback",
    )

    assert result.verdict == "block"
    assert "insufficient_evidence_safe_fallback_required" in result.reasons
    assert "高强度硬拉" not in result.text
    assert "暂不提供具体治疗建议" in result.text


def test_emergency_turn_always_uses_deterministic_immediate_triage():
    result = _verify(
        "我会把这条症状记录下来。",
        risk_level="emergency",
        sufficiency="safe_fallback",
        missing_discriminators=(),
    )

    assert result.verdict == "block"
    assert "emergency_safe_fallback_required" in result.reasons
    assert "立即" in result.text
    assert "急诊" in result.text
    assert "记录下来" not in result.text


def test_high_risk_turn_uses_deterministic_urgent_evaluation():
    result = _verify(
        "可以先观察几天。",
        risk_level="high",
        sufficiency="safe_fallback",
        missing_discriminators=(),
    )

    assert result.verdict == "block"
    assert "尽快就医" in result.text
    assert "严重外伤" in result.text
    assert "高热" in result.text
    assert "先观察几天" not in result.text


@pytest.mark.parametrize(
    "answer",
    [
        "这就是腰椎间盘突出。",
        "根据欧洲脊柱学会建议卧床三天。",
        "每天做麦肯基训练20次。",
    ],
)
def test_unsupported_free_form_medical_prose_is_never_released(answer):
    result = _verify(
        answer,
        sufficiency="sufficient",
        missing_discriminators=(),
    )

    assert answer not in result.text
    assert result.verdict in {"repair", "block"}
    assert set(result.evidence_refs_used) <= set(BASE["grounded_claims"])


def test_sufficient_answer_renders_only_selected_reviewed_claim_summaries():
    result = _verify(
        "请采用该边界 [claim:c_low_back_self_management_activity_boundary]。",
        sufficiency="sufficient",
        missing_discriminators=(),
    )

    assert result.verdict == "repair"
    assert result.evidence_refs_used == (
        "claim:c_low_back_self_management_activity_boundary",
    )
    assert BASE["grounded_claims"][
        "claim:c_low_back_self_management_activity_boundary"
    ] in result.text
    assert "请采用该边界" not in result.text


def test_unapproved_claim_or_named_authority_is_blocked():
    claim = _verify("依据 [claim:c_unreviewed_course_excerpt]，建议继续锻炼。")
    authority = _verify("根据 Mayo 指南，你不需要进一步评估。")

    assert "unsupported_claim_reference" in claim.reasons
    assert "unsupported_authority_reference" in authority.reasons


@pytest.mark.parametrize(
    ("organization", "answer"),
    [
        ("World Health Organization", "WHO 指南支持该边界。"),
        ("American College of Radiology", "ACR 指南支持该边界。"),
    ],
)
def test_authority_full_names_admit_their_canonical_abbreviations(
    organization,
    answer,
):
    result = _verify(
        answer,
        authority_organizations={organization},
    )

    assert "unsupported_authority_reference" not in result.reasons


def test_lowercase_who_in_ordinary_english_is_not_an_authority_reference():
    result = _verify(
        "People who have pain may need reassessment.",
        authority_organizations={"NICE"},
    )

    assert "unsupported_authority_reference" not in result.reasons


def test_paid_text_leakage_is_blocked():
    result = _verify("下面是付费课程正文和逐字稿：第一讲……")

    assert result.verdict == "block"
    assert "paid_content_leakage" in result.reasons
    assert "逐字稿" not in result.text


def test_claiming_unselected_personal_context_is_blocked():
    result = _verify("根据你的基因结果和化验报告，你应该做这套拉伸。")

    assert result.verdict == "block"
    assert "unsupported_personal_context" in result.reasons


def test_clarify_answer_missing_follow_up_is_repaired_deterministically():
    result = _verify(
        "目前更像普通腰痛，可以先在耐受范围内活动。这不是诊断。",
    )

    assert result.verdict == "repair"
    assert "clarification_safe_render_required" in result.reasons
    assert "是否有排尿困难" in result.text
    assert result.text.count("是否有排尿困难") == 1
