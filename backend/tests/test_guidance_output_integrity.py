"""Complete safe replies must not be fragments of rejected model documents."""

from app.services.guidance_validator import enforce_medical_evidence_boundaries


def test_rejected_markdown_plan_becomes_one_complete_short_reply():
    text = (
        "## 补剂执行方案\n| 项目 | 方案 |\n| --- | --- |\n"
        "| 维生素D | 建议每天补充2000IU |\n"
        "| 维生素C | 建议每天补充1000mg |\n"
    )
    result = enforce_medical_evidence_boundaries(text)
    assert result.flagged
    assert result.violations == ["unverified_dose_action"]
    assert "2000" not in result.text and "1000" not in result.text
    assert "|" not in result.text and "##" not in result.text
    assert result.text.count("暂不提供") == 1
    assert "[该建议" not in result.text
    assert result.text.endswith("。")


def test_dose_and_false_schedule_in_same_sentence_both_remain_auditable():
    result = enforce_medical_evidence_boundaries(
        "建议每天补充维生素D2000IU，已安排复查。"
    )
    assert set(result.violations) == {
        "unverified_dose_action",
        "unverified_schedule_claim",
    }
    assert "2000" not in result.text and "已安排" not in result.text
    assert "[" not in result.text


def test_real_receipt_and_verified_facts_survive_without_model_authored_claims():
    result = enforce_medical_evidence_boundaries(
        "已为你设置复查提醒。建议每天补充维生素D2000IU。",
        verified_write_receipt=True,
        trusted_write_summary="已保存饮水记录：500毫升。",
        trusted_fact_summary="今日睡眠记录为7小时。",
    )
    assert result.flagged
    assert "已保存饮水记录：500毫升。" in result.text
    assert "今日睡眠记录为7小时。" in result.text
    assert "已为你设置" not in result.text and "2000" not in result.text


def test_receipt_boolean_cannot_attest_model_authored_completion_sentence():
    result = enforce_medical_evidence_boundaries(
        "已为你安排复查。建议每天补充维生素D2000IU。",
        verified_write_receipt=True,
    )
    assert "已为你安排" not in result.text
    assert "已保存" not in result.text


def test_unverified_write_summary_cannot_create_a_success_claim():
    result = enforce_medical_evidence_boundaries(
        "建议每天补充维生素D2000IU。",
        trusted_write_summary="已保存饮水记录。",
    )
    assert "已保存" not in result.text


def test_receipt_boolean_alone_does_not_verify_a_medical_arrangement():
    result = enforce_medical_evidence_boundaries(
        "已安排复查。", verified_write_receipt=True
    )
    assert result.flagged
    assert result.violations == ["unverified_schedule_claim"]
    assert "已安排复查" not in result.text


def test_unrelated_saved_record_does_not_verify_an_appointment():
    result = enforce_medical_evidence_boundaries(
        "已安排复查。",
        verified_write_receipt=True,
        trusted_write_summary="已保存饮水记录：500毫升。",
    )
    assert result.flagged
    assert "已安排复查" not in result.text
    assert "已保存饮水记录：500毫升。" in result.text


def test_exact_independently_verified_arrangement_is_kept():
    result = enforce_medical_evidence_boundaries(
        "已安排复查。",
        verified_write_receipt=True,
        trusted_write_summary="已安排复查。",
    )
    assert not result.flagged
    assert "已安排复查。" in result.text
