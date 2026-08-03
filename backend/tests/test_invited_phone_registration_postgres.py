from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import os
import threading
import uuid

import pytest
from fastapi import HTTPException, Request, Response
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.api.auth import invited_phone_registration, verify_phone_code
from app.config import settings
from app.models.agent_audit_log import AgentAuditLog
from app.models.registration_invitation import (
    PhoneRegistrationGrant,
    RegistrationAuthAttemptAudit,
    RegistrationInvitation,
)
from app.models.phone_auth import PhoneAuthCode
from app.models.user import GarminCredential, User
from app.services.registration_invitation import (
    create_phone_registration_grant,
    create_registration_invitation,
)
from app.services.phone_auth import _hash_code, consume_phone_code


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
POSTGRES_TEST_ENABLED = bool(
    TEST_DATABASE_URL
    and make_url(TEST_DATABASE_URL).get_backend_name() == "postgresql"
)


@pytest.mark.skipif(not POSTGRES_TEST_ENABLED, reason="requires TEST_DATABASE_URL PostgreSQL")
def test_postgres_two_sessions_create_at_most_one_user_and_consume_once(monkeypatch):
    assert TEST_DATABASE_URL is not None
    schema = f"invited_registration_{uuid.uuid4().hex}"
    admin_engine = create_engine(TEST_DATABASE_URL)
    engine = None
    monkeypatch.setattr(
        settings,
        "registration_invitation_digest_key",
        "registration-invitation-test-key-with-at-least-32-bytes",
    )
    try:
        with admin_engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_engine(
            TEST_DATABASE_URL,
            connect_args={"options": f"-csearch_path={schema}"},
        )
        for table in (
            User.__table__,
            GarminCredential.__table__,
            AgentAuditLog.__table__,
            RegistrationInvitation.__table__,
            PhoneRegistrationGrant.__table__,
            RegistrationAuthAttemptAudit.__table__,
        ):
            table.create(engine)
        Session = sessionmaker(bind=engine, expire_on_commit=False)
        creator = Session()
        invitation = create_registration_invitation(creator, "13800138111")
        grant = create_phone_registration_grant(creator, "13800138111")
        manual_code = invitation.manual_code
        ticket = grant.token
        invitation_id = invitation.invitation.id
        creator.commit()
        creator.close()

        barrier = threading.Barrier(2)
        outcomes: list[tuple[str, int | str]] = []
        outcome_lock = threading.Lock()

        def register(idempotency_key: str) -> None:
            session = Session()
            request = Request(
                {
                    "type": "http",
                    "method": "POST",
                    "path": "/api/v1/auth/invited-registration",
                    "headers": [],
                    "client": ("127.0.0.1", 10000),
                    "scheme": "http",
                    "server": ("testserver", 80),
                }
            )
            try:
                barrier.wait(timeout=5)
                result = asyncio.run(
                    invited_phone_registration(
                        request=request,
                        response=Response(),
                        payload={
                            "verified_phone_ticket": ticket,
                            "manual_code": manual_code,
                            "idempotency_key": idempotency_key,
                        },
                        db=session,
                    )
                )
                outcome = ("success", result.user.id)
            except HTTPException as exc:
                outcome = ("rejected", exc.detail["code"])
            finally:
                session.close()
            with outcome_lock:
                outcomes.append(outcome)

        threads = [
            threading.Thread(target=register, args=("pg-registration-key-0001",)),
            threading.Thread(target=register, args=("pg-registration-key-0002",)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)

        assert all(not thread.is_alive() for thread in threads)
        assert [kind for kind, _ in outcomes].count("success") == 1
        assert [kind for kind, _ in outcomes].count("rejected") == 1
        assert ("rejected", "INVITATION_ALREADY_USED") in outcomes
        verifier = Session()
        try:
            assert verifier.query(User).count() == 1
            consumed = verifier.get(RegistrationInvitation, invitation_id)
            assert consumed.status == "consumed"
            assert consumed.consumed_by == verifier.query(User.id).scalar()
            grant_row = verifier.query(PhoneRegistrationGrant).one()
            assert grant_row.consumed_by == consumed.consumed_by
            audits = verifier.query(RegistrationAuthAttemptAudit).all()
            assert sorted((item.outcome, item.error_code) for item in audits) == [
                ("rejected", "INVITATION_ALREADY_USED"),
                ("success", None),
            ]
            assert all(item.source_hmac and len(item.source_hmac) == 64 for item in audits)
            assert all(item.source_hmac != "127.0.0.1" for item in audits)
        finally:
            verifier.close()
    finally:
        if engine is not None:
            engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin_engine.dispose()


@pytest.mark.skipif(not POSTGRES_TEST_ENABLED, reason="requires TEST_DATABASE_URL PostgreSQL")
def test_postgres_concurrent_correct_otp_verify_has_exactly_one_grant(monkeypatch):
    assert TEST_DATABASE_URL is not None
    schema = f"phone_verify_{uuid.uuid4().hex}"
    admin_engine = create_engine(TEST_DATABASE_URL)
    engine = None
    monkeypatch.setattr(settings, "registration_invitation_grant_ttl_seconds", 600)
    monkeypatch.setattr(
        settings,
        "registration_invitation_digest_key",
        "registration-invitation-test-key-with-at-least-32-bytes",
    )
    try:
        with admin_engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_engine(
            TEST_DATABASE_URL,
            connect_args={"options": f"-csearch_path={schema}"},
        )
        for table in (
            User.__table__,
            GarminCredential.__table__,
            PhoneAuthCode.__table__,
            PhoneRegistrationGrant.__table__,
        ):
            table.create(engine)
        Session = sessionmaker(bind=engine, expire_on_commit=False)
        creator = Session()
        phone = "+8613800138222"
        code = "826431"
        creator.add(
            PhoneAuthCode(
                phone=phone,
                purpose="login",
                code_hash=_hash_code(phone, code, "login"),
                expires_at=datetime.now(UTC) + timedelta(minutes=5),
                attempt_count=0,
            )
        )
        creator.commit()
        creator.close()

        barrier = threading.Barrier(2)
        outcomes: list[str] = []
        lock = threading.Lock()

        def verify_once() -> None:
            session = Session()
            request = Request(
                {
                    "type": "http",
                    "method": "POST",
                    "path": "/api/v1/auth/phone/verify",
                    "headers": [],
                    "client": ("127.0.0.1", 10000),
                    "scheme": "http",
                    "server": ("testserver", 80),
                }
            )
            try:
                barrier.wait(timeout=5)
                result = asyncio.run(
                    verify_phone_code(
                        request=request,
                        response=Response(),
                        payload={"phone": phone, "code": code},
                        db=session,
                    )
                )
                outcome = result.outcome
            except HTTPException as exc:
                outcome = str(exc.detail)
            finally:
                session.close()
            with lock:
                outcomes.append(outcome)

        threads = [threading.Thread(target=verify_once) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)

        assert all(not thread.is_alive() for thread in threads)
        assert outcomes.count("invitation_required") == 1
        assert outcomes.count("验证码无效或已过期") == 1
        verifier = Session()
        try:
            assert verifier.query(PhoneRegistrationGrant).count() == 1
            assert verifier.query(PhoneAuthCode).one().consumed_at is not None
        finally:
            verifier.close()
    finally:
        if engine is not None:
            engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin_engine.dispose()


@pytest.mark.skipif(not POSTGRES_TEST_ENABLED, reason="requires TEST_DATABASE_URL PostgreSQL")
def test_postgres_concurrent_wrong_otp_attempts_do_not_lose_updates(monkeypatch):
    assert TEST_DATABASE_URL is not None
    schema = f"phone_attempts_{uuid.uuid4().hex}"
    admin_engine = create_engine(TEST_DATABASE_URL)
    engine = None
    monkeypatch.setattr(settings, "auth_phone_code_max_attempts", 3)
    try:
        with admin_engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_engine(
            TEST_DATABASE_URL,
            connect_args={"options": f"-csearch_path={schema}"},
        )
        PhoneAuthCode.__table__.create(engine)
        Session = sessionmaker(bind=engine, expire_on_commit=False)
        creator = Session()
        phone = "+8613800138333"
        creator.add(
            PhoneAuthCode(
                phone=phone,
                purpose="login",
                code_hash=_hash_code(phone, "826431", "login"),
                expires_at=datetime.now(UTC) + timedelta(minutes=5),
                attempt_count=0,
            )
        )
        creator.commit()
        creator.close()

        barrier = threading.Barrier(5)

        def fail_once() -> None:
            session = Session()
            try:
                barrier.wait(timeout=5)
                with pytest.raises(ValueError, match="验证码无效或已过期"):
                    consume_phone_code(session, phone, "999999")
            finally:
                session.rollback()
                session.close()

        threads = [threading.Thread(target=fail_once) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)

        assert all(not thread.is_alive() for thread in threads)
        verifier = Session()
        try:
            record = verifier.query(PhoneAuthCode).one()
            assert record.attempt_count == 3
            with pytest.raises(ValueError, match="验证码无效或已过期"):
                consume_phone_code(verifier, phone, "826431")
        finally:
            verifier.rollback()
            verifier.close()
    finally:
        if engine is not None:
            engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin_engine.dispose()
