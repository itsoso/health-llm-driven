"""Bounded daily-summary advice checks; not a general factual verifier."""
from types import SimpleNamespace

import pytest

from app.services import agent_daily_read_execution as daily
from app.services.agent_kernel.daily_read_plan import DailyReadPlan


@pytest.mark.parametrize("text", ["", " \n\t ", "###建议", "### 建议（可执行）\n", "**建议**", "建议：",
                                  "### 建议\n-", "**建议**\n**", "建议：\n---"])
def test_empty_advice_is_not_a_completed_advice_goal(text):
    assert daily.summary_advice_contract_failure(text) == "summary_advice_unavailable"


@pytest.mark.parametrize("heading", ["### 建议（可执行）", "**建议**", "建议：先补充漏记。"])
def test_explicit_advice_heading_discards_only_preceding_model_facts(heading):
    advice = heading + "\n保持规律作息。"
    assert daily.summary_advice_text("## 今日总结\n睡了7小时。\n" + advice) == advice


@pytest.mark.parametrize("text", ["根据这些记录，建议先补充漏记。", "建议：今天只吃了720千卡。"])
def test_advice_extraction_keeps_inline_word_and_unsafe_heading_content(text):
    assert daily.summary_advice_text(text) == text
    if "720" in text:
        assert daily.summary_advice_contract_failure(daily.summary_advice_text(text)) == "summary_advice_repeats_measurement"


@pytest.mark.parametrize("text", [
    "已记录热量1020千卡，继续规律饮食。", "今天约一千零二十卡路里。",
    "睡眠七小时。", "睡了7.5小时。", "时长四百二十分钟。",
    "睡眠评分80。", "评分八十分。", "评分为八十。", "热量为300 kcal。",
    "不应把1020千卡当作全天摄入。",
    "今天的已记录热量合计为720大卡。", "你今天睡了7小时。",
    "睡前半小时减少屏幕使用，但你今天睡了7小时。",
    "你今天饭后散步十分钟。",
])
def test_advice_cannot_repeat_observation_numbers_even_in_qualifiers(text):
    assert daily.summary_advice_contract_failure(text) == "summary_advice_repeats_measurement"


@pytest.mark.parametrize("text", [
    "今天只吃了早餐。", "今日总共摄入这些食物。", "全天只吃这些，太少了。",
    "你的摄入不足，应该加餐。", "这些记录表明摄入明显过量。",
    "不能据此判断摄入不足，但你的摄入过量。",
    "摄入的热量太少，建议加餐。",
    "今天的总摄入只有这些，建议补充蛋白质。",
])
def test_advice_cannot_infer_actual_complete_or_inadequate_intake(text):
    assert daily.summary_advice_contract_failure(text) == "summary_advice_infers_complete_intake"


@pytest.mark.parametrize("text", [
    "保持规律饮食和睡眠。", "可以先补充漏记，再观察整体情况。",
    "不能据此判断摄入不足。", "不能仅根据这些记录判断摄入过量。",
    "记录不代表全天实际摄入，也无法判断完整摄入。",
    "没有证据说明摄入不足。", "不应断言今天只吃了这些。",
    "无法判断全天总共摄入了什么。", "可先核对记录是否完整。",
    "不能据此判断摄入的热量太少。", "不能断言今天的总摄入只有这些。",
    "睡前半小时减少屏幕使用。", "饭后散步十分钟。",
    "建议饭后散步十分钟。",
    "只有总时长和睡眠评分两项，评分处于良好区间。",
    "建议把入睡安排在接下来半小时内。",
])
def test_qualitative_advice_and_explicit_uncertainty_pass(text):
    assert daily.summary_advice_contract_failure(text) is None


@pytest.mark.parametrize("payload", [
    {"records": [{"calories": 300}]},
    {"records": [{"record_date": "2026-09-12"}], "availability": "unavailable"},
    {"data": [{"record_date": "2026-09-12"}]},
    {"records": [{"record_date": "2026-09-12"}], "availability": "no_data"},
])
@pytest.mark.parametrize("summary", [False, True])
def test_summary_goal_cannot_verify_payload_that_fact_projection_rejects(payload, summary):
    plan = DailyReadPlan(dimensions=("diet", "sleep") if summary else ("diet",), start_date="2026-09-12",
                         end_date="2026-09-12", timezone="Asia/Shanghai", is_summary=summary, asks_advice=True)
    decision = SimpleNamespace(normalized_tool_name="health_query", normalized_args=plan.queries()[0], action="allow")
    goal = daily.daily_result_goal(plan, decision, payload)
    assert goal["status"] == "failed"
    assert goal["reason_code"] in ("query_result_unavailable", "query_result_scope_conflict")


