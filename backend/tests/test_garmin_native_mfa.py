import time

import pytest

from app.api import auth as auth_api
from app.models.user import User
from app.schemas.auth import GarminMFAVerifyRequest
from app.services.auth import garmin_credential_service
from app.services.data_collection.garmin_mfa import _mfa_sessions, verify_mfa_with_session
from app.services.data_collection.garmin_native_auth import decode_native_token_store


class FakeNativeClient:
    def __init__(self) -> None:
        self.is_authenticated = False

    def dumps(self) -> str:
        return '{"di_token":"mfa-token","di_refresh_token":"mfa-refresh"}'

    def connectapi(self, _path: str):
        return {"displayName": "mfa-user", "fullName": "MFA User"}


class FakeGarmin:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.client = FakeNativeClient()
        self.display_name = None
        self.full_name = None
        self.error = error
        self.resume_calls = []

    def resume_login(self, client_state, mfa_code: str):
        self.resume_calls.append((client_state, mfa_code))
        if self.error:
            raise self.error
        self.client.is_authenticated = True
        return None, None

    def get_full_name(self):
        return self.full_name


def _create_user_and_credential(db, suffix: str):
    user = User(
        username=f"garmin-mfa-{suffix}",
        email=f"app-mfa-{suffix}@example.com",
        hashed_password="unused",
        name=f"Garmin MFA {suffix}",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    credential = garmin_credential_service.save_credentials(
        db,
        user.id,
        f"garmin-mfa-{suffix}@example.com",
        "fake-password",
        requires_mfa=True,
    )
    return user, credential


def _put_session(user, credential, client, *, expires: float | None = None) -> str:
    session_id = f"session-{user.id}"
    _mfa_sessions[session_id] = {
        "client": client,
        "client_state": None,
        "email": credential.garmin_email,
        "is_cn": credential.is_cn,
        "user_id": user.id,
        "authenticated": False,
        "expires": expires if expires is not None else time.time() + 300,
    }
    return session_id


def test_native_mfa_accepts_none_client_state_and_persists_token(db) -> None:
    _mfa_sessions.clear()
    user, credential = _create_user_and_credential(db, "success")
    fake = FakeGarmin()
    session_id = _put_session(user, credential, fake)

    result = verify_mfa_with_session(
        session_id,
        "123456",
        user_id=user.id,
        db=db,
    )

    db.refresh(credential)
    assert result["success"] is True
    assert fake.resume_calls == [(None, "123456")]
    assert decode_native_token_store(credential.garth_session) == (
        '{"di_token":"mfa-token","di_refresh_token":"mfa-refresh"}'
    )
    assert credential.requires_mfa is False
    assert credential.credentials_valid is True
    assert credential.last_error is None
    assert credential.error_count == 0


def test_native_mfa_session_is_scoped_to_application_user(db) -> None:
    _mfa_sessions.clear()
    owner, credential = _create_user_and_credential(db, "owner")
    other = User(
        username="garmin-mfa-other",
        email="other@example.com",
        hashed_password="unused",
        name="Other",
        is_active=True,
    )
    db.add(other)
    db.commit()
    db.refresh(other)
    fake = FakeGarmin()
    session_id = _put_session(owner, credential, fake)

    result = verify_mfa_with_session(
        session_id,
        "123456",
        user_id=other.id,
        db=db,
    )

    assert result["success"] is False
    assert "无效" in result["message"] or "过期" in result["message"]
    assert fake.resume_calls == []


def test_expired_native_mfa_session_never_calls_garmin(db) -> None:
    _mfa_sessions.clear()
    user, credential = _create_user_and_credential(db, "expired")
    fake = FakeGarmin()
    session_id = _put_session(user, credential, fake, expires=time.time() - 1)

    result = verify_mfa_with_session(
        session_id,
        "123456",
        user_id=user.id,
        db=db,
    )

    assert result["success"] is False
    assert fake.resume_calls == []


def test_native_mfa_error_does_not_echo_code_or_upstream_secret(db, caplog) -> None:
    _mfa_sessions.clear()
    user, credential = _create_user_and_credential(db, "failure")
    fake = FakeGarmin(error=RuntimeError("invalid 123456 upstream-secret"))
    session_id = _put_session(user, credential, fake)

    result = verify_mfa_with_session(
        session_id,
        "123456",
        user_id=user.id,
        db=db,
    )

    rendered = result["message"] + caplog.text
    assert result["success"] is False
    assert "123456" not in rendered
    assert "upstream-secret" not in rendered


@pytest.mark.asyncio
async def test_verify_mfa_endpoint_clears_requires_mfa(db, monkeypatch) -> None:
    user, credential = _create_user_and_credential(db, "endpoint")

    def fake_verify(*_args, **_kwargs):
        return {
            "success": True,
            "message": "Garmin 验证成功",
            "session_id": "verified-session",
        }

    from app.services.data_collection import garmin_connect

    monkeypatch.setattr(garmin_connect, "verify_mfa_with_session", fake_verify)

    response = await auth_api.verify_garmin_mfa(
        GarminMFAVerifyRequest(mfa_code="123456", mfa_session_id="pending-session"),
        current_user=user,
        db=db,
    )

    db.refresh(credential)
    assert response.success is True
    assert credential.requires_mfa is False


@pytest.mark.asyncio
async def test_verify_mfa_endpoint_never_echoes_upstream_secret(
    db,
    monkeypatch,
    caplog,
) -> None:
    user, _credential = _create_user_and_credential(db, "safe-endpoint")

    def fail_verify(*_args, **_kwargs):
        raise RuntimeError("mfa-upstream-secret")

    from app.services.data_collection import garmin_connect

    monkeypatch.setattr(garmin_connect, "verify_mfa_with_session", fail_verify)

    response = await auth_api.verify_garmin_mfa(
        GarminMFAVerifyRequest(mfa_code="123456", mfa_session_id="pending-session"),
        current_user=user,
        db=db,
    )

    rendered = response.message + caplog.text
    assert response.success is False
    assert "mfa-upstream-secret" not in rendered
    assert "123456" not in rendered
    assert "Garmin" in response.message
