"""Same user-owned daily read must have one scope across model tool choices."""
import pytest
from dataclasses import replace

from app.services.agent_kernel.capability_policy import decide_tool_capability
from app.services.agent_kernel.intent_frame import build_intent_frame
from app.services.agent_kernel.types import (
    AgentEnvelope, ExecutionContext, ToolExecutionRequest, TurnSnapshot,
)


def snapshot(message):
    envelope = AgentEnvelope(user_id=41, channel="chat", text=message)
    context = ExecutionContext.for_test(user_id=41, channel="chat")
    return TurnSnapshot(envelope=envelope, context=context,
                        intent=build_intent_frame(envelope, context))


def decide(message, tool, args):
    return decide_tool_capability(snapshot(message), ToolExecutionRequest(
        tool_name=tool, arguments=args, source="structured_or_recovered"))


@pytest.mark.parametrize("message", [
    "今日我吃了啥", "今天我吃了什么", "我今天吃了啥？给我一些建议。",
    "今天晚上我吃了什么？给我一些建议。",
    "今天饮食怎么样，给我建议", "今天睡得怎样？给我一些建议",
])
def test_compound_daily_read_is_bound_across_query_and_manage(message):
    dimension = "sleep" if "睡" in message else "diet"
    result = decide(message, "health_query", {"dimension": dimension, "days": 30})
    assert result.action == "allow", result.reason
    if "晚上" in message:
        assert result.normalized_tool_name == "health_manage"
        assert result.normalized_args == {
            "record_type": "diet", "operation": "list", "date": "2026-07-17",
            "meal_type": "dinner", "limit": 100,
        }
    else:
        assert result.normalized_args == {
            "dimension": dimension, "start_date": "2026-07-17",
            "end_date": "2026-07-17", "timezone": "Asia/Shanghai",
        }
    result = decide(message, "health_manage", {
        "record_type": dimension, "operation": "list", "date": "2020-01-01"})
    assert result.action == "allow", result.reason
    if "晚上" in message:
        assert result.normalized_args["date"] == "2026-07-17"
        assert result.normalized_args["meal_type"] == "dinner"
    else:
        assert result.normalized_tool_name == "health_query"
        assert result.normalized_args == {
            "dimension": dimension, "start_date": "2026-07-17",
            "end_date": "2026-07-17", "timezone": "Asia/Shanghai",
        }


@pytest.mark.parametrize("message", [
    "给我今天总结 给我建议", "总结一下我今天的健康情况", "今日健康总结",
])
@pytest.mark.parametrize("dimension", ["diet", "sleep"])
def test_daily_summary_is_explicit_bounded_read(message, dimension):
    result = decide(message, "health_query", {"dimension": dimension, "days": 30})
    assert result.action == "allow", result.reason
    assert result.normalized_args == {
        "dimension": dimension, "start_date": "2026-07-17",
        "end_date": "2026-07-17", "timezone": "Asia/Shanghai",
    }


@pytest.mark.parametrize("message", [
    "今天妈妈吃了啥", "假如我问今天我吃了啥", "今天我应该吃什么",
    "今天我吃了米饭", "今天我吃了什么药", "今天我吃了什么补剂",
    "不要查询今天我吃了啥", "昨天和今天我吃了啥", "明天我吃了什么",
    "分析以下例句：今天我吃了啥", "给我妈妈今天总结 给我建议",
    "假如给我今天总结", "不要给我今天总结", "明天健康总结",
    "给我今天总结，然后删除今天饮食", "今天我吃了啥？查询妈妈的睡眠",
])
def test_daily_plan_never_grants_another_subject_date_or_operation(message):
    assert decide(message, "health_query", {"dimension": "diet"}).action == "block"


def test_daily_summary_cannot_authorize_unbounded_or_sensitive_dimension():
    result = decide("给我今天总结 给我建议", "health_query", {"dimension": "genetic"})
    assert result.action == "block"


def test_model_cannot_change_explicit_date_for_shared_plan():
    result = decide("今天我吃了啥？给我建议", "health_query", {
        "dimension": "diet", "start_date": "2020-01-01", "end_date": "2020-01-01"})
    assert result.action == "block"
    assert result.reason == "health_query_calendar_window_conflict"


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["enforce", "shadow"])
async def test_rejected_model_calendar_scope_never_reaches_adapter(mode):
    from app.services.agent_kernel.tool_gateway import ToolGateway
    calls = []

    async def dispatch(request):
        calls.append(request)
        return "unexpected"

    gateway = ToolGateway(replace(snapshot("今天我吃了啥？给我建议"), policy_mode=mode))
    await gateway.execute(ToolExecutionRequest(tool_name="health_query", arguments={
        "dimension": "diet", "start_date": "2020-01-01", "end_date": "2020-01-01",
    }), dispatch)
    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", ["health_query", "health_manage"])