def test_ordinary_daily_query_keeps_existing_attestation_contract():
    plan = DailyReadPlan(dimensions=("diet",), start_date="2026-09-12",
                         end_date="2026-09-12", timezone="Asia/Shanghai")
    decision = SimpleNamespace(normalized_tool_name="health_query", normalized_args=plan.queries()[0], action="allow")
    assert daily.daily_result_goal(plan, decision, {"records": [{"calories": 300}]})["status"] == "verified"


def test_actual_markdown_action_duration_is_not_an_observation():
    text = "### 建议\n**现在最该做的是收工睡觉。** 已经过零点了，建议把入睡安排在**接下来半小时内**，别再往后拖。"
    assert daily.summary_advice_contract_failure(text) is None


@pytest.mark.parametrize("suffix,reason", [
    ("", None), ("但你今天只睡了3小时。", "summary_advice_repeats_measurement"),
])
def test_actual_goal_and_future_timing_does_not_hide_observation(suffix, reason):
    text = "如果打算现在上床，按你的7.5小时睡眠目标倒推，明早8:10左右起床比较合适；屏幕调暗、离开手机15–20分钟更容易入睡。"
    assert daily.summary_advice_contract_failure(text + suffix) == reason


@pytest.mark.parametrize("text", ["建议每天睡8小时。", "目标睡眠时长为8小时。", "可以散步15–20分钟。"])
def test_future_actions_and_goals_do_not_require_fixed_wording(text):
    assert daily.summary_advice_contract_failure(text) is None


@pytest.mark.parametrize("text", ["昨晚睡眠7小时。", "睡眠时长为7小时。", "实际散步十分钟。", "睡眠：7小时。"])
def test_duration_with_explicit_observation_cue_is_rejected(text):
    assert daily.summary_advice_contract_failure(text) == "summary_advice_repeats_measurement"


def test_diet_evaluation_requires_explicit_advice_section_without_changing_summary_default():
    prose = "我会先查询今天的饮食记录，然后给出建议。"
    assert daily.summary_advice_text(prose) == prose
    assert daily.summary_advice_text(prose, require_heading=True) == ""
    assert daily.summary_advice_contract_failure(daily.summary_advice_text(prose, require_heading=True)) == "summary_advice_unavailable"


@pytest.mark.parametrize("text", [
    "建议：暂无建议。", "### 建议\n目前没有建议。", "建议：建议待补充。",
    "建议：我会先查询今天的饮食记录，然后给出建议。",
    "建议：我将读取记录，再分析你的饮食。",
])
def test_heading_cannot_verify_placeholder_or_only_a_promise_to_answer(text):
    assert daily.summary_advice_contract_failure(text) is not None


@pytest.mark.parametrize("text", [
    "建议：当前记录缺少份量和营养字段，暂不足以评价营养是否均衡。",
    "建议：目前没有足够信息给出个性化建议，可以先补充食物份量。",
    "建议：我会先查询记录。你可以先核对每条记录的份量。",
])
def test_explained_limits_or_real_actions_are_not_empty_advice(text):
    assert daily.summary_advice_contract_failure(text) is None


@pytest.mark.parametrize("text,reason", [
    ("建议：我会先分析。", "summary_advice_not_delivered"),
    ("建议：我会先查询，然后给出建议。", "summary_advice_not_delivered"),
    ("建议：蛋白数据缺失，说明今天缺口大概率在蛋白侧。", "summary_advice_infers_nutrient_gap"),
    ("建议：你的蛋白质摄入不足，应补充食物。", "summary_advice_infers_nutrient_gap"),
    ("建议：你今天缺少膳食纤维。", "summary_advice_infers_nutrient_gap"),
    ("建议：营养缺乏，需要调整饮食。", "summary_advice_infers_nutrient_gap"),
    ("建议：两条早餐名称和热量相同，说明是重复录入，建议删除其中一条。", "summary_advice_infers_record_error"),
    ("建议：两条记录重复，建议删掉一条。", "summary_advice_infers_record_error"),
    ("建议：午餐被标成了晚餐，建议改正餐次。", "summary_advice_infers_record_error"),
    ("建议：不能认定是重复录入，但这两条记录重复。", "summary_advice_infers_record_error"),
])
def test_retained_advice_cannot_assert_known_unsupported_inference_categories(text, reason):
    assert daily.summary_advice_contract_failure(text) == reason


