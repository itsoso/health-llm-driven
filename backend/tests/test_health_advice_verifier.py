from datetime import date

import pytest

from app.services.advice_guard import AdviceCandidate, AdviceGuard
from app.services.health_advice_verifier import verify_advice


def _candidate(**overrides) -> AdviceCandidate:
    base = {
        "user_id": 3,
        "source": "agent",
        "source_id": "chat:1",
        "domain": "sleep",
        "title": "下午咖啡因截止",
        "body": "今天 14:00 后不摄入咖啡因，连续 7 天观察入睡潜伏期。",
        "metric_key": "sleep_latency_minutes",
        "target_value": "decrease",
        "evidence_tier": "strong_behavioral",
        "confidence": "medium",
        "claim_boundary": "这是睡眠行为建议，不用于诊断睡眠障碍。",
        "valid_for_date": date(2026, 5, 20),
        "verification_metric": "sleep_latency_minutes",
        "verification_window_days": 7,
        "evidence_refs": ["claim:c_sleep_caffeine_boundary"],
        "evidence_source_types": ["guideline"],
    }
    base.update(overrides)
    return AdviceCandidate(**base)


def test_verifier_blocks_supplement_advice_without_evidence_or_metric():
    result = verify_advice(
        _candidate(
            domain="supplement",
            title="补充 5-MTHF",
            body="你可以开始补充 5-MTHF。",
            evidence_refs=[],
            evidence_source_types=[],
            verification_metric=None,
            verification_window_days=None,
        ),
        evidence_resolution={"evidence_refs": [], "support_status": "model_inference"},
        personal_matrix={},
        contraindications=[],
    )

    assert result.allowed is False
    assert result.decision == "blocked"
    assert result.reason == "high_risk_missing_evidence"
    assert "verification_metric" in result.required_changes


def test_verifier_blocks_pgx_medication_advice_without_guideline_source():
    result = verify_advice(
        _candidate(
            domain="supplement",
            title="CYP2C19 用药建议",
            body="根据你的 CYP2C19 结果调整用药。",
            evidence_refs=["claim:c_cyp2c19_boundary"],
            evidence_source_types=["dedao", "pubmed"],
            verification_metric="doctor_review",
            verification_window_days=14,
        ),
        evidence_resolution={"evidence_refs": ["claim:c_cyp2c19_boundary"]},
        personal_matrix={"signals": [{"signal_type": "genetics", "signal_id": "gene:CYP2C19"}]},
        contraindications=[],
    )

    assert result.allowed is False
    assert result.reason == "pgx_medication_requires_guideline"


def test_verifier_downgrades_low_risk_sleep_advice_without_external_evidence():
    result = verify_advice(
        _candidate(evidence_refs=[], evidence_source_types=[]),
        evidence_resolution={"evidence_refs": [], "support_status": "model_inference"},
        personal_matrix={},
        contraindications=[],
    )

    assert result.allowed is True
    assert result.decision == "downgraded"
    assert result.reason == "low_risk_missing_external_evidence"
    assert "model_inference" in result.audit_tags


def test_verifier_blocks_movement_intensity_increase_when_contraindicated():
    result = verify_advice(
        _candidate(
            domain="movement",
            title="提高运动强度",
            target_value="increase_intensity",
            evidence_tier="wearable_proxy",
        ),
        evidence_resolution={"evidence_refs": ["claim:c_activity_guideline"]},
        personal_matrix={},
        contraindications=[
            {
                "contraindication_id": "contra:training:low_recovery_high_intensity",
                "blocks": ["increase_intensity", "protocol:movement:hiit"],
                "severity": "moderate",
            }
        ],
    )

    assert result.allowed is False
    assert result.reason == "contraindicated"
    assert result.audit_tags == ["contra:training:low_recovery_high_intensity"]


def test_verifier_blocks_paid_source_leakage_markers():
    result = verify_advice(
        _candidate(
            body="课程原文：这一讲我们完整展开以下付费课程正文内容……" + "得到" * 120,
        ),
        evidence_resolution={"evidence_refs": ["claim:c_sleep_caffeine_boundary"]},
        personal_matrix={},
        contraindications=[],
    )

    assert result.allowed is False
    assert result.reason == "paid_content_leakage"


