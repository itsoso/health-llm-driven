"""OTP provider failures remain loud but never expose request credentials."""

import logging
import traceback

import httpx
import pytest

from app.config import settings
from app.services import phone_auth


PHONE = "+8613800138991"
OTP = "731942"
ACCESS_KEY_ID = "otp-access-key-private-marker"
ACCESS_KEY_SECRET = "otp-access-secret-private-marker"
PROVIDER_TEXT = "provider-free-form-private-marker"
SECRET_URL = (
    "https://provider.invalid/send?AccessKeyId=otp-access-key-private-marker"
    "&Signature=signature-private-marker"
    "&TemplateParam=731942&PhoneNumbers=13800138991"
)


@pytest.fixture(autouse=True)
def _production_sms(monkeypatch):
    monkeypatch.setattr(settings, "auth_phone_code_dev_echo", False)
    monkeypatch.setattr(settings, "auth_phone_code_resend_seconds", 0)
    monkeypatch.setattr(settings, "debug", False)
    monkeypatch.setattr(settings, "aliyun_sms_access_key_id", ACCESS_KEY_ID)
    monkeypatch.setattr(settings, "aliyun_sms_access_key_secret", ACCESS_KEY_SECRET)
    monkeypatch.setattr(phone_auth.secrets, "randbelow", lambda _limit: int(OTP))


class _FailureResponse:
    def __init__(self, failure: str):
        self.failure = failure

    def raise_for_status(self):
        if self.failure == "http_status":
            request = httpx.Request("GET", SECRET_URL)
            response = httpx.Response(502, request=request)
            raise httpx.HTTPStatusError(PROVIDER_TEXT, request=request, response=response)

    def json(self):
        if self.failure == "provider_reject":
            return {"Code": PROVIDER_TEXT, "Message": PROVIDER_TEXT}
        if self.failure == "invalid_ack":
            raise ValueError(f"{PROVIDER_TEXT} {SECRET_URL}")
        return {"Code": "OK"}


class _FailureClient:
    failure = ""

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def _request(self):
        if type(self).failure == "transport":
            request = httpx.Request("POST", SECRET_URL)
            raise httpx.RequestError(PROVIDER_TEXT, request=request)
        return _FailureResponse(type(self).failure)

    def get(self, url, params):
        return self._request()

    def post(self, url, data):
        return self._request()


def _configure_channel(monkeypatch, channel: str) -> None:
    if channel == "enterprise":
        monkeypatch.setattr(settings, "aliyun_sms_sign_name", "OTP-SIGN")
        monkeypatch.setattr(settings, "aliyun_sms_template_code", "SMS_OTP_PRIVATE")
        monkeypatch.setattr(settings, "aliyun_pnvs_sign_name", None)
        monkeypatch.setattr(settings, "aliyun_pnvs_template_code", None)
    else:
        monkeypatch.setattr(settings, "aliyun_sms_sign_name", None)
        monkeypatch.setattr(settings, "aliyun_sms_template_code", None)
        monkeypatch.setattr(settings, "aliyun_pnvs_sign_name", "PNVS-SIGN")
        monkeypatch.setattr(settings, "aliyun_pnvs_template_code", "100001")


def _forbidden_values() -> tuple[str, ...]:
    return (
        PHONE,
        "13800138991",
        OTP,
        ACCESS_KEY_ID,
        ACCESS_KEY_SECRET,
        "signature-private-marker",
        "TemplateParam",
        PROVIDER_TEXT,
        SECRET_URL,
    )


@pytest.mark.parametrize("channel", ["enterprise", "pnvs"])
@pytest.mark.parametrize(
    "failure",
    ["http_status", "transport", "provider_reject", "invalid_ack"],
)
def test_otp_delivery_failure_is_bounded_across_log_api_and_exception_chain(
    client, monkeypatch, caplog, channel, failure
):
    _configure_channel(monkeypatch, channel)
    _FailureClient.failure = failure
    monkeypatch.setattr(phone_auth.httpx, "Client", _FailureClient)
    sender = (
        phone_auth._send_aliyun_sms
        if channel == "enterprise"
        else phone_auth._send_aliyun_pnvs_sms
    )

    with caplog.at_level(logging.INFO), pytest.raises(
        phone_auth.PhoneCodeDeliveryFailed
    ) as exc_info:
        sender(PHONE, OTP)

    exception_surface = "".join(
        traceback.format_exception(exc_info.type, exc_info.value, exc_info.tb)
    ) + " ".join(
        (
            str(exc_info.value),
            repr(exc_info.value.__cause__),
            repr(exc_info.value.__context__),
        )
    )
    for forbidden in _forbidden_values():
        assert forbidden not in caplog.text
        assert forbidden not in exception_surface
    expected_code = {
        "http_status": "http_status",
        "transport": "transport",
        "provider_reject": "provider_rejected",
        "invalid_ack": "invalid_ack",
    }[failure]
    assert f"error_code={expected_code}" in caplog.text
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None

    caplog.clear()
    response = client.post(
        "/api/v1/auth/phone/code",
        json={"phone": PHONE, "purpose": "login"},
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "短信发送失败，请稍后再试"
    for forbidden in _forbidden_values():
        assert forbidden not in response.text
        assert forbidden not in caplog.text
