from datetime import UTC, datetime, timedelta

import pytest

from app.config import settings
from app.models.agent_audit_log import AgentAuditLog
from app.models.registration_invitation import (
    PhoneRegistrationGrant,
    RegistrationAuthAttemptAudit,
)
from app.models.user import User
from app.services.registration_invitation import (
    create_registration_invitation,
    registration_source_hmac,
)


@pytest.fixture(autouse=True)
def _invitation_settings(monkeypatch):
    monkeypatch.setattr(settings, "auth_phone_code_dev_echo", True)
    monkeypatch.setattr(settings, "auth_phone_code_resend_seconds", 0)
    monkeypatch.setattr(settings, "registration_invitation_rollout_enabled", True)
    monkeypatch.setattr(settings, "registration_invitation_enforcement_enabled", True)
    monkeypatch.setattr(
        settings,
        "registration_invitation_digest_key",
        "registration-invitation-test-key-with-at-least-32-bytes",
    )


def _otp(client, phone: str) -> str:
    response = client.post("/api/v1/auth/phone/code", json={"phone": phone})
    assert response.status_code == 200
    return response.json()["dev_code"]


def _verify(client, phone: str):
    return client.post(
        "/api/v1/auth/phone/verify",
        json={"phone": phone, "code": _otp(client, phone)},
    )


