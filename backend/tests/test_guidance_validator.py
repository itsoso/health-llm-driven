from app.services.guidance_validator import (
    build_confirmable_health_fact_draft,
    enforce_medical_evidence_boundaries,
    requires_medical_evidence_boundary,
)


def test_natural_health_facts_become_confirmable_draft_without_write_authority():
    draft = build_confirmable_health_fact_draft("咖啡因 180mg，昨晚 1点20 入睡")

    assert draft is not None
    assert draft["status"] == "draft"
    assert draft["requires_confirmation"] is True
    assert draft["authorized_write"] is False
    assert [fact["type"] for fact in draft["facts"]] == [
        "caffeine_intake",
        "sleep_onset",
    ]


def test_health_fact_question_is_not_diverted_into_write_draft():
    assert build_confirmable_health_fact_draft("咖啡因 180mg 会怎么影响睡眠？") is None


def test_health_fact_draft_does_not_intercept_explicit_record_command():
    assert (
        build_confirmable_health_fact_draft(
            "记录喝水500ml，记录昨晚23点入睡今天7点起床睡眠质量5分。"
        )
        is None
    )


def test_sensitive_medical_turn_requires_buffered_boundary_release():
    assert requires_medical_evidence_boundary("这个补剂剂量是否需要复查？") is True
    assert requires_medical_evidence_boundary("今天走了多少步？") is False


def test_medical_boundary_removes_unverified_dose_and_schedule_claims():
    result = enforce_medical_evidence_boundaries(
        "建议每天补充维生素D 2000IU，已经为你安排了复查。",
        evidence_sources=("健康记录",),
        verified_write_receipt=False,
    )

    assert result.flagged is True
    assert "2000IU" not in result.text
    assert "已安排" not in result.text
    assert "用户陈述" in result.text
    assert "已检索证据" in result.text
    assert "模型推断" in result.text


def test_verified_clinician_instruction_and_receipt_keep_claim_but_label_source():
    text = "医生建议每天服用药物 5mg，已安排复查。"
    result = enforce_medical_evidence_boundaries(
        text,
        has_clinician_instruction=True,
        verified_write_receipt=True,
    )

    assert result.flagged is False
    assert text in result.text
    assert "医生确认指示" in result.text
