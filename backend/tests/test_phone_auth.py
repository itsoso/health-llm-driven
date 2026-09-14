from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace
from unittest.mock import Mock

from app.config import settings
from app.models.phone_auth import PhoneAuthCode
from app.models.user import User
from app.services.registration_invitation import create_registration_invitation


def _enable_dev_codes(monkeypatch):
    monkeypatch.setattr(settings, "auth_phone_code_dev_echo", True, raising=False)
    monkeypatch.setattr(settings, "auth_phone_code_resend_seconds", 0, raising=False)


def _enable_invitation_enforcement(monkeypatch):
    _enable_dev_codes(monkeypatch)
    monkeypatch.setattr(settings, "registration_invitation_rollout_enabled", True)
    monkeypatch.setattr(settings, "registration_invitation_enforcement_enabled", True)
    monkeypatch.setattr(
        settings,
        "registration_invitation_digest_key",
        "phone-code-invitation-tests-key-with-32-bytes",
    )


def test_phone_code_rejects_uninvited_unknown_phone_before_issuing_code(
    client, db, monkeypatch
):
    _enable_invitation_enforcement(monkeypatch)
    from app.api import auth as auth_api

    issue_phone_code = Mock()
    monkeypatch.setattr(auth_api, "issue_phone_code", issue_phone_code)

    response = client.post("/api/v1/auth/phone/code", json={"phone": "13800138100"})

    assert response.status_code == 403
    assert response.json()["detail"] == {
        "code": "REGISTRATION_INVITATION_REQUIRED",
        "message": "该手机号尚未开通，请联系管理员",
    }
    issue_phone_code.assert_not_called()
    assert db.query(PhoneAuthCode).filter(PhoneAuthCode.phone == "+8613800138100").count() == 0


def test_phone_code_allows_unknown_phone_with_active_invitation(client, db, monkeypatch):
    _enable_invitation_enforcement(monkeypatch)
    create_registration_invitation(db, "13800138101")
    db.commit()

    response = client.post("/api/v1/auth/phone/code", json={"phone": "13800138101"})

    assert response.status_code == 200
    assert response.json()["phone"] == "+8613800138101"
    assert db.query(PhoneAuthCode).filter(PhoneAuthCode.phone == "+8613800138101").count() == 1


def test_phone_code_allows_send_failed_invitation(client, db, monkeypatch):
    _enable_invitation_enforcement(monkeypatch)
    created = create_registration_invitation(db, "13800138106")
    created.invitation.status = "send_failed"
    db.commit()

    response = client.post("/api/v1/auth/phone/code", json={"phone": "13800138106"})

    assert response.status_code == 200


def test_phone_code_rejects_expired_revoked_and_consumed_invitations(
    client, db, monkeypatch
):
    _enable_invitation_enforcement(monkeypatch)
    cases = (
        ("13800138103", "expired"),
        ("13800138104", "revoked"),
        ("13800138105", "consumed"),
        ("13800138107", "active_consumed"),
    )
    for phone, invitation_status in cases:
        created = create_registration_invitation(db, phone)
        created.invitation.status = invitation_status
        if invitation_status == "expired":
            created.invitation.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        if invitation_status == "active_consumed":
            created.invitation.status = "created"
            created.invitation.consumed_at = datetime.now(UTC)
        db.commit()

        response = client.post("/api/v1/auth/phone/code", json={"phone": phone})

        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "REGISTRATION_INVITATION_REQUIRED"

    assert db.query(PhoneAuthCode).count() == 0


def test_phone_code_allows_existing_phone_without_invitation(client, db, monkeypatch):
    _enable_invitation_enforcement(monkeypatch)
    db.add(
        User(
            username="existing_phone_code_user",
            name="Existing phone user",
            phone="+8613800138102",
            phone_verified_at=datetime.now(UTC),
            is_active=True,
            is_approved=True,
        )
    )
    db.commit()

    response = client.post("/api/v1/auth/phone/code", json={"phone": "13800138102"})

    assert response.status_code == 200
    assert response.json()["phone"] == "+8613800138102"


