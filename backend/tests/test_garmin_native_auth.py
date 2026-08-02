from datetime import UTC, datetime, timedelta
import logging

import pytest
from starlette.requests import Request

from app.api import auth as auth_api
from app.models.user import GarminCredential, User
from app.schemas.auth import GarminCredentialCreate
from app.services.auth import garmin_credential_service
from app.services.data_collection import garmin_connect
from app.services.data_collection.garmin_connect import GarminConnectService


def test_client_factory_supports_garminconnect_03_native_client() -> None:
    service = GarminConnectService("nobody@example.com", "not-a-real-password")

    client = service._create_client(verify_login=False)

    assert hasattr(client, "client")
    assert not hasattr(client, "garth")
    assert callable(client.client.dumps)
    assert callable(client.client.loads)
    assert client.client.is_authenticated is False


def test_native_token_store_is_versioned_encrypted_and_round_trips() -> None:
    from app.services.data_collection.garmin_native_auth import (
        decode_native_token_store,
        encode_native_token_store,
        has_native_token_store,
    )

    token_payload = '{"di_token":"top-secret-token","di_refresh_token":"refresh"}'

    envelope = encode_native_token_store(token_payload)

    assert "top-secret-token" not in envelope
    assert "refresh" not in envelope
    assert decode_native_token_store(envelope) == token_payload
    assert has_native_token_store(envelope) is True


@pytest.mark.parametrize(
    "stored_value",
    [
        '{"oauth1_token.json":{"oauth_token":"legacy"}}',
        "not-json",
        '{"version":2,"format":"garmin_di_oauth","ciphertext":"invalid"}',
    ],
)
def test_native_token_store_rejects_legacy_or_malformed_values(stored_value: str) -> None:
    from app.services.data_collection.garmin_native_auth import (
        GarminNativeTokenError,
        decode_native_token_store,
        has_native_token_store,
    )

    assert has_native_token_store(stored_value) is False
    with pytest.raises(GarminNativeTokenError):
        decode_native_token_store(stored_value)


