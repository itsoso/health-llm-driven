import pytest

from app.services.guidance_validator import (
    enforce_medical_evidence_boundaries,
    requires_medical_evidence_boundary,
)
from tests.test_agent_composed_synthesis_projection import run_projection
from tests.test_agent_read_repair_round_budget import (
    _isolate_twin_cache as _isolate_twin_cache,
    clock as clock,
    four_domain_user as four_domain_user,
    owned_data as owned_data,
)


@pytest.mark.parametrize(
    "text",
    [
        "建议后续补充：午餐/加餐、补剂准确名称/剂量/服用时间，以及睡眠入睡与醒来时间和情绪评分。",
        "请补充：补剂的真实名称、剂量、实际服用时间。",
        "请告诉我是否口服200mg。",
        "请告诉我能否口服２００ｍｇ？",
        "能否告诉我是否服用1000IU。",
        "我想确认能否口服200㎎。",
    ],
)
def test_benign_information_requests_are_byte_preserved(text):
    result = enforce_medical_evidence_boundaries(text)
    assert not result.flagged
    assert text in result.text


@pytest.mark.parametrize("separator", ["，", "。", "？", "；", "\n"])
@pytest.mark.parametrize(
    "instruction",
    [
        "口服300mg。",
        "请每天口服300mg。",
        "每天增加到400mg。",
        "每日减少到1000IU。",
        "请睡前服用。",
        "每天服用。",
    ],
)
def test_intake_question_does_not_hide_punctuated_instruction(separator, instruction):
    text = "请告诉我能否口服200mg" + separator + instruction
    result = enforce_medical_evidence_boundaries(text)
    assert requires_medical_evidence_boundary(text)
    assert result.flagged
    assert instruction not in result.text


@pytest.mark.parametrize(
    "instruction",
    [
        "然后口服300mg。",
        "然后请每天口服300mg。",
        "以及每天增加到400mg。",
        "并且每日减少到1000IU。",
        "然后请睡前服用。",
        "并每天服用。",
        "核对记录以后再口服300mg。",
        "核对记录以后再增加到400mg。",
    ],
)
def test_intake_question_does_not_hide_same_clause_instruction(instruction):
    text = "请告诉我能否口服200mg，" + instruction
    result = enforce_medical_evidence_boundaries(text)
    assert requires_medical_evidence_boundary(text)
    assert result.flagged


@pytest.mark.parametrize(
    "instruction",
    [
        "然后口服300mg。",
        "然后每天增加到400mg。",
        "并且每日减少到1000IU。",
        "然后请睡前服用。",
        "并每天服用。",
        "核对记录以后再口服300mg。",
        "核对记录以后再增加到400mg。",
    ],
)
def test_field_request_does_not_hide_same_clause_instruction(instruction):
    prefix = "建议补充：补剂名称/剂量/服用时间，"
    result = enforce_medical_evidence_boundaries(prefix + instruction)
    assert result.flagged


@pytest.mark.parametrize(
    "text",
    [
        "- 每天吃２００ｍｇ。",
        "1、每天吃１０００ＩＵ。",
        "（1）口服200㎎。",
        "建议补充：补剂名称/剂量/服用时间，\n* 每天增加到４００ｍｇ。",
    ],
)
def test_nfkc_and_list_prefix_commands_remain_blocked(text):
    result = enforce_medical_evidence_boundaries(text)
    assert requires_medical_evidence_boundary(text)
    assert result.flagged


@pytest.mark.parametrize(
    "text",
    [
        "请告诉我是否口服200mg，核对记录以后再口服300mg。",
        "建议补充：午餐/加餐、补剂准确名称/剂量/服用时间，核对记录以后再口服300mg。",
    ],
)
def test_exact_regression_does_not_launder_appended_oral_dose(text):
    result = enforce_medical_evidence_boundaries(text)
    assert requires_medical_evidence_boundary(text)
    assert result.flagged


def test_exact_trusted_clinician_relay_is_preserved_while_new_command_is_blocked():
    trusted = "医生医嘱：维生素D每天服用2000 IU。"
    relay = enforce_medical_evidence_boundaries(
        trusted,
        has_clinician_instruction=True,
        trusted_clinician_instructions=(trusted,),
    )
    assert not relay.flagged
    assert trusted in relay.text

    appended = "请每天增加到4000 IU。"
    mixed = enforce_medical_evidence_boundaries(
        trusted + "\n" + appended,
        has_clinician_instruction=True,
        trusted_clinician_instructions=(trusted,),
    )
    assert mixed.flagged
    assert trusted in mixed.text
    assert appended not in mixed.text


@pytest.mark.asyncio
@pytest.mark.parametrize("panel", [False, True])
@pytest.mark.parametrize(
    "answer",
    [
        "请告诉我是否口服200mg，核对记录以后再口服300mg。",
        "建议补充：午餐/加餐、补剂准确名称/剂量/服用时间，核对记录以后再口服300mg。",
    ],
)
async def test_main_and_panel_withhold_instruction_appended_to_intake_question(
    db, four_domain_user, monkeypatch, panel, answer,
):
    _, _, _, done, saved = await run_projection(
        db, four_domain_user, monkeypatch, panel=panel, answer=answer,
    )
    assert done["turn_outcome"]["status"] == "blocked"
    assert done["completion_status"] != "complete"
    assert answer not in saved.content


@pytest.mark.parametrize("prefix", [
    "请告诉我是否口服200mg", "建议补充：补剂名称/剂量/服用时间",
])
@pytest.mark.parametrize("separator", ["，", "；", "。", "\n"])
@pytest.mark.parametrize("transition", ["核对记录以后再", "等实际记录和产品标签以及既往记录都逐一核对清楚之后再"])
@pytest.mark.parametrize("action", ["口服300mg。", "增加到400mg。", "睡前服用。", "每天服用。"])
def test_independent_administration_does_not_depend_on_leading_request_window(
    prefix, separator, transition, action,
):
    result = enforce_medical_evidence_boundaries(prefix + separator + transition + action)
    assert result.flagged
    assert action not in result.text


@pytest.mark.parametrize("prefix", ["我不知道是否", "我不清楚是否", "无法确认是否", "未核实是否"])
def test_uncertain_intake_object_is_not_an_administration_instruction(prefix):
    text = prefix + "服用200mg。"
    result = enforce_medical_evidence_boundaries(text)
    assert not result.flagged
    assert text in result.text


@pytest.mark.parametrize("prefix", ["我不知道是否", "我不清楚是否", "无法确认是否", "未核实是否"])
@pytest.mark.parametrize("suffix", ["，核对完全部资料之后再口服300mg。", "。每天服用。"])
def test_uncertain_intake_object_never_hides_later_administration(prefix, suffix):
    result = enforce_medical_evidence_boundaries(prefix + "服用200mg" + suffix)
    assert result.flagged
    assert suffix not in result.text