def test_phone_code_rejects_inactive_or_unapproved_existing_phone(
    client, db, monkeypatch
):
    _enable_invitation_enforcement(monkeypatch)
    users = (
        User(
            username="inactive_phone_code_user",
            name="Inactive phone user",
            phone="+8613800138108",
            phone_verified_at=datetime.now(UTC),
            is_active=False,
            is_approved=True,
        ),
        User(
            username="unapproved_phone_code_user",
            name="Unapproved phone user",
            phone="+8613800138109",
            phone_verified_at=datetime.now(UTC),
            is_active=True,
            is_approved=False,
        ),
    )
    db.add_all(users)
    create_registration_invitation(db, "13800138108")
    create_registration_invitation(db, "13800138109")
    db.commit()

    for phone in ("13800138108", "13800138109"):
        response = client.post("/api/v1/auth/phone/code", json={"phone": phone})
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "REGISTRATION_INVITATION_REQUIRED"


def test_phone_code_rejects_unknown_phone_during_rollout_rollback(
    client, db, monkeypatch
):
    _enable_invitation_enforcement(monkeypatch)
    create_registration_invitation(db, "13800138110")
    db.commit()
    monkeypatch.setattr(settings, "registration_invitation_rollout_enabled", False)

    response = client.post("/api/v1/auth/phone/code", json={"phone": "13800138110"})

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "REGISTRATION_INVITATION_REQUIRED"
    assert db.query(PhoneAuthCode).count() == 0


def test_phone_code_login_auto_registers_and_reuses_existing_user(client, db, monkeypatch):
    _enable_dev_codes(monkeypatch)

    send = client.post("/api/v1/auth/phone/code", json={"phone": "13800138000"})
    assert send.status_code == 200
    code = send.json()["dev_code"]

    login = client.post("/api/v1/auth/phone/login", json={"phone": "+86 138 0013 8000", "code": code})
    assert login.status_code == 200
    body = login.json()
    assert body["access_token"]
    assert body["is_new_user"] is True
    assert body["user"]["phone"] == "+8613800138000"
    assert body["user"]["is_approved"] is True

    second_code = client.post("/api/v1/auth/phone/code", json={"phone": "13800138000"}).json()["dev_code"]
    second_login = client.post("/api/v1/auth/phone/login", json={"phone": "13800138000", "code": second_code})
    assert second_login.status_code == 200
    assert second_login.json()["is_new_user"] is False
    assert db.query(User).filter(User.phone == "+8613800138000").count() == 1


def test_phone_code_is_single_use(client, monkeypatch):
    _enable_dev_codes(monkeypatch)

    code = client.post("/api/v1/auth/phone/code", json={"phone": "13800138001"}).json()["dev_code"]
    assert client.post("/api/v1/auth/phone/login", json={"phone": "13800138001", "code": code}).status_code == 200

    reused = client.post("/api/v1/auth/phone/login", json={"phone": "13800138001", "code": code})
    assert reused.status_code == 400
    assert reused.json()["detail"] == "验证码无效或已过期"


def test_phone_code_rejects_expired_code(client, db, monkeypatch):
    _enable_dev_codes(monkeypatch)

    code = client.post("/api/v1/auth/phone/code", json={"phone": "13800138002"}).json()["dev_code"]
    from app.models.phone_auth import PhoneAuthCode

    record = db.query(PhoneAuthCode).filter(PhoneAuthCode.phone == "+8613800138002").first()
    record.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()

    expired = client.post("/api/v1/auth/phone/login", json={"phone": "13800138002", "code": code})
    assert expired.status_code == 400
    assert expired.json()["detail"] == "验证码无效或已过期"


