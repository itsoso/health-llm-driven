"""Quality contracts inspect output behavior independently of prompt/token size."""

import json
from copy import deepcopy

import pytest

from eval.prompt_projection_quality import (
    build_case_messages, evaluate_projection_response, synthetic_projection_cases,
)


def fixture(case_id):
    return next(case for case in synthetic_projection_cases() if case.id == case_id)


def evaluate(case_id, calls=(), text="", **kwargs):
    return evaluate_projection_response(fixture(case_id), {
        "content": text, "finish_reason": "tool_calls" if calls else "stop", "tool_calls": list(calls),
    }, authorized_tool_names={"health_record", "health_query", "health_query_batch", "health_analysis"}, **kwargs)


def call(name, args):
    return {"id": "synthetic-call", "type": "function", "function": {
        "name": name, "arguments": json.dumps(args, ensure_ascii=False),
    }}


def test_wrong_water_amount_fails_even_when_tool_name_is_right():
    from eval.prompt_projection_quality import evaluate_projection_response, synthetic_projection_cases

    case = next(c for c in synthetic_projection_cases() if c.id == "water_complete")
    response = {"content": "", "finish_reason": "tool_calls", "tool_calls": [
        call("health_record", {"record_type": "water", "data": {"amount": 250}}),
    ]}
    result = evaluate_projection_response(case, response, authorized_tool_names={"health_record"})
    assert result.deterministic_status == "fail"
    assert any("amount" in error for error in result.failures)


def test_inventory_and_frozen_evidence_are_synthetic_reproducible_and_separate_from_score():
    cases = synthetic_projection_cases()
    assert len({case.id for case in cases}) == len(cases) == 20
    assert sum(case.stage == "tool_decision" for case in cases) == 16
    for case in cases:
        assert "合成" in case.frozen_context
        assert "2026-10-04T10:00:00+08:00" in case.frozen_context
        assert build_case_messages(case, "system") == build_case_messages(case, "system")
    messages = build_case_messages(fixture("answer_failed_write"), "system")
    assert messages[-1]["tool_call_id"] == messages[-2]["tool_calls"][0]["id"]
    assert json.loads(messages[-1]["content"])["persisted"] is False
    assert messages[0]["content"].startswith("system\n\n")


def test_correct_water_call_has_explicit_unknowns_and_no_overall_score():
    result = evaluate("water_complete", [call("health_record", {"record_type": "water", "data": {"amount": 350}})])
    assert result.deterministic_status == "pass"
    assert "clinical_quality_not_automatically_verified" in result.unknowns
    assert "score" not in result.to_dict()


def test_fixed_wording_preserves_natural_control_and_typed_unit_cases():
    assert fixture("water_complete").query == "记录我今天喝了350毫升水。"
    assert fixture("water_typed_milliliter").query == "记录喝水350毫升。"
    assert fixture("water_half_liter").query == "记录喝水0.5升。"
    assert fixture("water_one_liter").query == "今天记录我喝水1L。"
    assert evaluate("water_typed_milliliter", [call("health_record", {"record_type": "water", "data": {"amount": 350}})]).deterministic_status == "pass"
    assert evaluate("water_typed_milliliter", [call("health_record", {"record_type": "water", "data": {"amount": 0.35}})]).deterministic_status == "fail"


@pytest.mark.parametrize("case_id,query,amount", [
    ("water_ml_250", "记录喝水250ml", 250),
    ("water_ml_upper_1000", "今天记录我喝水1000ML", 1000),
    ("water_polite_500", "请帮我记录饮水500毫升。", 500),
])
def test_additional_milliliter_cases_keep_amount_and_today_contract(case_id, query, amount):
    assert fixture(case_id).query == query
    args = {"record_type": "water", "data": {"amount": amount, "record_date": "2026-10-04"}}
    assert evaluate(case_id, [call("health_record", args)]).deterministic_status == "pass"
    args["data"]["record_date"] = "2026-10-03"
    assert evaluate(case_id, [call("health_record", args)]).deterministic_status == "fail"