def _create_user(db, phone: str) -> User:
    user = User(
        username="existing_phone_user",
        name="现有用户",
        phone=phone,
        phone_verified_at=datetime.now(UTC),
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_unknown_phone_verify_returns_ticket_without_creating_user(client, db):
    response = _verify(client, "13800138000")

    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "invitation_required"
    assert len(body["verified_phone_ticket"]) >= 22
    assert body["expires_in_seconds"] > 0
    assert "phone" not in body
    assert "grant_id" not in body
    assert db.query(User).count() == 0
    assert db.query(PhoneRegistrationGrant).count() == 1


def test_registration_attempt_audit_schema_contains_only_bounded_safe_fields():
    assert set(RegistrationAuthAttemptAudit.__table__.c.keys()) == {
        "id",
        "outcome",
        "error_code",
        "invitation_id",
        "grant_id",
        "user_id",
        "phone_masked",
        "source_hmac",
        "created_at",
    }


def test_phone_verify_openapi_declares_outcome_discriminator():
    from main import app

    schema = app.openapi()["paths"]["/api/v1/auth/phone/verify"]["post"]["responses"][
        "200"
    ]["content"]["application/json"]["schema"]
    assert schema["discriminator"]["propertyName"] == "outcome"


def test_registration_openapi_marks_sensitive_request_fields_write_only():
    from main import app

    document = app.openapi()
    paths = document["paths"]

    verify_properties = paths["/api/v1/auth/phone/verify"]["post"]["requestBody"][
        "content"
    ]["application/json"]["schema"]["properties"]
    assert verify_properties["code"]["writeOnly"] is True

    for path in ("/api/v1/auth/invitations/inspect", "/api/v1/auth/invited-registration"):
        properties = paths[path]["post"]["requestBody"]["content"]["application/json"][
            "schema"
        ]["properties"]
        for field in {
            "manual_code",
            "link_token",
            "verified_phone_ticket",
            "idempotency_key",
        } & properties.keys():
            schema = properties[field]
            assert schema.get("writeOnly") is True or any(
                candidate.get("writeOnly") is True
                for candidate in schema.get("anyOf", [])
            ), (path, field)


def test_registration_source_hmac_is_stable_separated_bounded_and_fail_safe(monkeypatch):
    from app.services import registration_invitation as service

    first = registration_source_hmac("203.0.113.7")
    same = registration_source_hmac("203.0.113.7")
    other = registration_source_hmac("203.0.113.8")

    assert first == same
    assert first != other
    assert len(first) == 64
    assert first != "203.0.113.7"
    assert registration_source_hmac(None) is None
    assert registration_source_hmac("x" * 257) is None

    def unavailable_key():
        raise RuntimeError("raw-source-must-not-escape")

    monkeypatch.setattr(service, "_digest_key", unavailable_key)
    assert registration_source_hmac("198.51.100.19") is None


def test_existing_phone_verify_authenticates_without_consuming_invite(client, db):
    user = _create_user(db, "+8613800138001")
    invitation = create_registration_invitation(db, "13800138001").invitation
    db.commit()

    response = _verify(client, "13800138001")

    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "authenticated"
    assert body["access_token"]
    assert body["user"]["id"] == user.id
    assert db.query(PhoneRegistrationGrant).count() == 0
    db.refresh(invitation)
    assert invitation.status == "created"
    assert invitation.consumed_at is None


def test_existing_user_cannot_consume_invite_through_registration_endpoint(client, db):
    user = _create_user(db, "+8613800138012")
    created = create_registration_invitation(db, "13800138012")
    db.commit()
    # Seed the verified ticket directly to exercise the defensive server-side
    # uniqueness check even if a stale client still holds a pre-login ticket.
    from app.services.registration_invitation import create_phone_registration_grant

    issued = create_phone_registration_grant(db, "13800138012")
    db.commit()

    response = client.post(
        "/api/v1/auth/invited-registration",
        json={
            "verified_phone_ticket": issued.token,
            "manual_code": created.manual_code,
            "idempotency_key": "registration-attempt-0012",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "REGISTRATION_USER_ALREADY_EXISTS"
    assert db.query(User).filter(User.phone == user.phone).count() == 1
    db.refresh(created.invitation)
    db.refresh(issued.grant)
    assert created.invitation.consumed_at is None
    assert issued.grant.consumed_at is None
    audit = db.query(RegistrationAuthAttemptAudit).one()
    assert audit.outcome == "rejected"
    assert audit.error_code == "REGISTRATION_USER_ALREADY_EXISTS"
    assert audit.user_id is None


def test_invited_registration_consumes_phone_bound_credentials_and_is_idempotent(
    client, db, caplog
):
    created = create_registration_invitation(db, "13800138002")
    db.commit()
    ticket = _verify(client, "13800138002").json()["verified_phone_ticket"]
    payload = {
        "verified_phone_ticket": ticket,
        "manual_code": created.manual_code,
        "idempotency_key": "registration-attempt-0001",
    }

    first = client.post("/api/v1/auth/invited-registration", json=payload)
    second = client.post("/api/v1/auth/invited-registration", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["user"]["id"] == second.json()["user"]["id"]
    assert first.json()["is_new_user"] is True
    assert second.json()["is_new_user"] is False
    assert db.query(User).filter(User.phone == "+8613800138002").count() == 1
    db.refresh(created.invitation)
    grant = db.query(PhoneRegistrationGrant).one()
    assert created.invitation.status == "consumed"
    assert created.invitation.consumed_by == first.json()["user"]["id"]
    assert grant.consumed_by == first.json()["user"]["id"]
    assert grant.idempotency_key_digest
    assert "registration-attempt-0001" not in grant.idempotency_key_digest
    assert (
        db.query(AgentAuditLog)
        .filter(AgentAuditLog.action == "invitation_consumed")
        .count()
        == 1
    )
    terminals = db.query(RegistrationAuthAttemptAudit).all()
    assert len(terminals) == 2  # initial success + explicit idempotent retry attempt
    assert all(item.outcome == "success" for item in terminals)
    assert all(item.error_code is None for item in terminals)
    assert all(item.user_id == first.json()["user"]["id"] for item in terminals)
    assert all(item.phone_masked == created.invitation.phone_masked for item in terminals)
    assert all(item.source_hmac and len(item.source_hmac) == 64 for item in terminals)
    assert all(item.source_hmac != "testclient" for item in terminals)
    assert "testclient" not in first.text
    assert "testclient" not in second.text
    assert "testclient" not in caplog.text


def test_replay_with_different_idempotency_key_is_rejected_without_duplicate(client, db):
    created = create_registration_invitation(db, "13800138003")
    db.commit()
    ticket = _verify(client, "13800138003").json()["verified_phone_ticket"]
    first_payload = {
        "verified_phone_ticket": ticket,
        "link_token": created.link_token,
        "idempotency_key": "registration-attempt-0002",
    }
    assert client.post("/api/v1/auth/invited-registration", json=first_payload).status_code == 200

    replay = client.post(
        "/api/v1/auth/invited-registration",
        json={**first_payload, "idempotency_key": "registration-attempt-0003"},
    )

    assert replay.status_code == 409
    assert replay.json()["detail"]["code"] == "INVITATION_ALREADY_USED"
    assert db.query(User).filter(User.phone == "+8613800138003").count() == 1
    audits = db.query(RegistrationAuthAttemptAudit).order_by(
        RegistrationAuthAttemptAudit.id
    ).all()
    assert [(item.outcome, item.error_code) for item in audits] == [
        ("success", None),
        ("rejected", "INVITATION_ALREADY_USED"),
    ]


@pytest.mark.parametrize("terminal_status", ["revoked", "expired"])
def test_terminal_invitation_is_rejected_without_consuming_grant(
    client, db, terminal_status
):
    created = create_registration_invitation(
        db,
        "13800138004",
        expires_at=(
            datetime.now(UTC) - timedelta(seconds=1)
            if terminal_status == "expired"
            else datetime.now(UTC) + timedelta(days=1)
        ),
    )
    if terminal_status == "revoked":
        created.invitation.status = "revoked"
    db.commit()
    ticket = _verify(client, "13800138004").json()["verified_phone_ticket"]

    response = client.post(
        "/api/v1/auth/invited-registration",
        json={
            "verified_phone_ticket": ticket,
            "manual_code": created.manual_code,
            "idempotency_key": "registration-attempt-0004",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == (
        "INVITATION_REVOKED" if terminal_status == "revoked" else "INVITATION_EXPIRED"
    )
    grant = db.query(PhoneRegistrationGrant).one()
    assert grant.consumed_at is None
    assert db.query(User).count() == 0
    audit = db.query(RegistrationAuthAttemptAudit).one()
    assert audit.outcome == "rejected"
    assert audit.error_code == (
        "INVITATION_REVOKED" if terminal_status == "revoked" else "INVITATION_EXPIRED"
    )
    assert audit.user_id is None
    assert audit.phone_masked == created.invitation.phone_masked


def test_phone_mismatch_and_invalid_input_do_not_echo_secrets_or_mutate(client, db):
    created = create_registration_invitation(db, "13800138005")
    db.commit()
    ticket = _verify(client, "13800138006").json()["verified_phone_ticket"]
    secret = "this-ticket-must-never-be-echoed!"

    mismatch = client.post(
        "/api/v1/auth/invited-registration",
        json={
            "verified_phone_ticket": ticket,
            "manual_code": created.manual_code,
            "idempotency_key": "registration-attempt-0005",
        },
    )
    invalid = client.post(
        "/api/v1/auth/invited-registration",
        json={
            "verified_phone_ticket": secret,
            "manual_code": "BAD-CODE",
            "idempotency_key": "x",
        },
    )

    assert mismatch.status_code == 400
    assert mismatch.json()["detail"]["code"] == "INVITATION_PHONE_MISMATCH"
    assert invalid.status_code == 400
    assert secret not in invalid.text
    assert "BAD-CODE" not in invalid.text
    assert db.query(User).count() == 0
    assert all(item.consumed_at is None for item in db.query(PhoneRegistrationGrant).all())
    db.refresh(created.invitation)
    assert created.invitation.consumed_at is None
    mismatch_audit, invalid_audit = db.query(RegistrationAuthAttemptAudit).order_by(
        RegistrationAuthAttemptAudit.id
    ).all()
    assert mismatch_audit.error_code == "INVITATION_PHONE_MISMATCH"
    assert invalid_audit.error_code == "REGISTRATION_INPUT_INVALID"
    assert invalid_audit.invitation_id is None
    assert invalid_audit.grant_id is None
    assert invalid_audit.user_id is None


def test_invitation_inspect_is_read_only_and_returns_masked_metadata(client, db):
    created = create_registration_invitation(db, "13800138007")
    db.commit()

    response = client.post(
        "/api/v1/auth/invitations/inspect",
        json={"link_token": created.link_token},
    )
    invalid = client.post(
        "/api/v1/auth/invitations/inspect",
        json={"manual_code": "23456789"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "valid": True,
        "phone_masked": created.invitation.phone_masked,
        "expires_at": created.invitation.expires_at.isoformat().replace("+00:00", "Z"),
    }
    assert invalid.status_code == 200
    assert invalid.json() == {"valid": False, "phone_masked": None, "expires_at": None}
    db.refresh(created.invitation)
    assert created.invitation.status == "created"
    assert created.invitation.consumed_at is None


def test_enforced_legacy_login_blocks_unknown_but_existing_user_still_logs_in(
    client, db
):
    unknown_code = _otp(client, "13800138008")
    blocked = client.post(
        "/api/v1/auth/phone/login",
        json={"phone": "13800138008", "code": unknown_code},
    )

    assert blocked.status_code == 403
    assert blocked.json()["detail"]["code"] == "REGISTRATION_INVITATION_REQUIRED"
    assert db.query(User).count() == 0
    assert db.query(PhoneRegistrationGrant).count() == 0

    user = _create_user(db, "+8613800138009")
    existing = client.post(
        "/api/v1/auth/phone/login",
        json={"phone": "13800138009", "code": _otp(client, "13800138009")},
    )
    assert existing.status_code == 200
    assert existing.json()["user"]["id"] == user.id


def test_legacy_login_keeps_compatibility_when_enforcement_is_off(client, db, monkeypatch):
    monkeypatch.setattr(settings, "registration_invitation_enforcement_enabled", False)

    response = client.post(
        "/api/v1/auth/phone/login",
        json={"phone": "13800138010", "code": _otp(client, "13800138010")},
    )

    assert response.status_code == 200
    assert response.json()["is_new_user"] is True
    assert db.query(User).filter(User.phone == "+8613800138010").count() == 1


def test_audit_write_failure_rolls_back_registration_without_echoing_error(
    client, db, monkeypatch
):
    from app.api import auth as auth_api

    created = create_registration_invitation(db, "13800138011")
    db.commit()
    ticket = _verify(client, "13800138011").json()["verified_phone_ticket"]

    def fail_audit(*args, **kwargs):
        raise RuntimeError("forced-audit-failure-with-sensitive-marker")

    monkeypatch.setattr(auth_api, "_write_registration_terminal_audit", fail_audit)
    response = client.post(
        "/api/v1/auth/invited-registration",
        json={
            "verified_phone_ticket": ticket,
            "manual_code": created.manual_code,
            "idempotency_key": "registration-attempt-0011",
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "REGISTRATION_PERSISTENCE_FAILED"
    assert "sensitive-marker" not in response.text
    assert db.query(User).count() == 0
    db.refresh(created.invitation)
    assert created.invitation.status == "created"
    grant = db.query(PhoneRegistrationGrant).one()
    assert grant.consumed_at is None


def test_rejected_attempt_audit_failure_preserves_original_safe_error(
    client, db, monkeypatch
):
    from app.api import auth as auth_api

    created = create_registration_invitation(db, "13800138013")
    created.invitation.status = "revoked"
    db.commit()
    ticket = _verify(client, "13800138013").json()["verified_phone_ticket"]

    def fail_terminal_audit(*args, **kwargs):
        raise RuntimeError("audit-sensitive-marker")

    monkeypatch.setattr(auth_api, "_write_registration_terminal_audit", fail_terminal_audit)
    response = client.post(
        "/api/v1/auth/invited-registration",
        json={
            "verified_phone_ticket": ticket,
            "manual_code": created.manual_code,
            "idempotency_key": "registration-attempt-0013",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVITATION_REVOKED"
    assert "sensitive-marker" not in response.text
    assert db.query(RegistrationAuthAttemptAudit).count() == 0


def test_invalid_ticket_and_unknown_invite_each_write_one_rejection_audit(client, db):
    created = create_registration_invitation(db, "13800138014")
    db.commit()
    ticket = _verify(client, "13800138014").json()["verified_phone_ticket"]

    invalid_ticket = client.post(
        "/api/v1/auth/invited-registration",
        json={
            "verified_phone_ticket": "A" * 43,
            "manual_code": created.manual_code,
            "idempotency_key": "registration-attempt-0014",
        },
    )
    unknown_invite = client.post(
        "/api/v1/auth/invited-registration",
        json={
            "verified_phone_ticket": ticket,
            "manual_code": "23456789",
            "idempotency_key": "registration-attempt-0015",
        },
    )

    assert invalid_ticket.json()["detail"]["code"] == "VERIFIED_PHONE_TICKET_EXPIRED"
    assert unknown_invite.json()["detail"]["code"] == "INVITATION_INVALID"
    audits = db.query(RegistrationAuthAttemptAudit).order_by(
        RegistrationAuthAttemptAudit.id
    ).all()
    assert [item.error_code for item in audits] == [
        "VERIFIED_PHONE_TICKET_EXPIRED",
        "INVITATION_INVALID",
    ]
    assert all(item.outcome == "rejected" for item in audits)


@pytest.mark.parametrize(
    ("raised", "expected_status", "expected_code"),
    [
        ("integrity", 409, "REGISTRATION_STATE_CONFLICT"),
        ("runtime", 503, "REGISTRATION_PERSISTENCE_FAILED"),
    ],
)
def test_persistence_failures_write_bounded_rejection_audit(
    client, db, monkeypatch, raised, expected_status, expected_code
):
    from sqlalchemy.exc import IntegrityError
    from app.api import auth as auth_api

    created = create_registration_invitation(db, "13800138015")
    db.commit()
    ticket = _verify(client, "13800138015").json()["verified_phone_ticket"]

    def fail_lookup(*args, **kwargs):
        if raised == "integrity":
            raise IntegrityError("bounded", {}, Exception("bounded"))
        raise RuntimeError("sensitive-runtime-marker")

    monkeypatch.setattr(auth_api, "find_phone_registration_grant_for_update", fail_lookup)
    response = client.post(
        "/api/v1/auth/invited-registration",
        json={
            "verified_phone_ticket": ticket,
            "manual_code": created.manual_code,
            "idempotency_key": "registration-attempt-0016",
        },
    )

    assert response.status_code == expected_status
    assert response.json()["detail"]["code"] == expected_code
    assert "sensitive-runtime-marker" not in response.text
    audit = db.query(RegistrationAuthAttemptAudit).one()
    assert audit.outcome == "rejected"
    assert audit.error_code == expected_code
    assert audit.user_id is None
