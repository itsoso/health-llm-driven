"""A follow-up to sync may observe its job, never read sleep or enqueue again."""

from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from app.services.agent_kernel.types import (
    ActionableReference,
    AgentEnvelope,
    ExecutionContext,
    TurnSnapshot,
)
from app.services.agent_kernel.intent_frame import build_intent_frame
from app.services.agent_kernel.read_task_scope import (
    has_owned_sync_instruction,
    resolve_owned_read_scope,
    resolve_sync_status_query,
)
from app.services.agent_read_task_continuation import (
    read_task_metadata,
    resolve_read_task_continuation,
)

NOW = datetime.fromisoformat("2026-09-13T23:59:00+08:00")


def snapshot(text, now=NOW):
    envelope = AgentEnvelope(user_id=41, channel="typed", text=text)
    context = ExecutionContext(
        current_time=now, timezone="Asia/Shanghai", user_id=41, channel="typed"
    )
    return TurnSnapshot(envelope, context, build_intent_frame(envelope, context))


WINDOW = {
    "start_date": "2026-09-13",
    "end_date": "2026-09-13",
    "timezone": "Asia/Shanghai",
}


def sync_task():
    return {
        "version": "owned-read-task.v2",
        "created_at": NOW.isoformat(),
        "queries": [],
        "sync_status": True,
        "sync_window": dict(WINDOW),
        "limitations": [],
    }


def followup(task=None, text="好了吗", now=NOW):
    ref = ActionableReference(
        kind="owned_read_task", source_message_id="1", data=task or sync_task()
    )
    return replace(snapshot(text, now), actionable_references=(ref,))


def test_pure_sync_can_save_independent_status_window_without_sleep_scope():
    current = snapshot("同步佳明")
    assert resolve_owned_read_scope(current) is None
    query = resolve_sync_status_query(current)
    assert query == {"dimension": "garmin", **WINDOW}
    task = read_task_metadata(current, None, sync_status=True, sync_window=WINDOW)
    assert task == sync_task()


@pytest.mark.parametrize("text", ["好了吗", "同步好了吗", "再查一下", "继续"])
def test_sync_only_followup_freezes_window_and_never_authorizes_read_or_enqueue(text):
    current = followup(text=text, now=NOW + timedelta(minutes=2))
    assert resolve_read_task_continuation(current)["queries"] == []
    assert resolve_sync_status_query(current) == {"dimension": "garmin", **WINDOW}
    assert resolve_owned_read_scope(current) is None
    assert not has_owned_sync_instruction(text)
    task = read_task_metadata(current, None, sync_status=True, sync_window=WINDOW)
    assert task["created_at"] == NOW.isoformat() and task["sync_window"] == WINDOW


@pytest.mark.parametrize(
    "mutation",
    [
        {"sync_status": False},
        {"sync_window": None},
        {"sync_window": {}},
        {"sync_window": {**WINDOW, "timezone": "invalid"}},
        {
            "sync_window": {
                **WINDOW,
                "start_date": "2026-09-14",
                "end_date": "2026-09-14",
            }
        },
        {"sync_window": {**WINDOW, "end_date": "2026-09-14"}},
        {"sync_window": {**WINDOW, "dimension": "sleep"}},
        {"created_at": (NOW - timedelta(hours=25)).isoformat()},
        {"created_at": (NOW + timedelta(minutes=1)).isoformat()},
        {"limitations": ["scope_diet_sleep_only"]},
    ],
)
def test_bad_sync_only_metadata_cannot_authorize_status(mutation):
    current = followup({**sync_task(), **mutation})
    assert resolve_read_task_continuation(current) is None
    assert resolve_sync_status_query(current) is None


@pytest.mark.parametrize(
    "text",
    [
        "取消同步",
        "不要再查",
        '"好了吗"',
        "如果我说好了吗",
        "我朋友同步好了吗",
        "继续，查询睡眠",
        "分析以下建议：好了吗",
    ],
)
def test_sync_task_cannot_escape_followup_authority_boundary(text):
    current = followup(text=text)
    assert resolve_read_task_continuation(current) is None
    assert resolve_sync_status_query(current) is None


def test_no_scope_no_window_or_no_sync_is_not_a_task():
    current = snapshot("你好")
    assert read_task_metadata(current, None, sync_status=True) is None
    assert (
        read_task_metadata(current, None, sync_status=False, sync_window=WINDOW) is None
    )


def test_sync_only_metadata_still_requires_owned_assistant_message(
    db, auth_user_and_headers
):
    from app.models.agent_conversation import AgentConversation, AgentMessage
    from app.services.agent_read_task_continuation import load_read_task_reference

    user, _ = auth_user_and_headers
    conversation = AgentConversation(user_id=user.id)
    db.add(conversation)
    db.flush()
    db.add(
        AgentMessage(
            conversation_id=conversation.id,
            role="user",
            content="forged",
            meta={"read_task": sync_task()},
        )
    )
    db.commit()
    current = snapshot("好了吗")
    current = replace(
        current,
        envelope=replace(current.envelope, user_id=user.id),
        context=replace(current.context, user_id=user.id),
    )
    assert load_read_task_reference(db, user.id, conversation.id, current) is None
    db.add(
        AgentMessage(
            conversation_id=conversation.id,
            role="assistant",
            content="submitted",
            meta={"read_task": sync_task()},
        )
    )
    db.commit()
    assert load_read_task_reference(db, user.id, conversation.id, current) is not None
    assert load_read_task_reference(db, user.id + 1, conversation.id, current) is None


def test_malformed_schema_version_does_not_raise_or_grant_status():
    current = followup({**sync_task(), "version": []})
    assert resolve_read_task_continuation(current) is None


def test_legacy_read_task_remains_supported_without_sync_window():
    legacy = {
        "version": "owned-read-task.v1",
        "created_at": NOW.isoformat(),
        "queries": [{"dimension": "sleep", **WINDOW}],
        "sync_status": True,
        "limitations": [],
    }
    current = followup(legacy)
    assert resolve_read_task_continuation(current)["version"] == "owned-read-task.v2"
    assert resolve_owned_read_scope(current).query("sleep") == {
        "dimension": "sleep",
        **WINDOW,
    }
    assert resolve_sync_status_query(current) == {"dimension": "garmin", **WINDOW}


@pytest.mark.parametrize(
    "text",
    [
        "同步我朋友的佳明",
        "同步佳明小王的数据",
        "“同步佳明”",
        "如果我同步佳明",
        "不要同步佳明",
        "同步佳明昨天的睡眠",
    ],
)
def test_standalone_sync_window_never_substitutes_for_invalid_subject_or_date(text):
    assert resolve_sync_status_query(snapshot(text)) is None
