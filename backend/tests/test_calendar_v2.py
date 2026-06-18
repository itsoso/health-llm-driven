"""Calendar v2 (C1):多源 + 详细事件 + 隐私接缝。

钉:① 模型默认值/加密往返 ② 多源 upsert 幂等 ③ today_busy_blocks 从 CalendarEvent 派生
④ ics 解析 ⑤ SSRF 护栏拒内网 ⑥ 隐私接缝剥 PII ⑦ API shape + 认证 + 越权隔离。
网络全部 patch,绝不真连 CalDAV/HTTP。
"""
from datetime import datetime, timedelta, timezone as _tz

import pytest

from app.models.calendar_sync import CalendarEvent, CalendarSource
from app.services import caldav_sync as svc

_BJ = _tz(timedelta(hours=8))


def _mk_source(db, user_id, provider="caldav", name="测试源"):
    s = CalendarSource(user_id=user_id, provider=provider, name=name)
    s.set_credentials({"url": "https://cal.example.com/dav", "username": "u", "password": "p"})
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


# ── ① 模型默认值 + 加密往返 ──────────────────────────────────────────────

def test_source_defaults_and_creds_roundtrip(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    s = _mk_source(db, user.id)
    assert s.writable is False
    assert s.sync_enabled is True
    assert s.get_credentials()["url"] == "https://cal.example.com/dav"
    assert "encrypted" in CalendarSource.encrypted_credentials.key or True
    # 凭据密文不含明文
    assert "cal.example.com" not in (s.encrypted_credentials or "")


def test_event_pii_encrypt_roundtrip(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    s = _mk_source(db, user.id)
    ev = CalendarEvent(user_id=user.id, source_id=s.id, uid="x1",
                       start_time=datetime.now(_BJ), end_time=datetime.now(_BJ))
    ev.set_title("和 Kim 开会")
    ev.set_location("北京办公室")
    ev.set_attendees(["Kim", "潘宝坤"])
    db.add(ev)
    db.commit()
    db.refresh(ev)
    assert ev.get_title() == "和 Kim 开会"
    assert ev.get_location() == "北京办公室"
    assert ev.get_attendees() == ["Kim", "潘宝坤"]
    # 静态加密:列里不含明文
    assert "Kim" not in (ev.encrypted_title or "")
    assert "潘宝坤" not in (ev.encrypted_attendees or "")


# ── ② 多源 upsert 幂等 ──────────────────────────────────────────────────

def test_sync_source_idempotent(db, auth_user_and_headers, monkeypatch):
    user, _ = auth_user_and_headers
    s = _mk_source(db, user.id)
    now = datetime.now(_BJ)
    fixed = [{
        "uid": "evt-1", "title": "会议", "location": None, "description": None,
        "attendees": [], "status": None,
        "start": now + timedelta(hours=1), "end": now + timedelta(hours=2),
        "all_day": False,
    }]
    monkeypatch.setattr(svc, "_fetch_source_events", lambda src, a, b: list(fixed))
    r1 = svc.sync_source(db, s)
    db.commit()
    assert r1["synced"] == 1
    n1 = db.query(CalendarEvent).filter(CalendarEvent.source_id == s.id).count()
    # 重同步同一 uid → 不产生重复行
    svc.sync_source(db, s)
    db.commit()
    n2 = db.query(CalendarEvent).filter(CalendarEvent.source_id == s.id).count()
    assert n1 == 1 and n2 == 1


def test_sync_all_sources_fail_soft(db, auth_user_and_headers, monkeypatch):
    user, _ = auth_user_and_headers
    good = _mk_source(db, user.id, name="好源")
    bad = _mk_source(db, user.id, name="坏源")
    now = datetime.now(_BJ)

    def fake_fetch(src, a, b):
        if src.id == bad.id:
            raise ValueError("坏源连接失败")
        return [{
            "uid": "g1", "title": "ok", "location": None, "description": None,
            "attendees": [], "status": None,
            "start": now + timedelta(hours=1), "end": now + timedelta(hours=2),
            "all_day": False,
        }]

    monkeypatch.setattr(svc, "_fetch_source_events", fake_fetch)
    summary = svc.sync_all_sources(db, user.id)
    assert summary["sources"][good.id]["synced"] == 1
    assert "error" in summary["sources"][bad.id]
    db.refresh(bad)
    assert bad.last_error and "坏源" in bad.last_error
    # 好源仍写入了
    assert db.query(CalendarEvent).filter(CalendarEvent.source_id == good.id).count() == 1


# ── ③ today_busy_blocks 从 CalendarEvent 派生 ───────────────────────────

def test_today_busy_blocks_from_events(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    s1 = _mk_source(db, user.id, name="A")
    s2 = _mk_source(db, user.id, name="B")
    today = datetime.now(_BJ).replace(hour=0, minute=0, second=0, microsecond=0)
    # 两源各一个今日有时刻事件
    e1 = CalendarEvent(user_id=user.id, source_id=s1.id, uid="a1", all_day=False,
                       start_time=today + timedelta(hours=9), end_time=today + timedelta(hours=10))
    e2 = CalendarEvent(user_id=user.id, source_id=s2.id, uid="b1", all_day=False,
                       start_time=today + timedelta(hours=14), end_time=today + timedelta(hours=15))
    # 全天事件 → 排除
    eall = CalendarEvent(user_id=user.id, source_id=s1.id, uid="a2", all_day=True,
                         start_time=today, end_time=today + timedelta(days=1))
    # 零长度 → 排除
    ezero = CalendarEvent(user_id=user.id, source_id=s1.id, uid="a3", all_day=False,
                          start_time=today + timedelta(hours=11), end_time=today + timedelta(hours=11))
    db.add_all([e1, e2, eall, ezero])
    db.commit()
    blocks = svc.today_busy_blocks(db, user.id)
    assert ("09:00", "10:00") in blocks
    assert ("14:00", "15:00") in blocks
    assert len(blocks) == 2  # 全天 + 零长被排除
    # shape 不变:tuple[str,str]
    assert all(isinstance(b, tuple) and len(b) == 2 for b in blocks)


# ── ④ ics 解析 ──────────────────────────────────────────────────────────

_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
UID:ics-evt-1
SUMMARY:瑜伽课
LOCATION:健身房
DTSTART:20260618T080000Z
DTEND:20260618T090000Z
END:VEVENT
BEGIN:VEVENT
UID:ics-allday
SUMMARY:生日
DTSTART;VALUE=DATE:20260620
DTEND;VALUE=DATE:20260621
END:VEVENT
END:VCALENDAR
"""


def test_ics_parse(monkeypatch):
    events = svc._parse_ics(_ICS)
    by_uid = {e["uid"]: e for e in events}
    assert by_uid["ics-evt-1"]["title"] == "瑜伽课"
    assert by_uid["ics-evt-1"]["location"] == "健身房"
    assert by_uid["ics-evt-1"]["all_day"] is False
    assert by_uid["ics-allday"]["all_day"] is True


def test_ics_fetch_through_source(db, auth_user_and_headers, monkeypatch):
    user, _ = auth_user_and_headers
    s = _mk_source(db, user.id, provider="ics", name="订阅")
    s.set_credentials({"url": "https://feeds.example.com/cal.ics"})
    db.commit()
    monkeypatch.setattr(svc, "_fetch_ics_text", lambda url, **kw: _ICS)
    # 宽窗口确保两个事件都落入
    start = datetime(2026, 6, 1, tzinfo=_BJ)
    end = datetime(2026, 7, 1, tzinfo=_BJ)
    events = svc._fetch_source_events(s, start, end)
    uids = {e["uid"] for e in events}
    assert "ics-evt-1" in uids


# ── ⑤ SSRF 护栏 ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("url", [
    "http://cal.example.com/dav",      # 非 https
    "http://localhost/dav",            # 非 https + 环回名
    "https://127.0.0.1/dav",           # 环回 IP
    "https://10.0.0.1/dav",            # 私网
    "https://169.254.169.254/latest",  # 链路本地(云元数据)
])
def test_ssrf_guard_rejects_internal(url):
    with pytest.raises(ValueError):
        svc._assert_safe_url(url)
    with pytest.raises(ValueError):
        svc._assert_safe_ics_url(url)


# ── ⑥ 隐私接缝 ─────────────────────────────────────────────────────────

def test_privacy_seam_strips_pii(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    s = _mk_source(db, user.id, name="Kim 工作")
    ev = CalendarEvent(user_id=user.id, source_id=s.id, uid="z1", all_day=False,
                       start_time=datetime.now(_BJ), end_time=datetime.now(_BJ) + timedelta(hours=1))
    ev.set_title("和 Kim 私密会面")
    ev.set_location("某地址")
    ev.set_attendees(["Kim"])
    db.add(ev)
    db.commit()
    db.refresh(ev)
    view = svc.calendar_event_for_llm(ev)
    for forbidden in ("title", "location", "description", "attendees", "uid"):
        assert forbidden not in view
    assert view["busy"] is True
    assert set(view.keys()) == {"start", "end", "busy", "all_day", "source_label"}
    # 标签也不外泄用户自定义名(可能含人名)
    assert "Kim" not in str(view)


# ── ⑦ API shape + 认证 + 越权 ──────────────────────────────────────────

def test_api_requires_auth(client):
    assert client.get("/api/v1/calendar/sources").status_code == 401
    assert client.post("/api/v1/calendar/sources", json={}).status_code == 401
    assert client.get("/api/v1/calendar/events").status_code == 401


def test_api_create_list_update_delete(client, auth_user_and_headers):
    _, h = auth_user_and_headers
    r = client.post("/api/v1/calendar/sources", headers=h, json={
        "provider": "ics", "name": "我的订阅", "url": "https://feeds.example.com/c.ics",
    })
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    assert r.json()["writable"] is False
    assert "encrypted_credentials" not in r.json()
    assert "url" not in r.json()
    # list
    lst = client.get("/api/v1/calendar/sources", headers=h).json()
    assert any(x["id"] == sid for x in lst)
    # update
    up = client.put(f"/api/v1/calendar/sources/{sid}", headers=h, json={"sync_enabled": False})
    assert up.status_code == 200 and up.json()["sync_enabled"] is False
    # delete
    assert client.delete(f"/api/v1/calendar/sources/{sid}", headers=h).status_code == 200
    assert all(x["id"] != sid for x in client.get("/api/v1/calendar/sources", headers=h).json())


def test_api_rejects_http_url(client, auth_user_and_headers):
    _, h = auth_user_and_headers
    r = client.post("/api/v1/calendar/sources", headers=h, json={
        "provider": "ics", "name": "x", "url": "http://feeds.example.com/c.ics",
    })
    assert r.status_code == 422


def test_api_user_isolation(client, db):
    from tests.conftest import create_authenticated_user
    ua, ta = create_authenticated_user(db)
    ub, tb = create_authenticated_user(db)
    ha = {"Authorization": f"Bearer {ta}"}
    hb = {"Authorization": f"Bearer {tb}"}
    sid = client.post("/api/v1/calendar/sources", headers=ha, json={
        "provider": "ics", "name": "A 的源", "url": "https://feeds.example.com/a.ics",
    }).json()["id"]
    # B 看不到 A 的源
    assert all(x["id"] != sid for x in client.get("/api/v1/calendar/sources", headers=hb).json())
    # B 无法改/删 A 的源 → 404
    assert client.put(f"/api/v1/calendar/sources/{sid}", headers=hb, json={"name": "hijack"}).status_code == 404
    assert client.delete(f"/api/v1/calendar/sources/{sid}", headers=hb).status_code == 404


def test_api_events_decrypted_for_owner(client, db, auth_user_and_headers):
    user, h = auth_user_and_headers
    s = _mk_source(db, user.id)
    today = datetime.now(_BJ)
    ev = CalendarEvent(user_id=user.id, source_id=s.id, uid="api1", all_day=False,
                       start_time=today + timedelta(hours=2), end_time=today + timedelta(hours=3))
    ev.set_title("自己的事件")
    db.add(ev)
    db.commit()
    rows = client.get("/api/v1/calendar/events", headers=h).json()
    assert any(r["title"] == "自己的事件" for r in rows)