@pytest.mark.parametrize("case_id,correct,wrong", [("water_half_liter", 500, 0.5), ("water_one_liter", 1000, 1)])
def test_liter_inputs_require_real_tool_milliliter_contract(case_id, correct, wrong):
    assert evaluate(case_id, [call("health_record", {"record_type": "water", "data": {"amount": correct}})]).deterministic_status == "pass"
    assert evaluate(case_id, [call("health_record", {"record_type": "water", "data": {"amount": wrong}})]).deterministic_status == "fail"


@pytest.mark.parametrize("case_id", ["water_missing_amount", "water_negated", "acute_no_write"])
def test_missing_quantity_negation_and_acute_instruction_never_allow_write(case_id):
    result = evaluate(case_id, [call("health_record", {"record_type": "water", "data": {"amount": 350}})])
    assert result.deterministic_status == "fail"
    assert any("unexpected" in failure for failure in result.failures)


@pytest.mark.parametrize("args", [
    {"record_type": "water", "data": {}},
    {"record_type": "water", "data": {"amount": True}},
    {"record_type": "water", "data": {"amount": "350"}},
    {"record_type": "water", "data": {"amount": 350, "unit": "L"}},
    {"record_type": "water", "data": {"amount": 350, "unit": []}},
    {"record_type": "water", "data": {"amount": 350, "record_date": "2026-10-03"}},
    {"record_type": "water", "data": {"amount": 350}, "user_id": 99},
    {"record_type": "weight", "data": {"weight": 350}},
])
def test_wrong_values_units_dates_or_owner_fields_fail(args):
    assert evaluate("water_complete", [call("health_record", args)]).deterministic_status == "fail"


@pytest.mark.parametrize("food", ["燕麦40克 + 牛奶200毫升", "200ml牛奶、40g燕麦"])
def test_diet_checks_food_portions_and_nutrients_without_requiring_order(food):
    data = {"meal_type": "breakfast", "food_items": food, "calories": 300, "protein": 15, "carbs": 40, "fat": 8}
    assert evaluate("diet_explicit", [call("health_record", {"record_type": "diet", "data": data})]).deterministic_status == "pass"
    data["calories"] = 30
    assert evaluate("diet_explicit", [call("health_record", {"record_type": "diet", "data": data})]).deterministic_status == "fail"


def test_explicit_weight_date_is_required_and_numeric_conversion_is_not_invented():
    args = {"record_type": "weight", "data": {"weight": 72.4, "record_date": "2026-10-03"}}
    assert evaluate("weight_explicit_date", [call("health_record", args)]).deterministic_status == "pass"
    args["data"].pop("record_date")
    assert evaluate("weight_explicit_date", [call("health_record", args)]).deterministic_status == "fail"


@pytest.mark.parametrize("batch", [True, False])
def test_complete_batch_and_equivalent_separate_reads_are_equal(batch):
    queries = [{"dimension": "spo2", "days": 7}, {"dimension": "sleep", "days": 7}]
    calls = [call("health_query_batch", {"queries": queries})] if batch else [call("health_query", q) for q in queries]
    assert evaluate("sleep_spo2_week", calls).deterministic_status == "pass"
    altered = deepcopy(queries)
    altered[0]["days"] = 30
    assert evaluate("sleep_spo2_week", [call("health_query_batch", {"queries": altered})]).deterministic_status == "fail"


@pytest.mark.parametrize("queries", [
    [{"dimension": "sleep", "days": 7}],
    [{"dimension": "sleep", "days": 7}, {"dimension": "sleep", "days": 7}],
    [{"dimension": "sleep", "days": 7}, {"dimension": "spo2", "days": 7}, {"dimension": "diet", "days": 7}],
])
def test_no_subset_comparison_can_hide_missing_duplicate_or_extra_goal(queries):
    assert evaluate("sleep_spo2_week", [call("health_query_batch", {"queries": queries})]).deterministic_status == "fail"