def test_password_set_and_change_work_after_phone_login(client, monkeypatch):
    _enable_dev_codes(monkeypatch)

    code = client.post("/api/v1/auth/phone/code", json={"phone": "13800138003"}).json()["dev_code"]
    login = client.post("/api/v1/auth/phone/login", json={"phone": "13800138003", "code": code})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    set_password = client.post("/api/v1/auth/password/set", json={"new_password": "first-passphrase"}, headers=headers)
    assert set_password.status_code == 200

    password_login = client.post("/api/v1/auth/login/json", json={"username": "13800138003", "password": "first-passphrase"})
    assert password_login.status_code == 200

    changed = client.post(
        "/api/v1/auth/password/change",
        json={"old_password": "first-passphrase", "new_password": "second-passphrase"},
        headers=headers,
    )
    assert changed.status_code == 200

    old_password = client.post("/api/v1/auth/login/json", json={"username": "13800138003", "password": "first-passphrase"})
    assert old_password.status_code == 401
    new_password = client.post("/api/v1/auth/login/json", json={"username": "13800138003", "password": "second-passphrase"})
    assert new_password.status_code == 200


def test_phone_code_send_fails_loud_when_delivery_is_not_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "auth_phone_code_dev_echo", False, raising=False)
    monkeypatch.setattr(settings, "debug", False, raising=False)
    monkeypatch.setattr(settings, "app_env", "production", raising=False)
    monkeypatch.setattr(settings, "aliyun_access_key_id", None, raising=False)
    monkeypatch.setattr(settings, "aliyun_access_key_secret", None, raising=False)
    monkeypatch.setattr(settings, "aliyun_sms_access_key_id", None, raising=False)
    monkeypatch.setattr(settings, "aliyun_sms_access_key_secret", None, raising=False)
    monkeypatch.setattr(settings, "aliyun_sms_sign_name", None, raising=False)
    monkeypatch.setattr(settings, "aliyun_sms_template_code", None, raising=False)
    monkeypatch.setattr(settings, "aliyun_pnvs_sign_name", None, raising=False)
    monkeypatch.setattr(settings, "aliyun_pnvs_template_code", None, raising=False)

    response = client.post("/api/v1/auth/phone/code", json={"phone": "13800138004"})

    assert response.status_code == 503
    assert response.json()["detail"] == "短信通道未配置，请稍后再试"


def test_phone_code_sends_via_aliyun_sms_when_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "auth_phone_code_dev_echo", False, raising=False)
    monkeypatch.setattr(settings, "auth_phone_code_resend_seconds", 0, raising=False)
    monkeypatch.setattr(settings, "debug", False, raising=False)
    monkeypatch.setattr(settings, "app_env", "production", raising=False)
    monkeypatch.setattr(settings, "aliyun_sms_access_key_id", "test-key", raising=False)
    monkeypatch.setattr(settings, "aliyun_sms_access_key_secret", "test-secret", raising=False)
    monkeypatch.setattr(settings, "aliyun_sms_sign_name", "阿衡", raising=False)
    monkeypatch.setattr(settings, "aliyun_sms_template_code", "SMS_123456", raising=False)

    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"Code": "OK", "Message": "OK"}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            captured["timeout"] = kwargs.get("timeout")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, params):
            captured["url"] = url
            captured["params"] = params
            return FakeResponse()

    from app.services import phone_auth

    monkeypatch.setattr(phone_auth, "httpx", SimpleNamespace(Client=FakeClient), raising=False)

    response = client.post("/api/v1/auth/phone/code", json={"phone": "13800138005"})

    assert response.status_code == 200
    body = response.json()
    assert body["phone"] == "+8613800138005"
    assert body["dev_code"] is None
    params = captured["params"]
    assert captured["url"] == "https://dysmsapi.aliyuncs.com/"
    assert params["Action"] == "SendSms"
    assert params["PhoneNumbers"] == "13800138005"
    assert params["SignName"] == "阿衡"
    assert params["TemplateCode"] == "SMS_123456"
    assert "Signature" in params
    assert len(json.loads(params["TemplateParam"])["code"]) == 6


