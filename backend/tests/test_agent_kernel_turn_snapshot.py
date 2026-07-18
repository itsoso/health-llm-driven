from datetime import datetime, timezone

from app.models.user_profile import UserProfile
from app.services.agent_kernel.context import (
    build_turn_snapshot,
    format_turn_time_context_prompt,
)


def test_turn_snapshot_uses_one_user_local_time_for_prompt_and_tool_context(db, auth_user_and_headers):
    user, _headers = auth_user_and_headers
    db.add(UserProfile(user_id=user.id, timezone="America/New_York"))
    db.commit()

    snapshot = build_turn_snapshot(
        db,
        user_id=user.id,
        channel="typed",
        text="我明天几点起床比较合理？",
        now_utc=datetime(2026, 7, 17, 2, 30, tzinfo=timezone.utc),
        run_id="run-test",
        turn_id="turn-test",
    )

    assert snapshot.context.current_time_iso == "2026-07-16T22:30:00-04:00"
    assert snapshot.context.timezone == "America/New_York"
    assert snapshot.context.run_id == "run-test"
    assert snapshot.context.turn_id == "turn-test"
    assert snapshot.intent.primary == "read"

    prompt = format_turn_time_context_prompt(snapshot.context)
    assert "用户本地当前时间: 2026-07-16T22:30:00-04:00" in prompt
    assert "用户本地今天: 2026-07-16" in prompt


def test_turn_snapshot_reference_time_normalizes_relative_record_dates(db, auth_user_and_headers):
    from app.services.llm.tool_validator import validate_tool_call

    user, _headers = auth_user_and_headers
    snapshot = build_turn_snapshot(
        db,
        user_id=user.id,
        channel="typed",
        text="记录昨天午餐吃了牛肉面",
        now_utc=datetime(2026, 7, 17, 0, 30, tzinfo=timezone.utc),
    )
    args = {
        "record_type": "diet",
        "data": {"food_items": "牛肉面", "record_date": "2026-07-09"},
    }

    result = validate_tool_call(
        "health_record",
        args,
        db=db,
        user_id=user.id,
        reference_now=snapshot.context.current_time,
    )

    assert result["data"]["data"]["record_date"] == "2026-07-17"


def test_reminder_time_follow_up_refines_only_an_active_reminder_continuation(
    db,
    auth_user_and_headers,
):
    from app.services.agent_executor import AgentExecutor

    user, _headers = auth_user_and_headers
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    executor._current_turn_user_message = "9点到20点"
    executor._current_turn_recent_messages = [
        {
            "role": "assistant",
            "content": "我会设置循环饮水提醒。请告诉我开始和结束时间。",
        }
    ]

    snapshot = executor._ensure_agent_kernel_turn(channel="typed")

    assert (snapshot.intent.primary, snapshot.intent.domain, snapshot.intent.operation) == (
        "write",
        "reminder",
        "create",
    )
    assert "continuation:reminder_schedule" in snapshot.intent.evidence
    assert executor._agent_kernel_event_bus is not None
    assert "agent.intent_refined" in [event.name for event in executor._agent_kernel_event_bus.events]


def test_time_fragment_without_a_reminder_prompt_remains_ambiguous(db, auth_user_and_headers):
    user, _headers = auth_user_and_headers
    snapshot = build_turn_snapshot(
        db,
        user_id=user.id,
        channel="typed",
        text="9点到20点",
    )

    assert snapshot.intent.primary == "unknown"
