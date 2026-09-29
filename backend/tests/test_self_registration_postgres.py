"""Real PostgreSQL transaction, migration and worker claim evidence."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
import threading
from unittest.mock import AsyncMock

from fastapi import HTTPException, Request, Response
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.api.auth import verify_phone_code
from app.config import settings
from app.models.phone_auth import PhoneAuthCode, RegistrationAdminNotification
from app.models.user import User
from app.services.phone_auth import _hash_code
from app.services.registration_notification import deliver_registration_notifications
from app.services.notification.telegram_push import TelegramPushService

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL", "").startswith("postgresql"), reason="requires PostgreSQL test DB")


def test_postgres_concurrent_registration_commits_one_account_and_event(db, monkeypatch):
    monkeypatch.setattr(settings, "auth_phone_self_registration_enabled", True)
    monkeypatch.setattr(settings, "auth_phone_registration_auto_approve", True)
    phone, code = "+8613800138773", "823641"
    db.add(PhoneAuthCode(phone=phone, purpose="login", code_hash=_hash_code(phone, code, "login"),
                         expires_at=datetime.now(UTC) + timedelta(minutes=5), attempt_count=0))
    db.commit()
    Session = sessionmaker(bind=db.get_bind())
    barrier = threading.Barrier(2)
    def attempt():
        request = Request({"type": "http", "method": "POST", "path": "/api/v1/auth/phone/verify",
                           "headers": [], "client": ("127.0.0.1", 19999), "scheme": "http", "server": ("testserver", 80)})
        with Session() as session:
            barrier.wait(timeout=10)
            try:
                result = asyncio.run(verify_phone_code(request=request, response=Response(),
                    payload={"phone": phone, "code": code}, db=session))
                return result.is_new_user
            except HTTPException as exc:
                return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: attempt(), range(2)))
    assert sorted(outcomes, key=str) == sorted([True, 400], key=str)
    assert db.query(User).count() == db.query(RegistrationAdminNotification).count() == 1
    assert db.query(PhoneAuthCode).one().consumed_at is not None


@pytest.mark.asyncio
async def test_postgres_skip_locked_prevents_duplicate_delivery(db, monkeypatch):
    user = User(username="outbox-pg", name="Synthetic", phone="+8613800138774")
    db.add(user)
    db.flush()
    db.add(RegistrationAdminNotification(user_id=user.id))
    db.commit()
    Session = sessionmaker(bind=db.get_bind())
    sender = AsyncMock(return_value={"success": True})
    monkeypatch.setattr(TelegramPushService, "send_message", sender)
    db.query(RegistrationAdminNotification).with_for_update().one()
    with Session() as competing:
        assert await deliver_registration_notifications(competing) == {"sent": 0, "failed": 0}
    sender.assert_not_called()
    db.rollback()
    with Session() as winner:
        assert await deliver_registration_notifications(winner) == {"sent": 1, "failed": 0}
    assert sender.await_count == 1
    db.expire_all()
    assert db.query(RegistrationAdminNotification).one().sent_at.tzinfo is not None


def test_postgres_migration_replay_unique_cascade_and_due_index(db):
    engine = db.get_bind()
    RegistrationAdminNotification.__table__.drop(engine)
    sql = (Path(__file__).parents[1] / "migrations/managed/20260929_120000_registration_admin_notifications.postgresql.sql").read_text()
    with engine.begin() as connection:
        connection.execute(text(sql))
        connection.execute(text(sql))
        assert connection.execute(text("SELECT indexname FROM pg_indexes WHERE indexname = 'ix_registration_admin_notifications_due'")).scalar_one()
    user = User(username="migration-pg", name="Synthetic")
    db.add(user)
    db.flush()
    db.add(RegistrationAdminNotification(user_id=user.id))
    db.commit()
    db.add(RegistrationAdminNotification(user_id=user.id))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    with engine.begin() as connection:
        connection.execute(text("SET LOCAL enable_seqscan = off"))
        plan = str(connection.execute(text("EXPLAIN SELECT * FROM registration_admin_notifications WHERE status='pending' AND next_attempt_at <= now() ORDER BY next_attempt_at LIMIT 1")).all())
        assert "ix_registration_admin_notifications_due" in plan
    db.delete(user)
    db.commit()
    assert db.query(RegistrationAdminNotification).count() == 0
    db.add(RegistrationAdminNotification(user_id=99999999))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