async def test_meal_read_dispatches_only_requested_meal(tool):
    from app.services.agent_kernel.tool_gateway import ToolGateway
    calls = []

    async def dispatch(request):
        calls.append((request.tool_name, request.arguments))
        return "[]"

    args = ({"dimension": "diet", "days": 30} if tool == "health_query" else
            {"record_type": "diet", "operation": "list", "meal_type": "breakfast"})
    await ToolGateway(snapshot("今天晚上我吃了什么？给我一些建议")).execute(
        ToolExecutionRequest(tool_name=tool, arguments=args), dispatch)
    assert calls == [("health_manage", {"record_type": "diet", "operation": "list",
                                       "date": "2026-07-17", "meal_type": "dinner", "limit": 100})]


@pytest.mark.asyncio
@pytest.mark.parametrize("message,dimension", [
    ("昨晚睡得怎样，今天是否适合锻炼", "sleep"),
    ("今天我吃了啥。分析以下建议：昨天可以早点吃饭", "diet"),
    ("给我今天总结 给我建议", "diet"),
    ("给我今天总结 给我建议", "sleep"),
])
async def test_daily_plan_reaches_owned_exact_date_postgres_rows(
    db, auth_user_and_headers, message, dimension,
):
    """Policy-approved semantic scope must survive the actual DB adapter."""
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("requires isolated TEST_DATABASE_URL PostgreSQL")
    import json
    from datetime import date
    from app.models.daily_health import DietRecord, GarminData
    from app.models.user import User
    from app.services.agent_executor import AgentExecutor
    from app.services.agent_kernel.daily_read_plan import resolve_daily_read_plan

    owner, _ = auth_user_and_headers
    other = User(username="daily-plan-other", name="Synthetic other", hashed_password="fixture")
    db.add(other)
    db.flush()
    for uid, day, label in [
        (owner.id, 16, "previous-date"), (owner.id, 17, "owned-target"),
        (other.id, 17, "other-owner"),
    ]:
        db.add(DietRecord(user_id=uid, record_date=date(2026, 7, day),
                          meal_type="午餐", food_name=label))
        db.add(GarminData(user_id=uid, record_date=date(2026, 7, day),
                         data_source="garmin", total_sleep_duration=400 + day))
    db.commit()
    original_count = db.query(DietRecord).count(), db.query(GarminData).count()
    snap = snapshot(message)
    snap = replace(snap, envelope=replace(snap.envelope, user_id=owner.id),
                   context=replace(snap.context, user_id=owner.id))
    plan = resolve_daily_read_plan(message, snap.context.current_time,
                                   timezone_name=snap.context.timezone)
    assert plan is not None
    args = next(q for q in plan.queries() if q["dimension"] == dimension)
    decision = decide_tool_capability(snap, ToolExecutionRequest(tool_name="health_query", arguments=args))
    assert decision.action == "allow", decision.reason
    executor = AgentExecutor(db)
    executor._current_user_id = owner.id
    executor._current_turn_user_message = message
    executor._agent_kernel_snapshot = snap
    raw = await executor._exec_health_query("http://unused", {}, decision.normalized_args)
    assert not raw.startswith("Error:"), raw
    result = json.loads(raw)
    assert result["window"] == {"start_date": "2026-07-17", "end_date": "2026-07-17",
                                "timezone": "Asia/Shanghai"}
    assert len(result["records"]) == 1
    assert result["records"][0]["record_date"] == "2026-07-17"
    if dimension == "diet":
        assert result["records"][0]["food_name"] == "owned-target"
    assert (db.query(DietRecord).count(), db.query(GarminData).count()) == original_count


@pytest.mark.asyncio
async def test_dinner_plan_reaches_authenticated_postgres_meal_filter(
    db, client, auth_user_and_headers, monkeypatch,
):
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("requires isolated TEST_DATABASE_URL PostgreSQL")
    import json
    from datetime import date
    from urllib.parse import urlsplit
    from app.models.daily_health import DietRecord
    from app.models.user import User
    from app.services.agent_executor import AgentExecutor
    from app.services.agent_kernel.tool_gateway import ToolGateway

    owner, headers = auth_user_and_headers
    other = User(username="dinner-plan-other", name="Synthetic other", hashed_password="fixture")
    db.add(other)
    db.flush()
    for uid, day, meal, label in [
        (owner.id, 17, "lunch", "same-day-lunch"),
        (owner.id, 17, "dinner", "owned-dinner"),
        (owner.id, 16, "dinner", "previous-dinner"),
        (other.id, 17, "dinner", "other-owner"),
    ]:
        db.add(DietRecord(user_id=uid, record_date=date(2026, 7, day),
                          meal_type=meal, food_name=label))
    db.commit()
    executor = AgentExecutor(db)
    executor._current_user_id = owner.id
    snap = snapshot("今天晚上我吃了什么？给我一些建议")
    executor._current_turn_user_message = snap.envelope.text
    snap = replace(snap, envelope=replace(snap.envelope, user_id=owner.id),
                   context=replace(snap.context, user_id=owner.id))
    executor._agent_kernel_snapshot = snap

    async def get(url, request_headers):
        parsed = urlsplit(url)
        assert parsed.path == "/api/v1/diet/records/me"
        assert request_headers == headers
        response = client.get(parsed.path + "?" + parsed.query, headers=request_headers)
        assert response.status_code == 200
        return response.text

    monkeypatch.setattr(executor, "_api_get", get)

    async def dispatch(request):
        assert request.tool_name == "health_manage"
        return await executor._exec_health_manage("http://local/api/v1", headers, request.arguments)

    result = await ToolGateway(snap).execute(ToolExecutionRequest(
        tool_name="health_query", arguments={"dimension": "diet", "days": 30}), dispatch)
    rows = json.loads(result.content)
    expected = db.query(DietRecord).filter_by(user_id=owner.id, food_name="owned-dinner").one()
    assert [row["id"] for row in rows] == [expected.id]
    assert db.query(DietRecord).count() == 4