def test_verifier_blocks_epigenetic_short_term_antiaging_overclaim():
    result = verify_advice(
        _candidate(
            domain="recovery",
            title="甲基化抗衰已经逆转",
            body="你的甲基化报告证明这 7 天抗衰成功，生物年龄已经被逆转。",
            evidence_refs=["claim:epigenetic_proxy_boundary"],
            evidence_source_types=["pubmed"],
            verification_metric="pace_of_aging",
            verification_window_days=7,
        ),
        evidence_resolution={"evidence_refs": ["claim:epigenetic_proxy_boundary"]},
        personal_matrix={
            "signals": [
                {
                    "signal_type": "epigenetic",
                    "signal_id": "epigenetic.pace_of_aging",
                    "reliability": "experimental",
                }
            ]
        },
        contraindications=[],
    )

    assert result.allowed is False
    assert result.decision == "blocked"
    assert result.reason == "epigenetic_overclaim"
    assert "rewrite_as_long_term_proxy" in result.required_changes
    assert "epigenetic_boundary" in result.audit_tags


def test_verifier_blocks_lab_derived_diagnosis_even_with_evidence_refs():
    # HbA1c 是化验事实, 把它变成确诊结论走更精确的 lab_report_boundary
    # (医学诊断越界的化验子集), 而非泛化的 medical_boundary。拦截不减: 仍
    # allowed=False + blocked, 只是 reason/tag 更具体。
    result = verify_advice(
        _candidate(
            domain="measurement",
            risk_level="high",
            title="HbA1c 诊断结论",
            body="这次 HbA1c 已经确诊糖尿病，不需要再复查或找医生确认。",
            evidence_refs=["claim:hba1c_recheck_boundary"],
            evidence_source_types=["guideline"],
            verification_metric="hba1c_percent",
            verification_window_days=84,
        ),
        evidence_resolution={"evidence_refs": ["claim:hba1c_recheck_boundary"]},
        personal_matrix={},
        contraindications=[],
    )

    assert result.allowed is False
    assert result.reason == "lab_report_boundary_violation"
    assert "rewrite_lab_fact_without_diagnosis" in result.required_changes
    assert "lab_report_boundary" in result.audit_tags


def test_verifier_blocks_nonlab_diagnostic_overclaim_via_medical_boundary():
    # 无化验语境的纯诊断越界仍归 medical_boundary — 确保 lab_report_boundary
    # 只截走化验子集, 泛化诊断护栏的测试覆盖不丢。
    result = verify_advice(
        _candidate(
            domain="emotion",
            risk_level="high",
            title="情绪症状判断",
            body="你这些症状一定会得抑郁症，已经得了，不需要医生确认。",
            evidence_refs=["claim:mood_boundary"],
            evidence_source_types=["guideline"],
            verification_metric="mood_check",
            verification_window_days=14,
        ),
        evidence_resolution={"evidence_refs": ["claim:mood_boundary"]},
        personal_matrix={},
        contraindications=[],
    )

    assert result.allowed is False
    assert result.reason == "medical_boundary_violation"
    assert "rewrite_without_diagnosis_or_treatment" in result.required_changes
    assert "medical_boundary_violation" in result.audit_tags


def test_verifier_blocks_self_medication_change_even_with_guideline_source():
    result = verify_advice(
        _candidate(
            domain="doctor_handoff",
            title="LDL-C 与他汀调整",
            body="根据 LDL-C 偏高，今晚自行加量他汀，后面再观察。",
            evidence_refs=["claim:ldl_doctor_boundary"],
            evidence_source_types=["guideline"],
            verification_metric="doctor_review",
            verification_window_days=30,
        ),
        evidence_resolution={"evidence_refs": ["claim:ldl_doctor_boundary"]},
        personal_matrix={},
        contraindications=[],
    )

    assert result.allowed is False
    assert result.reason == "medical_boundary_violation"
    assert "remove_self_medication_change" in result.required_changes


