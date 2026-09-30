"""Login policy must be identical across form and JSON entry points."""

import uuid

import pytest

from app.models.user import User
from app.services.auth import auth_service


def test_json_login_rejects_unapproved_account(client, db):
    password = "review-policy-test-password"
    username = f"pending_{uuid.uuid4().hex[:10]}"
    user = User(
        username=username,
        email=f"{username}@example.test",
        hashed_password=auth_service.get_password_hash(password),
        name="Pending review user",
        is_active=True,
        is_approved=False,
    )
    db.add(user)
    db.commit()

    response = client.post(
        "/api/v1/auth/login/json",
        json={"username": username, "password": password},
    )

    assert response.status_code == 403
    assert "审核" in response.json()["detail"]


@pytest.fixture
def dual_login_user(db):
    user = User(
        username="dual_login_fixture",
        email="dual-login@example.test",
        phone="+8613800138991",
        hashed_password=auth_service.get_password_hash("dual-login-test-password"),
        name="Dual login test user",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    return user


@pytest.mark.parametrize("endpoint", ["/login", "/login/json"])
@pytest.mark.parametrize("identifier", ["13800138991", "+86 138 0013 8991", "dual-login@example.test"])
def test_phone_and_email_password_login_resolve_same_account(
    client, dual_login_user, endpoint, identifier
):
    payload = {"username": identifier, "password": "dual-login-test-password"}
    response = client.post(
        f"/api/v1/auth{endpoint}",
        **({"json": payload} if endpoint.endswith("json") else {"data": payload}),
    )

    assert response.status_code == 200
    assert response.json()["user"]["id"] == dual_login_user.id
    token = response.json()["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["id"] == dual_login_user.id


@pytest.mark.parametrize("identifier", ["13800138991", "dual-login@example.test"])
@pytest.mark.parametrize("policy", ["wrong_password", "no_password", "inactive", "unapproved"])
def test_password_login_keeps_credential_and_account_policy(
    client, db, dual_login_user, identifier, policy
):
    if policy == "no_password":
        dual_login_user.hashed_password = None
    elif policy == "inactive":
        dual_login_user.is_active = False
    elif policy == "unapproved":
        dual_login_user.is_approved = False
    db.commit()

    response = client.post(
        "/api/v1/auth/login/json",
        json={
            "username": identifier,
            "password": "wrong" if policy == "wrong_password" else "dual-login-test-password",
        },
    )

    assert response.status_code == (401 if policy in {"wrong_password", "no_password"} else 403)
    assert "access_token" not in response.json()


def test_sms_and_password_login_share_existing_account(client, dual_login_user, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "auth_phone_code_dev_echo", True)
    monkeypatch.setattr(settings, "registration_invitation_enforcement_enabled", True)
    sent = client.post("/api/v1/auth/phone/code", json={"phone": "13800138991"})
    assert sent.status_code == 200
    otp = client.post(
        "/api/v1/auth/phone/verify",
        json={"phone": "13800138991", "code": sent.json()["dev_code"]},
    )
    password = client.post(
        "/api/v1/auth/login/json",
        json={"username": "dual-login@example.test", "password": "dual-login-test-password"},
    )

    assert otp.status_code == password.status_code == 200
    assert otp.json()["outcome"] == "authenticated"
    assert otp.json()["user"]["id"] == password.json()["user"]["id"] == dual_login_user.id
