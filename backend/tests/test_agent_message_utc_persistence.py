"""Source timestamps must remain UTC even on non-UTC PostgreSQL sessions."""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.models.agent_conversation import AgentConversation, AgentMessage
from tests.conftest import create_authenticated_user


def test_message_default_roundtrips_utc_on_shanghai_connection(db):
    if db.bind.dialect.name != "postgresql":
        pytest.skip("Requires PostgreSQL timestamp parameter conversion")
    user, _ = create_authenticated_user(db)
    conversation = AgentConversation(user_id=user.id)
    db.add(conversation)
    db.commit()
    db.execute(text("SET LOCAL TIME ZONE 'Asia/Shanghai'"))
    before = datetime.now(UTC).replace(tzinfo=None)
    message = AgentMessage(conversation_id=conversation.id, role="user", content="synthetic")
    db.add(message)
    db.flush()
    message_id = message.id
    db.commit()
    db.expire_all()
    persisted = db.get(AgentMessage, message_id).created_at
    after = datetime.now(UTC).replace(tzinfo=None)
    assert persisted.tzinfo is None
    assert before - timedelta(seconds=1) <= persisted <= after + timedelta(seconds=1)
