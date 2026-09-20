"""Weekly self-analysis must bind dates without weakening owner authorization."""
from datetime import date, datetime
import json

import pytest

from app.services.agent_kernel.health_semantics import health_read_has_nonself_subject
from app.services.agent_kernel.intent_frame import build_intent_frame
from app.services.agent_kernel.read_task_scope import resolve_owned_read_scope
from app.services.agent_kernel.tool_gateway import ToolGateway
from app.services.agent_kernel.types import AgentEnvelope, ExecutionContext, TurnSnapshot, ToolExecutionRequest


def snapshot(text, now="2026-09-20T09:00:00+08:00", mode="enforce"):
    envelope = AgentEnvelope(user_id=41, channel="typed", text=text)
    context = ExecutionContext(user_id=41, channel="typed", timezone="Asia/Shanghai",
                               current_time=datetime.fromisoformat(now))
    return TurnSnapshot(envelope, context, build_intent_frame(envelope, context), policy_mode=mode)


@pytest.mark.parametrize("verb", ["分析", "复盘", "总结", "请分析一下"])
@pytest.mark.parametrize("owner", ["", "我的", "本人"])
def test_analysis_prefix_is_not_another_person(verb, owner):
    text = f"{verb}{owner}本周的饮食和睡眠"
    assert not health_read_has_nonself_subject(text)
    scope = resolve_owned_read_scope(snapshot(text))
    assert scope is not None
    for domain in ("diet", "sleep"):
        assert scope.query(domain) == {"dimension": domain, "start_date": "2026-09-14",
                                       "end_date": "2026-09-20", "timezone": "Asia/Shanghai"}


@pytest.mark.parametrize("text", [
    "分析张三本周的饮食和睡眠", "分析朋友的本周饮食和睡眠",
    "分析我的和李四的本周饮食", "不要分析本周的饮食和睡眠",
    "假如分析本周的饮食和睡眠", "“分析本周的饮食和睡眠”",
    "分析本周和上周的饮食", "分析本周晚上的饮食", "分析本周出差期间的睡眠",
    "分析本周的饮食，然后删除睡眠记录",
])
def test_unowned_or_unbound_week_does_not_gain_scope(text):
    assert resolve_owned_read_scope(snapshot(text)) is None


@pytest.mark.parametrize("mode", ["enforce", "shadow"])
@pytest.mark.asyncio
async def test_weekly_batch_dispatches_frozen_authorized_dates(mode):
    dispatched = []
    async def dispatch(request):
        dispatched.append(request)
        return '{"records": []}'
    result = await ToolGateway(snapshot("分析本周的饮食和睡眠", mode=mode)).execute(
        ToolExecutionRequest("health_query_batch", {"queries": [{"dimension": "diet"}, {"dimension": "sleep"}]}), dispatch)
    assert result.decision.action != "block"
    assert len(dispatched) == 1
    assert dispatched[0].arguments["queries"] == [
        {"dimension": d, "start_date": "2026-09-14", "end_date": "2026-09-20", "timezone": "Asia/Shanghai"}
        for d in ("diet", "sleep")
    ]


@pytest.mark.parametrize("text,now,start,end", [
    ("分析这周的睡眠", "2026-09-20T17:00:00+00:00", "2026-09-21", "2026-09-21"),
    ("分析上周的饮食和睡眠", "2026-09-20T09:00:00+08:00", "2026-09-07", "2026-09-13"),
    ("分析本周一的睡眠", "2026-09-20T09:00:00+08:00", "2026-09-14", "2026-09-14"),
])
def test_week_is_local_calendar_not_rolling_seven_days(text, now, start, end):
    scope = resolve_owned_read_scope(snapshot(text, now))
    assert scope is not None
    assert scope.query("sleep")["start_date"] == start
    assert scope.query("sleep")["end_date"] == end


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["enforce", "shadow"])
@pytest.mark.parametrize("query", [
    {"dimension": "diet", "user_id": 99},
    {"dimension": "diet", "start_date": "2026-09-01", "end_date": "2026-09-20"},
    {"dimension": "sleep", "timezone": "UTC"},
    {"dimension": "workout"},
])
async def test_model_cannot_expand_week_or_change_owner(mode, query):
    dispatched = []
    async def dispatch(request):
        dispatched.append(request)
        return '{}'
    result = await ToolGateway(snapshot("分析本周的饮食和睡眠", mode=mode)).execute(
        ToolExecutionRequest("health_query_batch", {"queries": [query]}), dispatch)
    assert result.decision.action == "block"
    assert not dispatched


@pytest.mark.asyncio
async def test_weekly_gateway_to_executor_reads_only_owned_week_rows(db):
    from app.models.user import User
    from app.models.daily_health import DietRecord, GarminData
    from app.services.agent_executor import AgentExecutor
    owner = User(username="week-a", email="week-a@example.test", name="Synthetic A", hashed_password="fixture")
    other = User(username="week-b", email="week-b@example.test", name="Synthetic B", hashed_password="fixture")
    db.add_all([owner, other])
    db.flush()
    for uid, day in [(owner.id, 13), (owner.id, 14), (owner.id, 20), (owner.id, 21), (other.id, 15)]:
        db.add(DietRecord(user_id=uid, record_date=date(2026, 9, day), meal_type="午餐", food_name="Synthetic meal"))
        db.add(GarminData(user_id=uid, record_date=date(2026, 9, day), data_source="garmin", total_sleep_duration=400))
    db.flush()
    turn = snapshot("分析本周的饮食和睡眠")
    from dataclasses import replace
    envelope = replace(turn.envelope, user_id=owner.id)
    context = replace(turn.context, user_id=owner.id)
    turn = replace(turn, envelope=envelope, context=context, intent=build_intent_frame(envelope, context))
    executor = AgentExecutor(db)
    executor._current_user_id = owner.id
    executor._agent_kernel_snapshot = turn
    executor._current_turn_user_message = envelope.text
    async def dispatch(request):
        return await executor._exec_health_query_batch("", {}, request.arguments)
    result = await ToolGateway(turn).execute(ToolExecutionRequest("health_query_batch", {
        "queries": [{"dimension": "diet", "days": 30}, {"dimension": "sleep", "days": 30}]
    }), dispatch)
    payload = json.loads(result.content)
    assert payload["status"] == "success"
    assert len(payload["results"]) == 2
    for item in payload["results"]:
        assert item["window"]["start_date"] == "2026-09-14"
        assert item["window"]["end_date"] == "2026-09-20"
        assert [r["record_date"] for r in item["records"]] == ["2026-09-14", "2026-09-20"]
