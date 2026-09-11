"""Synthetic regression cases; no production health payloads."""

import pytest

from app.services.guidance_validator import (
    enforce_medical_evidence_boundaries,
    requires_medical_evidence_boundary,
)


@pytest.mark.parametrize("text", [
    "你的补剂方案：把鱼油增加到每天四粒。",
    "辅酶Q10：每天两粒。",
    "建议停用红景天，鱼油加倍。仅供参考，不构成医疗建议。",
    "你的MTHFR变异意味着必须吃活性叶酸。",
    "你有MTHFR变异，普通叶酸无法利用，只能补活性叶酸。",
    "REM数据缺失，推测也严重不足。",
    "你今天精神好可能是皮质醇和肾上腺素在透支。",
    "不要加量，但建议把鱼油增加到四粒。",
    "资料显示，你应该把鱼油翻倍。",
    "不要加量但是你应该把鱼油增加到四粒。",
    "建议每天服用布洛芬两片。",
    "建议每天服用合成未知名称两片。",
    "补剂方案：\n鱼油：早晚各两粒。",
    "睡眠数据缺失，所以你的REM严重不足。",
    "你的MTHFR变异使你不能利用普通叶酸。",
])
def test_known_high_risk_narrative_is_withheld_even_with_generic_citations(text):
    result = enforce_medical_evidence_boundaries(text, evidence_sources=("医学资料目录",))
    assert result.flagged
    assert text not in result.text
    assert "核验" in result.text
    # Audit data must never contain model-authored health sentences.
    assert all(":" not in reason and " " not in reason for reason in result.violations)


@pytest.mark.parametrize("text", [
    "鱼油是一类补充剂，作用和适用性需要结合具体情况讨论。",
    "不要自行增加鱼油剂量。",
    "无需因为MTHFR变异就补充活性叶酸。",
    "MTHFR变异不意味着必须吃活性叶酸。",
    "REM数据缺失，不能据此推测REM严重不足。",
    "皮质醇参与昼夜节律调节，不能据此解释你今天的状态。",
    "已记录今天服用两粒鱼油。",
    "是否需要调整补剂，请与医生核对。",
    "不建议每天服用补剂5mg。",
    "可以咨询医生是否把鱼油增加到四粒。",
    "睡眠数据缺失，所以不能判断REM是否不足。",
])
def test_education_negation_and_record_acknowledgement_are_preserved(text):
    result = enforce_medical_evidence_boundaries(text)
    assert not result.flagged
    assert text in result.text


def test_clinician_topic_classification_does_not_authorize_model_dose_advice():
    result = enforce_medical_evidence_boundaries(
        "医生建议复查。你可以把鱼油增加到每天四粒。",
        has_clinician_instruction=True,
    )
    assert result.flagged
    assert "每天四粒" not in result.text


def test_only_exact_trusted_clinician_instruction_is_preserved():
    instruction = "医生已核实：每天服用药物5mg。"
    result = enforce_medical_evidence_boundaries(
        instruction + "另外建议把鱼油增加到四粒。",
        has_clinician_instruction=True,
        trusted_clinician_instructions=(instruction,),
    )
    assert result.flagged
    assert instruction in result.text
    assert "增加到四粒" not in result.text


def test_instruction_source_cannot_authorize_changed_quantity():
    result = enforce_medical_evidence_boundaries(
        "医生已核实：每天服用药物10mg。",
        has_clinician_instruction=True,
        trusted_clinician_instructions=("医生已核实：每天服用药物5mg。",),
    )
    assert result.flagged
    assert "10mg" not in result.text


def test_trusted_instruction_does_not_prove_an_appointment_was_created():
    text = "医生已核实：每天服用药物5mg，已安排复查。"
    result = enforce_medical_evidence_boundaries(
        text,
        has_clinician_instruction=True,
        trusted_clinician_instructions=(text,),
    )
    assert result.flagged
    assert "已安排" not in result.text
    assert "5mg" in result.text


@pytest.mark.parametrize("text", ["MTHFR与叶酸怎么理解", "昨晚REM没有数据", "鱼油需要加量吗", "睡眠分数低但精神好", "建议每天服用布洛芬两片。", "每天服用合成未知名称两片。"])
def test_sensitive_topics_require_pre_stream_buffering(text):
    assert requires_medical_evidence_boundary(text)
