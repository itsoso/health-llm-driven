"""Historical self reports must not masquerade as current clinical evidence."""

from datetime import datetime, timedelta, timezone

from app.models.conversation_memory import ConversationMemory
from app.services.conversation_memory_service import (
    get_relevant_memories,
    get_top_memory_for_opener,
)


def test_expired_reports_are_excluded_from_context_and_openers(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    now = datetime.now(timezone.utc)
    for kind in ("medical", "fact"):
        db.add(ConversationMemory(
            user_id=user.id, memory_type=kind, content=f"expired-{kind}",
            status="active", expires_at=now - timedelta(seconds=1),
        ))
    db.add(ConversationMemory(
        user_id=user.id, memory_type="medical", content="current-self-report",
        status="active", expires_at=now + timedelta(days=1),
    ))
    db.commit()
    assert "expired-" not in get_relevant_memories(db, user.id)
    assert [m.content for m in get_top_memory_for_opener(db, user.id)] == ["current-self-report"]


def test_medical_memory_retains_report_date_and_uncertain_clinical_status(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    db.add(ConversationMemory(
        user_id=user.id, memory_type="medical", content="我之前有胃部不适",
        status="active", created_at=datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc),
    ))
    db.commit()
    context = get_relevant_memories(db, user.id)
    assert "2026-09-01" in context
    assert "用户自述" in context
    assert "未经临床确认" in context
    assert "[医嘱]" not in context