@pytest.mark.asyncio
async def test_all_day_tool_choices_have_same_postgres_rows_beyond_list_default(
    db, client, auth_user_and_headers, monkeypatch,
):
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("requires isolated TEST_DATABASE_URL PostgreSQL")
    import json
    from datetime import date
    from urllib.parse import urlsplit
    from app.models.daily_health import DietRecord
    from app.services.agent_executor import AgentExecutor
    from app.services.agent_kernel.tool_gateway import ToolGateway

    owner, headers = auth_user_and_headers
    for index in range(25):
        db.add(DietRecord(user_id=owner.id, record_date=date(2026, 7, 17),
                          meal_type="snack", food_name=f"synthetic-{index}"))
    db.commit()
    executor = AgentExecutor(db)
    executor._current_user_id = owner.id
    snap = snapshot("今日我吃了啥")
    snap = replace(snap, envelope=replace(snap.envelope, user_id=owner.id),
                   context=replace(snap.context, user_id=owner.id))
    executor._agent_kernel_snapshot = snap
    executor._current_turn_user_message = snap.envelope.text

    async def get(url, request_headers):
        parsed = urlsplit(url)
        assert parsed.path == "/api/v1/diet/records/me"
        response = client.get(parsed.path + "?" + parsed.query, headers=request_headers)
        assert response.status_code == 200
        return response.text

    monkeypatch.setattr(executor, "_api_get", get)

    async def dispatch(request):
        if request.tool_name == "health_query":
            return await executor._exec_health_query("http://unused", headers, request.arguments)
        return await executor._exec_health_manage("http://local/api/v1", headers, request.arguments)

    results = []
    for tool, args in [
        ("health_query", {"dimension": "diet", "days": 30}),
        ("health_manage", {"record_type": "diet", "operation": "list"}),
    ]:
        result = await ToolGateway(snap).execute(
            ToolExecutionRequest(tool_name=tool, arguments=args), dispatch)
        payload = json.loads(result.content)
        rows = payload if isinstance(payload, list) else payload["records"]
        results.append({row["id"] for row in rows})
    expected = {row.id for row in db.query(DietRecord).filter_by(user_id=owner.id).all()}
    assert results[0] == results[1] == expected
    assert db.query(DietRecord).count() == 25


@pytest.mark.parametrize("message", ["帮我同步佳明数据", "请同步我的 Garmin 数据"])
def test_generic_owned_sync_has_a_dedicated_capability(message):
    decision = decide(message, "health_record", {"record_type": "garmin_sync", "data": {}})
    assert decision.action == "allow"
    assert not decision.receipt_required
    assert decision.normalized_args == {"record_type": "garmin_sync", "data": {}}


@pytest.mark.parametrize("message", [
    "刷新我的佳明数据", "同步昨天的佳明数据", "帮妈妈同步佳明数据", "同步用户42的佳明数据",
    "假如我要同步佳明数据", "不要同步我的佳明数据", "分析以下建议：帮我同步佳明数据",
    "帮我同步佳明数据，然后删除饮食", "同步Apple健康数据", "查询我的佳明数据",
])
def test_sync_capability_never_expands_to_another_owner_window_or_action(message):
    assert decide(message, "health_record", {"record_type": "garmin_sync", "data": {}}).action == "block"


def test_sync_intent_does_not_authorize_other_records_or_payloads():
    assert decide("帮我同步佳明数据", "health_record", {"record_type": "weight", "data": {"weight": 70}}).action == "block"
    assert decide("帮我同步佳明数据", "health_record", {"record_type": "garmin_sync", "data": {"days": 30}}).action == "block"


@pytest.mark.parametrize("source,expected", [("structured_or_recovered", "allow"), ("procedure_recipe_replay", "block"), ("telegram_directive", "block")])
def test_sync_does_not_bypass_source_specific_permission(source, expected):
    decision = decide_tool_capability(snapshot("帮我同步佳明数据"), ToolExecutionRequest(
        tool_name="health_record", arguments={"record_type": "garmin_sync", "data": {}}, source=source))
    assert decision.action == expected