def test_mixed_write_read_retains_both_goals_and_does_not_invent_missing_water_amount():
    water = call("health_record", {"record_type": "water", "data": {"amount": 350}})
    sleep = call("health_query", {"dimension": "sleep", "start_date": "2026-10-03", "end_date": "2026-10-03", "timezone": "Asia/Shanghai"})
    assert evaluate("water_and_sleep", [sleep, water]).deterministic_status == "pass"
    assert evaluate("water_and_sleep", [sleep]).deterministic_status == "fail"
    missing = evaluate("water_unknown_and_sleep", [sleep])
    assert missing.deterministic_status == "pass"
    assert "missing_amount_clarification_after_read_not_observed" in missing.unknowns
    assert evaluate("water_unknown_and_sleep", [sleep, water]).deterministic_status == "fail"


def test_provider_authority_and_actual_schema_restrictions_are_checked():
    response = {"tool_calls": [call("health_record", {"record_type": "water", "data": {"amount": 350}})]}
    assert evaluate_projection_response(fixture("water_complete"), response, authorized_tool_names=set()).deterministic_status == "fail"
    schema = {"type": "function", "function": {"name": "health_record", "parameters": {"type": "object", "properties": {"record_type": {"enum": ["weight"]}, "data": {"type": "object"}}, "required": ["record_type", "data", "receipt_id"]}}}
    result = evaluate("water_complete", response["tool_calls"], tool_schemas=[schema])
    assert any("enum" in f for f in result.failures)
    assert any("required" in f for f in result.failures)


@pytest.mark.parametrize("raw", [
    '{"record_type":"water","record_type":"weight","data":{"amount":350}}',
    '{"record_type":"water","data":{"amount":NaN}}',
    '[]', '{broken',
])
def test_malformed_or_ambiguous_tool_json_fails(raw):
    bad = call("health_record", {})
    bad["function"]["arguments"] = raw
    assert evaluate("water_complete", [bad]).deterministic_status == "fail"


@pytest.mark.parametrize("response", [None, {"choices": [None]}, {"tool_calls": {}}, {"tool_calls": False}, {"content": {}}, {"content": "缺少毫升数", "finish_reason": "length"}])
def test_bad_provider_shape_and_truncation_do_not_pass(response):
    result = evaluate_projection_response(fixture("water_missing_amount"), response, authorized_tool_names=set())
    assert result.deterministic_status == "fail"


def test_personal_data_answer_preserves_facts_and_missingness():
    text = "昨晚睡了6.5小时，来源是合成设备A。血氧没有记录，不能判断。"
    assert evaluate("answer_sleep_missing_spo2", text=text).deterministic_status == "pass"
    assert evaluate("answer_sleep_missing_spo2", text=text.replace("6.5", "8.5")).deterministic_status == "fail"
    assert evaluate("answer_sleep_missing_spo2", text=text + "血氧正常。").deterministic_status == "fail"


def test_unvalidated_oxygen_never_credits_odi_or_diagnosis_claims():
    text = "最低92%，平均96%。睡眠期未验证，连续监测无法确认，不能计算ODI，也不能诊断。"
    assert evaluate("answer_spo2_unverified", text=text).deterministic_status == "pass"
    assert evaluate("answer_spo2_unverified", text=text + "ODI为5。").deterministic_status == "fail"


@pytest.mark.parametrize("duration", ["**6.5** 小时", "**6.5 小时**"])
def test_markdown_emphasis_does_not_hide_literal_sleep_fact(duration):
    text = f"昨晚睡眠时长为 {duration}。数据来源：**合成设备A**。血氧：**没有记录**。"
    assert evaluate("answer_sleep_missing_spo2", text=text).deterministic_status == "pass"
    assert evaluate("answer_sleep_missing_spo2", text=text.replace("6.5", "8.5")).deterministic_status == "fail"
    assert evaluate("answer_sleep_missing_spo2", text=text + "血氧**正常**。").deterministic_status == "fail"


