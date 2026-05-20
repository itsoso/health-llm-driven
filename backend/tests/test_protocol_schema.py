import pytest
from pydantic import ValidationError

from app.schemas.protocol import (
    Contraindication,
    EvalCaseSpec,
    ProtocolFragment,
)


def _valid_protocol_payload(**overrides):
    payload = {
        "protocol_id": "protocol:sleep:caffeine_cutoff",
        "domain": "sleep",
        "title": "下午咖啡因截止",
        "source_claims": ["claim:c_adora2a_caffeine_sleep_boundary"],
        "source_types": ["dedao", "guideline"],
        "risk_level": "low",
        "applies_when": ["twin.sleep.sleep_latency_minutes > 30"],
        "forbidden_when": [],
        "action_template": {
            "type": "behavior",
            "instruction": "今天 14:00 后不摄入咖啡因。",
        },
        "verification": {
            "metric": "sleep_latency_minutes",
            "window_days": 7,
            "expected_direction": "decrease",
        },
        "claim_boundary": "这是睡眠行为建议，不用于诊断睡眠障碍。",
    }
    payload.update(overrides)
    return payload


def test_protocol_fragment_requires_core_contract_fields():
    protocol = ProtocolFragment.model_validate(_valid_protocol_payload())

    assert protocol.protocol_id == "protocol:sleep:caffeine_cutoff"
    assert protocol.domain == "sleep"
    assert protocol.risk_level == "low"
    assert protocol.verification.metric == "sleep_latency_minutes"

    missing_verification = _valid_protocol_payload()
    missing_verification.pop("verification")
    with pytest.raises(ValidationError) as exc:
        ProtocolFragment.model_validate(missing_verification)

    assert "verification" in str(exc.value)


def test_protocol_fragment_rejects_unknown_domain_and_risk_level():
    with pytest.raises(ValidationError) as exc:
        ProtocolFragment.model_validate(_valid_protocol_payload(domain="longevity", risk_level="extreme"))

    message = str(exc.value)
    assert "domain" in message
    assert "risk_level" in message


def test_contraindication_requires_trigger_blocks_fallback_and_severity():
    contraindication = Contraindication.model_validate(
        {
            "contraindication_id": "contra:training:low_recovery_high_intensity",
            "domain": "movement",
            "severity": "moderate",
            "trigger": ["twin.recovery.hrv_status == 'low'"],
            "blocks": ["protocol:movement:hiit"],
            "fallback": ["protocol:movement:zone1_walk"],
            "reason": "恢复状态不足时，先降低训练强度。",
        }
    )

    assert contraindication.severity == "moderate"
    assert contraindication.blocks == ["protocol:movement:hiit"]

    with pytest.raises(ValidationError) as exc:
        Contraindication.model_validate(
            {
                "contraindication_id": "contra:training:low_recovery_high_intensity",
                "domain": "movement",
                "severity": "moderate",
            }
        )

    message = str(exc.value)
    assert "trigger" in message
    assert "blocks" in message
    assert "fallback" in message


def test_high_risk_eval_case_requires_must_not_include_boundaries():
    valid = EvalCaseSpec.model_validate(
        {
            "case_id": "health_advice_verify_mthfr_001",
            "domain": "supplement",
            "risk_level": "high",
            "input": {
                "user_query": "我 MTHFR TT，是不是必须吃 5-MTHF？",
                "twin": {"genetics": {"MTHFR_C677T": "TT"}},
            },
            "expected": {
                "must_include": ["建议先看同型半胱氨酸"],
                "must_not_include": ["必须吃", "每日固定剂量"],
                "required_evidence_class": ["genetics_boundary", "supplement_safety"],
            },
        }
    )

    assert valid.expected.must_not_include == ["必须吃", "每日固定剂量"]

    with pytest.raises(ValidationError) as exc:
        EvalCaseSpec.model_validate(
            {
                "case_id": "health_advice_verify_mthfr_002",
                "domain": "supplement",
                "risk_level": "high",
                "input": {"user_query": "我该怎么吃补剂？", "twin": {}},
                "expected": {"must_include": ["需要化验确认"]},
            }
        )

    assert "must_not_include" in str(exc.value)
