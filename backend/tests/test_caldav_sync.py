"""CalDAV 同步:凭据加密往返 + 忙碌块同步(mock caldav 连接)+ 端点。"""
import uuid

import pytest

from app.models.user import User
from app.services import caldav_sync as svc


def _mk_user(db) -> User:
    u = User(username=f"cd_{uuid.uuid4().hex[:6]}", email=f"cd_{uuid.uuid4().hex[:6]}@x.com",
             hashed_password="x", name="cd", is_active=True, is_approved=True)
    db.add(u); db.commit(); db.refresh(u)
    return u


@pytest.fixture
def auth_headers(client, db):
    u = _mk_user(db)
    from app.services.auth import auth_service
    return u, {"Authorization": f"Bearer {auth_service.create_access_token({'sub': str(u.id)})}"}


def test_credential_encryption_roundtrip(db):
    u = _mk_user(db)
    cred = svc.save_credentials(db, u.id, url="https://caldav.example.com", username="me@x.com", password="app-pw-123")
    # 明文不落库
    assert "app-pw-123" not in (cred.encrypted_credentials or "")
    got = cred.get_credentials()
    assert got["url"] == "https://caldav.example.com" and got["password"] == "app-pw-123"


def test_calendar_endpoints(client, db, auth_headers):
    user, headers = auth_headers
    r = client.put("/api/v1/calendar/credentials", headers=headers,
                   json={"url": "https://cd", "username": "me", "password": "pw"})
    assert r.status_code == 200, r.text
    s = client.get("/api/v1/calendar/status", headers=headers)
    assert s.status_code == 200 and s.json()["connected"] is True


def test_ssrf_guard_rejects_http_and_private():
    for bad in ["http://caldav.example.com", "https://127.0.0.1/dav", "https://localhost/dav"]:
        with pytest.raises(ValueError):
            svc._assert_safe_caldav_url(bad)


def test_put_credentials_rejects_non_https(client, db, auth_headers):
    user, headers = auth_headers
    r = client.put("/api/v1/calendar/credentials", headers=headers,
                   json={"url": "http://cd", "username": "me", "password": "pw"})
    assert r.status_code == 422