def test_verifier_blocks_direct_medication_change_without_self_wording():
    result = verify_advice(
        _candidate(
            domain="medication",
            title="停用二甲双胍",
            body="从今天开始停用二甲双胍。",
            evidence_refs=["claim:medication_review_required"],
            evidence_source_types=["guideline"],
            verification_metric="doctor_review",
            verification_window_days=7,
        ),
        evidence_resolution={"evidence_refs": ["claim:medication_review_required"]},
        personal_matrix={},
        contraindications=[],
    )

    assert result.allowed is False
    assert result.reason == "medical_boundary_violation"
    assert "remove_self_medication_change" in result.required_changes


@pytest.mark.parametrize(
    "body",
    [
        "把二甲双胍换成格列美脲。",
        "二甲双胍改用格列美脲。",
        "把二甲双胍换为格列美脲。",
        "二甲双胍转为格列美脲。",
        "二甲双胍从每天一片改为两片。",
        "二甲双胍每天一片变成两片。",
        "二甲双胍从1片增加到2片。",
        "二甲双胍减半。",
        "不要自行停药；现在把二甲双胍减半。",
        "不要自行停药但把二甲双胍减半。",
        "不要自行停药：二甲双胍减半。",
        "不要自行停药.二甲双胍减半。",
        "如需调整剂量就把二甲双胍减半，请咨询医生。",
        "如果需要换药就改用格列美脲，请咨询医生。",
        "二甲双胍改服格列美脲。",
        "二甲双胍从半片调成一片。",
        "别再吃二甲双胍了。",
        "取消二甲双胍。",
        "停二甲双胍。",
        "二甲双胍停了。",
        "二甲双胍别吃了。",
        "二甲双胍不用吃了。",
        "把二甲双胍改吃格列美脲。",
        "把二甲双胍替成格列美脲。",
        "二甲双胍减到半片。",
        "二甲双胍从两片降到一片。",
        "如需把二甲双胍减半就执行。明天再咨询医生。",
        "如需停药就直接停。之后联系医生。",
        "不要自行做决定后把二甲双胍减半。",
        "不要自行停药，改服格列美脲。",
        "把降压药停了。",
        "降压药今天先停。",
        "二甲双胍从明天开始停了。",
        "二甲双胍明天停。",
        "把所有药从今晚开始停了。",
        "二甲双胍从明天起不吃了。",
        "明天不吃二甲双胍。",
        "从明天起不服二甲双胍。",
        "今晚不用降压药。",
        "二甲双胍明天不要吃了。",
        "二甲双胍明天减一片。",
        "二甲双胍明天少吃一片。",
        "二甲双胍明天加一片。",
        "二甲双胍明天多吃一片。",
        "明天加一片二甲双胍。",
        "停掉降糖药。",
        "把所有药都停了。",
        "如需停药就停，请咨询医生。",
        "如需停药就马上停，请咨询医生。",
        "如需停药便停下，并咨询医生。",
        "未经医生确认，把二甲双胍换成格列美脲。",
    ],
)
def test_verifier_recovers_named_medication_change_from_non_medication_domain(body):
    result = verify_advice(
        _candidate(
            domain="recovery",
            title="今天的行动",
            body=body,
            evidence_refs=["claim:medication_review_required"],
            evidence_source_types=["guideline"],
            verification_metric="doctor_review",
            verification_window_days=7,
        ),
        evidence_resolution={"evidence_refs": ["claim:medication_review_required"]},
        personal_matrix={},
        contraindications=[],
    )

    assert result.allowed is False
    assert result.reason == "medical_boundary_violation"
    assert "remove_self_medication_change" in result.required_changes


