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


@pytest.mark.parametrize("text", [
    "因此我无法还原你实际在吃的补剂方案是什么、每天吃几种、剂量多少。",
    "我不知道你每天服用多少种补剂。",
    "现有补剂记录无法确认你每次吃几粒。",
    "我不清楚你每日服用几片维生素。",
])
def test_unknown_existing_regimen_quantity_is_not_prescribed(text):
    assert not enforce_medical_evidence_boundaries(text).flagged


@pytest.mark.parametrize("text", [
    "我不知道你每天吃几种补剂，建议每天吃两片。",
    "我不知道你每天吃几种补剂但每天吃两片。",
    "补剂每天吃两片，我不清楚你每天吃几种。",
    "我无法确认你每次吃几粒补剂，所以请睡前服用。",
    "我不清楚你的补剂记录，每天服用两片。",
    "我不知道你每天吃几种补剂；每次增加到两片。",
    "我不清楚你每日服用几片维生素，不过应该每天补充。",
])
def test_unknown_regimen_object_cannot_hide_an_instruction(text):
    assert enforce_medical_evidence_boundaries(text).flagged


@pytest.mark.parametrize("text", ["每次增加到两片。", "每天减少到一粒。", "每日提高到500毫克。"])
def test_explicit_dose_change_does_not_require_repeating_medicine_name(text):
    assert enforce_medical_evidence_boundaries(text).flagged


@pytest.mark.parametrize("text", ["记录每天增加到两杯水。", "散步每日增加到十分钟。"])
def test_general_quantity_is_not_a_medicine_dose(text):
    assert not enforce_medical_evidence_boundaries(text).flagged


@pytest.mark.parametrize("text", [
    "我不知道你每天吃几种补剂。每天吃两片。",
    "我无法确认补剂数量；建议睡前服用。",
    "请睡前服用。",
    "每天吃两片。",
    "每次吃一粒即可。",
    "建议每天随餐口服。",
    "明白了。每天吃两片。",
    "明白了；每次吃一粒即可。",
    "明白了\n每天吃两片。",
])
def test_separate_or_bare_regimen_instruction_is_still_an_action(text):
    assert enforce_medical_evidence_boundaries(text).flagged


@pytest.mark.parametrize("text", [
    "每天喝两杯水。", "建议睡前散步十分钟。",
    "每天吃两片全麦面包。", "每次吃一粒葡萄。",
    "请告诉我你是否睡前服用。", "请告诉我你是否每天吃两片。",
    "请告诉我实际服用时间。", "我不知道你每天吃几种补剂。",
    "不建议睡前服用。", "不要每天吃两片。",
])
def test_bare_regimen_guard_preserves_food_information_and_negation(text):
    assert not enforce_medical_evidence_boundaries(text).flagged


@pytest.mark.parametrize("prefix", ["", "明白了。", "明白了；", "明白了\n"])
@pytest.mark.parametrize("instruction", ["每天吃500mg。", "每次吃1000 IU。", "每天 吃 500 MG。",
    "每日吃0.5毫克。", "每次吃二百微克。", "每天吃 10 iu。"])
def test_bare_regimen_mass_units_are_detected_before_sentence_checks(prefix, instruction):
    from app.services.guidance_validator import requires_medical_evidence_boundary
    assert requires_medical_evidence_boundary(prefix + instruction)
    assert enforce_medical_evidence_boundaries(prefix + instruction).flagged


@pytest.mark.parametrize("text", [
    "请告诉我你是否每天吃500mg。", "请告诉我你是否每次吃1000 IU。",
    "不要每天吃500mg。", "我不知道你每天吃多少毫克。",
])
def test_bare_mass_units_do_not_turn_questions_into_instructions(text):
    assert not enforce_medical_evidence_boundaries(text).flagged


_REGIMEN_PRESENTATION_PREFIXES = ["", "- ", "* ", "1. ", "1、", "（1）", "明白了。\n- ", "明白了；（1）"]


@pytest.mark.parametrize("prefix", _REGIMEN_PRESENTATION_PREFIXES)
@pytest.mark.parametrize("body", ["每天吃200mg。", "每天吃２００ｍｇ。", "每天吃200㎎。", "每天吃１０００ＩＵ。"])
def test_regimen_presentation_cannot_bypass_early_or_sentence_matching(prefix, body):
    from app.services.guidance_validator import requires_medical_evidence_boundary
    text = prefix + body
    assert requires_medical_evidence_boundary(text)
    result = enforce_medical_evidence_boundaries(text)
    assert result.flagged
    assert body not in result.text


@pytest.mark.parametrize("prefix", _REGIMEN_PRESENTATION_PREFIXES)
@pytest.mark.parametrize("body", [
    "请告诉我是否每天吃２００ｍｇ。", "我不知道每天吃多少毫克。",
    "每天吃两片全麦面包。", "每天喝２００ｍｌ水。", "建议睡前散步十分钟。",
    "不建议睡前服用。", "不要每天吃２００ｍｇ。",
])
def test_presentation_matching_preserves_benign_original_text(prefix, body):
    text = prefix + body
    result = enforce_medical_evidence_boundaries(text)
    assert not result.flagged
    assert text in result.text
