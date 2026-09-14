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
        assert _ACTUAL_MISSING_FIELDS_REQUEST not in saved.content
        assert "meta_query_invitation_removed" in done["output_quality_flags"]


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
    assert text not in saved.content
    if not action:
        assert "meta_query_invitation_removed" in done["output_quality_flags"]


@pytest.mark.parametrize("object_name", ["疗程", "用药周期", "服用周期", "治疗周期"])
@pytest.mark.parametrize("change", ["改为", "改成", "调整为", "调整到", "设为", "定为", "变更为", "延长到", "缩短到", "延长至", "缩短至", "延长为", "缩短为"])
@pytest.mark.parametrize("duration", ["14天", "两周", "一个月"])
@pytest.mark.parametrize("prefix", ["", "是否需要停用补剂，应由医生判断；"])
def test_course_duration_assignment_is_an_unverified_action(object_name, change, duration, prefix):
    from app.services.guidance_validator import enforce_medical_evidence_boundaries, requires_medical_evidence_boundary
    text = prefix + object_name + change + duration + "。"
    assert requires_medical_evidence_boundary(text)
    assert enforce_medical_evidence_boundaries(text).flagged


@pytest.mark.parametrize("text", [
    "既往疗程为两周。", "记录中的疗程时长为14天。", "上次疗程持续一个月。",
    "疗程已改为两周。", "疗程曾调整为14天。", "既往疗程已延长到两周。",
    "疗程是否需要调整，应由医生判断。", "疗程时长应由医生决定。",
    "不要将疗程改为两周。", "不建议把疗程延长到14天。",
])
def test_course_duration_records_and_deferred_decisions_are_not_instructions(text):
    from app.services.guidance_validator import enforce_medical_evidence_boundaries
    result = enforce_medical_evidence_boundaries(text)
    assert not result.flagged
    assert text in result.text


def test_course_duration_requires_exact_independent_clinician_relay():
    from app.services.guidance_validator import enforce_medical_evidence_boundaries
    text = "疗程改为两周。"
    assert not enforce_medical_evidence_boundaries(
        text, has_clinician_instruction=True, trusted_clinician_instructions=[text],
    ).flagged
    assert enforce_medical_evidence_boundaries(text, has_clinician_instruction=True).flagged
    assert enforce_medical_evidence_boundaries("医生说疗程改为两周。").flagged
    assert enforce_medical_evidence_boundaries(
        "疗程改为三周。", has_clinician_instruction=True, trusted_clinician_instructions=[text],
    ).flagged


@pytest.mark.parametrize("text", [
    "延长疗程至6周。", "缩短治疗周期到5天。", "延长用药周期为两个月。",
    "缩短服用周期至三星期。", "疗程调整到14日。",
    "不要自行改疗程，然后疗程改为两周。", "不要自行改疗程，但疗程改为两周。",
    "是否将疗程延长到两周，应由医生判断。", "请咨询医生是否将疗程延长到两周。",
])
def test_course_duration_reversed_and_appended_actions_still_block(text):
    from app.services.guidance_validator import enforce_medical_evidence_boundaries
    assert enforce_medical_evidence_boundaries(text).flagged


@pytest.mark.parametrize("text,blocked", [
    ("**疗程**改为两周。", True), ("疗程：改为两周。", True), ("疗程改为**两周**。", True),
    ("`疗程`调整为`14天`。", True), ("疗程 **延长为** 6周。", True), ("延长**疗程**至6周。", True),
    ("不建议**疗程**改为两周。", False), ("**疗程**已改为两周。", False),
    ("记录中的**疗程**为两周。", False), ("不要自行将疗程延长为6周。", False),
    ("既往疗程已缩短为5天。", False),
])
def test_course_duration_presentation_preserves_action_polarity(text, blocked):
    from app.services.guidance_validator import enforce_medical_evidence_boundaries, requires_medical_evidence_boundary
    if blocked:
        assert requires_medical_evidence_boundary(text)
    result = enforce_medical_evidence_boundaries(text)
    assert result.flagged is blocked
    if not blocked:
        assert text in result.text


@pytest.mark.parametrize("text,blocked", [
    ("疗程\n改为两周。", True), ("疗程改为\n两周。", True), ("延长\n疗程至6周。", True),
    ("是否需要停用补剂，应由医生判断；**疗程**\n改为两周。", True),
    ("如需更细的分析，可指定日期。疗程改为\n**两周**。", True),
    ("不要将疗程\n改为两周。", False), ("**不要将疗程**\n改为两周。", False),
    ("不要\n疗程改为两周。", True),
])
def test_course_duration_line_boundaries(text, blocked):
    from app.services.guidance_validator import enforce_medical_evidence_boundaries, requires_medical_evidence_boundary
    if blocked:
        assert requires_medical_evidence_boundary(text)
    result = enforce_medical_evidence_boundaries(text)
    assert result.flagged is blocked
    if not blocked:
        assert text in result.text