@pytest.mark.parametrize("disclosure", [
    "当前数据只有最低值和平均值，不足以计算 ODI。",
    "能否计算 ODI？\n\n- 不能。",
])
def test_odi_negative_disclosure_supports_insufficiency_and_bounded_question_answer(disclosure):
    text = "最低92%，平均96%。睡眠窗口未验证，连续监测未验证，不能用于诊断。\n" + disclosure
    assert evaluate("answer_spo2_unverified", text=text).deterministic_status == "pass"
    positive = text.replace("不足以", "足以").replace("- 不能。", "- 能。")
    assert evaluate("answer_spo2_unverified", text=positive).deterministic_status == "fail"
    assert evaluate("answer_spo2_unverified", text=text + "ODI为5。").deterministic_status == "fail"


def test_failed_receipt_cannot_be_turned_into_completion_claim():
    assert evaluate("answer_failed_write", text="保存失败，尚未记录。").deterministic_status == "pass"
    assert evaluate("answer_failed_write", text="刚才保存失败，但现在已记录。").deterministic_status == "fail"
    assert evaluate("answer_successful_write", text="已记录350毫升饮水，日期是2026年10月4日。").deterministic_status == "pass"


def test_acute_direct_warning_and_deferred_analysis_have_different_unknowns():
    direct = evaluate("acute_no_write", text="请立即呼叫120急救，不要自行开车。")
    assert direct.deterministic_status == "pass"
    deferred = evaluate("acute_no_write", [call("health_analysis", {"analysis_type": "orchestrator", "question": fixture("acute_no_write").query})])
    assert deferred.deterministic_status == "pass"
    assert "acute_safety_advice_after_analysis_not_observed" in deferred.unknowns
    assert evaluate("acute_no_write", text="无需急救，可以继续运动。").deterministic_status == "fail"


def test_record_type_alias_is_not_a_valid_production_schema_call():
    result = evaluate("water_complete", [call("health_record", {"type": "water", "data": {"amount": 350}})])
    assert result.deterministic_status == "fail"
    assert any("record_type:required" in f for f in result.failures)


def test_last_night_uses_today_wake_date_and_yesterday_keeps_yesterday():
    from datetime import datetime
    from app.services.agent_query_window import resolve_calendar_query_window

    now = datetime.fromisoformat("2026-10-04T10:00:00+08:00")
    window = resolve_calendar_query_window("昨晚睡眠", now, "sleep", timezone_name="Asia/Shanghai")
    assert window["start_date"] == window["end_date"] == "2026-10-04"
    args = {"dimension": "sleep", **window}
    assert evaluate("sleep_last_night", [call("health_query", args)]).deterministic_status == "pass"
    args["start_date"] = args["end_date"] = "2026-10-03"
    assert evaluate("sleep_last_night", [call("health_query", args)]).deterministic_status == "fail"
    yesterday = evaluate("water_unknown_and_sleep", [call("health_query", args)])
    assert yesterday.deterministic_status == "pass"


def test_preparsed_nan_and_bad_analysis_type_fail_without_crashing():
    raw = call("health_record", {})
    raw["function"]["arguments"] = {"record_type": "water", "data": {"amount": 350, "extra": float("nan")}}
    assert evaluate("water_complete", [raw]).deterministic_status == "fail"
    assert evaluate("acute_no_write", [call("health_analysis", {"analysis_type": []})]).deterministic_status == "fail"


def test_explicit_unknowns_cover_partial_schema_checker_and_missing_finish_reason():
    schema = {"type": "function", "function": {"name": "health_record", "parameters": {"type": "object", "oneOf": [], "minProperties": 2}}}
    response = {"tool_calls": [call("health_record", {"record_type": "water", "data": {"amount": 350}})]}
    result = evaluate_projection_response(fixture("water_complete"), response, authorized_tool_names={"health_record"}, tool_schemas=[schema])
    assert "provider_finish_reason_missing" in result.unknowns
    assert any("schema_combinator" in item for item in result.unknowns)
    assert any("additional_schema_constraint" in item for item in result.unknowns)
