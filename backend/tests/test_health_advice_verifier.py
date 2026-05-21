from datetime import date

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
