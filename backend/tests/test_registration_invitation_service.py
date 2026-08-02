from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import threading
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models.registration_invitation import PhoneRegistrationGrant
from app.services.registration_invitation import (
    InvalidRegistrationCredential,
    build_registration_invitation_deep_link,
    consume_phone_registration_grant,
    create_phone_registration_grant,
    create_registration_invitation,
    find_invitation_by_code,
    find_invitation_by_link_token,
    phone_lookup_hmac,
)


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
POSTGRES_TEST_ENABLED = bool(
    TEST_DATABASE_URL
    and make_url(TEST_DATABASE_URL).get_backend_name() == "postgresql"
)


@pytest.fixture(autouse=True)
def _dedicated_digest_key(monkeypatch):
    monkeypatch.setattr(
        settings,
        "registration_invitation_digest_key",
        "registration-invitation-test-key-with-at-least-32-bytes",
    )


def test_generated_manual_code_excludes_ambiguous_characters(db):
    created = create_registration_invitation(db, "138 0013 8000")

    assert len(created.manual_code) == 8
    assert set(created.manual_code).isdisjoint(set("0O1IL"))
    assert created.manual_code.isalnum()
    assert len(created.link_token) >= 22  # >= 128 random bits when URL-safe encoded


def test_invitation_deep_link_matches_mobile_canonical_contract():
    token = "abcdefghijklmnopqrstuvwxyz_123456"

    assert build_registration_invitation_deep_link(token) == (
        "health://invite?token=abcdefghijklmnopqrstuvwxyz_123456"
    )

    repository_root = Path(__file__).resolve().parents[2]
    mobile_config = json.loads((repository_root / "mobile" / "app.json").read_text())
    assert "health" in mobile_config["expo"]["scheme"]


@pytest.mark.parametrize("invalid_token", ["short", "contains!punctuation", None])
def test_invitation_deep_link_rejects_invalid_token_without_reflecting_it(invalid_token):
    with pytest.raises(InvalidRegistrationCredential) as error:
        build_registration_invitation_deep_link(invalid_token)

    assert str(invalid_token) not in str(error.value)


def test_code_and_link_are_stored_as_digest_only(db):
    created = create_registration_invitation(db, "+86 138-0013-8000")
    db.flush()

    row = db.execute(
        text(
            "SELECT code_digest, link_token_digest, phone_ciphertext "
            "FROM registration_invitations WHERE id = :id"
        ),
        {"id": created.invitation.id},
    ).mappings().one()

    assert created.manual_code not in repr(row)
    assert created.link_token not in repr(row)
    assert "+8613800138000" not in row["phone_ciphertext"]
    assert created.invitation.code_digest != created.manual_code
    assert created.invitation.link_token_digest != created.link_token
    assert "manual_code" not in vars(created.invitation)
    assert "link_token" not in vars(created.invitation)
    assert find_invitation_by_code(db, created.manual_code) is created.invitation
    assert find_invitation_by_link_token(db, created.link_token) is created.invitation


def test_phone_hmac_matches_normalized_equivalent_numbers():
    assert phone_lookup_hmac("13800138000") == phone_lookup_hmac("+86 138-0013-8000")


def test_grant_is_short_lived_single_use_and_bound_to_phone(db, monkeypatch):
    monkeypatch.setattr(settings, "registration_invitation_grant_ttl_seconds", 120)
    now = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)
    issued = create_phone_registration_grant(db, "13800138000", now=now)
    db.flush()

    assert issued.expires_at == now + timedelta(seconds=120)
    assert issued.grant.token_digest != issued.token
    assert "token" not in vars(issued.grant)

    with pytest.raises(InvalidRegistrationCredential, match="invalid or expired"):
        consume_phone_registration_grant(
            db,
            issued.token,
            "+14155550101",
            now=now + timedelta(seconds=1),
        )
    assert issued.grant.consumed_at is None

    consumed = consume_phone_registration_grant(
        db,
        issued.token,
        "+8613800138000",
        now=now + timedelta(seconds=2),
    )
    assert consumed.id == issued.grant.id
    assert consumed.consumed_at == now + timedelta(seconds=2)

    with pytest.raises(InvalidRegistrationCredential, match="invalid or expired"):
        consume_phone_registration_grant(
            db,
            issued.token,
            "13800138000",
            now=now + timedelta(seconds=3),
        )


def test_expired_grant_cannot_be_consumed(db, monkeypatch):
    monkeypatch.setattr(settings, "registration_invitation_grant_ttl_seconds", 1)
    now = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)
    issued = create_phone_registration_grant(db, "+14155550101", now=now)
    db.flush()

    with pytest.raises(InvalidRegistrationCredential, match="invalid or expired"):
        consume_phone_registration_grant(
            db,
            issued.token,
            "+14155550101",
            now=now + timedelta(seconds=1),
        )
    assert issued.grant.consumed_at is None


@pytest.mark.skipif(not POSTGRES_TEST_ENABLED, reason="requires TEST_DATABASE_URL PostgreSQL")
def test_postgres_concurrent_grant_consumption_has_exactly_one_winner(monkeypatch):
    assert TEST_DATABASE_URL is not None
    schema = f"registration_grant_{uuid.uuid4().hex}"
    admin_engine = create_engine(TEST_DATABASE_URL)
    isolated_engine = None
    monkeypatch.setattr(
        settings,
        "registration_invitation_digest_key",
        "registration-invitation-test-key-with-at-least-32-bytes",
    )
    try:
        with admin_engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        isolated_engine = create_engine(
            TEST_DATABASE_URL,
            connect_args={"options": f"-csearch_path={schema}"},
        )
        with isolated_engine.begin() as connection:
            connection.execute(text("CREATE TABLE users (id SERIAL PRIMARY KEY)"))
        PhoneRegistrationGrant.__table__.create(isolated_engine)
        Session = sessionmaker(bind=isolated_engine, expire_on_commit=False)
        creator = Session()
        issued = create_phone_registration_grant(creator, "+14155550101")
        token = issued.token
        grant_id = issued.grant.id
        creator.commit()
        creator.close()

        barrier = threading.Barrier(2)
        outcomes: list[str] = []
        outcome_lock = threading.Lock()

        def consume_once() -> None:
            session = Session()
            try:
                barrier.wait(timeout=5)
                consume_phone_registration_grant(session, token, "+14155550101")
                session.commit()
                outcome = "success"
            except InvalidRegistrationCredential:
                session.rollback()
                outcome = "invalid"
            finally:
                session.close()
            with outcome_lock:
                outcomes.append(outcome)

        threads = [threading.Thread(target=consume_once) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        assert all(not thread.is_alive() for thread in threads)
        assert sorted(outcomes) == ["invalid", "success"]
        verifier = Session()
        try:
            assert verifier.get(PhoneRegistrationGrant, grant_id).consumed_at is not None
        finally:
            verifier.close()
    finally:
        if isolated_engine is not None:
            isolated_engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin_engine.dispose()