def test_course_duration_trusted_relay_keeps_negated_multiline_claim_safe():
    from app.services.guidance_validator import enforce_medical_evidence_boundaries
    trusted = "疗程改为两周。"
    text = trusted + "不要将疗程\n延长到三周。"
    result = enforce_medical_evidence_boundaries(text, has_clinician_instruction=True, trusted_clinician_instructions=[trusted])
    assert not result.flagged and text in result.text


@pytest.mark.parametrize("text", ["疗程\n改为两周。", "**疗程**：改为\n**两周**。"])
def test_course_duration_wrapped_trusted_relay_keeps_original_text(text):
    from app.services.guidance_validator import enforce_medical_evidence_boundaries
    result = enforce_medical_evidence_boundaries(text, has_clinician_instruction=True, trusted_clinician_instructions=[text])
    assert not result.flagged and text in result.text
    changed = text.replace("两周", "三周")
    assert enforce_medical_evidence_boundaries(changed, has_clinician_instruction=True, trusted_clinician_instructions=[text]).flagged


@pytest.mark.parametrize("recorded", ["已记录", "已经记录"])
@pytest.mark.parametrize("when", ["今天", "昨天", "昨日", "昨晚", "今早", "刚才", "此前"])
@pytest.mark.parametrize("intake", ["服用两粒鱼油", "口服200mg药物", "服用了１片药物", "服两粒鱼油"])
def test_completed_intake_acknowledgement_is_not_a_new_prescription(recorded, when, intake):
    text = f"{recorded}{when}{intake}。"
    result = enforce_medical_evidence_boundaries(text)
    assert not result.flagged
    assert text in result.text


@pytest.mark.parametrize("prefix", ["已记录", "已记录明天", "已记录后天", "已记录下周", "已记录今天计划", "已记录今天建议", "请记录今天", "记录今天", "建议今天", "是否已记录今天"])
def test_record_word_cannot_authorize_future_or_requested_intake(prefix):
    result = enforce_medical_evidence_boundaries(prefix + "服用两粒鱼油。")
    assert result.flagged
    assert "unverified_dose_action" in result.violations


@pytest.mark.parametrize("separator", ["，", "。", "；", "\n", "然后", "并且"])
@pytest.mark.parametrize("instruction", ["每天服用三粒。", "明天服用四粒。", "口服300mg。", "请睡前服用。", "疗程改为两周。", "把鱼油增加到四粒。", "剂量加到四粒。"])
def test_completed_intake_does_not_authorize_appended_action(separator, instruction):
    result = enforce_medical_evidence_boundaries("已记录今天服用两粒鱼油" + separator + instruction)
    assert result.flagged
    assert instruction not in result.text


@pytest.mark.parametrize("text", [
    "已记录今天服用两粒鱼油，服用时间改为睡前。",
    "已记录今天服用两粒鱼油，医生说疗程改为两周。",
    "建议已记录今天服用两粒鱼油。",
    "已记录今天服用两粒鱼油，以后每天服用三粒。",
])
def test_record_acknowledgement_is_not_blanket_medical_authority(text):
    result = enforce_medical_evidence_boundaries(text)
    assert result.flagged


def test_record_acknowledgement_question_does_not_exempt_intake_action():
    result = enforce_medical_evidence_boundaries("已记录今天服用两粒鱼油？")
    assert result.flagged


@pytest.mark.parametrize("appendix", [
    "。\n明天服3粒。", "，明天四粒。", "，后天四粒。", "，明早四粒。", "，之后四粒。",
    "，**明天四粒**。", "：明天四粒。", "。明天四粒。", "。明天四片药物。",
    "。明天200mg。", "。明天3粒鱼油。", "，明天：**四粒**。", "。明天\n四粒。",
])
def test_completed_intake_cannot_hide_future_shorthand(appendix):
    result = enforce_medical_evidence_boundaries("已记录今天服用两粒鱼油" + appendix)
    assert result.flagged
    assert "unverified_dose_action" in result.violations


