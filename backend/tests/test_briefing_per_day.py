"""每日简报对话改造为每日独立 conversation 后的回归测试."""
from datetime import UTC, date, datetime

from app.tasks.notifications import (
    _briefing_title_for,
    _get_or_create_briefing_conversation,
    _write_briefing_message,
)
from app.models.agent_conversation import AgentConversation, AgentMessage
from app.services.agent_conversation_service import AgentConversationService


def test_briefing_title_uses_date(db):
    assert _briefing_title_for(date(2026, 4, 25)) == "每日健康简报 · 04-25"
    assert _briefing_title_for(date(2026, 1, 1)) == "每日健康简报 · 01-01"


def test_per_day_creates_distinct_conversations(db):
    """两个不同日期 → 两条不同 conversation, 互不干扰."""
    c1 = _get_or_create_briefing_conversation(db, user_id=42, target_date=date(2026, 4, 25))
    c2 = _get_or_create_briefing_conversation(db, user_id=42, target_date=date(2026, 4, 26))
    assert c1.id != c2.id
    assert c1.title == "每日健康简报 · 04-25"
    assert c2.title == "每日健康简报 · 04-26"


def test_same_day_idempotent(db):
    """同一天调用两次 → 复用同一条 conversation."""
    c1 = _get_or_create_briefing_conversation(db, user_id=42, target_date=date(2026, 4, 25))
    c2 = _get_or_create_briefing_conversation(db, user_id=42, target_date=date(2026, 4, 25))
    assert c1.id == c2.id


def test_write_message_lands_in_correct_day_bucket(db):
    _write_briefing_message(db, user_id=7, content="今日 4-25 简报", target_date=date(2026, 4, 25))
    _write_briefing_message(db, user_id=7, content="今日 4-26 简报", target_date=date(2026, 4, 26))

    convs = db.query(AgentConversation).filter(AgentConversation.user_id == 7).order_by(AgentConversation.title).all()
    assert len(convs) == 2
    assert convs[0].title == "每日健康简报 · 04-25"
    assert convs[1].title == "每日健康简报 · 04-26"

    msgs_25 = db.query(AgentMessage).filter(AgentMessage.conversation_id == convs[0].id).all()
    msgs_26 = db.query(AgentMessage).filter(AgentMessage.conversation_id == convs[1].id).all()
    assert len(msgs_25) == 1 and "4-25" in msgs_25[0].content
    assert len(msgs_26) == 1 and "4-26" in msgs_26[0].content


def test_refreshing_existing_briefing_does_not_reclaim_latest_conversation(db, monkeypatch):
    """Background data refreshes must not masquerade as user chat activity."""
    target_date = date(2026, 4, 25)
    _write_briefing_message(db, user_id=7, content="旧简报", target_date=target_date)

    briefing = db.query(AgentConversation).filter(
        AgentConversation.user_id == 7,
        AgentConversation.title == "每日健康简报 · 04-25",
    ).one()
    briefing.updated_at = datetime(2026, 4, 25, 10, 0)

    user_conversation = AgentConversation(
        user_id=7,
        title="午餐记录",
        updated_at=datetime(2026, 4, 25, 11, 0),
    )
    db.add(user_conversation)
    db.flush()
    db.add(AgentMessage(
        conversation_id=user_conversation.id,
        role="user",
        content="记录午餐",
    ))
    db.commit()

    class NoonDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 4, 25, 12, 0, tzinfo=tz or UTC)

    monkeypatch.setattr("app.tasks.notifications.datetime", NoonDatetime)

    _write_briefing_message(db, user_id=7, content="刷新后的简报", target_date=target_date)

    db.refresh(briefing)
    refreshed_message = db.query(AgentMessage).filter(
        AgentMessage.conversation_id == briefing.id,
        AgentMessage.role == "assistant",
    ).one()
    ordered = AgentConversationService(db).get_conversations(user_id=7)

    assert refreshed_message.content == "刷新后的简报"
    assert briefing.updated_at == datetime(2026, 4, 25, 10, 0)
    assert ordered[0].id == user_conversation.id
