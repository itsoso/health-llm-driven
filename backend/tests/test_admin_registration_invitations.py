from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.api import admin_registration_invitations as admin_api
from app.config import settings
from app.models.agent_audit_log import AgentAuditLog
from app.models.registration_invitation import RegistrationInvitation
from app.services.registration_invitation import (
    create_registration_invitation,
    find_invitation_by_code,
    find_invitation_by_link_token,
)


PATH = "/api/v1/admin/registration-invitations"
SAFE_ITEM_FIELDS = {
    "id",
    "phone_masked",
    "note",
    "status",
    "expires_at",
    "created_at",
    "updated_at",
    "prepared_for_delivery",
}


def _admin_headers(db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    user.is_admin = True
    db.commit()
    return user, headers


def _create(client, headers, phone="13800138000", **extra):
    return client.post(PATH, headers=headers, json={"phone": phone, **extra})


def test_create_uses_default_expiry_returns_credentials_once_and_audits(
    client, db, auth_user_and_headers, monkeypatch
):
    admin, headers = _admin_headers(db, auth_user_and_headers)
    monkeypatch.setattr(settings, "registration_invitation_expiry_days", 7)
    before = datetime.now(UTC)

    response = _create(client, headers, note="早期体验用户")

    assert response.status_code == 201
    payload = response.json()
    assert payload["phone_masked"] == "+86 138****8000"
    assert payload["status"] == "send_failed"
    assert payload["prepared_for_delivery"] is False
    assert payload["delivery_status"] == "send_failed"
    assert payload["delivery_error_code"] == "sms_not_configured"
    assert len(payload["manual_code"]) == 8
    assert payload["link_token"]
    assert payload["deep_link"].endswith(payload["link_token"])
    assert before + timedelta(days=6, hours=23) < datetime.fromisoformat(payload["expires_at"])
    assert "phone" not in payload
    assert "phone_hmac" not in payload
    assert "phone_ciphertext" not in payload
    assert "code_digest" not in payload
    assert "link_token_digest" not in payload

    row = db.get(RegistrationInvitation, payload["id"])
    assert row is not None
    assert row.created_by == admin.id
    assert row.code_digest != payload["manual_code"]
    assert row.link_token_digest != payload["link_token"]
    audit = (
        db.query(AgentAuditLog)
        .filter(AgentAuditLog.action == "registration_invitation_created")
        .one()
    )
    assert audit.user_id == admin.id
    assert audit.result_detail == {
        "invitation_id": row.id,
        "status": "created",
        "action": "create",
        "actor_id": admin.id,
    }
    serialized_audit = str(audit.result_detail)
    assert "13800138000" not in serialized_audit
    assert payload["manual_code"] not in serialized_audit
    assert payload["link_token"] not in serialized_audit


def test_create_rejects_second_active_invitation_with_stable_safe_code(
    client, db, auth_user_and_headers
):
    _, headers = _admin_headers(db, auth_user_and_headers)
    assert _create(client, headers).status_code == 201

    response = _create(client, headers, phone="+86 138-0013-8000")

    assert response.status_code == 409
    assert response.json() == {
        "detail": {
            "code": "active_registration_invitation_conflict",
            "message": "该手机号当前无法创建新邀请",
        }
    }
    assert "13800138000" not in response.text


def test_create_expires_stale_row_and_audits_both_transitions_atomically(
    client, db, auth_user_and_headers
):
    admin, headers = _admin_headers(db, auth_user_and_headers)
    stale = create_registration_invitation(db, "13800138000", created_by=admin.id).invitation
    db.commit()
    stale.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()

    response = _create(client, headers, phone="+86 138-0013-8000")

    assert response.status_code == 201
    db.refresh(stale)
    assert stale.status == "expired"
    audits = (
        db.query(AgentAuditLog)
        .filter(
            AgentAuditLog.action.in_(
                ["registration_invitation_expired", "registration_invitation_created"]
            )
        )
        .order_by(AgentAuditLog.id.asc())
        .all()
    )
    assert [audit.action for audit in audits] == [
        "registration_invitation_expired",
        "registration_invitation_created",
    ]
    assert audits[0].result_detail == {
        "invitation_id": stale.id,
        "status": "expired",
        "action": "expire_for_replacement",
        "actor_id": admin.id,
        "reason": "time_expired",
    }
    serialized = str(audits[0].result_detail)
    assert "13800138000" not in serialized
    assert stale.code_digest not in serialized
    assert stale.link_token_digest not in serialized


def test_expiry_audit_failure_rolls_back_old_and_new_invitation_mutations(
    client, db, auth_user_and_headers
):
    admin, headers = _admin_headers(db, auth_user_and_headers)
    stale = create_registration_invitation(db, "13800138000", created_by=admin.id).invitation
    db.commit()
    stale.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    stale_id = stale.id

    def fail_expiry_audit(session, flush_context, instances):
        del flush_context, instances
        if any(
            isinstance(item, AgentAuditLog)
            and item.action == "registration_invitation_expired"
            for item in session.new
        ):
            raise SQLAlchemyError("simulated bounded audit persistence failure")

    event.listen(db, "before_flush", fail_expiry_audit)
    try:
        response = _create(client, headers, phone="+86 138-0013-8000")
    finally:
        event.remove(db, "before_flush", fail_expiry_audit)

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "registration_invitation_persistence_failed"
    db.expire_all()
    assert db.get(RegistrationInvitation, stale_id).status == "created"
    assert db.query(RegistrationInvitation).count() == 1
    assert (
        db.query(AgentAuditLog)
        .filter(
            AgentAuditLog.action.in_(
                ["registration_invitation_expired", "registration_invitation_created"]
            )
        )
        .count()
        == 0
    )


def test_list_is_bounded_newest_first_and_uses_strict_field_allowlist(
    client, db, auth_user_and_headers
):
    _, headers = _admin_headers(db, auth_user_and_headers)
    first = _create(client, headers, phone="13800138000").json()
    second = _create(client, headers, phone="13900139000").json()

    response = client.get(f"{PATH}?limit=1&offset=0", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert payload["limit"] == 1
    assert payload["offset"] == 0
    assert len(payload["items"]) == 1
    assert payload["items"][0]["id"] == second["id"]
    assert set(payload["items"][0]) == SAFE_ITEM_FIELDS
    assert first["manual_code"] not in response.text
    assert second["link_token"] not in response.text
    assert "13800138000" not in response.text
    assert "13900139000" not in response.text


def test_list_rejects_excessive_offset_before_query(client, db, auth_user_and_headers):
    _, headers = _admin_headers(db, auth_user_and_headers)

    response = client.get(f"{PATH}?offset=10001", headers=headers)

    assert response.status_code == 422


def test_resend_rotates_credentials_on_same_row_and_invalidates_old_credentials(
    client, db, auth_user_and_headers
):
    admin, headers = _admin_headers(db, auth_user_and_headers)
    created = _create(client, headers).json()
    row = db.get(RegistrationInvitation, created["id"])
    old_code_digest = row.code_digest
    old_link_digest = row.link_token_digest

    response = client.post(f"{PATH}/{row.id}/resend", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == row.id
    assert payload["status"] == "send_failed"
    assert payload["prepared_for_delivery"] is False
    assert payload["delivery_status"] == "send_failed"
    assert payload["delivery_error_code"] == "sms_not_configured"
    assert payload["manual_code"] != created["manual_code"]
    assert payload["link_token"] != created["link_token"]
    db.refresh(row)
    assert row.code_digest != old_code_digest
    assert row.link_token_digest != old_link_digest
    assert find_invitation_by_code(db, created["manual_code"]) is None
    assert find_invitation_by_link_token(db, created["link_token"]) is None
    assert find_invitation_by_code(db, payload["manual_code"]).id == row.id
    assert find_invitation_by_link_token(db, payload["link_token"]).id == row.id
    audit = (
        db.query(AgentAuditLog)
        .filter(AgentAuditLog.action == "registration_invitation_credentials_rotated")
        .one()
    )
    assert audit.result_detail == {
        "invitation_id": row.id,
        "status": "created",
        "action": "resend_prepare",
        "actor_id": admin.id,
    }

    listed = client.get(PATH, headers=headers).text
    assert payload["manual_code"] not in listed
    assert payload["link_token"] not in listed


def test_resend_rejects_terminal_invitation(client, db, auth_user_and_headers):
    _, headers = _admin_headers(db, auth_user_and_headers)
    created = _create(client, headers).json()
    row = db.get(RegistrationInvitation, created["id"])
    row.status = "consumed"
    row.consumed_at = datetime.now(UTC)
    db.commit()

    response = client.post(f"{PATH}/{row.id}/resend", headers=headers)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "registration_invitation_not_active"


def test_revoke_only_active_invitation_and_records_audit(client, db, auth_user_and_headers):
    admin, headers = _admin_headers(db, auth_user_and_headers)
    created = _create(client, headers).json()

    response = client.post(f"{PATH}/{created['id']}/revoke", headers=headers)

    assert response.status_code == 200
    assert response.json()["status"] == "revoked"
    assert "manual_code" not in response.json()
    assert "link_token" not in response.json()
    audit = (
        db.query(AgentAuditLog)
        .filter(AgentAuditLog.action == "registration_invitation_revoked")
        .one()
    )
    assert audit.result_detail == {
        "invitation_id": created["id"],
        "status": "revoked",
        "action": "revoke",
        "actor_id": admin.id,
    }

    repeated = client.post(f"{PATH}/{created['id']}/revoke", headers=headers)
    assert repeated.status_code == 409
    assert repeated.json()["detail"]["code"] == "registration_invitation_not_active"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", PATH),
        ("POST", PATH),
        ("POST", f"{PATH}/1/resend"),
        ("POST", f"{PATH}/1/revoke"),
    ],
)
def test_non_admin_is_rejected_by_every_endpoint(
    client, db, auth_user_and_headers, method, path
):
    _, non_admin_headers = auth_user_and_headers
    kwargs = {"json": {"phone": "13800138000"}} if path == PATH and method == "POST" else {}
    assert client.request(method, path, headers=non_admin_headers, **kwargs).status_code == 403


def test_unauthenticated_list_is_rejected(client):
    assert client.get(PATH).status_code == 401


@pytest.mark.parametrize(
    "phone",
    [
        "",
        "not-a-phone",
        "13800138000" * 100,
    ],
)
def test_invalid_phone_uses_stable_error_without_echo(client, db, auth_user_and_headers, phone):
    _, headers = _admin_headers(db, auth_user_and_headers)

    response = _create(client, headers, phone=phone)

    assert response.status_code == 422
    assert response.json() == {
        "detail": {
            "code": "registration_invitation_phone_invalid",
            "message": "手机号格式不正确",
        }
    }
    if phone:
        assert phone not in response.text


@pytest.mark.parametrize(
    "phone",
    [
        13800138000,
        None,
        ["13800138000", "nested-secret"],
        {"value": "13800138000", "nested": "nested-secret"},
    ],
)
def test_non_string_phone_is_rejected_without_pydantic_input_echo(
    client, db, auth_user_and_headers, phone
):
    _, headers = _admin_headers(db, auth_user_and_headers)

    response = _create(client, headers, phone=phone)

    assert response.status_code == 422
    assert response.json() == {
        "detail": {
            "code": "registration_invitation_phone_invalid",
            "message": "手机号格式不正确",
        }
    }
    assert "13800138000" not in response.text
    assert "nested-secret" not in response.text


def test_create_maps_integrity_race_without_leaking_database_parameters(
    client, db, auth_user_and_headers, monkeypatch
):
    _, headers = _admin_headers(db, auth_user_and_headers)
    sensitive_params = {"phone_ciphertext": "+8613800138000", "code_digest": "secret-digest"}

    def raise_integrity(*args, **kwargs):
        raise IntegrityError("INSERT registration_invitations", sensitive_params, Exception("unique"))

    monkeypatch.setattr(admin_api, "create_registration_invitation", raise_integrity)

    response = _create(client, headers)

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "registration_invitation_persistence_failed"
    assert "+8613800138000" not in response.text
    assert "secret-digest" not in response.text


class _FakeDiag:
    def __init__(self, constraint_name):
        self.constraint_name = constraint_name


class _FakePgIntegrity(Exception):
    def __init__(self, constraint_name):
        self.diag = _FakeDiag(constraint_name)


@pytest.mark.parametrize(
    ("orig", "expected_status", "expected_code"),
    [
        (
            _FakePgIntegrity("uq_registration_invitations_active_phone_hmac"),
            409,
            "active_registration_invitation_conflict",
        ),
        (
            _FakePgIntegrity("registration_invitations_created_by_fkey"),
            503,
            "registration_invitation_persistence_failed",
        ),
        (
            _FakePgIntegrity("registration_invitations_code_digest_key"),
            503,
            "registration_invitation_persistence_failed",
        ),
        (
            Exception("UNIQUE constraint failed: registration_invitations.phone_hmac"),
            409,
            "active_registration_invitation_conflict",
        ),
        (
            Exception("UNIQUE constraint failed: registration_invitations.link_token_digest"),
            503,
            "registration_invitation_persistence_failed",
        ),
        (Exception("unknown integrity failure"), 503, "registration_invitation_persistence_failed"),
    ],
)
def test_integrity_errors_are_classified_by_exact_constraint_only(
    client,
    db,
    auth_user_and_headers,
    monkeypatch,
    orig,
    expected_status,
    expected_code,
):
    _, headers = _admin_headers(db, auth_user_and_headers)
    sensitive_params = {"phone_ciphertext": "+8613800138000", "code_digest": "secret-digest"}

    def raise_integrity(*args, **kwargs):
        raise IntegrityError("sensitive sql", sensitive_params, orig)

    monkeypatch.setattr(admin_api, "create_registration_invitation", raise_integrity)

    response = _create(client, headers)

    assert response.status_code == expected_status
    assert response.json()["detail"]["code"] == expected_code
    assert "+8613800138000" not in response.text
    assert "secret-digest" not in response.text


@pytest.mark.parametrize("operation", ["create", "resend", "revoke"])
def test_mutation_response_never_reads_database_after_successful_commit(
    client, db, auth_user_and_headers, monkeypatch, operation
):
    _, headers = _admin_headers(db, auth_user_and_headers)
    invitation_id = None
    if operation != "create":
        invitation = create_registration_invitation(db, "13800138000").invitation
        db.commit()
        invitation_id = invitation.id

    refresh_calls = []

    def fail_if_refreshed(*args, **kwargs):
        refresh_calls.append((args, kwargs))
        raise SQLAlchemyError("database read attempted after commit")

    monkeypatch.setattr(db, "refresh", fail_if_refreshed)

    if operation == "create":
        response = _create(client, headers)
        assert response.status_code == 201
        assert response.json()["manual_code"]
        assert response.json()["link_token"]
    else:
        response = client.post(f"{PATH}/{invitation_id}/{operation}", headers=headers)
        assert response.status_code == 200
        if operation == "resend":
            assert response.json()["manual_code"]
            assert response.json()["link_token"]
        else:
            assert response.json()["status"] == "revoked"
    assert refresh_calls == []


def test_commit_failure_rolls_back_and_returns_safe_error(
    client, db, auth_user_and_headers, monkeypatch
):
    _, headers = _admin_headers(db, auth_user_and_headers)
    original_commit = db.commit
    commit_calls = 0

    def fail_mutation_commit():
        nonlocal commit_calls
        commit_calls += 1
        if commit_calls == 2:
            raise SQLAlchemyError("simulated commit failure with +8613800138000")
        return original_commit()

    monkeypatch.setattr(db, "commit", fail_mutation_commit)

    response = _create(client, headers)

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "registration_invitation_persistence_failed"
    assert "+8613800138000" not in response.text
    assert db.query(RegistrationInvitation).count() == 0
