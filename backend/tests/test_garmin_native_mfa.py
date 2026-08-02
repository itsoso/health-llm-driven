import time
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from starlette.requests import Request

from app.api import auth as auth_api
from app.models.user import User
from app.schemas.auth import GarminCredentialCreate, GarminMFAVerifyRequest
from app.services.auth import garmin_credential_service
from app.services.data_collection import garmin_connect
from app.services.data_collection.garmin_mfa import _mfa_sessions, verify_mfa_with_session
from app.services.data_collection.garmin_native_auth import (
    decode_native_token_store,
    encode_native_token_store,
)


class FakeNativeClient:
    def __init__(self) -> None:
        self.is_authenticated = False

    def dumps(self) -> str:
        return '{"di_token":"mfa-token","di_refresh_token":"mfa-refresh"}'

    def connectapi(self, _path: str):
        return {"displayName": "mfa-user", "fullName": "MFA User"}


def test_mfa_schema_accepts_only_six_digits() -> None:
    with pytest.raises(ValueError):
        GarminMFAVerifyRequest(mfa_code="abcdef", mfa_session_id="pending-session")


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
        "purpose": "existing",
        "attempts": 0,
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


def test_native_mfa_never_resumes_when_saved_account_changed(db) -> None:
    _mfa_sessions.clear()
    user, credential = _create_user_and_credential(db, "changed")
    fake = FakeGarmin()
    session_id = _put_session(user, credential, fake)
    credential.garmin_email = "replacement@example.com"
    db.commit()

    result = verify_mfa_with_session(
        session_id,
        "123456",
        user_id=user.id,
        db=db,
    )

    assert result["success"] is False
    assert fake.resume_calls == []


def test_native_mfa_stops_after_five_invalid_codes(db) -> None:
    _mfa_sessions.clear()
    user, credential = _create_user_and_credential(db, "attempts")
    fake = FakeGarmin(error=RuntimeError("invalid code"))
    session_id = _put_session(user, credential, fake)

    for _ in range(5):
        result = verify_mfa_with_session(
            session_id,
            "123456",
            user_id=user.id,
            db=db,
        )

    assert result["success"] is False
    assert session_id not in _mfa_sessions
    assert len(fake.resume_calls) == 5


def test_native_mfa_verification_serializes_shared_session_access(db) -> None:
    _mfa_sessions.clear()
    user, credential = _create_user_and_credential(db, "thread-safe")

    class ConcurrentInvalidGarmin(FakeGarmin):
        def __init__(self) -> None:
            super().__init__()
            self._counter_lock = threading.Lock()
            self.active = 0
            self.max_active = 0

        def resume_login(self, client_state, mfa_code: str):
            with self._counter_lock:
                self.active += 1
                self.max_active = max(self.max_active, self.active)
            try:
                time.sleep(0.05)
                raise RuntimeError("invalid code")
            finally:
                with self._counter_lock:
                    self.active -= 1

    fake = ConcurrentInvalidGarmin()
    session_id = _put_session(user, credential, fake)
    _mfa_sessions[session_id]["purpose"] = "test"

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                verify_mfa_with_session,
                session_id,
                "123456",
                user_id=user.id,
                db=db,
            )
            for _ in range(2)
        ]
        results = [future.result(timeout=2) for future in futures]

    assert all(result["success"] is False for result in results)
    assert fake.max_active == 1


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
        Request({"type": "http", "method": "POST", "path": "/auth/garmin/verify-mfa", "client": ("127.0.0.1", 12345), "headers": []}),
        GarminMFAVerifyRequest(mfa_code="123456", mfa_session_id="pending-session"),
        current_user=user,
        db=db,
    )

    db.refresh(credential)
    assert response.success is True
    assert credential.requires_mfa is True


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
        Request({"type": "http", "method": "POST", "path": "/auth/garmin/verify-mfa", "client": ("127.0.0.1", 12345), "headers": []}),
        GarminMFAVerifyRequest(mfa_code="123456", mfa_session_id="pending-session"),
        current_user=user,
        db=db,
    )

    rendered = response.message + caplog.text
    assert response.success is False
    assert "mfa-upstream-secret" not in rendered
    assert "123456" not in rendered
    assert "Garmin" in response.message


@pytest.mark.asyncio
async def test_test_connection_mfa_flow_is_side_effect_free(db, monkeypatch) -> None:
    """“测试连接”完成 MFA 后不得替换已保存连接或重置其错误状态。"""
    _mfa_sessions.clear()
    user, credential = _create_user_and_credential(db, "test-purpose")
    original_token = encode_native_token_store(
        '{"di_token":"original","di_refresh_token":"original-refresh"}'
    )
    credential.garth_session = original_token
    credential.credentials_valid = False
    credential.requires_mfa = True
    credential.error_count = 3
    credential.last_error = "existing failure"
    db.commit()

    class ChallengeGarmin(FakeGarmin):
        def __init__(self, *_args, **_kwargs) -> None:
            super().__init__()

        def login(self):
            return "needs_mfa", None

    monkeypatch.setattr(garmin_connect, "Garmin", ChallengeGarmin)
    request = Request({
        "type": "http",
        "method": "POST",
        "path": "/auth/garmin/test-connection",
        "client": ("127.0.0.1", 12345),
        "headers": [],
    })

    challenge = await auth_api.test_garmin_connection(
        request,
        GarminCredentialCreate(
            garmin_email=credential.garmin_email,
            garmin_password="fake-password",
            is_cn=credential.is_cn,
        ),
        current_user=user,
        db=db,
    )
    assert challenge.mfa_required is True
    assert _mfa_sessions[challenge.mfa_session_id]["purpose"] == "test"

    verified = await auth_api.verify_garmin_mfa(
        request,
        GarminMFAVerifyRequest(
            mfa_code="123456",
            mfa_session_id=challenge.mfa_session_id,
        ),
        current_user=user,
        db=db,
    )

    db.expire_all()
    persisted = db.query(type(credential)).filter_by(user_id=user.id).one()
    assert verified.success is True
    assert verified.session_id is None
    assert persisted.garth_session == original_token
    assert persisted.credentials_valid is False
    assert persisted.requires_mfa is True
    assert persisted.error_count == 3
    assert persisted.last_error == "existing failure"
