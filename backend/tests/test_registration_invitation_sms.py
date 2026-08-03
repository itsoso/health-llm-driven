from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import logging
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import event
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.api import admin_registration_invitations as admin_api
from app.config import settings
from app.models.agent_audit_log import AgentAuditLog
from app.models.registration_invitation import RegistrationInvitation
from app.services.registration_invitation import create_registration_invitation


@pytest.fixture(autouse=True)
def _invite_sms_config(monkeypatch):
    monkeypatch.setattr(settings, "registration_invitation_rollout_enabled", True)
    monkeypatch.setattr(settings, "aliyun_sms_access_key_id", "invite-key")
    monkeypatch.setattr(settings, "aliyun_sms_access_key_secret", "invite-secret")
    monkeypatch.setattr(settings, "registration_invitation_sms_sign_name", "小巴邀请")
    monkeypatch.setattr(
        settings,
        "registration_invitation_sms_template_code",
        "SMS_INVITE_123",
    )


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _Client:
    response_payload = {
        "Code": "OK",
        "BizId": "provider-biz-id",
        "RequestId": "provider-request-id",
    }
    captured_params = None
    error = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url, data):
        type(self).captured_params = dict(data)
        if type(self).error is not None:
            raise type(self).error
        return _Response(type(self).response_payload)


@pytest.fixture(autouse=True)
def _reset_client():
    _Client.response_payload = {
        "Code": "OK",
        "BizId": "provider-biz-id",
        "RequestId": "provider-request-id",
    }
    _Client.captured_params = None
    _Client.error = None


def _prepared(db):
    return create_registration_invitation(
        db,
        "13800138000",
        created_by=1,
        expires_at=datetime.now(UTC) + timedelta(days=3),
    )


def _deliver(db, prepared, monkeypatch):
    from app.services import registration_invitation_sms as sms

    monkeypatch.setattr(sms, "httpx", SimpleNamespace(Client=_Client))
    result = sms.deliver_registration_invitation_sms(
        db,
        prepared.invitation,
        manual_code=prepared.manual_code,
        link_token=prepared.link_token,
        actor_id=1,
    )
    db.flush()
    return result


def test_enterprise_aliyun_ack_marks_sent_and_uses_dedicated_template(db, monkeypatch):
    prepared = _prepared(db)

    result = _deliver(db, prepared, monkeypatch)

    assert result.delivery_status == "sent"
    assert result.error_code is None
    assert prepared.invitation.status == "sent"
    assert prepared.invitation.send_attempt_count == 1
    assert prepared.invitation.last_send_error_code is None
    params = _Client.captured_params
    assert params["Action"] == "SendSms"
    assert params["SignName"] == "小巴邀请"
    assert params["TemplateCode"] == "SMS_INVITE_123"
    assert params["TemplateCode"] != settings.aliyun_sms_template_code
    assert params["PhoneNumbers"] == "13800138000"
    template = json.loads(params["TemplateParam"])
    assert set(template) == {"code", "link", "expires"}
    assert template["code"] == prepared.manual_code
    assert template["link"] == f"health://invite?token={prepared.link_token}"
    assert template["expires"]

    audit = (
        db.query(AgentAuditLog)
        .filter(AgentAuditLog.action == "registration_invitation_send_terminal")
        .one()
    )
    assert audit.result_detail == {
        "invitation_id": prepared.invitation.id,
        "status": "sent",
        "error_code": None,
        "attempt": 1,
        "actor_id": 1,
    }


@pytest.mark.parametrize(
    ("dedicated_id", "dedicated_secret"),
    [("dedicated-id", None), (None, "dedicated-secret")],
)
def test_delivery_rejects_partial_dedicated_access_key_pair_without_http(
    db, monkeypatch, dedicated_id, dedicated_secret
):
    prepared = _prepared(db)
    monkeypatch.setattr(settings, "aliyun_access_key_id", "fallback-id")
    monkeypatch.setattr(settings, "aliyun_access_key_secret", "fallback-secret")
    monkeypatch.setattr(settings, "aliyun_sms_access_key_id", dedicated_id)
    monkeypatch.setattr(settings, "aliyun_sms_access_key_secret", dedicated_secret)
    monkeypatch.setattr(
        __import__("app.services.registration_invitation_sms", fromlist=["httpx"]),
        "httpx",
        SimpleNamespace(Client=_Client),
    )

    result = _deliver(db, prepared, monkeypatch)

    assert result.delivery_status == "send_failed"
    assert result.error_code == "sms_not_configured"
    assert _Client.captured_params is None


