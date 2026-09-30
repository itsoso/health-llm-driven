from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from app.config import settings
from app.models.user import User
from app.models.phone_auth import PhoneAuthCode


@pytest.fixture(autouse=True)
def public_registration(monkeypatch):
    monkeypatch.setattr(settings, "auth_phone_self_registration_enabled", True, raising=False)
    monkeypatch.setattr(settings, "registration_invitation_enforcement_enabled", True)
    monkeypatch.setattr(settings, "registration_invitation_rollout_enabled", False)
    monkeypatch.setattr(settings, "auth_phone_registration_auto_approve", True)
    monkeypatch.setattr(settings, "auth_phone_code_dev_echo", True)
    monkeypatch.setattr(settings, "auth_phone_code_resend_seconds", 0)


def register(client, phone="13800138771", endpoint="verify"):
    sent = client.post("/api/v1/auth/phone/code", json={"phone": phone})
    assert sent.status_code == 200
    return client.post(f"/api/v1/auth/phone/{endpoint}", json={"phone": phone, "code": sent.json()["dev_code"]})


@pytest.mark.parametrize("endpoint", ["verify", "login"])
def test_public_registration_and_later_login_create_one_notification(client, db, endpoint):
    result = register(client, endpoint=endpoint)
    assert result.status_code == 200
    body = result.json()
    assert body["is_new_user"] is True
    assert body["user"]["phone_verified_at"]
    assert body["user"]["is_approved"] is True
    again = register(client, endpoint=endpoint)
    assert again.status_code == 200
    assert again.json()["is_new_user"] is False
    assert again.json()["user"]["id"] == body["user"]["id"]
    assert db.query(User).count() == 1
    from app.models.phone_auth import RegistrationAdminNotification
    assert db.query(RegistrationAdminNotification).count() == 1
    assert db.query(RegistrationAdminNotification).one().status == "pending"


def test_invalid_or_replayed_otp_does_not_register(client, db):
    bad = client.post("/api/v1/auth/phone/verify", json={"phone": "13800138771", "code": "000000"})
    assert bad.status_code == 400
    assert db.query(User).count() == 0
    sent = client.post("/api/v1/auth/phone/code", json={"phone": "13800138771"}).json()
    payload = {"phone": sent["phone"], "code": sent["dev_code"]}
    assert client.post("/api/v1/auth/phone/verify", json=payload).status_code == 200
    assert client.post("/api/v1/auth/phone/verify", json=payload).status_code == 400
    assert db.query(User).count() == 1


def test_registration_rollback_preserves_otp_and_does_not_leave_user(client, db, monkeypatch):
    from app.api import auth
    sent = client.post("/api/v1/auth/phone/code", json={"phone": "13800138771"}).json()
    def fail(*args, **kwargs):
        raise RuntimeError("synthetic outbox failure")
    monkeypatch.setattr(auth, "enqueue_registration_notification", fail)
    result = client.post("/api/v1/auth/phone/verify", json={"phone": sent["phone"], "code": sent["dev_code"]})
    assert result.status_code == 500
    db.rollback()
    assert db.query(User).count() == 0
    assert db.query(PhoneAuthCode).one().consumed_at is None


def test_disabled_account_cannot_reregister(client, db):
    db.add(User(username="blocked", name="Blocked", phone="+8613800138771", is_active=False, is_approved=True))
    db.commit()
    sent = client.post("/api/v1/auth/phone/code", json={"phone": "13800138771"})
    assert sent.status_code == 403
    assert db.query(PhoneAuthCode).count() == 0


@pytest.mark.asyncio
async def test_notification_failure_is_durable_and_retried_without_duplicate(client, db, monkeypatch):
    from app.models.phone_auth import RegistrationAdminNotification
    from app.services.registration_notification import deliver_registration_notifications
    from app.services.notification.telegram_push import TelegramPushService
    assert register(client).status_code == 200
    sender = AsyncMock(side_effect=[{"success": False, "reason": "transport_error"}, {"success": True}])
    monkeypatch.setattr(TelegramPushService, "send_message", sender)
    first = await deliver_registration_notifications(db)
    assert first == {"sent": 0, "failed": 1}
    row = db.query(RegistrationAdminNotification).one()
    assert row.status == "pending"
    assert row.attempts == 1
    assert row.last_error == "transport_error"
    assert await deliver_registration_notifications(db) == {"sent": 0, "failed": 0}
    row.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    assert await deliver_registration_notifications(db) == {"sent": 1, "failed": 0}
    assert await deliver_registration_notifications(db) == {"sent": 0, "failed": 0}
    assert sender.await_count == 2
    message = sender.call_args.args[0]
    assert "新用户注册" in message
    assert "13800138771" not in message
    assert "****" in message
    assert sender.call_args.kwargs["parse_mode"] is None
    assert row.sent_at is not None


