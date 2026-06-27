import json
import uuid
from unittest.mock import patch

from app.api import agent as agent_api
from app.services.agent_executor import AgentExecutor


def _parse_sse_events(raw: str) -> list[dict]:
    events: list[dict] = []
    for block in raw.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        for line in block.splitlines():
            if line.startswith("data:"):
                events.append(json.loads(line.removeprefix("data:").strip()))
    return events


def test_agent_stream_emits_inline_card_before_done_and_keeps_done_cards(client, db, auth_user_and_headers, monkeypatch):
    user, headers = auth_user_and_headers
    agent_api._RECENT_DUP_CACHE.clear()

    class _DBProxy:
        def __init__(self, real):
            object.__setattr__(self, "_real", real)

        def __getattr__(self, name):
            if name == "close":
                return lambda: None
            return getattr(self._real, name)

        def __setattr__(self, name, val):
            setattr(self._real, name, val)

    def _session_factory():
        return _DBProxy(db)

    async def fake_run_stream(self, **kwargs):
        assert kwargs["user_id"] == user.id
        yield {"event": "agent_start", "data": {"conversation_id": 42}}
        yield {"event": "token", "data": {"content": "今天先做一个低摩擦行动。"}}
        yield {"event": "done", "data": {"conversation_id": 42, "message_id": None}}

    descriptor = {
        "type": "agenda_action",
        "data": {
            "id": "hydration-1",
            "title": "喝 200ml 温水",
            "subtitle": "起床后补水",
            "scheduled_for": "08:00",
            "source": {"object_type": "health_protocol", "object_id": 12},
            "deep_link": "/agenda",
        },
        "actions": [
            {
                "action": "complete_agenda",
                "endpoint": "/agenda/complete",
                "label": "完成",
                "payload": {"source": {"object_type": "health_protocol", "object_id": 12}},
                "style": "primary",
            }
        ],
    }

    monkeypatch.setattr(AgentExecutor, "run_stream", fake_run_stream)
    monkeypatch.setattr("app.services.inline_cards.build_cards", lambda _db, _user_id, _msg: [descriptor])
    monkeypatch.setattr("app.services.inline_cards.extract_inline_card_blocks", lambda _text: [])

    with patch("app.database.SessionLocal", new=_session_factory):
        with client.stream(
            "POST",
            "/api/v1/agent/stream",
            headers=headers,
            json={"message": f"今天我该做什么 {uuid.uuid4().hex}"},
        ) as resp:
            assert resp.status_code == 200
            raw = "".join(resp.iter_text())

    events = _parse_sse_events(raw)
    event_names = [event["event"] for event in events]

    assert event_names == ["agent_start", "token", "card", "done"]
    assert events[2]["data"] == {
        "descriptor": descriptor,
        "anchor": "after_current_token",
    }
    assert events[3]["data"]["cards"] == [descriptor]