@pytest.mark.parametrize(
    "body",
    [
        "不要自行停药；如需调整剂量，请咨询医生。",
        "切勿自行停用二甲双胍，请咨询医生。",
        "严禁自行把二甲双胍减半，请咨询医生。",
        "换药前请先咨询医生。",
        "必须先咨询医生再调整剂量。",
        "不要自行停药或减半，请咨询医生。",
        "切勿自行换药或调整剂量，请咨询医生。",
        "禁止擅自停药、换药或减量，请咨询医生。",
        "请勿擅自停用或改服其他药物。",
        "不要自行停用二甲双胍或改服格列美脲。",
    ],
)
def test_verifier_allows_warning_against_self_directed_medication_change(body):
    result = verify_advice(
        _candidate(
            domain="medication",
            title="用药安全提醒",
            body=body,
            evidence_refs=["claim:medication_review_required"],
            evidence_source_types=["guideline"],
            verification_metric="doctor_review",
            verification_window_days=7,
        ),
        evidence_resolution={"evidence_refs": ["claim:medication_review_required"]},
        personal_matrix={},
        contraindications=[],
    )

    assert result.allowed is True


@pytest.mark.parametrize(
    "body",
    [
        "二甲双胍改善了血糖。",
        "二甲双胍转运机制说明。",
        "二甲双胍在体内的停留时间。",
        "服用二甲双胍期间不要吃辛辣食物。",
    ],
)
def test_verifier_allows_non_prescriptive_drug_explanation(body):
    result = verify_advice(
        _candidate(domain="medication", title="药物知识", body=body),
        evidence_resolution={"evidence_refs": ["claim:c_sleep_caffeine_boundary"]},
        personal_matrix={},
        contraindications=[],
    )

    assert result.allowed is True


@pytest.mark.parametrize(
    "body",
    [
        "停用跑步机，改为户外步行。",
        "停用睡前闹钟，改成自然唤醒。",
    ],
)
def test_verifier_does_not_treat_non_medication_stop_as_medication_change(body):
    result = verify_advice(
        _candidate(
            domain="movement",
            title="调整今天的习惯",
            body=body,
        ),
        evidence_resolution={"evidence_refs": ["claim:c_sleep_caffeine_boundary"]},
        personal_matrix={},
        contraindications=[],
    )

    assert result.allowed is True


def test_verifier_blocks_red_flag_symptom_downgrade_even_with_sleep_evidence():
    result = verify_advice(
        _candidate(
            domain="sleep",
            title="胸痛后睡眠观察",
            body="胸痛和呼吸困难先在家观察，用睡眠卫生和放松训练处理，不需要就医。",
            evidence_refs=["claim:sleep_hygiene_general"],
            evidence_source_types=["guideline"],
            verification_metric="sleep_duration_hours",
            verification_window_days=7,
        ),
        evidence_resolution={"evidence_refs": ["claim:sleep_hygiene_general"]},
        personal_matrix={},
        contraindications=[],
    )

    assert result.allowed is False
    assert result.reason == "medical_boundary_violation"
    assert "escalate_red_flag_symptoms" in result.required_changes


def test_verifier_allows_epigenetic_long_term_proxy_boundary():
    result = verify_advice(
        _candidate(
            domain="measurement",
            title="甲基化长期趋势复测",
            body="甲基化时钟只作为长期代理指标；先用 8-12 周睡眠、运动和代谢闭环，再复测趋势，不把短期变化当作确定抗衰疗效。",
            evidence_refs=["claim:epigenetic_proxy_boundary"],
            evidence_source_types=["pubmed"],
            verification_metric="pace_of_aging",
            verification_window_days=90,
        ),
        evidence_resolution={"evidence_refs": ["claim:epigenetic_proxy_boundary"]},
        personal_matrix={
            "signals": [
                {
                    "signal_type": "epigenetic",
                    "signal_id": "epigenetic.pace_of_aging",
                    "reliability": "experimental",
                }
            ]
        },
        contraindications=[],
    )

    assert result.allowed is True
    assert result.reason == "allowed"


def test_advice_guard_applies_health_verifier_for_candidate_contract():
    guard = AdviceGuard(existing=[])
    result = guard.evaluate(
        _candidate(
            domain="supplement",
            title="补充 5-MTHF",
            body="你可以开始补充 5-MTHF。",
            evidence_refs=[],
            evidence_source_types=[],
            verification_metric=None,
            verification_window_days=None,
        )
    )

    assert result.allowed is False
    assert result.reason == "high_risk_missing_evidence"
