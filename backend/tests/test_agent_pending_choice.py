"""Bounded numbered choices never act as fresh write authorization."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
from types import SimpleNamespace

import pytest

from app.models.agent_conversation import AgentConversation, AgentMessage
from app.models.user import User
from app.services.agent_pending_choice import (
    attach_pending_choice,
    resolve_message_choice,
    resolve_pending_choice,
)


NOW = datetime(2026, 9, 11, 15, 58, tzinfo=timezone.utc)
BODY = "请选择一项，回复编号：\n1. 查看昨晚睡眠\n2. 查看昨天饮食"


def _message(content=BODY, **overrides):
    return SimpleNamespace(id=7, conversation_id=5, role="assistant", content=content,
                           created_at=NOW, meta={}, **overrides)


def test_attach_binds_explicit_server_time_and_does_not_commit():
    message = _message()
    assert attach_pending_choice(message, now=NOW)
    pending = message.meta["pending_choice"]
    assert pending["source_message_id"] == 7
    assert datetime.fromisoformat(pending["issued_at"]).utcoffset() == timedelta(0)
    assert datetime.fromisoformat(pending["expires_at"]) == NOW + timedelta(minutes=10)


def test_safe_number_resolves_only_a_canonical_query_with_bound_date():
    message = _message()
    attach_pending_choice(message, now=NOW)
    result = resolve_message_choice(message, "１", now=NOW + timedelta(minutes=4))
    assert result.status == "resolved"
    # Midnight in Beijing has passed, but the pending target must not drift.
    assert result.query == "查询2026-09-11的睡眠"
    assert result.source_message_id == 7


@pytest.mark.parametrize("reply", ["0", "3", "1 删除记录", "选1", "1.5", "一"])
def test_invalid_selection_is_not_contextual_authorization(reply):
    message = _message()
    attach_pending_choice(message, now=NOW)
    assert resolve_message_choice(message, reply, now=NOW) is None


@pytest.mark.parametrize("offset", [-1, 601])
def test_expired_or_future_pending_choice_is_rejected(offset):
    message = _message()
    attach_pending_choice(message, now=NOW)
    assert resolve_message_choice(message, "1", now=NOW + timedelta(seconds=offset)) is None


def test_write_or_confirmation_choice_keeps_original_confirmation_flow():
    message = _message("请选择：\n1. 查看昨天饮食\n2. 确认记录补剂\n3. 删除上一餐")
    assert attach_pending_choice(message, now=NOW)
    for number in ("2", "3"):
        result = resolve_message_choice(message, number, now=NOW)
        assert result.status == "requires_original_confirmation"
        assert result.query is None


@pytest.mark.parametrize("content", [
    "说明：\n1. 查看昨晚睡眠\n2. 查看昨天饮食",
    "请选择：\n1. 查看昨晚睡眠\n1. 查看昨天饮食",
    "请选择：\n1. 查看昨晚睡眠\n2. 查询其他用户的睡眠",
    "请选择：\n1. 查看昨晚睡眠并保存\n2. 查看昨天饮食",
    "请选择：\n1. 查看昨晚睡眠\n2. 查看昨天饮食\n6. 查看今天运动",
    "例子：界面里会出现“请选择”字样\n1. 查看昨晚睡眠\n2. 查看昨天饮食",
])
def test_explanatory_or_unsafe_lists_are_not_read_query_choices(content):
    message = _message(content)
    attach_pending_choice(message, now=NOW)
    result = resolve_message_choice(message, "1", now=NOW)
    assert result is None or result.query is None


def test_changed_body_or_rebound_metadata_is_rejected_without_legacy_fallback():
    message = _message()
    attach_pending_choice(message, now=NOW)
    original = deepcopy(message.meta)
    message.content = BODY.replace("昨晚睡眠", "今天饮食")
    assert resolve_message_choice(message, "1", now=NOW) is None
    message.content = BODY
    message.meta = deepcopy(original)
    message.meta["pending_choice"]["source_message_id"] = 99
    assert resolve_message_choice(message, "1", now=NOW) is None
    message.meta = deepcopy(original)
    message.meta["pending_choice"]["options"][0]["query_key"] = "delete_all"
    assert resolve_message_choice(message, "1", now=NOW) is None


def test_legacy_plaintext_requires_an_aware_timestamp():
    message = _message()
    assert resolve_message_choice(message, "1", now=NOW).query == "查询2026-09-11的睡眠"
    message.created_at = NOW.replace(tzinfo=None)
    assert resolve_message_choice(message, "1", now=NOW) is None


def test_partial_reply_and_naive_server_clock_fail_closed():
    message = _message()
    message.meta = {"client_turn_finalized": False}
    assert not attach_pending_choice(message, now=NOW)
    message.meta = {}
    with pytest.raises(ValueError):
        attach_pending_choice(message, now=NOW.replace(tzinfo=None))


def test_malformed_pending_metadata_cannot_fall_back_or_crash():
    message = _message()
    attach_pending_choice(message, now=NOW)
    message.content = "没有待选项"
    message.meta["pending_choice"]["body_sha256"] = hashlib.sha256(message.content.encode()).hexdigest()
    message.meta["pending_choice"]["options"] = None
    assert resolve_message_choice(message, "1", now=NOW) is None
    message.content = BODY
    message.meta = {"completion_status": []}
    assert resolve_message_choice(message, "1", now=NOW) is None


@pytest.fixture
def stored_choice(db):
    owner, other = User(name="Synthetic owner"), User(name="Synthetic other")
    db.add_all([owner, other])
    db.flush()
    conv = AgentConversation(user_id=owner.id)
    db.add(conv)
    db.flush()
    assistant = AgentMessage(conversation_id=conv.id, role="assistant", content=BODY)
    db.add(assistant)
    db.flush()
    attach_pending_choice(assistant, now=NOW)
    db.commit()
    return owner, other, conv, assistant


def test_database_lookup_is_scoped_to_owner_and_conversation(db, stored_choice):
    owner, other, conv, _ = stored_choice
    assert resolve_pending_choice(db, user_id=owner.id, conversation_id=conv.id,
                                  reply="1", now=NOW).status == "resolved"
    assert resolve_pending_choice(db, user_id=other.id, conversation_id=conv.id,
                                  reply="1", now=NOW) is None
    assert resolve_pending_choice(db, user_id=owner.id, conversation_id=conv.id + 1,
                                  reply="1", now=NOW) is None


def test_only_exact_current_persisted_numeric_reply_may_be_skipped(db, stored_choice):
    owner, _, conv, assistant = stored_choice
    reply = AgentMessage(conversation_id=conv.id, role="user", content="1")
    db.add(reply)
    db.commit()
    args = dict(user_id=owner.id, conversation_id=conv.id, reply="1", now=NOW)
    assert resolve_pending_choice(db, **args) is None
    assert resolve_pending_choice(db, **args, current_user_message_id=reply.id).source_message_id == assistant.id
    assert resolve_pending_choice(db, **args, current_user_message_id=assistant.id) is None
    reply.content = "新的独立问题"
    db.commit()
    assert resolve_pending_choice(db, **args, current_user_message_id=reply.id) is None


def test_newest_assistant_cannot_reactivate_an_older_choice(db, stored_choice):
    owner, _, conv, _ = stored_choice
    db.add(AgentMessage(conversation_id=conv.id, role="assistant", content="其他回答"))
    db.commit()
    assert resolve_pending_choice(db, user_id=owner.id, conversation_id=conv.id,
                                  reply="1", now=NOW) is None


def test_known_medical_source_label_does_not_hide_read_choice():
    from types import SimpleNamespace
    from datetime import datetime, timezone
    from app.services.agent_pending_choice import build_pending_choice
    message = SimpleNamespace(id=99, conversation_id=3, role='assistant', meta={'client_turn_finalized': True},
        content='信息来源：用户陈述、模型推断。\n请选择一项，回复编号：\n1. 查看昨晚睡眠\n2. 查看昨天饮食')
    assert build_pending_choice(message, now=datetime.now(timezone.utc)) is not None