@pytest.mark.parametrize(
    ("invite_sign", "invite_template"),
    [("OTP签名", "SMS_INVITE_123"), ("小巴邀请", "SMS_OTP_123")],
)
def test_production_delivery_rejects_reused_otp_sign_or_template_without_http(
    db, monkeypatch, invite_sign, invite_template
):
    prepared = _prepared(db)
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "aliyun_sms_sign_name", "OTP签名")
    monkeypatch.setattr(settings, "aliyun_sms_template_code", "SMS_OTP_123")
    monkeypatch.setattr(settings, "registration_invitation_sms_sign_name", invite_sign)
    monkeypatch.setattr(settings, "registration_invitation_sms_template_code", invite_template)

    result = _deliver(db, prepared, monkeypatch)

    assert result.delivery_status == "send_failed"
    assert result.error_code == "sms_not_configured"
    assert _Client.captured_params is None


@pytest.mark.parametrize(
    ("failure", "expected_code"),
    [
        ("provider", "provider_rejected"),
        ("invalid_ack", "provider_invalid_ack"),
        ("missing", "sms_not_configured"),
        ("timeout", "provider_timeout"),
        ("transport", "transport_failed"),
    ],
)
def test_terminal_failures_are_persistable_and_bounded(
    db, monkeypatch, failure, expected_code
):
    prepared = _prepared(db)
    if failure == "provider":
        _Client.response_payload = {"Code": "isv.BUSINESS_LIMIT_CONTROL", "Message": "raw"}
    elif failure == "invalid_ack":
        _Client.response_payload = {"Code": "OK", "BizId": "", "RequestId": 123}
    elif failure == "missing":
        monkeypatch.setattr(settings, "registration_invitation_sms_template_code", None)
    elif failure == "timeout":
        _Client.error = httpx.TimeoutException("secret timeout body")
    else:
        _Client.error = RuntimeError("secret transport body")

    result = _deliver(db, prepared, monkeypatch)

    assert result.delivery_status == "send_failed"
    assert result.error_code == expected_code
    assert prepared.invitation.status == "send_failed"
    assert prepared.invitation.send_attempt_count == 1
    assert prepared.invitation.last_send_error_code == expected_code
    assert len(prepared.invitation.last_send_error_code) <= 64
    audit = (
        db.query(AgentAuditLog)
        .filter(AgentAuditLog.action == "registration_invitation_send_terminal")
        .one()
    )
    assert audit.result_detail["error_code"] == expected_code
    assert "raw" not in str(audit.result_detail)
    assert "secret" not in str(audit.result_detail)


def test_failure_logs_never_contain_delivery_secrets(db, monkeypatch, caplog):
    prepared = _prepared(db)
    phone = prepared.invitation.phone_ciphertext
    _Client.response_payload = {
        "Code": "REJECTED",
        "Message": f"{phone} {prepared.manual_code} {prepared.link_token}",
    }

    with caplog.at_level(logging.INFO):
        _deliver(db, prepared, monkeypatch)

    output = caplog.text
    assert phone not in output
    assert prepared.manual_code not in output
    assert prepared.link_token not in output
    assert prepared.invitation.code_digest not in output
    assert prepared.invitation.link_token_digest not in output
    assert "provider-biz-id" not in output
    assert f"invitation_id={prepared.invitation.id}" in output


