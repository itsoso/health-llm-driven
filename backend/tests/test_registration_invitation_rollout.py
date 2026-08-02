"""Rollout policy for invitation-only phone registration."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.config import settings
from app.models.invitation import InvitationCode, UserApplication
from app.models.registration_invitation import PhoneRegistrationGrant
from app.models.user import User
from app.services.auth import auth_service
from app.services.registration_invitation import create_phone_registration_grant


@pytest.fixture(autouse=True)
def _rollout_settings(monkeypatch):
    monkeypatch.setattr(settings, "auth_phone_code_dev_echo", True)
    monkeypatch.setattr(settings, "auth_phone_code_resend_seconds", 0)
    monkeypatch.setattr(settings, "auth_phone_registration_auto_approve", True)
    monkeypatch.setattr(settings, "registration_invitation_rollout_enabled", True)
    monkeypatch.setattr(settings, "registration_invitation_enforcement_enabled", True)
    monkeypatch.setattr(
        settings,
        "registration_invitation_digest_key",
        "registration-invitation-rollout-tests-32-byte-key",
    )


def _otp(client, phone: str) -> str:
    response = client.post("/api/v1/auth/phone/code", json={"phone": phone})
    assert response.status_code == 200
    return response.json()["dev_code"]


def _existing_user(db, phone: str, suffix: str = "existing") -> User:
    user = User(
        username=f"rollout_{suffix}",
        name="Existing user",
        phone=phone,
        phone_verified_at=datetime.now(UTC),
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _auth_headers(user: User) -> dict[str, str]:
    token = auth_service.create_access_token({"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


def test_rollout_modes_are_explicit_and_fail_safe(monkeypatch):
    matrix = [
        (False, False, "legacy_only"),
        (True, False, "ota_compatibility"),
        (True, True, "enforced"),
        (False, True, "rollback_closed"),
    ]
    for rollout, enforcement, expected in matrix:
        monkeypatch.setattr(settings, "registration_invitation_rollout_enabled", rollout)
        monkeypatch.setattr(settings, "registration_invitation_enforcement_enabled", enforcement)
        assert settings.registration_invitation_mode == expected


def test_enforcement_off_supports_pre_ota_legacy_phone_registration(
    client, db, monkeypatch
):
    monkeypatch.setattr(settings, "registration_invitation_enforcement_enabled", False)

    response = client.post(
        "/api/v1/auth/phone/login",
        json={"phone": "13800138201", "code": _otp(client, "13800138201")},
    )

    assert response.status_code == 200
    assert response.json()["is_new_user"] is True
    assert db.query(User).filter(User.phone == "+8613800138201").count() == 1


@pytest.mark.parametrize("enforcement", [False, True])
def test_existing_phone_login_works_in_both_enforcement_states(
    client, db, monkeypatch, enforcement
):
    monkeypatch.setattr(settings, "registration_invitation_enforcement_enabled", enforcement)
    user = _existing_user(db, "+8613800138202", suffix=str(enforcement).lower())

    response = client.post(
        "/api/v1/auth/phone/login",
        json={"phone": "13800138202", "code": _otp(client, "13800138202")},
    )

    assert response.status_code == 200
    assert response.json()["user"]["id"] == user.id
    assert response.json()["is_new_user"] is False


def test_enforcement_blocks_all_public_legacy_account_creation_paths(
    client, db
):
    legacy_code = InvitationCode(code="LEGACY88", max_uses=10, used_count=0, is_active=True)
    db.add(legacy_code)
    db.commit()

    phone_response = client.post(
        "/api/v1/auth/phone/login",
        json={"phone": "13800138203", "code": _otp(client, "13800138203")},
    )
    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "username": "legacy_register_user",
            "email": "legacy-register@example.com",
            "password": "safe-test-password",
            "name": "Legacy Register",
            "invite_code": settings.default_invite_code,
        },
    )
    application_response = client.post(
        "/api/v1/invitation/apply",
        json={
            "email": "legacy-application@example.com",
            "name": "Legacy Application",
            "phone": "13800138204",
            "invitation_code": legacy_code.code,
            "password": "safe-test-password",
        },
    )

    for response in (phone_response, register_response, application_response):
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "REGISTRATION_INVITATION_REQUIRED"
    assert db.query(User).count() == 0
    assert db.query(UserApplication).count() == 0


def test_enforcement_blocks_approval_that_would_create_a_legacy_user(client, db):
    admin = User(
        username="rollout_admin",
        name="Admin",
        is_active=True,
        is_approved=True,
        is_admin=True,
    )
    invite = InvitationCode(code="REVIEW88", max_uses=10, used_count=1, is_active=True)
    db.add_all([admin, invite])
    db.flush()
    application = UserApplication(
        email="pending-legacy@example.com",
        name="Pending legacy",
        phone="13800138205",
        hashed_password=auth_service.get_password_hash("safe-test-password"),
        invitation_code_id=invite.id,
        status="pending",
    )
    db.add(application)
    db.commit()
    db.refresh(admin)
    db.refresh(application)

    response = client.post(
        f"/api/v1/invitation/applications/{application.id}/review",
        json={"approved": True, "note": "legacy approval"},
        headers=_auth_headers(admin),
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "REGISTRATION_INVITATION_REQUIRED"
    assert db.query(User).filter(User.email == application.email).count() == 0
    db.refresh(application)
    assert application.status == "pending"


@pytest.mark.parametrize("rollout", [True, False])
def test_enforcement_blocks_pending_wechat_approval_in_enforced_and_rollback_modes(
    client, db, monkeypatch, rollout
):
    monkeypatch.setattr(settings, "registration_invitation_rollout_enabled", rollout)
    admin = User(
        username=f"wechat_gate_admin_{rollout}",
        name="Admin",
        is_active=True,
        is_approved=True,
        is_admin=True,
    )
    pending = User(
        username=f"pending_wechat_{rollout}",
        name="Pending WeChat",
        wechat_openid=f"wechat-openid-{rollout}",
        is_active=True,
        is_approved=False,
    )
    db.add_all([admin, pending])
    db.commit()
    db.refresh(admin)
    db.refresh(pending)

    response = client.post(
        f"/api/v1/invitation/applications/{-pending.id}/review",
        json={"approved": True, "note": "must not bypass rollout gate"},
        headers=_auth_headers(admin),
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "REGISTRATION_INVITATION_REQUIRED"
    db.refresh(pending)
    assert pending.is_approved is False
    assert pending.is_active is True


def test_enforcement_still_allows_rejecting_pending_wechat_for_cleanup(client, db):
    admin = User(
        username="wechat_reject_admin",
        name="Admin",
        is_active=True,
        is_approved=True,
        is_admin=True,
    )
    pending = User(
        username="pending_wechat_reject",
        name="Pending WeChat",
        wechat_openid="wechat-openid-reject",
        is_active=True,
        is_approved=False,
    )
    db.add_all([admin, pending])
    db.commit()
    db.refresh(admin)
    db.refresh(pending)

    response = client.post(
        f"/api/v1/invitation/applications/{-pending.id}/review",
        json={"approved": False, "note": "cleanup"},
        headers=_auth_headers(admin),
    )

    assert response.status_code == 200
    db.refresh(pending)
    assert pending.is_approved is False
    assert pending.is_active is False


def test_compatibility_window_keeps_pending_wechat_approval_semantics(
    client, db, monkeypatch
):
    monkeypatch.setattr(settings, "registration_invitation_enforcement_enabled", False)
    admin = User(
        username="wechat_compat_admin",
        name="Admin",
        is_active=True,
        is_approved=True,
        is_admin=True,
    )
    pending = User(
        username="pending_wechat_compat",
        name="Pending WeChat",
        wechat_openid="wechat-openid-compat",
        is_active=True,
        is_approved=False,
    )
    db.add_all([admin, pending])
    db.commit()
    db.refresh(admin)
    db.refresh(pending)

    response = client.post(
        f"/api/v1/invitation/applications/{-pending.id}/review",
        json={"approved": True, "note": "compatibility window"},
        headers=_auth_headers(admin),
    )

    assert response.status_code == 200
    db.refresh(pending)
    assert pending.is_approved is True
    assert pending.is_active is True


@pytest.mark.parametrize("approved", [True, False])
def test_forged_negative_id_cannot_review_non_wechat_user(
    client, db, monkeypatch, approved
):
    monkeypatch.setattr(settings, "registration_invitation_enforcement_enabled", False)
    admin = User(
        username=f"negative_id_admin_{approved}",
        name="Admin",
        is_active=True,
        is_approved=True,
        is_admin=True,
    )
    ordinary = User(
        username=f"ordinary_negative_id_target_{approved}",
        name="Ordinary",
        is_active=True,
        is_approved=False,
        wechat_openid=None,
    )
    db.add_all([admin, ordinary])
    db.commit()
    db.refresh(admin)
    db.refresh(ordinary)

    response = client.post(
        f"/api/v1/invitation/applications/{-ordinary.id}/review",
        json={"approved": approved, "note": "forged negative id"},
        headers=_auth_headers(admin),
    )

    assert response.status_code == 404
    db.refresh(ordinary)
    assert ordinary.is_approved is False
    assert ordinary.is_active is True


@pytest.mark.parametrize("approved", [True, False])
def test_inactive_wechat_user_cannot_be_reviewed_or_revived_by_negative_id(
    client, db, monkeypatch, approved
):
    monkeypatch.setattr(settings, "registration_invitation_enforcement_enabled", False)
    admin = User(
        username=f"inactive_wechat_admin_{approved}",
        name="Admin",
        is_active=True,
        is_approved=True,
        is_admin=True,
    )
    rejected = User(
        username=f"inactive_wechat_target_{approved}",
        name="Rejected WeChat",
        is_active=False,
        is_approved=False,
        wechat_openid=f"inactive-wechat-openid-{approved}",
    )
    db.add_all([admin, rejected])
    db.commit()
    db.refresh(admin)
    db.refresh(rejected)

    response = client.post(
        f"/api/v1/invitation/applications/{-rejected.id}/review",
        json={"approved": approved, "note": "must remain terminal"},
        headers=_auth_headers(admin),
    )

    assert response.status_code == 404
    db.refresh(rejected)
    assert rejected.is_approved is False
    assert rejected.is_active is False


def test_pending_application_list_only_includes_active_unapproved_wechat_users(
    client, db
):
    admin = User(
        username="pending_wechat_list_admin",
        name="Admin",
        is_active=True,
        is_approved=True,
        is_admin=True,
    )
    active_pending = User(
        username="active_pending_wechat",
        name="Active Pending",
        is_active=True,
        is_approved=False,
        wechat_openid="active-pending-openid",
    )
    inactive_rejected = User(
        username="inactive_rejected_wechat",
        name="Inactive Rejected",
        is_active=False,
        is_approved=False,
        wechat_openid="inactive-rejected-openid",
    )
    db.add_all([admin, active_pending, inactive_rejected])
    db.commit()
    db.refresh(admin)
    db.refresh(active_pending)
    db.refresh(inactive_rejected)

    response = client.get(
        "/api/v1/invitation/applications?status=pending",
        headers=_auth_headers(admin),
    )

    assert response.status_code == 200
    virtual_ids = {item["id"] for item in response.json() if item["id"] < 0}
    assert virtual_ids == {-active_pending.id}
    assert -inactive_rejected.id not in virtual_ids


def test_invitation_stats_only_count_active_unapproved_wechat_users(client, db):
    admin = User(
        username="pending_wechat_stats_admin",
        name="Admin",
        is_active=True,
        is_approved=True,
        is_admin=True,
    )
    active_pending = User(
        username="stats_active_pending_wechat",
        name="Stats Active Pending",
        is_active=True,
        is_approved=False,
        wechat_openid="stats-active-openid",
    )
    inactive_rejected = User(
        username="stats_inactive_rejected_wechat",
        name="Stats Inactive Rejected",
        is_active=False,
        is_approved=False,
        wechat_openid="stats-inactive-openid",
    )
    db.add_all([admin, active_pending, inactive_rejected])
    db.commit()
    db.refresh(admin)

    response = client.get(
        "/api/v1/invitation/stats",
        headers=_auth_headers(admin),
    )

    assert response.status_code == 200
    assert response.json()["applications"]["pending_wechat_users"] == 1
    assert response.json()["applications"]["pending"] == 1


def test_default_invite_code_cannot_authorize_invited_phone_registration(
    client, db, monkeypatch
):
    monkeypatch.setattr(settings, "default_invite_code", "ABCDEFGH")
    grant = create_phone_registration_grant(db, "13800138206")
    db.commit()

    response = client.post(
        "/api/v1/auth/invited-registration",
        json={
            "verified_phone_ticket": grant.token,
            "manual_code": settings.default_invite_code,
            "idempotency_key": "rollout-default-code-0001",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVITATION_INVALID"
    assert db.query(User).count() == 0


def test_safe_rollback_closes_new_registration_but_keeps_existing_login(
    client, db, monkeypatch
):
    monkeypatch.setattr(settings, "registration_invitation_rollout_enabled", False)
    monkeypatch.setattr(settings, "registration_invitation_enforcement_enabled", True)
    existing = _existing_user(db, "+8613800138207", suffix="rollback")

    existing_response = client.post(
        "/api/v1/auth/phone/verify",
        json={"phone": "13800138207", "code": _otp(client, "13800138207")},
    )
    unknown_response = client.post(
        "/api/v1/auth/phone/verify",
        json={"phone": "13800138208", "code": _otp(client, "13800138208")},
    )
    inspect_response = client.post(
        "/api/v1/auth/invitations/inspect",
        json={"manual_code": "ABCDEFGH"},
    )
    register_response = client.post(
        "/api/v1/auth/invited-registration",
        json={
            "verified_phone_ticket": "A" * 22,
            "manual_code": "ABCDEFGH",
            "idempotency_key": "rollout-rollback-key-0001",
        },
    )

    assert existing_response.status_code == 200
    assert existing_response.json()["outcome"] == "authenticated"
    assert existing_response.json()["user"]["id"] == existing.id
    for response in (unknown_response, inspect_response, register_response):
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "REGISTRATION_CLOSED"
    assert db.query(User).count() == 1
    assert db.query(PhoneRegistrationGrant).count() == 0


def test_compatibility_register_does_not_log_invitation_credentials(
    client, monkeypatch, caplog
):
    monkeypatch.setattr(settings, "registration_invitation_enforcement_enabled", False)
    monkeypatch.setattr(settings, "default_invite_code", "SAFE2345")
    caplog.set_level("INFO", logger="app.api.auth")

    response = client.post(
        "/api/v1/auth/register",
        json={
            "username": "compat_register_user",
            "email": "compat-register@example.com",
            "password": "safe-test-password",
            "name": "Compatibility Register",
            "invite_code": "SAFE2345",
        },
    )

    assert response.status_code == 200
    assert "SAFE2345" not in caplog.text


def test_environment_example_documents_all_modes_and_required_production_secrets():
    example = Path(".env.example").read_text(encoding="utf-8")

    for contract in (
        "false/false = legacy_only",
        "true/false = ota_compatibility",
        "true/true = enforced",
        "false/true = rollback_closed",
        "REGISTRATION_INVITATION_DIGEST_KEY=",
        "ALIYUN_SMS_ACCESS_KEY_ID=",
        "ALIYUN_SMS_ACCESS_KEY_SECRET=",
        "ALIYUN_ACCESS_KEY_ID=",
        "ALIYUN_ACCESS_KEY_SECRET=",
        "ALIYUN_SMS_SIGN_NAME=",
        "ALIYUN_SMS_TEMPLATE_CODE=",
        "REGISTRATION_INVITATION_SMS_SIGN_NAME=",
        "REGISTRATION_INVITATION_SMS_TEMPLATE_CODE=",
    ):
        assert contract in example
    assert "仅本地/短期兼容" in example
    assert "专用 key 为空时复用" in example
    assert "ID 与 SECRET 必须成对设置" in example
    assert "生产邀请值不得与其相同" in example
