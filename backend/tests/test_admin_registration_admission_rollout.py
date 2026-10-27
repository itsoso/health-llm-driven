"""Administrator admission is independent of legacy invitation settings."""

import pytest

from app.config import settings
from app.models.agent_audit_log import AgentAuditLog
from app.models.user import User
from app.services.auth import auth_service


def _headers(user: User) -> dict[str, str]:
    token = auth_service.create_access_token({"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


def _admin(db, suffix: str) -> User:
    admin = User(
        username=f"admission_admin_{suffix}",
        email=f"admission-admin-{suffix}@example.com",
        name="Admission Admin",
        is_active=True,
        is_approved=True,
        is_admin=True,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin


@pytest.mark.parametrize("rollout", [True, False])
@pytest.mark.parametrize("kind", ["ordinary", "wechat"])
def test_admin_can_approve_existing_accounts_even_with_stale_invitation_flags(
    client, db, monkeypatch, rollout, kind
):
    monkeypatch.setattr(settings, "registration_invitation_rollout_enabled", rollout)
    monkeypatch.setattr(settings, "registration_invitation_enforcement_enabled", True)
    admin = _admin(db, f"block-{rollout}-{kind}")
    target = User(
        username=f"legacy_target_{rollout}_{kind}",
        email=f"legacy-target-{rollout}-{kind}@example.com",
        name="Legacy Target",
        wechat_openid=(f"legacy-openid-{rollout}" if kind == "wechat" else None),
        is_active=True,
        is_approved=False,
    )
    db.add(target)
    db.commit()
    db.refresh(target)

    response = client.put(
        f"/api/v1/admin/users/{target.id}/approve",
        headers=_headers(admin),
        json={"is_approved": True},
    )

    assert response.status_code == 200
    db.refresh(target)
    assert target.is_approved is True
    assert target.is_active is True
    audits = db.query(AgentAuditLog).filter(AgentAuditLog.user_id == admin.id).all()
    assert [item.action for item in audits] == ["privileged_request_authorized"]


@pytest.mark.parametrize("rollout", [True, False])
def test_admin_can_create_users_even_with_stale_invitation_flags(
    client, db, monkeypatch, rollout
):
    monkeypatch.setattr(settings, "registration_invitation_rollout_enabled", rollout)
    monkeypatch.setattr(settings, "registration_invitation_enforcement_enabled", True)
    admin = _admin(db, f"create-block-{rollout}")

    response = client.post(
        "/api/v1/admin/users/create",
        headers=_headers(admin),
        json={
            "username": f"blocked_admin_create_{rollout}",
            "email": f"blocked-admin-create-{rollout}@example.com",
            "password": "safe-test-password",
            "name": "Blocked Create",
            "is_approved": True,
        },
    )

    assert response.status_code == 200
    created = db.query(User).filter(User.id == response.json()["user_id"]).one()
    assert created.is_active and created.is_approved
    assert not created.is_admin
    assert created.phone is None
    assert auth_service.verify_password("safe-test-password", created.hashed_password)
    assert db.query(User).count() == 2


@pytest.mark.parametrize("rollout", [True, False])
def test_enforcement_keeps_admin_rejection_cleanup_available(
    client, db, monkeypatch, rollout
):
    monkeypatch.setattr(settings, "registration_invitation_rollout_enabled", rollout)
    monkeypatch.setattr(settings, "registration_invitation_enforcement_enabled", True)
    admin = _admin(db, f"reject-{rollout}")
    target = User(
        username=f"cleanup_target_{rollout}",
        name="Cleanup Target",
        is_active=True,
        is_approved=True,
    )
    db.add(target)
    db.commit()

    response = client.put(
        f"/api/v1/admin/users/{target.id}/approve",
        headers=_headers(admin),
        json={"is_approved": False},
    )

    assert response.status_code == 200
    db.refresh(target)
    assert target.is_approved is False


@pytest.mark.parametrize("rollout", [True, False])
def test_non_enforced_modes_preserve_admin_approval_and_create(
    client, db, monkeypatch, rollout
):
    monkeypatch.setattr(settings, "registration_invitation_rollout_enabled", rollout)
    monkeypatch.setattr(settings, "registration_invitation_enforcement_enabled", False)
    admin = _admin(db, f"compat-{rollout}")
    target = User(
        username=f"compat_target_{rollout}",
        name="Compat Target",
        is_active=True,
        is_approved=False,
    )
    db.add(target)
    db.commit()

    approval = client.put(
        f"/api/v1/admin/users/{target.id}/approve",
        headers=_headers(admin),
        json={"is_approved": True},
    )
    creation = client.post(
        "/api/v1/admin/users/create",
        headers=_headers(admin),
        json={
            "username": f"compat_admin_create_{rollout}",
            "email": f"compat-admin-create-{rollout}@example.com",
            "password": "safe-test-password",
            "name": "Compat Create",
            "is_approved": True,
        },
    )

    assert approval.status_code == 200
    assert creation.status_code == 200
    db.refresh(target)
    assert target.is_approved is True
    assert db.query(User).filter(
        User.username == f"compat_admin_create_{rollout}"
    ).one().is_approved is True


def test_admin_approval_of_missing_user_returns_not_found(
    client, db, monkeypatch
):
    monkeypatch.setattr(settings, "registration_invitation_enforcement_enabled", True)
    admin = _admin(db, "unknown")

    response = client.put(
        "/api/v1/admin/users/999999/approve",
        headers=_headers(admin),
        json={"is_approved": True},
    )

    assert response.status_code == 404


@pytest.mark.parametrize("authenticated", [False, True])
def test_direct_user_creation_still_requires_admin(client, db, authenticated):
    ordinary = User(username="ordinary", name="Ordinary", is_active=True, is_approved=True)
    db.add(ordinary)
    db.commit()
    result = client.post("/api/v1/admin/users/create",
        headers=_headers(ordinary) if authenticated else {},
        json={"username": "new-person", "email": "new@example.com",
              "password": "test-only-password", "name": "New"})
    assert result.status_code in (401, 403)
    assert db.query(User).count() == 1