def test_real_httpx_info_logging_never_exposes_posted_invitation_secrets(
    db, monkeypatch, caplog
):
    from app.services import registration_invitation_sms as sms

    prepared = _prepared(db)
    frozen = sms.freeze_registration_invitation_delivery(
        prepared.invitation,
        manual_code=prepared.manual_code,
        link_token=prepared.link_token,
    )
    captured_requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(
            200,
            json={
                "Code": "OK",
                "RequestId": "provider-request-id",
                "BizId": "provider-biz-id",
            },
        )

    real_client = httpx.Client
    transport = httpx.MockTransport(handler)

    def client_factory(**kwargs):
        return real_client(transport=transport, timeout=kwargs.get("timeout"))

    monkeypatch.setattr(sms.httpx, "Client", client_factory)
    with caplog.at_level(logging.INFO):
        outcome = sms.send_frozen_registration_invitation_sms(frozen)

    assert outcome.delivery_status == "sent"
    assert len(captured_requests) == 1
    request = captured_requests[0]
    assert request.method == "POST"
    assert request.url.query == b""
    assert request.headers["content-type"].startswith("application/x-www-form-urlencoded")
    body = request.content.decode("utf-8")
    assert "PhoneNumbers=13800138000" in body
    assert "TemplateParam=" in body
    assert "AccessKeyId=invite-key" in body
    assert "Signature=" in body

    output = caplog.text
    for secret in (
        "13800138000",
        prepared.manual_code,
        prepared.link_token,
        "invite-key",
        "Signature=",
    ):
        assert secret not in output


def test_real_httpx_transport_exception_content_is_never_logged(
    db, monkeypatch, caplog
):
    from app.services import registration_invitation_sms as sms

    prepared = _prepared(db)
    frozen = sms.freeze_registration_invitation_delivery(
        prepared.invitation,
        manual_code=prepared.manual_code,
        link_token=prepared.link_token,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout(
            f"{prepared.manual_code} {prepared.link_token} invite-key Signature=secret",
            request=request,
        )

    real_client = httpx.Client
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        sms.httpx,
        "Client",
        lambda **kwargs: real_client(transport=transport, timeout=kwargs.get("timeout")),
    )

    with caplog.at_level(logging.INFO):
        outcome = sms.send_frozen_registration_invitation_sms(frozen)

    assert outcome.error_code == "provider_timeout"
    for secret in (
        "13800138000",
        prepared.manual_code,
        prepared.link_token,
        "invite-key",
        "Signature=secret",
    ):
        assert secret not in caplog.text


def test_invite_transport_does_not_change_existing_otp_template_config(db, monkeypatch):
    monkeypatch.setattr(settings, "aliyun_sms_sign_name", "OTP签名")
    monkeypatch.setattr(settings, "aliyun_sms_template_code", "SMS_OTP_456")
    prepared = _prepared(db)

    _deliver(db, prepared, monkeypatch)

    assert _Client.captured_params["SignName"] == "小巴邀请"
    assert _Client.captured_params["TemplateCode"] == "SMS_INVITE_123"
    assert settings.aliyun_sms_sign_name == "OTP签名"
    assert settings.aliyun_sms_template_code == "SMS_OTP_456"


def test_aliyun_invitation_signature_known_vector_preserves_utf8_and_json_encoding():
    from app.services import phone_auth
    from app.services.registration_invitation_sms import (
        FrozenRegistrationInvitationDelivery,
        build_aliyun_invitation_sms_params,
    )

    payload = FrozenRegistrationInvitationDelivery(
        invitation_id=42,
        expected_code_digest="a" * 64,
        expected_link_token_digest="b" * 64,
        phone="+8613800138000",
        manual_code="ABCD2345",
        link_token="token_1234567890123456789012",
        expires_at=datetime(2026, 8, 5, 12, 34, tzinfo=UTC),
    )

    params = build_aliyun_invitation_sms_params(
        payload,
        access_key_id="test-access-id",
        access_key_secret="test-access-secret",
        sign_name="小巴邀请",
        template_code="SMS_INVITE_123",
        nonce="nonce-123",
        timestamp="2026-08-02T12:34:56Z",
    )

    assert params["TemplateParam"] == (
        '{"code":"ABCD2345","link":"health://invite?token='
        'token_1234567890123456789012","expires":"2026-08-05 12:34 UTC"}'
    )
    unsigned = {key: value for key, value in params.items() if key != "Signature"}
    canonical = "&".join(
        f"{phone_auth._aliyun_percent_encode(key)}="
        f"{phone_auth._aliyun_percent_encode(unsigned[key])}"
        for key in sorted(unsigned)
    )
    assert canonical == (
        "AccessKeyId=test-access-id&Action=SendSms&Format=JSON&PhoneNumbers=13800138000&"
        "RegionId=cn-hangzhou&SignName=%E5%B0%8F%E5%B7%B4%E9%82%80%E8%AF%B7&"
        "SignatureMethod=HMAC-SHA1&SignatureNonce=nonce-123&SignatureVersion=1.0&"
        "TemplateCode=SMS_INVITE_123&TemplateParam=%7B%22code%22%3A%22ABCD2345%22%2C%22"
        "link%22%3A%22health%3A%2F%2Finvite%3Ftoken%3Dtoken_1234567890123456789012%22%"
        "2C%22expires%22%3A%222026-08-05%2012%3A34%20UTC%22%7D&Timestamp=2026-08-02T12%"
        "3A34%3A56Z&Version=2017-05-25"
    )
    assert params["Signature"] == "vj61YvFbGn+5AxZgdSNXGLI3hQ4="