@pytest.mark.parametrize("appendix", [
    "不建议明天服用四粒。", "不要自行加量。", "不要明天四粒。", "不建议睡前服用。",
    "明天四片全麦面包。", "明天三粒葡萄。", "今天吃两片面包。",
])
def test_completed_intake_preserves_negation_and_explicit_food(appendix):
    text = "已记录今天服用两粒鱼油，" + appendix
    result = enforce_medical_evidence_boundaries(text)
    assert not result.flagged
    assert text in result.text


@pytest.mark.parametrize("object_text", ["胶囊", "软胶囊", "这个", "复合B", "保持一周", "坚持", "继续", "就可以了", "全麦面包胶囊", "葡萄胶囊"])
def test_completed_intake_future_unknown_objects_are_not_food_authority(object_text):
    result = enforce_medical_evidence_boundaries("已记录今天服用两粒鱼油，明天四粒" + object_text + "。")
    assert result.flagged


@pytest.mark.parametrize("text", ["明天服3粒。", "建议服3片。", "记录今天服两粒鱼油。", "已记录明天服两粒鱼油。"])
def test_record_word_cannot_authorize_short_intake_verb(text):
    assert enforce_medical_evidence_boundaries(text).flagged


@pytest.mark.parametrize("continuation", [
    "也", "再", "仍", "仍然", "依然", "依旧", "还是", "还", "继续", "维持", "保持",
    "各", "都", "先", "要", "需", "需要", "照旧", "照常", "照样", "也是", "仍为",
    "继续维持", "继续保持在", "还是应该继续维持在", "也依旧继续保持在",
    "睡前再", "晚餐后仍", "固定", "一共", "共", "按", "改为", "开始继续",
    "接着", "接着再", "补充", "再补充", "增加到", "减少到", "提高到", "降低到",
    "加到", "减到", "吃上", "服上", "仍旧", "仍旧保持", "恢复到",
    "补上", "再补", "补服", "续上", "用上", "恢复为", "增加至", "换成", "补充到",
    "坚持", "务必", "最好", "记得", "一定要", "可以", "推荐", "计划", "准备", "改用", "换服",
])
@pytest.mark.parametrize("when", ["明天", "之后", "后续", "明早", "下一次", "下次", "明日", "今晚"])
@pytest.mark.parametrize("separator", ["，", "。", "\n"])
def test_completed_intake_cannot_authorize_future_continuation_particles(when, continuation, separator):
    result = enforce_medical_evidence_boundaries(
        "已记录今天服了两粒鱼油" + separator + when + continuation + "两粒。"
    )
    assert result.flagged
    assert "unverified_dose_action" in result.violations


@pytest.mark.parametrize("tail", [
    "明天也两片全麦面包。", "后续仍三粒葡萄。", "明天再两粒花生。",
    "不要明天也两粒。", "不建议后续继续两粒。", "无需明早仍两粒。",
])
def test_completed_intake_future_continuation_keeps_food_and_negation(tail):
    text = "已记录今天服了两粒鱼油，" + tail
    result = enforce_medical_evidence_boundaries(text)
    assert not result.flagged
    assert text in result.text


@pytest.mark.parametrize("reference", ["照原量", "同样", "保持原来", "还是按原计划", "剂量", "鱼油", "鱼油还是", "的鱼油", "鱼油用", "每种补剂", "剂量维持"])
@pytest.mark.parametrize("when", ["明天", "之后", "下次", "接下来"])
def test_completed_intake_cannot_authorize_reordered_future_quantity(reference, when):
    result = enforce_medical_evidence_boundaries("已记录今天服了两粒鱼油。" + when + reference + "两粒。")
    assert result.flagged


@pytest.mark.parametrize("lead", ["请确认", "请告诉我", "能否告诉我", "我想确认"])
@pytest.mark.parametrize("predicate", ["是否仍然服用两粒鱼油", "是不是继续口服200mg药物"])
def test_record_acknowledgement_future_directed_question_is_not_a_prescription(lead, predicate):
    text = lead + "明天" + predicate + "？"
    result = enforce_medical_evidence_boundaries(text)
    assert not result.flagged
    assert text in result.text


@pytest.mark.parametrize("text", [
    "明天还是两粒吗？", "明天两粒，不要加量。", "明天两粒不要加量。",
    "请确认明天是否仍然服用两粒鱼油？明天还是两粒。",
    "请确认明天是否仍然服用两粒鱼油，然后每天服用四粒？",
])
def test_record_acknowledgement_question_and_tail_negation_do_not_grant_authority(text):
    assert enforce_medical_evidence_boundaries(text).flagged


