"""Bounded daily-summary advice checks; not a general factual verifier."""
from types import SimpleNamespace

import pytest

from app.services import agent_daily_read_execution as daily
from app.services.agent_kernel.daily_read_plan import DailyReadPlan


@pytest.mark.parametrize("text", ["", " \n\t "])
def test_empty_advice_is_not_a_completed_advice_goal(text):
    assert daily.summary_advice_contract_failure(text) == "summary_advice_unavailable"


@pytest.mark.parametrize("text", [
    "已记录热量1020千卡，继续规律饮食。", "今天约一千零二十卡路里。",
    "睡眠七小时。", "睡了7.5小时。", "时长四百二十分钟。",
    "睡眠评分80。", "评分八十分。", "评分为八十。", "热量为300 kcal。",
    "不应把1020千卡当作全天摄入。",
])
def test_advice_cannot_repeat_observation_numbers_even_in_qualifiers(text):
    assert daily.summary_advice_contract_failure(text) == "summary_advice_repeats_measurement"


@pytest.mark.parametrize("text", [
    "今天只吃了早餐。", "今日总共摄入这些食物。", "全天只吃这些，太少了。",
    "你的摄入不足，应该加餐。", "这些记录表明摄入明显过量。",
    "不能据此判断摄入不足，但你的摄入过量。",
])
def test_advice_cannot_infer_actual_complete_or_inadequate_intake(text):
    assert daily.summary_advice_contract_failure(text) == "summary_advice_infers_complete_intake"


@pytest.mark.parametrize("text", [
    "保持规律饮食和睡眠。", "可以先补充漏记，再观察整体情况。",
    "不能据此判断摄入不足。", "不能仅根据这些记录判断摄入过量。",
    "记录不代表全天实际摄入，也无法判断完整摄入。",
    "没有证据说明摄入不足。", "不应断言今天只吃了这些。",
    "无法判断全天总共摄入了什么。", "可先核对记录是否完整。",
])
def test_qualitative_advice_and_explicit_uncertainty_pass(text):
    assert daily.summary_advice_contract_failure(text) is None


@pytest.mark.parametrize("payload", [
    {"records": [{"calories": 300}]},
    {"records": [{"record_date": "2026-09-12"}], "availability": "unavailable"},
    {"data": [{"record_date": "2026-09-12"}]},
    {"records": [{"record_date": "2026-09-12"}], "availability": "no_data"},
])
def test_summary_goal_cannot_verify_payload_that_fact_projection_rejects(payload):
    plan = DailyReadPlan(dimensions=("diet", "sleep"), start_date="2026-09-12",
                         end_date="2026-09-12", timezone="Asia/Shanghai", is_summary=True)
    decision = SimpleNamespace(normalized_tool_name="health_query", normalized_args=plan.queries()[0], action="allow")
    goal = daily.daily_result_goal(plan, decision, payload)
    assert goal["status"] == "failed"
    assert goal["reason_code"] in ("query_result_unavailable", "query_result_scope_conflict")


def test_ordinary_daily_query_keeps_existing_attestation_contract():
    plan = DailyReadPlan(dimensions=("diet",), start_date="2026-09-12",
                         end_date="2026-09-12", timezone="Asia/Shanghai")
    decision = SimpleNamespace(normalized_tool_name="health_query", normalized_args=plan.queries()[0], action="allow")
    assert daily.daily_result_goal(plan, decision, {"records": [{"calories": 300}]})["status"] == "verified"