def test_admin_create_reports_delivery_failure_and_returns_copy_fallback(
    client, db, auth_user_and_headers, monkeypatch
):
    user, headers = auth_user_and_headers
    user.is_admin = True
    db.commit()
    monkeypatch.setattr(settings, "registration_invitation_sms_template_code", None)

    response = client.post(
        "/api/v1/admin/registration-invitations",
        headers=headers,
        json={"phone": "13800138000", "note": "must not enter provider payload"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["delivery_status"] == "send_failed"
    assert payload["delivery_error_code"] == "sms_not_configured"
    assert payload["manual_code"]
    assert payload["deep_link"] == f"health://invite?token={payload['link_token']}"
    row = db.get(RegistrationInvitation, payload["id"])
    assert row.status == "send_failed"
    assert row.send_attempt_count == 1


def test_admin_resend_reuses_row_rotates_credentials_and_delivers_new_values(
    client, db, auth_user_and_headers, monkeypatch
):
    from app.services import registration_invitation_sms as sms
    from app.services.registration_invitation import (
        find_invitation_by_code,
        find_invitation_by_link_token,
    )

    user, headers = auth_user_and_headers
    user.is_admin = True
    db.commit()
    monkeypatch.setattr(sms, "httpx", SimpleNamespace(Client=_Client))
    created = client.post(
        "/api/v1/admin/registration-invitations",
        headers=headers,
        json={"phone": "13800138000"},
    ).json()
    old_code = created["manual_code"]
    old_link = created["link_token"]

    response = client.post(
        f"/api/v1/admin/registration-invitations/{created['id']}/resend",
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == created["id"]
    assert payload["delivery_status"] == "sent"
    assert payload["manual_code"] != old_code
    assert payload["link_token"] != old_link
    assert json.loads(_Client.captured_params["TemplateParam"])["code"] == payload["manual_code"]
    assert find_invitation_by_code(db, old_code) is None
    assert find_invitation_by_link_token(db, old_link) is None
    assert db.query(RegistrationInvitation).count() == 1
    assert db.get(RegistrationInvitation, created["id"]).send_attempt_count == 2


def test_provider_ack_followed_by_commit_failure_is_observable_and_never_retried(
    client, db, auth_user_and_headers, monkeypatch, caplog
):
    from app.services import registration_invitation_sms as sms

    user, headers = auth_user_and_headers
    user.is_admin = True
    db.commit()
    original_commit = db.commit
    calls = 0

    def fail_commit_after_provider_ack():
        nonlocal calls
        calls += 1
        if calls == 3:
            raise SQLAlchemyError("sensitive commit detail +8613800138000")
        return original_commit()

    monkeypatch.setattr(sms, "httpx", SimpleNamespace(Client=_Client))
    monkeypatch.setattr(db, "commit", fail_commit_after_provider_ack)
    with caplog.at_level(logging.INFO):
        response = client.post(
            "/api/v1/admin/registration-invitations",
            headers=headers,
            json={"phone": "13800138000"},
        )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "provider_ack_persistence_failed"
    assert calls == 3
    verification_db = sessionmaker(bind=db.get_bind())()
    try:
        assert verification_db.query(RegistrationInvitation).count() == 1
        row = verification_db.query(RegistrationInvitation).one()
        assert row.status == "created"
        assert row.send_attempt_count == 0
        delivered = json.loads(_Client.captured_params["TemplateParam"])
        from app.services.registration_invitation import find_invitation_by_code

        assert find_invitation_by_code(verification_db, delivered["code"]).id == row.id
    finally:
        verification_db.close()
    assert "provider_ack_persistence_failed" in caplog.text
    assert "+8613800138000" not in caplog.text


def test_provider_ack_followed_by_audit_flush_failure_is_not_reported_as_unsent(
    client, db, auth_user_and_headers, monkeypatch, caplog
):
    from app.services import registration_invitation_sms as sms

    user, headers = auth_user_and_headers
    user.is_admin = True
    db.commit()
    provider_calls = 0
    original_post = _Client.post

    def counted_post(self, url, data):
        nonlocal provider_calls
        provider_calls += 1
        return original_post(self, url, data)

    def fail_terminal_audit(session, flush_context, instances):
        del flush_context, instances
        if any(
            isinstance(item, AgentAuditLog)
            and item.action == "registration_invitation_send_terminal"
            for item in session.new
        ):
            raise SQLAlchemyError("sensitive audit persistence detail")

    monkeypatch.setattr(_Client, "post", counted_post)
    monkeypatch.setattr(sms, "httpx", SimpleNamespace(Client=_Client))
    event.listen(db, "before_flush", fail_terminal_audit)
    try:
        with caplog.at_level(logging.INFO):
            response = client.post(
                "/api/v1/admin/registration-invitations",
                headers=headers,
                json={"phone": "13800138000"},
            )
    finally:
        event.remove(db, "before_flush", fail_terminal_audit)

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "provider_ack_persistence_failed"
    assert provider_calls == 1
    verification_db = sessionmaker(bind=db.get_bind())()
    try:
        assert verification_db.query(RegistrationInvitation).count() == 1
        row = verification_db.query(RegistrationInvitation).one()
        assert row.status == "created"
        assert row.send_attempt_count == 0
    finally:
        verification_db.close()
    assert "provider_ack_persistence_failed" in caplog.text
    assert "sensitive audit persistence detail" not in caplog.text


def test_provider_ack_followed_by_response_snapshot_failure_is_bounded(
    client, db, auth_user_and_headers, monkeypatch, caplog
):
    from app.services import registration_invitation_sms as sms

    user, headers = auth_user_and_headers
    user.is_admin = True
    db.commit()
    monkeypatch.setattr(sms, "httpx", SimpleNamespace(Client=_Client))

    def fail_snapshot(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("sensitive response snapshot +8613800138000")

    monkeypatch.setattr(admin_api, "_delivered_payload", fail_snapshot)
    with caplog.at_level(logging.INFO):
        response = client.post(
            "/api/v1/admin/registration-invitations",
            headers=headers,
            json={"phone": "13800138000"},
        )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "provider_ack_persistence_failed"
    verification_db = sessionmaker(bind=db.get_bind())()
    try:
        assert verification_db.query(RegistrationInvitation).one().status == "created"
    finally:
        verification_db.close()
    assert "+8613800138000" not in caplog.text


def test_phase_one_commit_failure_never_calls_provider(
    client, db, auth_user_and_headers, monkeypatch
):
    from app.services import registration_invitation_sms as sms

    user, headers = auth_user_and_headers
    user.is_admin = True
    db.commit()
    original_commit = db.commit
    commit_calls = 0
    provider_calls = 0
    original_post = _Client.post

    def fail_phase_one_commit():
        nonlocal commit_calls
        commit_calls += 1
        if commit_calls == 2:
            raise SQLAlchemyError("phase-one failed")
        return original_commit()

    def counted_post(self, url, data):
        nonlocal provider_calls
        provider_calls += 1
        return original_post(self, url, data)

    monkeypatch.setattr(db, "commit", fail_phase_one_commit)
    monkeypatch.setattr(_Client, "post", counted_post)
    monkeypatch.setattr(sms, "httpx", SimpleNamespace(Client=_Client))

    response = client.post(
        "/api/v1/admin/registration-invitations",
        headers=headers,
        json={"phone": "13800138000"},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "registration_invitation_persistence_failed"
    assert provider_calls == 0
    assert db.query(RegistrationInvitation).count() == 0


def test_exception_before_delivery_attempt_leaves_recoverable_created_row(
    client, db, auth_user_and_headers, monkeypatch, caplog
):
    user, headers = auth_user_and_headers
    user.is_admin = True
    db.commit()

    def fail_before_attempt(payload):
        del payload
        raise RuntimeError("sensitive pre-delivery detail +8613800138000")

    monkeypatch.setattr(
        admin_api,
        "send_frozen_registration_invitation_sms",
        fail_before_attempt,
    )
    with caplog.at_level(logging.INFO):
        response = client.post(
            "/api/v1/admin/registration-invitations",
            headers=headers,
            json={"phone": "13800138000"},
        )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "registration_invitation_delivery_not_started"
    verification_db = sessionmaker(bind=db.get_bind())()
    try:
        row = verification_db.query(RegistrationInvitation).one()
        assert row.status == "created"
        assert row.send_attempt_count == 0
    finally:
        verification_db.close()
    assert "registration_invitation_delivery_not_started" in caplog.text
    assert "+8613800138000" not in caplog.text


def test_ack_phase_two_failure_after_resend_keeps_rotated_credentials_durable(
    client, db, auth_user_and_headers, monkeypatch
):
    from app.services import registration_invitation_sms as sms
    from app.services.registration_invitation import (
        find_invitation_by_code,
        find_invitation_by_link_token,
    )

    user, headers = auth_user_and_headers
    user.is_admin = True
    db.commit()
    monkeypatch.setattr(sms, "httpx", SimpleNamespace(Client=_Client))
    created = client.post(
        "/api/v1/admin/registration-invitations",
        headers=headers,
        json={"phone": "13800138000"},
    ).json()
    old_code = created["manual_code"]
    old_link = created["link_token"]
    original_commit = db.commit
    commit_calls = 0

    def fail_resend_phase_two_commit():
        nonlocal commit_calls
        commit_calls += 1
        if commit_calls == 3:
            raise SQLAlchemyError("phase-two resend failed")
        return original_commit()

    monkeypatch.setattr(db, "commit", fail_resend_phase_two_commit)
    response = client.post(
        f"/api/v1/admin/registration-invitations/{created['id']}/resend",
        headers=headers,
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "provider_ack_persistence_failed"
    verification_db = sessionmaker(bind=db.get_bind())()
    try:
        row = verification_db.get(RegistrationInvitation, created["id"])
        assert row.status == "created"
        assert find_invitation_by_code(verification_db, old_code) is None
        assert find_invitation_by_link_token(verification_db, old_link) is None
        delivered = json.loads(_Client.captured_params["TemplateParam"])
        assert find_invitation_by_code(verification_db, delivered["code"]).id == row.id
        new_link = delivered["link"].rsplit("=", 1)[-1]
        assert find_invitation_by_link_token(verification_db, new_link).id == row.id
        assert verification_db.query(RegistrationInvitation).count() == 1
    finally:
        verification_db.close()


def _rotate_phase_one_snapshot(db, invitation_id):
    from app.services.registration_invitation import rotate_registration_invitation_credentials
    from app.services.registration_invitation_sms import freeze_registration_invitation_delivery

    row = db.get(RegistrationInvitation, invitation_id)
    rotated = rotate_registration_invitation_credentials(db, row)
    frozen = freeze_registration_invitation_delivery(
        row,
        manual_code=rotated.manual_code,
        link_token=rotated.link_token,
    )
    db.flush()
    credential_snapshot = admin_api._credential_payload_snapshot(
        row,
        rotated.manual_code,
        rotated.link_token,
    )
    db.commit()
    return frozen, credential_snapshot


def test_older_success_cannot_overwrite_newer_failed_resend(
    db, auth_user_and_headers, caplog
):
    from app.services.registration_invitation import (
        find_invitation_by_code,
        find_invitation_by_link_token,
    )
    from app.services.registration_invitation_sms import RegistrationInvitationDeliveryResult

    actor, _ = auth_user_and_headers
    initial = create_registration_invitation(db, "13800138000", created_by=actor.id)
    invitation_id = initial.invitation.id
    db.commit()
    phase_a, snapshot_a = _rotate_phase_one_snapshot(db, invitation_id)
    phase_b, snapshot_b = _rotate_phase_one_snapshot(db, invitation_id)

    with caplog.at_level(logging.INFO):
        with pytest.raises(HTTPException) as exc_info:
            admin_api._persist_delivery_outcome(
                db,
                delivery_payload=phase_a,
                actor_id=actor.id,
                credential_snapshot=snapshot_a,
                outcome=RegistrationInvitationDeliveryResult("sent", None),
            )
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "delivery_attempt_superseded"

    response = admin_api._persist_delivery_outcome(
        db,
        delivery_payload=phase_b,
        actor_id=actor.id,
        credential_snapshot=snapshot_b,
        outcome=RegistrationInvitationDeliveryResult("send_failed", "provider_rejected"),
    )
    assert response.status == "send_failed"

    verification_db = sessionmaker(bind=db.get_bind())()
    try:
        row = verification_db.get(RegistrationInvitation, invitation_id)
        assert row.status == "send_failed"
        assert row.send_attempt_count == 1
        assert find_invitation_by_code(verification_db, phase_a.manual_code) is None
        assert find_invitation_by_link_token(verification_db, phase_a.link_token) is None
        assert find_invitation_by_code(verification_db, phase_b.manual_code).id == invitation_id
        assert find_invitation_by_link_token(verification_db, phase_b.link_token).id == invitation_id
        assert (
            verification_db.query(AgentAuditLog)
            .filter(AgentAuditLog.action == "registration_invitation_send_terminal")
            .count()
            == 1
        )
    finally:
        verification_db.close()
    assert phase_a.expected_code_digest not in caplog.text
    assert phase_a.expected_link_token_digest not in caplog.text


def test_older_failure_cannot_overwrite_newer_successful_resend(
    db, auth_user_and_headers
):
    from app.services.registration_invitation import find_invitation_by_code
    from app.services.registration_invitation_sms import RegistrationInvitationDeliveryResult

    actor, _ = auth_user_and_headers
    initial = create_registration_invitation(db, "13800138000", created_by=actor.id)
    invitation_id = initial.invitation.id
    db.commit()
    phase_a, snapshot_a = _rotate_phase_one_snapshot(db, invitation_id)
    phase_b, snapshot_b = _rotate_phase_one_snapshot(db, invitation_id)

    response = admin_api._persist_delivery_outcome(
        db,
        delivery_payload=phase_b,
        actor_id=actor.id,
        credential_snapshot=snapshot_b,
        outcome=RegistrationInvitationDeliveryResult("sent", None),
    )
    assert response.status == "sent"
    with pytest.raises(HTTPException) as exc_info:
        admin_api._persist_delivery_outcome(
            db,
            delivery_payload=phase_a,
            actor_id=actor.id,
            credential_snapshot=snapshot_a,
            outcome=RegistrationInvitationDeliveryResult("send_failed", "provider_timeout"),
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "delivery_attempt_superseded"

    verification_db = sessionmaker(bind=db.get_bind())()
    try:
        row = verification_db.get(RegistrationInvitation, invitation_id)
        assert row.status == "sent"
        assert row.send_attempt_count == 1
        assert find_invitation_by_code(verification_db, phase_a.manual_code) is None
        assert find_invitation_by_code(verification_db, phase_b.manual_code).id == invitation_id
        assert (
            verification_db.query(AgentAuditLog)
            .filter(AgentAuditLog.action == "registration_invitation_send_terminal")
            .count()
            == 1
        )
    finally:
        verification_db.close()