def _configure_pnvs(monkeypatch):
    monkeypatch.setattr(settings, "auth_phone_code_dev_echo", False, raising=False)
    monkeypatch.setattr(settings, "auth_phone_code_resend_seconds", 0, raising=False)
    monkeypatch.setattr(settings, "debug", False, raising=False)
    monkeypatch.setattr(settings, "app_env", "production", raising=False)
    monkeypatch.setattr(settings, "aliyun_sms_access_key_id", "test-key", raising=False)
    monkeypatch.setattr(settings, "aliyun_sms_access_key_secret", "test-secret", raising=False)
    monkeypatch.setattr(settings, "aliyun_sms_sign_name", None, raising=False)
    monkeypatch.setattr(settings, "aliyun_sms_template_code", None, raising=False)
    monkeypatch.setattr(settings, "aliyun_pnvs_sign_name", "恒创联众", raising=False)
    monkeypatch.setattr(settings, "aliyun_pnvs_template_code", "100001", raising=False)


class _FakePnvsClient:
    """Captures dypnsapi POST calls; response payload injected per test."""

    captured: dict = {}
    payload: dict = {}

    def __init__(self, *args, **kwargs):
        type(self).captured["timeout"] = kwargs.get("timeout")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url, data):
        type(self).captured["url"] = url
        type(self).captured["params"] = data

        payload = type(self).payload

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return payload

        return FakeResponse()


def test_phone_code_sends_via_aliyun_pnvs_when_configured(client, monkeypatch):
    _configure_pnvs(monkeypatch)
    _FakePnvsClient.captured = {}
    _FakePnvsClient.payload = {"Code": "OK", "Success": True}

    from app.services import phone_auth

    monkeypatch.setattr(phone_auth, "httpx", SimpleNamespace(Client=_FakePnvsClient), raising=False)

    response = client.post("/api/v1/auth/phone/code", json={"phone": "13800138006"})

    assert response.status_code == 200
    body = response.json()
    assert body["phone"] == "+8613800138006"
    assert body["dev_code"] is None
    params = _FakePnvsClient.captured["params"]
    assert _FakePnvsClient.captured["url"] == "https://dypnsapi.aliyuncs.com/"
    assert params["Action"] == "SendSmsVerifyCode"
    assert params["PhoneNumber"] == "13800138006"
    assert params["SignName"] == "恒创联众"
    assert params["TemplateCode"] == "100001"
    assert "Signature" in params
    template_param = json.loads(params["TemplateParam"])
    assert len(template_param["code"]) == 6
    assert template_param["min"] == "5"


def test_phone_code_pnvs_rejection_fails_loud(client, monkeypatch):
    _configure_pnvs(monkeypatch)
    _FakePnvsClient.captured = {}
    _FakePnvsClient.payload = {"Code": "Forbidden.NoPermission", "Success": False}

    from app.services import phone_auth

    monkeypatch.setattr(phone_auth, "httpx", SimpleNamespace(Client=_FakePnvsClient), raising=False)

    response = client.post("/api/v1/auth/phone/code", json={"phone": "13800138007"})

    assert response.status_code == 503
    assert response.json()["detail"] == "短信发送失败，请稍后再试"


def test_phone_code_prefers_enterprise_sms_channel_over_pnvs(client, monkeypatch):
    _configure_pnvs(monkeypatch)
    monkeypatch.setattr(settings, "aliyun_sms_sign_name", "小巴", raising=False)
    monkeypatch.setattr(settings, "aliyun_sms_template_code", "SMS_654321", raising=False)

    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"Code": "OK", "Message": "OK"}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url, params):
            captured["url"] = url
            captured["params"] = params
            return FakeResponse()

    from app.services import phone_auth

    monkeypatch.setattr(phone_auth, "httpx", SimpleNamespace(Client=FakeClient), raising=False)

    response = client.post("/api/v1/auth/phone/code", json={"phone": "13800138008"})

    assert response.status_code == 200
    assert captured["url"] == "https://dysmsapi.aliyuncs.com/"
    assert captured["params"]["SignName"] == "小巴"
