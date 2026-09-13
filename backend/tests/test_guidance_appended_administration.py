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


@pytest.mark.parametrize("text", [
    "请告诉我是否口服200mg，核对记录以后再每天吃两片。",
    "请告诉我是否口服200mg，核对记录以后再吃2片。",
    "建议后续补充：午餐/加餐、补剂准确名称/剂量/服用时间，"
    "核对记录以后再吃2片。",
    "我不知道是否服用200mg，核对完全部资料之后再每天吃两片。",
])
def test_existing_intake_amount_vocabulary_cannot_follow_information_projection(text):
    result = enforce_medical_evidence_boundaries(text)
    assert result.flagged, text


@pytest.mark.asyncio
@pytest.mark.parametrize("panel", [False, True])
async def test_main_and_panel_block_long_appended_eat_amount(
    db, four_domain_user, monkeypatch, panel,
):
    answer = "请告诉我是否口服200mg，核对记录以后再每天吃两片。"
    _, _, _, done, saved = await run_projection(
        db, four_domain_user, monkeypatch, panel=panel, answer=answer,
    )
    assert done["turn_outcome"]["status"] == "blocked"
    assert done["completion_status"] != "complete"
    assert answer not in saved.content


_ADMINISTRATION_UNIT_ALIASES = ["mg", "MG", "μg", "µg", "ug", "IU", "单位", "毫克", "微克", "粒", "片"]


@pytest.mark.parametrize("unit", _ADMINISTRATION_UNIT_ALIASES)
@pytest.mark.parametrize("verb", ["吃", "服用", "口服"])
def test_administration_units_are_shared_after_information_projection(unit, verb):
    action = "核对记录以后再" + verb + "300" + unit + "。"
    result = enforce_medical_evidence_boundaries("请告诉我是否口服200mg，" + action)
    assert result.flagged
    assert action not in result.text


@pytest.mark.parametrize("unit", _ADMINISTRATION_UNIT_ALIASES)
@pytest.mark.parametrize("verb", ["吃", "服用", "口服"])
def test_same_unit_intake_question_preserves_original_wording(unit, verb):
    text = "我不知道是否" + verb + "200" + unit + "。"
    result = enforce_medical_evidence_boundaries(text)
    assert not result.flagged
    assert text in result.text


@pytest.mark.parametrize("unit", ["克", "g"])
@pytest.mark.parametrize("verb", ["服用", "口服"])
def test_explicit_oral_gram_quantity_is_independent_of_leading_request(unit, verb):
    result = enforce_medical_evidence_boundaries("请告诉我是否口服200mg，核对后再" + verb + "2" + unit + "。")
    assert result.flagged


@pytest.mark.parametrize("text", [
    "核对记录以后再吃两片全麦面包。", "早餐吃一粒葡萄。",
    "每天喝200ml水。", "建议把蔬菜增加到100克。",
])
def test_named_food_and_water_are_not_medication_administration(text):
    result = enforce_medical_evidence_boundaries(text)
    assert not result.flagged
    assert text in result.text


_ACTUAL_MISSING_FIELDS_REQUEST = (
    "为了给出更精准建议，需要补充当前症状、午餐/加餐、补剂具体名称/剂量/单位/服用时间、"
    "睡眠起止时间，以及情绪和工作压力情况。"
)


@pytest.mark.parametrize("field_request", [
    _ACTUAL_MISSING_FIELDS_REQUEST,
    "需要补充当前症状、补剂具体名称/剂量/单位/服用时间。",
    "请提供补剂具体名称、剂量、单位、服用时间。",
    "建议补齐补剂具体名称/剂量/单位/服用时间。",
])
def test_explicit_record_fields_without_colon_are_information_objects(field_request):
    result = enforce_medical_evidence_boundaries(field_request)
    assert not result.flagged
    assert field_request in result.text


@pytest.mark.parametrize("separator", ["，", "。", "；", "\n"])
@pytest.mark.parametrize("action", ["每天服用两片。", "请睡前服用。", "剂量增加到200mg。", "核对以后再吃2片。"])
def test_noncolon_record_fields_do_not_hide_a_later_action(separator, action):
    text = "需要补充当前症状、补剂具体名称/剂量/单位/服用时间" + separator + action
    result = enforce_medical_evidence_boundaries(text)
    assert result.flagged
    assert action not in result.text


