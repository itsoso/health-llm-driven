"""Composed reads cannot borrow ownership, dates, or write authority."""

from datetime import datetime
from dataclasses import replace

import pytest

from app.services.agent_kernel.intent_frame import build_intent_frame
from app.services.agent_kernel.read_task_scope import (
    has_owned_sync_instruction,
    resolve_owned_read_scope,
    resolve_sync_status_query,
)
from app.services.agent_kernel.types import (
    ActionableReference,
    AgentEnvelope,
    ExecutionContext,
    TurnSnapshot,
)


def snapshot(text, now="2026-09-13T09:00:00+08:00"):
    env = AgentEnvelope(user_id=41, channel="typed", text=text)
    context = ExecutionContext(
        current_time=datetime.fromisoformat(now),
        timezone="Asia/Shanghai",
        user_id=41,
        channel="typed",
    )
    return TurnSnapshot(env, context, build_intent_frame(env, context))


@pytest.mark.parametrize(
    "text",
    [
        "同步一下佳明，再分析昨晚睡眠。",
        "麻烦把我的佳明数据刷新一下，然后看看昨晚睡得怎么样。",
        "拉取一下我的 Garmin 数据，然后分析2026-09-11的睡眠。",
    ],
)
def test_explicit_sync_then_sleep_allows_status_for_same_frozen_window(text):
    turn = snapshot(text)
    scope = resolve_owned_read_scope(turn)
    assert scope is not None
    assert has_owned_sync_instruction(text)
    assert resolve_sync_status_query(turn) == {
        **scope.query("sleep"),
        "dimension": "garmin",
    }


@pytest.mark.parametrize(
    "text",
    [
        "同步佳明中张三的数据，再分析昨晚睡眠。",
        "同步佳明里王小明的数据，再分析昨晚睡眠。",
        "同步佳明账号123的数据，再分析昨晚睡眠。",
        "同步朋友的佳明数据，再分析昨晚睡眠。",
        "假如同步佳明，再分析昨晚睡眠。",
        "“同步佳明，再分析昨晚睡眠。”",
        "别分析我昨天的行动",
        "先不分析我昨天的行动",
        "分析我昨天的行动，先别",
        "“分析我昨天的行动”",
        "'分析我昨天的行动'",
        "分析张三昨天的行动",
        "复盘李四昨日的健康情况",
        "分析以下例句：分析我昨天的行动",
        "分析昨天睡眠，然后记录体重70公斤",
        "分析昨天睡眠，然后加入今天的计划",
        "分析昨天睡眠，然后更新饮食记录",
    ],
)
def test_non_authorizing_composition_does_not_gain_read_or_sync_scope(text):
    turn = snapshot(text)
    assert resolve_owned_read_scope(turn) is None
    assert resolve_sync_status_query(turn) is None
    assert not has_owned_sync_instruction(text)


@pytest.mark.parametrize(
    "text",
    [
        "分析昨天和今天的睡眠",
        "分析2026-09-10和2026-09-12的睡眠",
        "佳明同步完成了吗，分析明天睡眠",
        "佳明同步完成了吗，分析上个月的睡眠",
        "佳明同步完成了吗，分析昨天和今天睡眠",
    ],
)
def test_ambiguous_or_unresolved_date_never_falls_back_to_today(text):
    turn = snapshot(text)
    assert resolve_owned_read_scope(turn) is None
    assert resolve_sync_status_query(turn) is None


@pytest.mark.parametrize("text", ["分析我昨天的行动", "复盘我昨日的健康情况"])
def test_broad_retrospective_has_only_declared_supported_domains(text):
    scope = resolve_owned_read_scope(snapshot(text))
    assert scope is not None
    assert {q["dimension"] for q in scope.queries} == {"diet", "sleep"}
    assert {q["start_date"] for q in scope.queries} == {"2026-09-12"}
    assert scope.limitations == ("scope_diet_sleep_only",)
    assert scope.query("genetic") is None
    assert not has_owned_sync_instruction(text)


@pytest.mark.parametrize(
    "text",
    [
        "给我今天的睡眠计划，分析一下",
        "分析昨天的健康情况，给我饮食计划",
        "帮我起草今天的计划",
        "看看我的睡眠，给我今天的计划",
    ],
)
def test_plan_draft_cannot_borrow_its_date_or_domain_for_historical_read(text):
    assert resolve_owned_read_scope(snapshot(text)) is None


def test_plan_draft_can_follow_an_explicitly_dated_domain_read():
    scope = resolve_owned_read_scope(snapshot("先分析昨天的睡眠，再起草今天的计划"))
    assert scope is not None
    assert scope.queries == (
        {
            "dimension": "sleep",
            "start_date": "2026-09-12",
            "end_date": "2026-09-12",
            "timezone": "Asia/Shanghai",
        },
    )


def test_status_only_uses_business_timezone_not_datetime_host_day():
    query = resolve_sync_status_query(
        snapshot("佳明数据同步完成了吗？", now="2026-09-12T20:00:00+00:00")
    )
    assert query["start_date"] == query["end_date"] == "2026-09-13"


def continued_snapshot(
    text="再查一下", *, sync_status=True, created_at="2026-09-12T10:00:00+08:00"
):
    reference = ActionableReference(
        kind="owned_read_task",
        source_message_id="123",
        data={
            "version": "owned-read-task.v1",
            "created_at": created_at,
            "queries": [
                {
                    "dimension": "sleep",
                    "start_date": "2026-09-12",
                    "end_date": "2026-09-12",
                    "timezone": "Asia/Shanghai",
                }
            ],
            "sync_status": sync_status,
            "limitations": [],
        },
    )
    return replace(snapshot(text), actionable_references=(reference,))


def test_server_continuation_preserves_previous_absolute_day_without_sync_write():
    turn = continued_snapshot()
    scope = resolve_owned_read_scope(turn)
    assert scope is not None
    assert scope.query("sleep")["start_date"] == "2026-09-12"
    assert resolve_sync_status_query(turn) == {
        **scope.query("sleep"),
        "dimension": "garmin",
    }
    assert not has_owned_sync_instruction(turn.envelope.text)


def test_read_only_continuation_does_not_invent_sync_status_authority():
    turn = continued_snapshot(sync_status=False)
    assert resolve_owned_read_scope(turn) is not None
    assert resolve_sync_status_query(turn) is None


@pytest.mark.parametrize(
    "text",
    [
        "不要再查一下",
        "假如再查一下",
        "“再查一下”",
        "再查一下朋友的睡眠",
        "继续分析，然后删除昨天睡眠",
    ],
)
def test_reference_does_not_authorize_non_short_followup(text):
    turn = continued_snapshot(text)
    assert resolve_owned_read_scope(turn) is None
    assert resolve_sync_status_query(turn) is None


def test_expired_continuation_cannot_refresh_relative_dates():
    turn = continued_snapshot(created_at="2026-09-11T10:00:00+08:00")
    assert resolve_owned_read_scope(turn) is None
    assert resolve_sync_status_query(turn) is None
