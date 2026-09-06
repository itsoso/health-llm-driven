"""Cookie changes must not grant consent or dispatch an old tab's data as another user."""
from unittest.mock import Mock

import pytest
from app.config import settings

from app.services.web_session import WEB_SESSION_COOKIE
from sqlalchemy.orm import sessionmaker
from tests.conftest import create_authenticated_user


@pytest.fixture(autouse=True)
def _trusted_test_origin(monkeypatch):
    monkeypatch.setattr(settings, "web_session_allowed_origins", "http://testserver")


def test_cookie_account_switch_cannot_accept_another_subjects_disclosure(client, db):
    first, _ = create_authenticated_user(db)
    second, token = create_authenticated_user(db)
    client.cookies.set(WEB_SESSION_COOKIE, token)
    headers = {"Origin": "http://testserver", "X-Reva-AI-Subject": str(first.id)}
    response = client.put("/api/v1/auth/ai-consent", headers=headers,
                          json={"accepted": True, "policy_version": "2026-09-06.1"})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "auth_session_changed"
    from app.services.ai_consent import get_ai_consent
    assert not get_ai_consent(db, second.id)["accepted"]


@pytest.mark.parametrize("path", ["/api/v1/auth/ai-consent", "/api/v1/agent/send"])
def test_expected_subject_is_assertion_not_target_selection(client, db, monkeypatch, path):
    first, _ = create_authenticated_user(db)
    _, token = create_authenticated_user(db)
    headers = {"Authorization": f"Bearer {token}", "X-Reva-AI-Subject": str(first.id)}
    dispatch = Mock(side_effect=AssertionError("mismatched actor must not dispatch"))
    monkeypatch.setattr("app.api.agent.require_ai_consent", dispatch)
    response = (client.get(path, headers=headers) if path.endswith("ai-consent") else
                client.post(path, headers=headers, json={"message": "synthetic draft"}))
    assert response.status_code == 409
    dispatch.assert_not_called()


def test_cookie_consent_write_requires_subject_and_returns_bound_subject(client, db):
    user, token = create_authenticated_user(db)
    client.cookies.set(WEB_SESSION_COOKIE, token)
    body = {"accepted": True, "policy_version": "2026-09-06.1"}
    headers = {"Origin": "http://testserver"}
    assert client.put("/api/v1/auth/ai-consent", headers=headers, json=body).status_code == 409
    headers["X-Reva-AI-Subject"] = str(user.id)
    response = client.put("/api/v1/auth/ai-consent", headers=headers, json=body)
    assert response.status_code == 200
    assert response.json()["subject_id"] == user.id


def test_cookie_ai_request_requires_subject_even_when_current_account_consented(client, db, monkeypatch):
    from app.services import ai_consent
    user, token = create_authenticated_user(db)
    ai_consent.update_ai_consent(db, user.id, True, ai_consent.POLICY_VERSION)
    monkeypatch.setattr(ai_consent, "SessionLocal", sessionmaker(bind=db.get_bind()))
    client.cookies.set(WEB_SESSION_COOKIE, token)
    admit = Mock(side_effect=AssertionError("unbound old-tab draft must not dispatch"))
    monkeypatch.setattr("app.api.agent._admit_agent_runtime", admit)
    response = client.post("/api/v1/agent/send", headers={"Origin": "http://testserver"},
                           json={"message": "synthetic old-tab draft"})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "auth_session_changed"
    admit.assert_not_called()
    # Reading the disclosure and ordinary account data remains available.
    assert client.get("/api/v1/auth/ai-consent").status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 200