@pytest.mark.parametrize("text", [
    "建议补充维生素。", "需要补充补剂剂量200mg。",
    "建议补齐补剂具体名称/剂量/单位/服用时间改为睡前。",
])
def test_noncolon_field_projection_does_not_accept_medication_or_assigned_values(text):
    assert enforce_medical_evidence_boundaries(text).flagged


@pytest.mark.asyncio
@pytest.mark.parametrize("panel", [False, True])
@pytest.mark.parametrize("action", ["", "核对记录以后再吃2片。"])
async def test_main_and_panel_complete_only_the_information_request(
    db, four_domain_user, monkeypatch, panel, action,
):
    answer = _ACTUAL_MISSING_FIELDS_REQUEST + action
    _, _, _, done, saved = await run_projection(
        db, four_domain_user, monkeypatch, panel=panel, answer=answer,
    )
    if action:
        assert done["turn_outcome"]["status"] == "blocked"
        assert action not in saved.content
    else:
        assert done["completion_status"] == "complete"
        assert done["turn_outcome"]["status"] == "complete"
        assert _ACTUAL_MISSING_FIELDS_REQUEST in saved.content


@pytest.mark.parametrize("text", [
    "为了给出建议，需要补充当前症状、维生素D。",
    "建议补充：补剂名称/剂量/服用时间、维生素D。",
    "建议补充当前症状、补剂具体名称/剂量/单位/服用时间，维生素D。",
    "建议补充当前症状、补剂具体名称/剂量/单位/服用时间, 维生素D。",
])
def test_mixed_record_field_and_medicine_objects_are_not_projected(text):
    assert enforce_medical_evidence_boundaries(text).flagged


_ACTUAL_RECORDING_FIELDS = (
    "2. **补全关键记录**：把每天午餐/加餐、实际补剂名称+剂量+服用时间、"
    "入睡/醒来时间、情绪和工作压力简单记录下来，后续才能做更个体化的分析；"
)


@pytest.mark.parametrize("text", [
    _ACTUAL_RECORDING_FIELDS,
    "请记录每天的补剂具体名称、剂量和服用时间。",
    "每天的服用时间不明确，不能判断补剂方案。",
    "请告诉我已有的服用时间。",
    "已记录的服用时间：睡前。",
    "不要调整服用时间。",
])
def test_intake_time_field_is_not_an_administration_verb(text):
    result = enforce_medical_evidence_boundaries(text)
    assert not result.flagged
    assert text in result.text


@pytest.mark.parametrize("text", [
    "补剂应该调整服用时间为睡前。",
    "建议把补剂服用时间改为睡前。",
    "请将维生素服用时间改为早上。",
    "修改服用时间。", "改变服用时间。", "指定服用时间。",
    "设置服用时间。", "安排服用时间。",
    "服用时间改到睡前。", "服用时间调整为早上。",
    "服用时间调整到晚上。", "服用时间设为早上。",
    "服用时间定在睡前。", "服用时间安排在晚上。",
    "服用时间提前到早上。", "服用时间推迟到晚上。",
    "服用时间应为睡前。", "服用时间应该为早上。",
    "建议服用时间：睡前。", "请将服用时间设为０８：３０。",
])
def test_explicit_intake_time_actions_need_verified_evidence(text):
    assert enforce_medical_evidence_boundaries(text).flagged


@pytest.mark.parametrize("action", [
    "每天服用两片。", "请睡前服用。", "剂量增加到200mg。", "服用时间改到睡前。",
])
@pytest.mark.parametrize("separator", ["，", "。", "；", "\n"])
def test_time_field_noun_does_not_hide_later_administration(action, separator):
    assert enforce_medical_evidence_boundaries(_ACTUAL_RECORDING_FIELDS + separator + action).flagged


@pytest.mark.asyncio
@pytest.mark.parametrize("panel", [False, True])
@pytest.mark.parametrize("action", ["", "服用时间改到睡前。"])
async def test_main_and_panel_distinguish_time_field_from_timing_action(
    db, four_domain_user, monkeypatch, panel, action,
):
    text = _ACTUAL_RECORDING_FIELDS + action
    _, _, _, done, saved = await run_projection(
        db, four_domain_user, monkeypatch, answer=text, panel=panel,
    )
    assert done['completion_status'] == ('error' if action else 'complete')
    assert done['turn_outcome']['status'] == ('blocked' if action else 'complete')
    assert (text in saved.content) is not bool(action)