@pytest.mark.parametrize("text", [
    "建议：缺少蛋白质数据，请补充记录。",
    "建议：营养字段缺失不代表营养缺乏。",
    "建议：没有足够证据判断蛋白质摄入不足。",
    "建议：不能据此判断缺口在蛋白质侧。",
    "建议：可以先核对是否存在重复录入。",
    "建议：可以检查两条记录是否重复。",
    "建议：不能认定两条记录重复。",
    "建议：餐次标签与当前时间不同，不代表午餐被标成了晚餐。",
    "建议：先核对餐次和实际用餐时间是否一致。",
    "建议：我会先分析。你可以先核对记录是否完整。",
])
def test_missing_data_and_non_presupposing_record_checks_still_complete(text):
    assert daily.summary_advice_contract_failure(text) is None


@pytest.mark.parametrize("text", [
    "建议：两条记录相同不代表重复录入。",
    "建议：餐次标签差异不足以证明误录。",
    "建议：晚餐标记不能说明午餐被标成了晚餐。",
    "建议：需要时可以对记录重复查询。",
])
def test_record_error_negation_applies_to_the_verdict_after_its_subject(text):
    assert daily.summary_advice_contract_failure(text) is None


@pytest.mark.parametrize("text", [
    "建议：避免重复录入。",
    "建议：防止重复记录，先核对已保存条目。",
])
def test_record_error_prevention_is_an_action_not_a_claim(text):
    assert daily.summary_advice_contract_failure(text) is None


@pytest.mark.parametrize("field", [
    "蛋白质的记录", "蛋白质摄入记录", "蛋白质的摄入记录",
    "蛋白质摄入量的记录", "蛋白质含量的数据",
])
def test_nutrient_missing_data_noun_phrase_is_not_a_deficit(field):
    assert daily.summary_advice_contract_failure(f"建议：目前缺少{field}，请补全记录。") is None


@pytest.mark.parametrize("text", [
    "建议：缺少蛋白质的记录，说明你的蛋白质摄入不足。",
    "建议：缺少蛋白质的摄入记录且蛋白质缺乏。",
])
def test_data_noun_suffix_cannot_hide_a_later_deficit_claim(text):
    assert daily.summary_advice_contract_failure(text) == "summary_advice_infers_nutrient_gap"


@pytest.mark.parametrize("text", [
    "建议：是否存在重复录入需要先核对。",
    "建议：是否有重复记录，需要先检查。",
    "建议：有没有重复录入，需要核对明细。",
    "建议：这两条记录是否重复，需要先核对。",
    "建议：午餐是否被标成晚餐需要先核对。",
])
def test_local_question_modifier_can_precede_the_check_action(text):
    assert daily.summary_advice_contract_failure(text) is None


@pytest.mark.parametrize("text", [
    "建议：是否存在重复录入需要核对，但这些记录是重复录入。",
    "建议：是否需要补充份量，存在重复录入。",
    "建议：核对是否完整后确认这是重复录入。",
])
def test_unrelated_or_earlier_question_does_not_excuse_record_assertion(text):
    assert daily.summary_advice_contract_failure(text) == "summary_advice_infers_record_error"


@pytest.mark.parametrize("meal", [False, True])
@pytest.mark.parametrize("empty", [False, True])
def test_evaluation_attests_projectable_query_and_real_meal_list_shapes(meal, empty):
    plan = DailyReadPlan(dimensions=("diet",), start_date="2026-09-12",
                         end_date="2026-09-12", timezone="Asia/Shanghai",
                         meal_type="dinner" if meal else None, asks_advice=True)
    rows = [] if empty else [{"record_date": plan.start_date, "meal_type": "dinner", "calories": 300}]
    payload = rows if meal else {"records": rows, "availability": "no_data" if empty else "available"}
    decision = SimpleNamespace(normalized_tool_name="health_manage" if meal else "health_query",
                               normalized_args=plan.diet_list_args() if meal else plan.queries()[0], action="allow")
    goal = daily.daily_result_goal(plan, decision, payload)
    assert goal["status"] == "verified"
    projected_payload = {"records": rows} if meal else payload
    facts = daily.verified_daily_summary(plan, {"diet": projected_payload}, {"diet": goal}, include_non_summary=True)
    assert "无法核对" not in facts and "查询未完成" not in facts
    assert ("没有可用记录" if empty else "已记录热量合计300千卡") in facts


@pytest.mark.parametrize("row", [{"calories": 300}, {"record_date": "2001-01-01", "calories": 300}])
def test_meal_list_wrapper_never_invents_the_record_day(row):
    plan = DailyReadPlan(dimensions=("diet",), start_date="2026-09-12",
                         end_date="2026-09-12", timezone="Asia/Shanghai", meal_type="dinner", asks_advice=True)
    decision = SimpleNamespace(normalized_tool_name="health_manage", normalized_args=plan.diet_list_args(), action="allow")
    assert daily.daily_result_goal(plan, decision, [row])["status"] == "failed"