@pytest.mark.parametrize("tail", ["明天面包两片。", "明天全麦面包还是两片。", "后续葡萄三粒。", "明天的葡萄再三粒。"])
def test_completed_intake_future_explicit_food_before_quantity(tail):
    text = "已记录今天服了两粒鱼油。" + tail
    result = enforce_medical_evidence_boundaries(text)
    assert not result.flagged
    assert text in result.text


@pytest.mark.parametrize("history", ["", "已记录今天服了两粒鱼油。"])
@pytest.mark.parametrize("text", ["明天需要带两片检查影像给医生。", "明天整理两片病理切片。", "明天整理报告两片。"])
def test_completed_intake_does_not_turn_document_counts_into_doses(history, text):
    result = enforce_medical_evidence_boundaries(history + text)
    assert not result.flagged
    assert history + text in result.text


def test_record_acknowledgement_future_dose_field_question_is_not_an_action():
    text = "请确认明天的剂量是不是两粒？"
    result = enforce_medical_evidence_boundaries(text)
    assert not result.flagged
    assert text in result.text


@pytest.mark.parametrize("history", ["", "已记录今天服了两粒鱼油。"])
@pytest.mark.parametrize("text", [
    "明天把两片药带给医生核对。", "明天带两片药给医生核对。",
    "明天拍两片药片的包装照片。", "明天核对两片鱼油软胶囊的批号。",
    "明天查看两片药的包装标签。", "明天携带两片药给药师核对。",
    "下次拍摄两粒胶囊的照片。",
])
def test_completed_intake_preserves_explicit_medicine_handling(history, text):
    result = enforce_medical_evidence_boundaries(history + text)
    assert not result.flagged
    assert history + text in result.text


@pytest.mark.parametrize("text", [
    "明天核对后服两片药。", "明天拍照后仍服两片药。",
    "明天带两片药给医生核对，然后服两片药。",
    "明天把两片药带给医生核对。明天还是两片。",
    "明天拍两片药片的包装照片后服两片药。",
    "明天核对两片鱼油软胶囊的批号并加量到四粒。",
])
def test_completed_intake_medicine_handling_cannot_authorize_administration(text):
    assert enforce_medical_evidence_boundaries(text).flagged


@pytest.mark.parametrize("history", ["", "已记录今天服了两粒鱼油。"])
@pytest.mark.parametrize("medicine", ["辅酶Q10软胶囊", "维生素D3胶囊", "复合维生素片"])
@pytest.mark.parametrize("appended", ["", "然后口服两片药。"])
def test_completed_intake_named_supplement_handling_keeps_actions_visible(history, medicine, appended):
    text = history + "明天核对两粒" + medicine + "的批号。" + appended
    result = enforce_medical_evidence_boundaries(text)
    assert result.flagged is bool(appended)
    if not appended:
        assert text in result.text


@pytest.mark.parametrize("separator", ["。", "，", "；", "\n"])
def test_intake_checkin_format_is_a_record_noun(separator):
    text = "睡眠和补剂分别以每日睡眠条目及服用打卡形式出现" + separator
    result = enforce_medical_evidence_boundaries(text)
    assert not result.flagged
    assert text in result.text


@pytest.mark.parametrize("instruction", [
    "每日服用两粒鱼油。", "请睡前服用。", "明天200mg。", "疗程改为两周。",
    "服用时间改为睡前。", "建议鱼油每天服用。",
])
@pytest.mark.parametrize("placement", ["before", "after"])
def test_record_format_noun_never_hides_other_administration(instruction, placement):
    record = "睡眠和补剂分别以每日睡眠条目及服用打卡形式出现，"
    text = instruction + record if placement == "before" else record + instruction
    result = enforce_medical_evidence_boundaries(text)
    assert result.flagged
    assert "unverified_dose_action" in result.violations


@pytest.mark.parametrize("text", [
    "建议每日服用打卡形式出现的药物。",
    "补剂每日服用打卡形式出现的两粒药物。",
    "补剂每日服用打卡形式出现后再加两粒。",
    "补剂每日服用打卡形式出现然后服用两粒。",
])
def test_record_format_prefix_does_not_authorize_a_medical_object(text):
    assert enforce_medical_evidence_boundaries(text).flagged


@pytest.mark.parametrize("instruction", [
    "补剂建议服用鱼油", "建议按既有情况服用补剂", "补剂请在睡前服用",
])
def test_greedy_regimen_match_cannot_hide_before_record_format(instruction):
    text = instruction + "，记录以服用打卡形式出现。"
    result = enforce_medical_evidence_boundaries(text)
    assert result.flagged
    assert "unverified_dose_action" in result.violations
