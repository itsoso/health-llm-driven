"""Screenshot regression: a bounded weight trend read survives a later bad tool proposal."""

from dataclasses import replace
from datetime import date, datetime

import pytest
from app.services.agent_kernel.capability_policy import decide_tool_capability
from app.services.agent_kernel.intent_frame import build_intent_frame
from app.services.agent_kernel.read_task_scope import resolve_owned_read_scope
from app.services.agent_kernel.types import (
    AgentEnvelope,
    CapabilityDecision,
    ExecutionContext,
    ToolExecutionRequest,
    ToolExecutionResult,
    TurnSnapshot,
)

REQUEST = "体重半年来增加很多 怎么办"
WINDOW = {
    "dimension": "weight",
    "days": 183,
    "start_date": "2026-04-27",
    "end_date": "2026-10-26",
    "timezone": "Asia/Shanghai",
}


def snapshot(text=REQUEST, *, owner=41, envelope_owner=41):
    envelope = AgentEnvelope(user_id=envelope_owner, channel="typed", text=text)
    context = ExecutionContext(
        user_id=owner,
        channel="typed",
        timezone="Asia/Shanghai",
        current_time=datetime.fromisoformat("2026-10-26T11:35:00+08:00"),
    )
    return TurnSnapshot(envelope, context, build_intent_frame(envelope, context))


def test_weight_trend_advice_binds_the_expressed_window_and_only_weight():
    from app.services.agent_composed_read_completion import read_scope_notices

    turn = snapshot()
    scope = resolve_owned_read_scope(turn)
    assert scope is not None
    assert scope.queries == (WINDOW,)
    assert scope.composite_advice is True
    assert any("最近183天" in notice for notice in read_scope_notices(scope))

    allowed = decide_tool_capability(
        turn, ToolExecutionRequest("health_query", {"dimension": "weight", "days": 183})
    )
    assert allowed.action == "allow", allowed.reason
    assert allowed.normalized_args == WINDOW

    blocked = decide_tool_capability(
        turn, ToolExecutionRequest("health_query", {"dimension": "diet", "days": 183})
    )
    assert blocked.action == "block"
    assert blocked.reason == "health_query_dimension_conflict"


@pytest.mark.parametrize(
    "text",
    [
        "朋友体重半年来增加很多怎么办",
        "不要查询我的体重，半年来增加很多怎么办",
        "假设体重半年来增加很多怎么办",
        "解释这句话：“体重半年来增加很多怎么办”",
        "体重半年来增加很多怎么办，只看早餐",
    ],
)
def test_weight_trend_scope_does_not_erase_owner_cancellation_or_filters(text):
    assert resolve_owned_read_scope(snapshot(text)) is None


def test_weight_trend_scope_requires_authenticated_owner_match():
    turn = snapshot()
    assert (
        resolve_owned_read_scope(
            replace(turn, context=replace(turn.context, user_id=42))
        )
        is None
    )


def test_verified_weight_read_remains_complete_after_unrequested_dimension_is_blocked():
    from app.services.agent_composed_read_completion import (
        evaluate_composed_read_completion,
    )

    scope = resolve_owned_read_scope(snapshot())
    payload = {
        "dimension": "weight",
        "window": {
            key: value
            for key, value in WINDOW.items()
            if key not in {"dimension", "days"}
        },
        "availability": "available",
        "records": [
            {"id": 1, "record_date": "2026-05-01", "source": "manual", "weight": 70.6},
            {"id": 2, "record_date": "2026-10-25", "source": "manual", "weight": 73.5},
        ],
        "limitations": ["recorded_measurements_not_continuous_history"],
    }
    completion = evaluate_composed_read_completion(
        scope,
        [
            ToolExecutionResult(
                "health_query",
                payload,
                decision=CapabilityDecision(
                    "allow", "owned_weight_trend", "health_query", WINDOW
                ),
            ),
            ToolExecutionResult(
                "health_query",
                {"status": "rejected", "error_code": "health_query_dimension_conflict"},
                decision=CapabilityDecision(
                    "block",
                    "health_query_dimension_conflict",
                    "health_query",
                    {"dimension": "diet", "days": 183},
                ),
            ),
        ],
    )
    assert completion.complete is True
    assert completion.missing_dimensions == ()
    assert "70.6" in completion.trusted_fact_summary
    assert "73.5" in completion.trusted_fact_summary


def test_weight_trend_reader_returns_only_owned_rows_in_the_bound_window(db):
    from app.models.user import User
    from app.models.weight import WeightRecord
    from app.services.agent_longitudinal_read import read_longitudinal_health_query
    from app.services.agent_query_window import QueryWindow

    users = [
        User(name=f"Synthetic {i}", email=f"weight-trend-{i}@example.test")
        for i in range(2)
    ]
    db.add_all(users)
    db.flush()
    for owner, day, weight in (
        (users[0].id, date(2026, 4, 27), 70.6),
        (users[0].id, date(2026, 10, 26), 73.5),
        (users[0].id, date(2026, 4, 26), 90.0),
        (users[1].id, date(2026, 7, 1), 99.0),
    ):
        db.add(WeightRecord(user_id=owner, record_date=day, weight=weight))
    db.flush()

    result = read_longitudinal_health_query(
        db,
        users[0].id,
        "weight",
        QueryWindow(date(2026, 4, 27), date(2026, 10, 26), "Asia/Shanghai"),
    )
    assert [row["weight"] for row in result["records"]] == [70.6, 73.5]
    assert result["window"] == {
        "start_date": "2026-04-27",
        "end_date": "2026-10-26",
        "timezone": "Asia/Shanghai",
    }


@pytest.mark.asyncio
async def test_weight_trend_runtime_keeps_verified_answer_after_bad_sibling_proposal(
    db, auth_user_and_headers, monkeypatch
):
    from app.models.weight import WeightRecord
    from app.services.agent_executor import AgentExecutor

    user, _ = auth_user_and_headers
    now = datetime.fromisoformat("2026-10-26T11:35:00+08:00")
    clock = ExecutionContext.now.__func__
    monkeypatch.setattr(
        ExecutionContext,
        "now",
        classmethod(lambda cls, **kw: clock(cls, **{**kw, "now_utc": now})),
    )
    db.add_all(
        [
            WeightRecord(user_id=user.id, record_date=date(2026, 5, 1), weight=70.6),
            WeightRecord(user_id=user.id, record_date=date(2026, 10, 25), weight=73.5),
        ]
    )
    db.commit()

    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    executor._current_turn_user_message = REQUEST
    executor._start_agent_kernel_turn(user_id=user.id, message=REQUEST, channel="typed")

    weight_result = await executor._execute_tool(
        "health_query", {"dimension": "weight", "days": 183}, None
    )
    diet_result = await executor._execute_tool(
        "health_query", {"dimension": "diet", "days": 183}, None
    )

    assert "70.6" in weight_result and "73.5" in weight_result
    assert "health_query_dimension_conflict" in diet_result
    assert executor._all_scoped_reads_verified() is True
    assert executor._unresolved_read_failure_notice() is None
    completion = executor._composed_read_completion()
    assert completion.complete is True
    assert "70.6" in completion.trusted_fact_summary
    assert "73.5" in completion.trusted_fact_summary
