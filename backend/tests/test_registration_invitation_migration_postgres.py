"""Schema contracts for invitation-only phone registration."""

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import uuid

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.models.registration_invitation import (
    PhoneRegistrationGrant,
    RegistrationAuthAttemptAudit,
    RegistrationInvitation,
)
from app.models._encrypted import StrictEncryptedString, StrictEncryptionError
from app.services.managed_migrations import apply_managed_migrations


MIGRATION_ID = "20260801_230000_registration_invitations"
ACTIVE_INDEX = "uq_registration_invitations_active_phone_hmac"
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
POSTGRES_TEST_ENABLED = bool(
    TEST_DATABASE_URL
    and make_url(TEST_DATABASE_URL).get_backend_name() == "postgresql"
)


def _migration_path(dialect: str) -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "managed"
        / f"{MIGRATION_ID}.{dialect}.sql"
    )


def test_registration_invitation_model_uses_only_encrypted_phone_and_digests():
    invitation_columns = RegistrationInvitation.__table__.c
    grant_columns = PhoneRegistrationGrant.__table__.c

    assert "phone" not in invitation_columns
    assert "code" not in invitation_columns
    assert "link_token" not in invitation_columns
    assert "token" not in grant_columns
    assert isinstance(invitation_columns.phone_ciphertext.type, StrictEncryptedString)
    assert isinstance(grant_columns.phone_ciphertext.type, StrictEncryptedString)
    assert invitation_columns.code_digest.unique is True
    assert invitation_columns.link_token_digest.unique is True
    assert grant_columns.token_digest.unique is True
    assert set(RegistrationAuthAttemptAudit.__table__.c.keys()) == {
        "id", "outcome", "error_code", "invitation_id", "grant_id",
        "user_id", "phone_masked", "source_hmac", "created_at",
    }


def test_registration_invitation_is_usable_is_deterministic():
    now = datetime(2026, 8, 1, 23, 0, tzinfo=timezone.utc)
    invitation = RegistrationInvitation(status="sent", expires_at=now + timedelta(hours=1))

    assert invitation.is_usable(now) is True
    assert invitation.status == "sent"

    invitation.status = "revoked"
    assert invitation.is_usable(now) is False
    assert invitation.status == "revoked"

    invitation.status = "sent"
    invitation.expires_at = now
    assert invitation.is_usable(now) is False
    assert invitation.status == "sent"


