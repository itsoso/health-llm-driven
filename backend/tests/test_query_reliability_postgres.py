"""Owned meal completeness, date filtering and cap failure against PostgreSQL."""

import json
from datetime import date
from dataclasses import replace
from urllib.parse import urlsplit
import pytest
from app.services.agent_executor import AgentExecutor
from app.services.agent_kernel.types import (
    AgentEnvelope,
    ExecutionContext,
    TurnSnapshot,
    ToolExecutionRequest,
)
from app.services.agent_kernel.intent_frame import build_intent_frame
from app.services.agent_kernel.tool_gateway import ToolGateway
from app.services.agent_kernel.daily_read_plan import resolve_daily_read_plan
from app.services.agent_daily_read_execution import daily_result_goal


@pytest.fixture(autouse=True)
def isolate(isolated_agent_protocol_transport):
    pass


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [25, 100])
async def test_dinner_rows_complete_or_explicitly_bounded(
    db, client, auth_user_and_headers, monkeypatch, count
):
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("requires isolated PostgreSQL test database")
    from app.models.daily_health import DietRecord
    from app.models.user import User

    owner, headers = auth_user_and_headers
    other = User(
        username="review-other-owner", name="Synthetic other", hashed_password="fixture"
    )
    db.add(other)
    db.flush()
    for index in range(count):
        db.add(
            DietRecord(
                user_id=owner.id,
                record_date=date(2026, 7, 17),
                meal_type="dinner",
                food_name=f"synthetic-{index}",
            )
        )
    for uid, day, meal, label in [
        (owner.id, 16, "dinner", "wrong-day"),
        (owner.id, 17, "lunch", "wrong-meal"),
        (other.id, 17, "dinner", "wrong-owner"),
    ]:
        db.add(
            DietRecord(
                user_id=uid,
                record_date=date(2026, 7, day),
                meal_type=meal,
                food_name=label,
            )
        )
    db.commit()
    message = "今天晚上我吃了什么？给我一些建议"
    envelope = AgentEnvelope(user_id=owner.id, channel="chat", text=message)
    context = ExecutionContext.for_test(user_id=owner.id, channel="chat")
    snap = TurnSnapshot(
        envelope=envelope, context=context, intent=build_intent_frame(envelope, context)
    )
    plan = resolve_daily_read_plan(
        message, context.current_time, timezone_name=context.timezone
    )
    executor = AgentExecutor(db)
    executor._current_user_id = owner.id
    executor._current_turn_user_message = message
    executor._agent_kernel_snapshot = snap

    async def get(url, request_headers):
        parsed = urlsplit(url)
        assert parsed.path == "/api/v1/diet/records/me"
        response = client.get(parsed.path + "?" + parsed.query, headers=headers)
        assert response.status_code == 200
        return response.text

    monkeypatch.setattr(executor, "_api_get", get)

    async def dispatch(request):
        return await executor._exec_health_manage(
            "http://local/api/v1", headers, request.arguments
        )

    result = await ToolGateway(snap).execute(
        ToolExecutionRequest(tool_name="health_query", arguments={"dimension": "diet"}),
        dispatch,
    )
    rows = json.loads(result.content)
    goal = daily_result_goal(plan, result.decision, result.content)
    expected_ids = {
        row.id
        for row in db.query(DietRecord)
        .filter_by(user_id=owner.id, record_date=date(2026, 7, 17), meal_type="dinner")
        .all()
    }
    assert {row["id"] for row in rows} == expected_ids
    assert db.query(DietRecord).count() == count + 3
    if count == 25:
        assert len(rows) == count, (
            "A meal list must not silently omit requested owned rows"
        )
        assert goal["status"] == "verified"
    else:
        assert goal["status"] == "failed", (
            "At cap cannot attest completeness without overflow evidence"
        )
