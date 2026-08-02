from __future__ import annotations

import logging

import pytest

from app.config import Settings, settings
from app.services import registration_invitation as service


@pytest.fixture(autouse=True)
def _dedicated_digest_key(monkeypatch):
    monkeypatch.setattr(
        settings,
        "registration_invitation_digest_key",
        "registration-invitation-test-key-with-at-least-32-bytes",
    )


def test_invalid_credential_still_uses_constant_time_digest_comparison(db, monkeypatch):
    """Only the in-memory digest comparison is claimed to be constant time."""

    calls: list[tuple[str, str]] = []
    real_compare_digest = service.hmac.compare_digest

    def observed_compare_digest(left: str, right: str) -> bool:
        calls.append((left, right))
        return real_compare_digest(left, right)

    monkeypatch.setattr(service.hmac, "compare_digest", observed_compare_digest)

    assert service.find_invitation_by_code(db, None) is None
    assert service.find_invitation_by_code(db, "not valid !") is None
    assert service.find_invitation_by_link_token(db, object()) is None

    assert len(calls) == 3
    assert all(len(left) == len(right) == 64 for left, right in calls)


@pytest.mark.parametrize(
    ("lookup", "invalid_value"),
    [
        ("code", "A" * 10_000),
        ("code", "ABCD!234"),
        ("link", "secret/" * 2_000),
        ("link", "x" * 129),
        ("grant", "private+" * 2_000),
        ("grant", "y" * 129),
    ],
    ids=[
        "code-too-long",
        "code-bad-charset",
        "link-too-long-bad-charset",
        "link-too-long",
        "grant-too-long-bad-charset",
        "grant-too-long",
    ],
)
def test_invalid_public_credential_is_mapped_to_fixed_sentinel_before_hmac(
    db,
    monkeypatch,
    lookup,
    invalid_value,
):
    hashed_messages: list[bytes] = []
    real_hmac_new = service.hmac.new

    def observed_hmac_new(key, msg=None, digestmod=None):
        if msg is not None:
            hashed_messages.append(msg)
        return real_hmac_new(key, msg, digestmod)

    monkeypatch.setattr(service.hmac, "new", observed_hmac_new)

    if lookup == "code":
        result = service.find_invitation_by_code(db, invalid_value)
    elif lookup == "link":
        result = service.find_invitation_by_link_token(db, invalid_value)
    else:
        with pytest.raises(service.InvalidRegistrationCredential):
            service.consume_phone_registration_grant(db, invalid_value, "+14155550199")
        result = None

    assert result is None
    assert hashed_messages
    assert all(invalid_value.encode() not in message for message in hashed_messages)
    assert all(len(message) < 160 for message in hashed_messages)


def test_phone_ciphertext_round_trips_but_repr_logs_and_errors_are_redacted(db, caplog):
    phone = "+14155550199"
    caplog.set_level(logging.DEBUG)

    created = service.create_registration_invitation(db, phone)
    issued = service.create_phone_registration_grant(db, phone)
    db.flush()
    db.expire_all()

    persisted = db.get(type(created.invitation), created.invitation.id)
    assert persisted is not None
    assert persisted.phone_ciphertext == phone
    assert phone not in repr(persisted)
    assert phone not in repr(created)
    assert created.manual_code not in repr(created)
    assert created.link_token not in repr(created)
    assert issued.token not in repr(issued)
    assert phone not in caplog.text
    assert created.manual_code not in caplog.text
    assert created.link_token not in caplog.text
    assert issued.token not in caplog.text

    with pytest.raises(service.InvalidRegistrationCredential) as exc_info:
        service.consume_phone_registration_grant(db, "bad grant", phone)
    error_text = repr(exc_info.value) + str(exc_info.value)
    assert phone not in error_text
    assert "bad grant" not in error_text


@pytest.mark.parametrize(
    ("rollout_enabled", "enforcement_enabled"),
    [(True, False), (False, True), (True, True)],
)
@pytest.mark.parametrize("digest_key", [None, "short-key"])
def test_production_registration_flags_require_strong_dedicated_digest_key(
    rollout_enabled,
    enforcement_enabled,
    digest_key,
):
    configured = dict(
        _env_file=None,
        secret_key="S" * 32,
        app_env="production",
        debug=False,
        garmin_encryption_key="B" * 44,
        device_encryption_key="C" * 44,
        registration_invitation_rollout_enabled=rollout_enabled,
        registration_invitation_enforcement_enabled=enforcement_enabled,
    )

    missing = Settings(**configured, registration_invitation_digest_key=digest_key)
    with pytest.raises(ValueError, match="REGISTRATION_INVITATION_DIGEST_KEY"):
        missing.validate_required_security()


@pytest.mark.parametrize(
    ("rollout_enabled", "enforcement_enabled"),
    [(True, False), (False, True), (True, True)],
)
def test_production_registration_flags_accept_32_byte_digest_key(
    rollout_enabled,
    enforcement_enabled,
):
    present = Settings(
        _env_file=None,
        secret_key="S" * 32,
        app_env="production",
        debug=False,
        garmin_encryption_key="B" * 44,
        device_encryption_key="C" * 44,
        registration_invitation_rollout_enabled=rollout_enabled,
        registration_invitation_enforcement_enabled=enforcement_enabled,
        registration_invitation_digest_key="K" * 32,
    )
    present.validate_required_security()


@pytest.mark.parametrize(
    ("rollout_enabled", "enforcement_enabled", "digest_key"),
    [
        (True, False, None),
        (False, True, None),
        (True, False, "short-key"),
        (False, True, "short-key"),
    ],
)
def test_runtime_fails_closed_for_missing_or_short_production_digest_key(
    monkeypatch,
    rollout_enabled,
    enforcement_enabled,
    digest_key,
):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "registration_invitation_rollout_enabled", rollout_enabled)
    monkeypatch.setattr(
        settings,
        "registration_invitation_enforcement_enabled",
        enforcement_enabled,
    )
    monkeypatch.setattr(settings, "registration_invitation_digest_key", digest_key)

    with pytest.raises(RuntimeError) as exc_info:
        service.phone_lookup_hmac("+14155550199")
    if digest_key:
        assert digest_key not in str(exc_info.value)


def test_development_defaults_do_not_require_digest_key():
    development = Settings(
        _env_file=None,
        secret_key="S" * 32,
        app_env="development",
        registration_invitation_enforcement_enabled=True,
        registration_invitation_digest_key=None,
    )

    development.validate_required_security()