def test_invitation_phone_encryption_failure_is_fail_loud_and_never_persists_plaintext(
    db,
    monkeypatch,
):
    from app.models import _encrypted

    plaintext = "+14155550101"

    def fail_encrypt(_value: bytes) -> bytes:
        raise RuntimeError(f"forced encryption failure for {plaintext}")

    monkeypatch.setattr(_encrypted._fernet, "encrypt", fail_encrypt)
    invitation = RegistrationInvitation(
        code_digest="strict-code-digest",
        link_token_digest="strict-link-digest",
        phone_ciphertext=plaintext,
        phone_hmac="strict-phone-hmac",
        phone_masked="+1***01",
        status="sent",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(invitation)

    with pytest.raises(StrictEncryptionError, match="sensitive value encryption failed") as exc_info:
        db.flush()
    assert plaintext not in str(exc_info.value)
    assert plaintext not in repr(exc_info.value)
    assert plaintext not in repr(getattr(exc_info.value, "params", None))
    assert plaintext not in repr(getattr(exc_info.value, "orig", None))
    assert plaintext not in repr(vars(exc_info.value))
    assert plaintext not in repr(exc_info.value.__cause__)
    assert plaintext not in repr(exc_info.value.__context__)
    db.rollback()

    persisted = db.execute(text(
        "SELECT phone_ciphertext FROM registration_invitations "
        "WHERE code_digest = 'strict-code-digest'"
    )).all()
    assert persisted == []


def test_grant_phone_encryption_failure_is_fail_loud_and_never_persists_plaintext(
    db,
    monkeypatch,
):
    from app.models import _encrypted

    plaintext = "+14155550102"

    def fail_encrypt(_value: bytes) -> bytes:
        raise RuntimeError(f"forced grant encryption failure for {plaintext}")

    monkeypatch.setattr(_encrypted._fernet, "encrypt", fail_encrypt)
    grant = PhoneRegistrationGrant(
        token_digest="strict-token-digest",
        phone_hmac="strict-grant-phone-hmac",
        phone_ciphertext=plaintext,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    db.add(grant)

    with pytest.raises(StrictEncryptionError, match="sensitive value encryption failed") as exc_info:
        db.flush()
    assert plaintext not in str(exc_info.value)
    assert plaintext not in repr(exc_info.value)
    assert plaintext not in repr(getattr(exc_info.value, "params", None))
    assert plaintext not in repr(getattr(exc_info.value, "orig", None))
    assert plaintext not in repr(vars(exc_info.value))
    assert plaintext not in repr(exc_info.value.__cause__)
    assert plaintext not in repr(exc_info.value.__context__)
    db.rollback()

    persisted = db.execute(text(
        "SELECT phone_ciphertext FROM phone_registration_grants "
        "WHERE token_digest = 'strict-token-digest'"
    )).all()
    assert persisted == []


def test_strict_encrypted_result_rejects_ciphertext_from_wrong_key_without_leak(
    monkeypatch, caplog
):
    from app.models import _encrypted

    plaintext = "+14155550991"
    ciphertext = _encrypted._fernet.encrypt(plaintext.encode()).decode()
    monkeypatch.setattr(_encrypted, "_fernet", Fernet(Fernet.generate_key()))

    with pytest.raises(StrictEncryptionError) as exc_info:
        StrictEncryptedString(512).process_result_value(ciphertext, None)

    exposed = " ".join(
        (
            str(exc_info.value),
            repr(exc_info.value),
            repr(exc_info.value.__cause__),
            repr(exc_info.value.__context__),
            caplog.text,
        )
    )
    assert "sensitive value decryption failed" in str(exc_info.value)
    assert plaintext not in exposed
    assert ciphertext not in exposed
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


def test_strict_encrypted_result_rejects_corrupt_ciphertext_without_raw_fallback(
    caplog,
):
    corrupt = "corrupt-ciphertext-must-not-return-or-log"

    with pytest.raises(StrictEncryptionError) as exc_info:
        StrictEncryptedString(512).process_result_value(corrupt, None)

    exposed = " ".join(
        (
            str(exc_info.value),
            repr(exc_info.value),
            repr(exc_info.value.__cause__),
            repr(exc_info.value.__context__),
            caplog.text,
        )
    )
    assert corrupt not in exposed
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


@pytest.mark.parametrize(
    ("operation", "message"),
    [
        ("bind", "sensitive value encryption failed"),
        ("result", "sensitive value decryption failed"),
    ],
)
def test_strict_encrypted_rejects_empty_string_without_exception_context(
    operation, message, caplog
):
    encrypted = StrictEncryptedString(512)
    processor = (
        encrypted.process_bind_param
        if operation == "bind"
        else encrypted.process_result_value
    )

    with pytest.raises(StrictEncryptionError, match=message) as exc_info:
        processor("", None)

    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    assert "拒绝" in caplog.text


def test_strict_encrypted_allows_none_and_round_trips_non_empty_value():
    encrypted = StrictEncryptedString(512)
    plaintext = "+14155550992"

    assert encrypted.process_bind_param(None, None) is None
    assert encrypted.process_result_value(None, None) is None
    ciphertext = encrypted.process_bind_param(plaintext, None)
    assert ciphertext
    assert ciphertext != plaintext
    assert encrypted.process_result_value(ciphertext, None) == plaintext


def test_is_usable_normalizes_sqlite_roundtrip_timestamps_as_utc():
    sqlite_engine = create_engine("sqlite:///:memory:")
    with sqlite_engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
    RegistrationInvitation.__table__.create(sqlite_engine)
    sqlite_session = sessionmaker(bind=sqlite_engine)()
    now_utc = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)
    invitation = RegistrationInvitation(
        code_digest="roundtrip-code-digest",
        link_token_digest="roundtrip-link-digest",
        phone_ciphertext="+14155550103",
        phone_hmac="roundtrip-phone-hmac",
        phone_masked="+1***03",
        status="sent",
        expires_at=now_utc + timedelta(minutes=5),
    )
    try:
        sqlite_session.add(invitation)
        sqlite_session.commit()
        invitation_id = invitation.id
        sqlite_session.expire_all()

        persisted = sqlite_session.get(RegistrationInvitation, invitation_id)
        assert persisted is not None
        assert persisted.expires_at.tzinfo is None
        assert persisted.is_usable(now_utc) is True
        assert persisted.is_usable(now_utc.replace(tzinfo=None)) is True
        assert persisted.is_usable(
            (now_utc + timedelta(minutes=5)).replace(tzinfo=None)
        ) is False
    finally:
        sqlite_session.close()
        sqlite_engine.dispose()


def test_sqlite_managed_migration_creates_constraints_and_partial_uniqueness(tmp_path: Path):
    sqlite_file = _migration_path("sqlite")
    postgres_file = _migration_path("postgresql")
    assert sqlite_file.exists()
    assert postgres_file.exists()

    isolated = tmp_path / "managed"
    isolated.mkdir()
    (isolated / sqlite_file.name).write_text(
        sqlite_file.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys = ON"))
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))

    first = apply_managed_migrations(engine, isolated)
    replay = apply_managed_migrations(engine, isolated)

    assert [item.id for item in first.applied] == [MIGRATION_ID]
    assert [item.id for item in replay.skipped] == [MIGRATION_ID]
    assert {
        "registration_invitations",
        "phone_registration_grants",
        "registration_auth_attempt_audits",
    }.issubset(
        inspect(engine).get_table_names()
    )
    invitation_columns = {
        item["name"] for item in inspect(engine).get_columns("registration_invitations")
    }
    grant_columns = {
        item["name"] for item in inspect(engine).get_columns("phone_registration_grants")
    }
    audit_columns = {
        item["name"]
        for item in inspect(engine).get_columns("registration_auth_attempt_audits")
    }
    assert {
        "id", "code_digest", "link_token_digest", "phone_ciphertext",
        "phone_hmac", "phone_masked", "status", "expires_at",
        "consumed_by", "consumed_at", "created_by",
    }.issubset(invitation_columns)
    assert {
        "id", "token_digest", "phone_hmac", "phone_ciphertext",
        "expires_at", "consumed_by", "idempotency_key_digest",
        "consumed_at", "created_at",
    }.issubset(grant_columns)
    assert {
        "id", "outcome", "error_code", "invitation_id", "grant_id",
        "user_id", "phone_masked", "source_hmac", "created_at",
    } == audit_columns
    invitation_uniques = {
        tuple(item["column_names"])
        for item in inspect(engine).get_unique_constraints("registration_invitations")
    }
    grant_uniques = {
        tuple(item["column_names"])
        for item in inspect(engine).get_unique_constraints("phone_registration_grants")
    }
    assert ("code_digest",) in invitation_uniques
    assert ("link_token_digest",) in invitation_uniques
    assert ("token_digest",) in grant_uniques
    assert ACTIVE_INDEX in {
        item["name"] for item in inspect(engine).get_indexes("registration_invitations")
    }

    invitation_insert = text(
        "INSERT INTO registration_invitations "
        "(code_digest, link_token_digest, phone_ciphertext, phone_hmac, phone_masked, "
        "status, expires_at) VALUES "
        "(:code_digest, :link_token_digest, 'ciphertext', 'same-phone', '+1***01', "
        ":status, CURRENT_TIMESTAMP)"
    )
    with engine.begin() as conn:
        conn.execute(
            invitation_insert,
            {"code_digest": "code-1", "link_token_digest": "link-1", "status": "sent"},
        )
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                invitation_insert,
                {"code_digest": "code-2", "link_token_digest": "link-2", "status": "created"},
            )
    with engine.begin() as conn:
        conn.execute(text(
            "UPDATE registration_invitations SET status = 'revoked' WHERE code_digest = 'code-1'"
        ))
        conn.execute(
            invitation_insert,
            {"code_digest": "code-2", "link_token_digest": "link-2", "status": "sent"},
        )
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                invitation_insert,
                {"code_digest": "code-3", "link_token_digest": "link-3", "status": "invalid"},
            )


