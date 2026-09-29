"""The actual recommendation must compile and execute through the daily plan."""
from datetime import datetime, timezone

import pytest

from app.services.agent_kernel.daily_read_plan import resolve_daily_read_plan
from app.services.conversation_starters import _suggest_evening
from tests.test_agent_read_plan_binding import decide
from tests.test_conversation_starters import _make_signals
from tests.test_query_reliability_outcomes import _calendar_payload, _run_scripted


LEGACY_STARTER = "总结一下我今天的健康数据，并给睡前几个小建议"


def generated_starter():
    candidate = _suggest_evening(_make_signals(local_hour=21, diet_records_today=1))
    assert candidate is not None
    return candidate.text


@pytest.mark.parametrize("text", [LEGACY_STARTER, None, "请总结一下我昨天的饮食和睡眠记录，并给我一些睡前建议"])
def test_evening_starter_binds_explicit_business_day_and_advice(text):
    text = text or generated_starter()
    plan = resolve_daily_read_plan(text, datetime(2026, 9, 29, 17, tzinfo=timezone.utc))
    assert plan is not None
    assert plan.dimensions == ("diet", "sleep")
    assert plan.is_summary and plan.asks_advice
    expected_day = "2026-09-29" if "昨天" in text else "2026-09-30"
    assert plan.start_date == plan.end_date == expected_day
    assert plan.timezone == "Asia/Shanghai"


@pytest.mark.parametrize("edit", [
    lambda text: text.replace("我今天", "我妈妈今天"),
    lambda text: "假如用户说：" + text,
    lambda text: "分析这句话：『" + text + "』",
    lambda text: "不要" + text,
    lambda text: text + "，然后删除今天的饮食",
    lambda text: text + "，再查询基因",
    lambda text: text.replace("今天", "明天"),
])
def test_edited_recommendation_does_not_retain_daily_authority(edit):
    assert resolve_daily_read_plan(edit(generated_starter()), datetime(2026, 9, 29)) is None


@pytest.mark.parametrize("dimension", ["diet", "sleep"])
def test_starter_permission_is_bound_without_trusting_model_scope(dimension):
    result = decide(generated_starter(), "health_query", {"dimension": dimension, "days": 30, "user_id": 999})
    assert result.action == "allow", result.reason
    assert result.normalized_args == {
        "dimension": dimension, "start_date": "2026-07-17", "end_date": "2026-07-17", "timezone": "Asia/Shanghai",
    }
    wrong_day = decide(generated_starter(), "health_query", {"dimension": dimension, "start_date": "2020-01-01", "end_date": "2020-01-01"})
    assert wrong_day.action == "block"


@pytest.mark.parametrize("tool,args", [
    ("health_query", {"dimension": "genetic"}),
    ("health_record", {"record_type": "weight", "data": {"weight": 70}}),
])
def test_starter_does_not_authorize_other_reads_or_writes(tool, args):
    assert decide(generated_starter(), tool, args).action == "block"


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("data_state", ["available", "no_data", "partial_failure"])
async def test_actual_starter_through_pi_gateway_and_persisted_answer(
    db, auth_user_and_headers, monkeypatch, isolated_agent_protocol_transport, legacy, data_state,
):
    user, _ = auth_user_and_headers

    def dispatch(request):
        assert request.tool_name == "health_query"
        assert request.arguments["dimension"] in {"diet", "sleep"}
        if data_state == "partial_failure" and request.arguments["dimension"] == "sleep":
            return {"status": "failed", "error": "lookup_failed", "records": []}
        rows = ([{"record_date": request.arguments["start_date"], "food_name": "合成燕麦", "calories": 300}]
                if data_state != "no_data" and request.arguments["dimension"] == "diet" else [])
        return _calendar_payload(request, records=rows, availability="available" if rows else "no_data")

    _, done, persisted, public, dispatched = await _run_scripted(
        db, user, monkeypatch, query=LEGACY_STARTER if legacy else generated_starter(),
        # The model's broad proposal must be replaced by the server-owned plan.
        first_tool="health_analysis", first_args={"analysis_type": "orchestrator"},
        dispatch=dispatch, reply="### 建议\n睡前半小时减少屏幕使用。",
        turn_id=f"evening-{legacy}-{data_state}",
    )
    assert [request.arguments["dimension"] for request in dispatched] == ["diet", "sleep"]
    assert all(request.arguments["start_date"] == request.arguments["end_date"] for request in dispatched)
    expected = "partial" if data_state == "partial_failure" else "complete"
    assert done["turn_outcome"]["status"] == expected
    assert done["completion_status"] == ("error" if expected == "partial" else "complete")
    assert not done["write_receipts"]
    assert "睡前半小时减少屏幕使用" in public
    assert "睡前半小时减少屏幕使用" in persisted.content
    if data_state != "no_data":
        assert "已记录热量合计300千卡" in public
    goals = {goal["goal_id"]: goal["status"] for goal in done["turn_outcome"]["goals"]}
    assert goals == {"diet": "verified", "sleep": "failed" if expected == "partial" else "verified", "summary_advice": "verified"}