@pytest.mark.asyncio
async def test_unconfigured_telegram_stays_pending(client, db, monkeypatch):
    from app.models.phone_auth import RegistrationAdminNotification
    from app.services.registration_notification import deliver_registration_notifications
    monkeypatch.setattr(settings, "telegram_bot_token", None)
    assert register(client).status_code == 200
    assert await deliver_registration_notifications(db) == {"sent": 0, "failed": 1}
    row = db.query(RegistrationAdminNotification).one()
    assert row.last_error == "not_configured"
    assert row.status == "pending"


def test_public_mode_is_observable():
    assert settings.registration_invitation_mode == "self_registration"


def test_notification_privacy_backstop_handles_sensitive_and_benign_text(db, monkeypatch):
    from app.models.phone_auth import RegistrationAdminNotification
    from app.services import registration_notification as service
    user = User(id=18, phone="+8613800138771", name="private-diagnosis-must-not-be-read")
    event = RegistrationAdminNotification(id=2, user_id=18, created_at=datetime(2026, 9, 29, tzinfo=UTC))
    benign = service.registration_message(event, user)
    assert "2026-09-29 08:00:00" in benign
    assert "private-diagnosis" not in benign
    monkeypatch.setattr(service, "mask_phone", lambda phone: "阿司匹林")
    protected = service.registration_message(event, user)
    assert "阿司匹林" not in protected
    assert "请进入管理后台查看" in protected


def test_sqlite_notification_migration_is_replay_safe():
    import sqlite3
    from pathlib import Path
    sql = (Path(__file__).parents[1] / "migrations/managed/20260929_120000_registration_admin_notifications.sqlite.sql").read_text()
    with sqlite3.connect(":memory:") as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("CREATE TABLE users (id INTEGER PRIMARY KEY)")
        connection.executescript(sql)
        connection.executescript(sql)
        connection.execute("INSERT INTO users(id) VALUES(1)")
        connection.execute("INSERT INTO registration_admin_notifications(user_id) VALUES(1)")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("INSERT INTO registration_admin_notifications(user_id) VALUES(1)")
        connection.execute("DELETE FROM users WHERE id=1")
        assert connection.execute("SELECT count(*) FROM registration_admin_notifications").fetchone()[0] == 0


def test_registered_celery_job_delivers_committed_notification(client, db, monkeypatch):
    from app.celery_app import celery_app
    from app.tasks import notifications
    from app.models.phone_auth import RegistrationAdminNotification
    from app.services.notification.telegram_push import TelegramPushService
    assert register(client).status_code == 200
    monkeypatch.setattr(notifications, "SessionLocal", lambda: db)
    sender = AsyncMock(return_value={"success": True})
    monkeypatch.setattr(TelegramPushService, "send_message", sender)
    assert celery_app.conf.beat_schedule["registration-admin-notifications"]["task"] == notifications.send_registration_admin_notifications.name
    assert notifications.send_registration_admin_notifications.run() == {"sent": 1, "failed": 0}
    assert db.query(RegistrationAdminNotification).one().status == "sent"


@pytest.mark.parametrize("endpoint", ["verify", "login"])
def test_registration_flush_conflict_is_safe_and_rolls_back(client, db, monkeypatch, caplog, endpoint):
    from app.api import auth
    from sqlalchemy.exc import IntegrityError
    sent = client.post("/api/v1/auth/phone/code", json={"phone": "13800138771"}).json()
    private = "synthetic-private-sql-parameter"
    def fail(*args, **kwargs):
        raise IntegrityError("INSERT users", {"phone": private}, Exception(private))
    monkeypatch.setattr(auth, "enqueue_registration_notification", fail)
    result = client.post(f"/api/v1/auth/phone/{endpoint}", json={"phone": sent["phone"], "code": sent["dev_code"]})
    assert result.status_code == 409
    assert private not in result.text
    assert private not in caplog.text
    assert db.query(User).count() == 0
    assert db.query(PhoneAuthCode).one().consumed_at is None


@pytest.mark.parametrize("endpoint", ["verify", "login"])
def test_registration_storage_failure_redacts_sql_parameters(client, db, monkeypatch, caplog, endpoint):
    from app.api import auth
    from sqlalchemy.exc import OperationalError
    sent = client.post("/api/v1/auth/phone/code", json={"phone": "13800138771"}).json()
    private = "synthetic-private-storage-parameter"
    def fail(*args, **kwargs):
        raise OperationalError("INSERT users", {"phone": private}, Exception(private))
    monkeypatch.setattr(auth, "enqueue_registration_notification", fail)
    result = client.post(f"/api/v1/auth/phone/{endpoint}", json={"phone": sent["phone"], "code": sent["dev_code"]})
    assert result.status_code == 500
    assert result.json()["detail"]["code"] == "PHONE_REGISTRATION_FAILED"
    assert private not in result.text
    assert private not in caplog.text
    assert db.query(User).count() == 0
    assert db.query(PhoneAuthCode).one().consumed_at is None
