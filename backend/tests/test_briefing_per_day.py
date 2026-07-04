"""每日简报对话改造为每日独立 conversation 后的回归测试."""
from datetime import date

from app.tasks.notifications import (
    _briefing_title_for,
    _get_or_create_briefing_conversation,
    _write_briefing_message,
)
from app.models.agent_conversation import AgentConversation, AgentMessage


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
