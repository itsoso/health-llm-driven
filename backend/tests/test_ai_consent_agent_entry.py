"""Reject undisclosed AI use before an SSE 200 or persistent Agent turn."""
from unittest.mock import Mock

import pytest
from sqlalchemy.orm import sessionmaker

from app.services import ai_consent


@pytest.mark.parametrize("path", ["stream", "send"])
def test_unconsented_agent_request_does_not_admit_or_start_stream(client, db, auth_user_and_headers, monkeypatch, path):
    _, headers = auth_user_and_headers
    monkeypatch.setattr(ai_consent, "SessionLocal", sessionmaker(bind=db.get_bind()))
    admit = Mock(side_effect=AssertionError("no Agent work before consent"))
    monkeypatch.setattr("app.api.agent._admit_agent_runtime", admit)
    response = client.post(f"/api/v1/agent/{path}", headers=headers,
                           json={"message": "合成测试消息", "client_turn_id": f"consent-entry-{path}"})
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "ai_consent_required"
    assert "text/event-stream" not in response.headers.get("content-type", "")
    admit.assert_not_called()