def test_replacing_credentials_clears_stale_authentication_state(db) -> None:
    user = User(
        username="garmin-native-reset",
        email="app-user@example.com",
        hashed_password="unused",
        name="Garmin Native Reset",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    credential = garmin_credential_service.save_credentials(
        db,
        user.id,
        "old-garmin@example.com",
        "old-password",
    )
    credential.garth_session = "legacy-token-state"
    credential.session_expires_at = datetime.now(UTC) + timedelta(hours=12)
    credential.requires_mfa = True
    credential.login_locked_until = datetime.now(UTC) + timedelta(minutes=30)
    credential.error_count = 3
    credential.last_error = "old failure"
    db.commit()

    updated = garmin_credential_service.save_credentials(
        db,
        user.id,
        "new-garmin@example.com",
        "new-password",
        is_cn=True,
    )

    assert updated.garth_session is None
    assert updated.session_expires_at is None
    assert updated.requires_mfa is False
    assert updated.login_locked_until is None
    assert updated.error_count == 0
    assert updated.last_error is None
    assert updated.credentials_valid is True
    assert garmin_credential_service.decrypt_password(updated.encrypted_password) == "new-password"
    assert db.query(GarminCredential).filter_by(user_id=user.id).one().id == updated.id


def test_general_secret_codec_keeps_password_round_trip() -> None:
    encrypted = garmin_credential_service.encrypt_secret("private-value")

    assert "private-value" not in encrypted
    assert garmin_credential_service.decrypt_secret(encrypted) == "private-value"


@pytest.mark.asyncio
async def test_connection_endpoint_never_echoes_upstream_secret(
    db,
    monkeypatch,
    caplog,
) -> None:
    user, _credential = _create_saved_credential(db, "safe-endpoint")

    def fail_connection(_self, db=None):
        raise RuntimeError("upstream-secret-value")

    monkeypatch.setattr(
        GarminConnectService,
        "test_connection_with_mfa",
        fail_connection,
    )

    response = await auth_api.test_garmin_connection(
        Request({"type": "http", "method": "POST", "path": "/auth/garmin/test-connection", "client": ("127.0.0.1", 12345), "headers": []}),
        GarminCredentialCreate(
            garmin_email="garmin-safe-endpoint@example.com",
            garmin_password="password-secret-value",
            is_cn=False,
        ),
        current_user=user,
        db=db,
    )

    rendered = response.message + caplog.text
    assert response.success is False
    assert "upstream-secret-value" not in rendered
    assert "password-secret-value" not in rendered
    assert "暂时不可用" in response.message


def test_daily_sync_logging_never_echoes_upstream_secret(
    db,
    monkeypatch,
    caplog,
) -> None:
    service = GarminConnectService(
        "garmin-safe-log@example.com",
        "password-secret-value",
        user_id=99,
    )

    def fail_authentication(_db):
        raise RuntimeError("sync-upstream-secret")

    monkeypatch.setattr(service, "_ensure_authenticated", fail_authentication)

    with pytest.raises(RuntimeError, match="sync-upstream-secret"):
        service.sync_daily_data(db, 99, datetime.now(UTC).date())

    assert "sync-upstream-secret" not in caplog.text
    assert "password-secret-value" not in caplog.text


def test_native_token_restore_redacts_third_party_debug_logging(
    db,
    monkeypatch,
    caplog,
) -> None:
    from app.services.data_collection.garmin_native_auth import encode_native_token_store

    user, credential = _create_saved_credential(db, "debug-redaction")
    token_payload = '{"di_token":"debug-secret-token","di_refresh_token":"debug-refresh"}'
    credential.garth_session = encode_native_token_store(token_payload)
    db.commit()

    class LoggingGarmin:
        def __init__(self, *_args, **_kwargs):
            self.client = type("Native", (), {"is_authenticated": False})()
            self.display_name = None

        def login(self, tokenstore=None):
            logging.getLogger("garminconnect").debug("tokenstore=%s", tokenstore)
            raise RuntimeError("restore failed")

    monkeypatch.setattr(garmin_connect, "Garmin", LoggingGarmin)
    service = GarminConnectService(
        credential.garmin_email,
        "fake-password",
        user_id=user.id,
    )

    with caplog.at_level(logging.DEBUG, logger="garminconnect"):
        assert service._load_session_from_db(db) is False

    assert "debug-secret-token" not in caplog.text
    assert "debug-refresh" not in caplog.text


def test_atomic_connect_failure_preserves_existing_credentials(db, monkeypatch) -> None:
    user, credential = _create_saved_credential(db, "atomic-failure")
    credential.garth_session = "old-token-envelope"
    old_password = credential.encrypted_password
    db.commit()

    class FailingGarmin:
        def __init__(self, *_args, **_kwargs):
            self.client = type("Native", (), {"is_authenticated": False})()
            self.display_name = None

        def login(self):
            raise RuntimeError("wrong password")

    monkeypatch.setattr(garmin_connect, "Garmin", FailingGarmin)
    service = GarminConnectService(
        "replacement@example.com",
        "wrong-password",
        user_id=user.id,
    )

    result = service.connect_and_save(db)

    db.refresh(credential)
    assert result["success"] is False
    assert credential.garmin_email == "garmin-atomic-failure@example.com"
    assert credential.encrypted_password == old_password
    assert credential.garth_session == "old-token-envelope"


def test_atomic_connect_success_replaces_credentials_and_token(db, monkeypatch) -> None:
    from app.services.data_collection.garmin_native_auth import decode_native_token_store

    user, credential = _create_saved_credential(db, "atomic-success")
    fake_garmin = _install_fake_garmin(monkeypatch)
    service = GarminConnectService(
        "replacement@example.com",
        "replacement-password",
        is_cn=True,
        user_id=user.id,
    )

    result = service.connect_and_save(db)

    db.refresh(credential)
    assert result["success"] is True
    assert fake_garmin.instances[0].login_calls == [None]
    assert credential.garmin_email == "replacement@example.com"
    assert credential.is_cn is True
    assert garmin_credential_service.decrypt_password(credential.encrypted_password) == (
        "replacement-password"
    )
    assert decode_native_token_store(credential.garth_session) == (
        '{"di_token":"new","di_refresh_token":"refresh"}'
    )


def test_atomic_connect_commit_failure_preserves_existing_credentials(db, monkeypatch) -> None:
    user, credential = _create_saved_credential(db, "atomic-rollback")
    credential.garth_session = "old-token-envelope"
    old_password = credential.encrypted_password
    db.commit()
    _install_fake_garmin(monkeypatch)
    original_commit = db.commit

    def fail_commit():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(db, "commit", fail_commit)
    service = GarminConnectService(
        "replacement@example.com",
        "replacement-password",
        user_id=user.id,
    )

    result = service.connect_and_save(db)

    monkeypatch.setattr(db, "commit", original_commit)
    db.expire_all()
    persisted = db.query(GarminCredential).filter_by(user_id=user.id).one()
    assert result["success"] is False
    assert persisted.garmin_email == "garmin-atomic-rollback@example.com"
    assert persisted.encrypted_password == old_password
    assert persisted.garth_session == "old-token-envelope"


def test_login_lock_uses_consistent_datetime_awareness(db) -> None:
    user, credential = _create_saved_credential(db, "login-lock")
    credential.login_locked_until = datetime.now(UTC) + timedelta(minutes=10)
    db.commit()
    service = GarminConnectService(
        credential.garmin_email,
        "fake-password",
        user_id=user.id,
    )

    assert service._check_login_lock(db) is not None


def _create_saved_credential(db, suffix: str = "service") -> tuple[User, GarminCredential]:
    user = User(
        username=f"garmin-native-{suffix}",
        email=f"app-{suffix}@example.com",
        hashed_password="unused",
        name=f"Garmin Native {suffix}",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    credential = garmin_credential_service.save_credentials(
        db,
        user.id,
        f"garmin-{suffix}@example.com",
        "fake-password",
    )
    return user, credential


def _install_fake_garmin(
    monkeypatch,
    *,
    login_result: tuple[str | None, object | None] = (None, None),
    dumped_payload: str = '{"di_token":"new","di_refresh_token":"refresh"}',
):
    class FakeNativeClient:
        def __init__(self) -> None:
            self.is_authenticated = False

        def dumps(self) -> str:
            return dumped_payload

        def loads(self, _payload: str) -> None:
            self.is_authenticated = True

        def connectapi(self, _path: str):
            return {"displayName": "fake-display", "fullName": "Fake User"}

    class FakeGarmin:
        instances = []

        def __init__(self, email, password, is_cn=False, **kwargs) -> None:
            self.username = email
            self.password = password
            self.is_cn = is_cn
            self.kwargs = kwargs
            self.client = FakeNativeClient()
            self.display_name = None
            self.full_name = None
            self.login_calls = []
            self.__class__.instances.append(self)

        def login(self, tokenstore=None):
            self.login_calls.append(tokenstore)
            if login_result[0] != "needs_mfa":
                self.client.is_authenticated = True
                self.display_name = "fake-display"
            return login_result

        def get_full_name(self):
            return self.full_name

    monkeypatch.setattr(garmin_connect, "Garmin", FakeGarmin)
    return FakeGarmin


def test_fresh_native_login_persists_encrypted_token_store(db, monkeypatch) -> None:
    from app.services.data_collection.garmin_native_auth import decode_native_token_store

    user, _credential = _create_saved_credential(db, "fresh")
    fake_garmin = _install_fake_garmin(monkeypatch)
    service = GarminConnectService(
        "garmin-fresh@example.com",
        "fake-password",
        user_id=user.id,
    )

    service._ensure_authenticated(db)

    stored = db.query(GarminCredential).filter_by(user_id=user.id).one()
    assert service._authenticated is True
    assert fake_garmin.instances[0].login_calls == [None]
    assert decode_native_token_store(stored.garth_session) == (
        '{"di_token":"new","di_refresh_token":"refresh"}'
    )
    assert stored.requires_mfa is False


def test_native_token_restore_uses_login_tokenstore_and_persists_rotation(db, monkeypatch) -> None:
    from app.services.data_collection.garmin_native_auth import (
        decode_native_token_store,
        encode_native_token_store,
    )

    user, credential = _create_saved_credential(db, "restore")
    original_payload = '{"di_token":"old","di_refresh_token":"old-refresh"}'
    credential.garth_session = encode_native_token_store(original_payload)
    db.commit()
    fake_garmin = _install_fake_garmin(
        monkeypatch,
        dumped_payload='{"di_token":"rotated","di_refresh_token":"new-refresh"}',
    )
    service = GarminConnectService(
        "garmin-restore@example.com",
        "fake-password",
        user_id=user.id,
    )

    service._ensure_authenticated(db)

    stored = db.query(GarminCredential).filter_by(user_id=user.id).one()
    assert fake_garmin.instances[0].login_calls == [original_payload]
    assert decode_native_token_store(stored.garth_session) == (
        '{"di_token":"rotated","di_refresh_token":"new-refresh"}'
    )


def test_legacy_session_is_not_passed_to_native_login(db, monkeypatch) -> None:
    user, credential = _create_saved_credential(db, "legacy")
    credential.garth_session = '{"oauth1_token.json":{"oauth_token":"legacy-secret"}}'
    db.commit()
    fake_garmin = _install_fake_garmin(monkeypatch)
    service = GarminConnectService(
        "garmin-legacy@example.com",
        "fake-password",
        user_id=user.id,
    )

    service._ensure_authenticated(db)

    assert fake_garmin.instances[0].login_calls == [None]


def test_native_mfa_tuple_registers_user_bound_session(db, monkeypatch) -> None:
    from app.services.data_collection.garmin_connect import GarminMFARequiredError

    garmin_connect._mfa_sessions.clear()
    user, _credential = _create_saved_credential(db, "mfa")
    _install_fake_garmin(monkeypatch, login_result=("needs_mfa", None))
    service = GarminConnectService(
        "garmin-mfa@example.com",
        "fake-password",
        user_id=user.id,
    )

    with pytest.raises(GarminMFARequiredError) as exc_info:
        service._ensure_authenticated(db)

    session_id = exc_info.value.client_state["session_id"]
    session = garmin_connect._mfa_sessions[session_id]
    assert session["user_id"] == user.id
    assert session["email"] == "garmin-mfa@example.com"
    assert session["client_state"] is None
    assert session["authenticated"] is False


def test_workout_sync_accepts_authenticated_native_client() -> None:
    from app.services.workout_sync import WorkoutSyncService

    class Native:
        is_authenticated = True

    class Client:
        client = Native()

    authenticated_client = Client()

    service = WorkoutSyncService(
        "garmin-workout@example.com",
        "fake-password",
        user_id=42,
        client=authenticated_client,
    )

    assert service.client is authenticated_client
    assert service._authenticated is True


def test_session_renewal_delegates_to_shared_native_service(db, monkeypatch) -> None:
    from app.services.data_collection import garmin_connect as garmin_connect_module
    from app.services.data_collection.garmin_native_auth import encode_native_token_store
    from app.tasks.garmin_sync import _renew_single_session

    user, credential = _create_saved_credential(db, "renew")
    credential.garth_session = encode_native_token_store(
        '{"di_token":"renew-old","di_refresh_token":"renew-refresh"}'
    )
    db.commit()
    calls = []

    class FakeGarminService:
        def __init__(self, email, password, is_cn=False, user_id=None):
            calls.append((email, password, is_cn, user_id))
            self.client = object()

        def _ensure_authenticated(self, passed_db):
            assert passed_db is db

    monkeypatch.setattr(garmin_connect_module, "GarminConnectService", FakeGarminService)

    result = _renew_single_session(db, credential, "[test-renew]")

    assert result == "renewed"
    assert calls == [
        (credential.garmin_email, "fake-password", credential.is_cn, user.id),
    ]
