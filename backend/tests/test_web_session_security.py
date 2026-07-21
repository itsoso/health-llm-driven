"""Web browser sessions must not depend on script-readable bearer storage."""

import uuid

from app.config import settings
from app.models.user import User
from app.services.auth import auth_service


def _password_user(db):
    password = "web-session-test-password"
    username = f"web_session_{uuid.uuid4().hex[:10]}"
    user = User(
        username=username,
        email=f"{username}@example.test",
        hashed_password=auth_service.get_password_hash(password),
        name="Web session user",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user, password


def test_web_login_sets_http_only_cookie_and_cookie_authenticates(client, db):
    user, password = _password_user(db)

    login = client.post(
        "/api/v1/auth/login/json",
        headers={"X-Auth-Transport": "web-cookie"},
        json={"username": user.username, "password": password},
    )

    assert login.status_code == 200
    cookie = login.headers.get("set-cookie", "")
    assert "health_session=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    assert "Max-Age=63072000" in cookie
    assert login.json()["access_token"] == "__web_cookie_session__"
    assert client.get("/api/v1/auth/me").status_code == 200


def test_native_login_still_returns_bearer_token(client, db):
    user, password = _password_user(db)

    login = client.post(
        "/api/v1/auth/login/json",
        json={"username": user.username, "password": password},
    )

    assert login.status_code == 200
    token = login.json()["access_token"]
    assert token != "__web_cookie_session__"
    assert auth_service.decode_token(token)["sub"] == str(user.id)


def test_cookie_mutation_requires_trusted_origin(client, db, monkeypatch):
    user, password = _password_user(db)
    monkeypatch.setattr(settings, "web_session_allowed_origins", "http://testserver")
    login = client.post(
        "/api/v1/auth/login/json",
        headers={"X-Auth-Transport": "web-cookie"},
        json={"username": user.username, "password": password},
    )
    assert login.status_code == 200

    missing_origin = client.post(
        "/api/v1/auth/password/change",
        json={"old_password": password, "new_password": "updated-password-123"},
    )
    assert missing_origin.status_code == 403

    foreign_origin = client.post(
        "/api/v1/auth/password/change",
        headers={"Origin": "https://attacker.example"},
        json={"old_password": password, "new_password": "updated-password-123"},
    )
    assert foreign_origin.status_code == 403

    trusted_origin = client.post(
        "/api/v1/auth/password/change",
        headers={"Origin": "http://testserver"},
        json={"old_password": password, "new_password": "updated-password-123"},
    )
    assert trusted_origin.status_code == 200


def test_bearer_mutation_does_not_require_browser_origin(client, db):
    user, password = _password_user(db)
    token = auth_service.create_access_token({"sub": str(user.id)})

    response = client.post(
        "/api/v1/auth/password/change",
        headers={"Authorization": f"Bearer {token}"},
        json={"old_password": password, "new_password": "updated-password-123"},
    )

    assert response.status_code == 200


def test_web_logout_clears_cookie(client, db, monkeypatch):
    user, password = _password_user(db)
    monkeypatch.setattr(settings, "web_session_allowed_origins", "http://testserver")
    client.post(
        "/api/v1/auth/login/json",
        headers={"X-Auth-Transport": "web-cookie"},
        json={"username": user.username, "password": password},
    )

    logout = client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "http://testserver"},
    )

    assert logout.status_code == 200
    assert "health_session=" in logout.headers.get("set-cookie", "")
    assert client.get("/api/v1/auth/me").status_code == 401


def test_cookie_family_proxy_can_switch_back_without_browser_token_storage(
    client,
    db,
    monkeypatch,
):
    user, password = _password_user(db)
    monkeypatch.setattr(settings, "web_session_allowed_origins", "http://testserver")
    origin = {"Origin": "http://testserver"}
    login = client.post(
        "/api/v1/auth/login/json",
        headers={"X-Auth-Transport": "web-cookie"},
        json={"username": user.username, "password": password},
    )
    assert login.status_code == 200
    assert client.post("/api/v1/family/groups", headers=origin, json={"name": "Test"}).status_code == 200
    member = client.post(
        "/api/v1/family/members",
        headers=origin,
        json={"name": "Managed", "relationship_type": "other"},
    )
    assert member.status_code == 200

    switched = client.post(
        "/api/v1/family/switch",
        headers=origin,
        json={"user_id": member.json()["user_id"]},
    )
    assert switched.status_code == 200
    assert switched.json()["access_token"] == "__web_cookie_session__"
    assert client.get("/api/v1/family/proxy-status").json()["is_proxy_mode"] is True

    restored = client.post("/api/v1/family/switch-back", headers=origin)
    assert restored.status_code == 200
    status_response = client.get("/api/v1/family/proxy-status")
    assert status_response.status_code == 200
    assert status_response.json()["is_proxy_mode"] is False
    assert status_response.json()["acting_as"] == user.id