@pytest.mark.skipif(not POSTGRES_TEST_ENABLED, reason="requires TEST_DATABASE_URL PostgreSQL")
def test_postgres_managed_migration_is_replay_safe_and_enforces_contract(tmp_path: Path):
    assert TEST_DATABASE_URL is not None
    schema = f"registration_invitation_{uuid.uuid4().hex}"
    admin_engine = create_engine(TEST_DATABASE_URL)
    migration_engine = None
    try:
        with admin_engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        migration_engine = create_engine(
            TEST_DATABASE_URL,
            connect_args={"options": f"-csearch_path={schema}"},
        )
        with migration_engine.begin() as conn:
            conn.execute(text("CREATE TABLE users (id SERIAL PRIMARY KEY)"))

        postgres_file = _migration_path("postgresql")
        isolated = tmp_path / "postgresql-managed"
        isolated.mkdir()
        (isolated / postgres_file.name).write_text(
            postgres_file.read_text(encoding="utf-8"),
            encoding="utf-8",
        )

        first = apply_managed_migrations(migration_engine, isolated)
        replay = apply_managed_migrations(migration_engine, isolated)

        assert [item.id for item in first.applied] == [MIGRATION_ID]
        assert [item.id for item in replay.skipped] == [MIGRATION_ID]
        indexes = {
            item["name"]: item
            for item in inspect(migration_engine).get_indexes("registration_invitations")
        }
        assert indexes[ACTIVE_INDEX]["unique"] is True
        assert indexes[ACTIVE_INDEX]["dialect_options"]["postgresql_where"] is not None
        foreign_keys = {
            tuple(item["constrained_columns"]): item
            for item in inspect(migration_engine).get_foreign_keys("registration_invitations")
        }
        assert foreign_keys[("consumed_by",)]["options"]["ondelete"] == "SET NULL"
        assert foreign_keys[("created_by",)]["options"]["ondelete"] == "SET NULL"
        grant_foreign_keys = {
            tuple(item["constrained_columns"]): item
            for item in inspect(migration_engine).get_foreign_keys(
                "phone_registration_grants"
            )
        }
        assert grant_foreign_keys[("consumed_by",)]["options"]["ondelete"] == "SET NULL"
        audit_foreign_keys = {
            tuple(item["constrained_columns"]): item
            for item in inspect(migration_engine).get_foreign_keys(
                "registration_auth_attempt_audits"
            )
        }
        for constrained in (("invitation_id",), ("grant_id",), ("user_id",)):
            assert audit_foreign_keys[constrained]["options"]["ondelete"] == "SET NULL"
    finally:
        if migration_engine is not None:
            migration_engine.dispose()
        with admin_engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin_engine.dispose()
