import pytest
from app.services.guidance_validator import enforce_medical_evidence_boundaries


@pytest.mark.parametrize(
    "text",
    [
        "要评估，我需要你直接告诉我：名称 + 剂量 + 每天什么时间吃。",
        "请告诉我补剂的名称、剂量，以及每天什么时间服用。",
        "请告诉我补剂的名称、剂量和服用时间。",
    ],
)
def test_request_for_actual_regimen_is_not_a_new_prescription(text):
    assert not enforce_medical_evidence_boundaries(text).flagged


@pytest.mark.parametrize(
    "text",
    [
        "请告诉我补剂名称，然后每天服用两片。",
        "请告诉我补剂名称。每天服用两片。",
        "补剂应该每天吃两片。",
        "需要告诉医生：把补剂增加到两片。",
    ],
)
def test_request_intro_cannot_launder_a_new_regimen(text):
    assert enforce_medical_evidence_boundaries(text).flagged


@pytest.mark.parametrize(
    "text",
    [
        "我来告诉你每天什么时间服用补剂：睡前服用。",
        "请告诉我每天什么时间服用维生素，我建议早上补充。",
        "请告诉我每天什么时间服用补剂，先列出名称并核对已有的实际记录和来源，睡前服用。",
    ],
)
def test_question_cannot_hide_appended_or_assistant_authored_regimen(text):
    assert enforce_medical_evidence_boundaries(text).flagged


def test_request_to_complete_actual_record_fields_is_not_a_regimen():
    text = "建议先把补剂的真实名称 + 剂量 + 服用时间补上，饮食把三大营养素填上。"
    assert not enforce_medical_evidence_boundaries(text).flagged


@pytest.mark.parametrize(
    "text",
    [
        "补剂应该调整服用时间为睡前。",
        "建议把补剂服用时间改为睡前。",
        "请将维生素服用时间改为早上。",
        "请告诉我补剂名称，然后每天吃两片，最后什么时间服用。",
    ],
)
def test_field_nouns_or_later_questions_cannot_hide_prescription(text):
    assert enforce_medical_evidence_boundaries(text).flagged


@pytest.mark.parametrize("text", [
    "成分的功效、安全性、推荐摄入量和药物相互作用，请以美国国立医学图书馆《草药与膳食补充剂资料库》为准核对，并与医生或药师确认——我不会替你新增补剂、调整剂量或安排服用时点。",
    "请查看补充剂的名称和已有记录。",
])
def test_supplement_noun_in_information_request_is_not_an_action(text):
    assert not enforce_medical_evidence_boundaries(text).flagged


@pytest.mark.parametrize("text", [
    "请参考膳食补充剂资料库，然后每天服用两片。",
    "维生素应该每天补充。",
])
def test_supplement_noun_does_not_hide_an_actual_action(text):
    assert enforce_medical_evidence_boundaries(text).flagged
