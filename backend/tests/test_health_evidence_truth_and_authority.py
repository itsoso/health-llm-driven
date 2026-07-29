"""Truthful continuation semantics and sealed emergency authority references."""

from datetime import UTC, datetime
import json
from pathlib import Path

import pytest

import app.config as config_module
from app.agents.safety_guardian.rules.symptoms import cauda_equina_warning
from app.config import settings
from app.services.health_evidence import RiskLevel, classify_health_intent
from app.services.health_evidence.continuation import (
    parse_health_evidence_continuation,
)
from app.services.health_evidence.intent import (
    affirmed_low_back_discriminator_ids,
)
from app.twin.schema import HealthTwin, TwinMeta


def _continuation_context(discriminator_id: str) -> str:
    return json.dumps(
        {
            "health_evidence_continuation": {
                "version": "health-evidence-continuation.v1",
                "parent_intent_id": "health_advice.symptom.low_back_pain",
                "parent_message_id": 912,
                "parent_turn_id": "truthful-group-answer",
                "answers": [
                    {
                        "discriminator_id": discriminator_id,
                        "answer": "yes",
                    }
                ],
            }
        },
        ensure_ascii=False,
    )


@pytest.mark.parametrize(
    ("discriminator_id", "expected_phrase", "expected_risk"),
    [
        (
            "low_back.cauda_equina",
            "排尿困难、膀胱/肠道控制改变或会阴感觉异常中至少一项为是",
            RiskLevel.EMERGENCY,
        ),
        (
            "low_back.progressive_neurologic_deficit",
            "双腿明显或进行性麻木/无力警示线索中至少一项为是",
            RiskLevel.EMERGENCY,
        ),
        (
            "low_back.major_trauma",
            "近期严重外伤警示线索为是",
            RiskLevel.HIGH,
        ),
        (
            "low_back.systemic_red_flag",
            "发热、不明原因体重下降或癌症/严重感染史中至少一项为是",
            RiskLevel.HIGH,
        ),
    ],
)
def test_group_yes_preserves_disjunction_without_inventing_specific_facts(
    discriminator_id: str,
    expected_phrase: str,
    expected_risk: RiskLevel,
):
    parsed = parse_health_evidence_continuation(
        _continuation_context(discriminator_id)
    )

    assert parsed.continuation is not None
    canonical_query = parsed.continuation.canonical_query()
    assert expected_phrase in canonical_query
    assert "排不出尿并且会阴麻木" not in canonical_query
    assert "双腿无力" not in canonical_query
    assert "伴有高热" not in canonical_query
    assert affirmed_low_back_discriminator_ids(canonical_query) == {
        discriminator_id
    }
    assert classify_health_intent(canonical_query).risk_level == expected_risk


def test_cauda_equina_guardian_references_sealed_ng127_authority(
    monkeypatch,
):
    monkeypatch.setattr(settings, "health_evidence_runtime_enabled", True)
    twin = HealthTwin(
        meta=TwinMeta(
            user_id=1,
            generated_at=datetime(2026, 7, 29, tzinfo=UTC),
        )
    )
    twin.acute.symptom_texts_all = ["腰痛", "突然排尿困难"]

    alert = cauda_equina_warning(twin)

    assert alert is not None
    assert alert.references == [
        (
            "https://www.nice.org.uk/guidance/ng127/chapter/"
            "Recommendations-for-adults-aged-over-16"
        ),
        "https://www.nhs.uk/conditions/back-pain/",
    ]
    assert all("ng59" not in reference for reference in alert.references)


def test_runtime_flag_comment_records_actual_owner_release_boundary():
    source = Path(config_module.__file__).read_text(encoding="utf-8")
    start = source.index("# 同端健康证据运行时")
    end = source.index("health_evidence_model_id", start)
    flag_block = source[start:end]

    assert "reviewer_role=product_owner" in flag_block
    assert "T1 source boundary review" in flag_block
    assert "clinical_signoff=not_claimed" in flag_block
    assert "independent medical sign-off" not in flag_block
