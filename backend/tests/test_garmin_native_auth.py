from datetime import UTC, datetime, timedelta

import pytest

from app.models.user import GarminCredential, User
from app.services.auth import garmin_credential_service
from app.services.data_collection.garmin_connect import GarminConnectService


def test_client_factory_supports_garminconnect_03_native_client() -> None:
    service = GarminConnectService("nobody@example.com", "not-a-real-password")

    client = service._create_patched_client(verify_login=False)

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
