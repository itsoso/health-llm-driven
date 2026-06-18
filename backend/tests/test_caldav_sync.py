"""CalDAV 同步:凭据加密往返 + 忙碌块同步(mock caldav 连接)+ 端点。"""
import uuid
from datetime import datetime

import pytest

from app.models.user import User
from app.models.calendar_sync import CalendarCredential, CalendarBusyBlock
from app.services import caldav_sync as svc


def _mk_user(db) -> User:
    u = User(username=f"cd_{uuid.uuid4().hex[:6]}", email=f"cd_{uuid.uuid4().hex[:6]}@x.com",
             hashed_password="x", name="cd", is_active=True, is_approved=True)
    db.add(u); db.commit(); db.refresh(u)
    return u


@pytest.fixture
def auth_headers(client, db):
    u = _mk_user(db)
    from app.services.auth import auth_service
    return u, {"Authorization": f"Bearer {auth_service.create_access_token({'sub': str(u.id)})}"}


def test_credential_encryption_roundtrip(db):
    u = _mk_user(db)
    cred = svc.save_credentials(db, u.id, url="https://caldav.example.com", username="me@x.com", password="app-pw-123")
    # 明文不落库
    assert "app-pw-123" not in (cred.encrypted_credentials or "")
    got = cred.get_credentials()
    assert got["url"] == "https://caldav.example.com" and got["password"] == "app-pw-123"


def test_sync_today_upserts_busy_blocks(db, monkeypatch):
    u = _mk_user(db)
    svc.save_credentials(db, u.id, url="https://cd", username="me", password="pw")
    today = svc._china_today()
    fake = [
        (datetime(today.year, today.month, today.day, 12, 0),
         datetime(today.year, today.month, today.day, 13, 0), "uid-1", "季度复盘会"),
        (datetime(today.year, today.month, today.day, 15, 30),
         datetime(today.year, today.month, today.day, 16, 0), "uid-2", "1:1"),
    ]
    monkeypatch.setattr(svc, "_fetch_events", lambda *a, **k: fake)
    res = svc.sync_today(db, u.id)
    assert res["synced"] == 2
    blocks = svc.today_busy_blocks(db, u.id)
    assert ("12:00", "13:00") in blocks and ("15:30", "16:00") in blocks
    # 标题加密存、可解密
    row = db.query(CalendarBusyBlock).filter(CalendarBusyBlock.external_uid == "uid-1").first()
    assert "季度复盘会" not in (row.encrypted_title or "") and row.get_title() == "季度复盘会"


def test_sync_today_full_replace_idempotent(db, monkeypatch):
    u = _mk_user(db)
    svc.save_credentials(db, u.id, url="https://cd", username="me", password="pw")
    today = svc._china_today()
    monkeypatch.setattr(svc, "_fetch_events", lambda *a, **k: [
        (datetime(today.year, today.month, today.day, 9, 0),
         datetime(today.year, today.month, today.day, 10, 0), "u1", "A")])
    svc.sync_today(db, u.id); svc.sync_today(db, u.id)  # 跑两次
    assert db.query(CalendarBusyBlock).filter(CalendarBusyBlock.user_id == u.id).count() == 1  # 全量替换不翻倍


def test_sync_fail_loud_records_error(db, monkeypatch):
    u = _mk_user(db)
    svc.save_credentials(db, u.id, url="https://cd", username="me", password="pw")
    def _boom(*a, **k):
        raise RuntimeError("连接超时")
    monkeypatch.setattr(svc, "_fetch_events", _boom)
    with pytest.raises(RuntimeError):
        svc.sync_today(db, u.id)
    cred = db.query(CalendarCredential).filter(CalendarCredential.user_id == u.id).first()
    assert cred.last_error and "连接超时" in cred.last_error  # 失败被记下,不假装成功


def test_no_credential_skips(db):
    u = _mk_user(db)
    assert svc.sync_today(db, u.id)["skipped"] == "no_credential"


def test_calendar_endpoints(client, db, auth_headers):
    user, headers = auth_headers
    r = client.put("/api/v1/calendar/credentials", headers=headers,
                   json={"url": "https://cd", "username": "me", "password": "pw"})
    assert r.status_code == 200, r.text
    s = client.get("/api/v1/calendar/status", headers=headers)
    assert s.status_code == 200 and s.json()["connected"] is True


def test_ssrf_guard_rejects_http_and_private():
    for bad in ["http://caldav.example.com", "https://127.0.0.1/dav", "https://localhost/dav"]:
        with pytest.raises(ValueError):
            svc._assert_safe_caldav_url(bad)


def test_put_credentials_rejects_non_https(client, db, auth_headers):
    user, headers = auth_headers
    r = client.put("/api/v1/calendar/credentials", headers=headers,
                   json={"url": "http://cd", "username": "me", "password": "pw"})
    assert r.status_code == 422
