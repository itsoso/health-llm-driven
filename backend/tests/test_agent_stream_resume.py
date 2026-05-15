import uuid
from unittest.mock import patch

import pytest

from app.models.user import User
from app.services.agent_executor import AgentExecutor


def _make_user(db, name="agent_resume"):
    user = User(
        username=f"{name}_{uuid.uuid4().hex[:8]}",
        email=f"{name}_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        name=name,
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_agent_start_includes_conversation_id_for_resume(db):
    user = _make_user(db)
    executor = AgentExecutor(db)

    async def _fake_call_llm(self, messages, tools):
        return "可以，先休息一天。"

    with patch.object(AgentExecutor, "_call_llm", new=_fake_call_llm):
        events = []
        async for event in executor.run_stream(user.id, "今天还能跑步吗？"):
            events.append(event)
            if event.get("event") == "agent_start":
                break

    start = events[0]
    assert start["event"] == "agent_start"
    assert isinstance(start["data"].get("conversation_id"), int)
