"""卧室环境快照: service + API + 隐私守门 (设计文档 §9/§11 地基).

覆盖:
- record_snapshot → get_current (新鲜)
- stale 判定 (老 captured_at)
- get_history 时间倒序
- 用户隔离 (u2 看不到 u1)
- 坏数值容错不崩
- API 三端点 200 + shape + 401 (无 token)
- 隐私守门: twin_to_prompt_blob 输出不含 co2/卧室快照内容
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.user import User
from app.services import bedroom_environment_service as svc
from app.services.auth import auth_service


def _make_user(db) -> User:
    u = User(
        username=f"bed_{uuid.uuid4().hex[:8]}",
        email=f"bed_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        name="bedtest",
        is_active=True,
        is_approved=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


# ─────────────────────────── service ───────────────────────────

def test_record_then_get_current_fresh(db):
    u = _make_user(db)
    svc.record_snapshot(
        db,
        u.id,
        {"co2_ppm": 850, "pm25": 5, "temperature_c": 22.5, "humidity_percent": 48},
    )
    cur = svc.get_current(db, u.id)
    assert cur is not None
    assert cur["co2_ppm"] == 850.0
    assert cur["temperature_c"] == 22.5
    assert cur["room_id"] == "bedroom"
    assert cur["confidence"] == "medium"
    assert cur["stale"] is False


def test_stale_when_old(db):
    u = _make_user(db)
    old = datetime.now(timezone.utc) - timedelta(minutes=30)
    svc.record_snapshot(db, u.id, {"co2_ppm": 1100, "captured_at": old.isoformat()})
    cur = svc.get_current(db, u.id)
    assert cur is not None
    assert cur["stale"] is True


def test_get_history_desc_order(db):
    u = _make_user(db)
    now = datetime.now(timezone.utc)
    for i, ago in enumerate((180, 60, 5)):  # 不同时刻, 避免唯一约束冲突
        svc.record_snapshot(
            db,
            u.id,
            {"co2_ppm": 800 + i, "captured_at": (now - timedelta(minutes=ago)).isoformat()},
        )
    hist = svc.get_history(db, u.id, days=7)
    assert len(hist) == 3
    ts = [h["captured_at"] for h in hist]
    assert ts == sorted(ts, reverse=True)  # 时间倒序


def test_history_respects_days_window(db):
    u = _make_user(db)
    now = datetime.now(timezone.utc)
    svc.record_snapshot(db, u.id, {"co2_ppm": 800, "captured_at": now.isoformat()})
    svc.record_snapshot(
        db, u.id, {"co2_ppm": 900, "captured_at": (now - timedelta(days=10)).isoformat()}
    )
    hist = svc.get_history(db, u.id, days=7)
    assert len(hist) == 1  # 10 天前那条被窗口排除


def test_user_isolation(db):
    u1 = _make_user(db)
    u2 = _make_user(db)
    svc.record_snapshot(db, u1.id, {"co2_ppm": 999})
    assert svc.get_current(db, u2.id) is None
    assert svc.get_history(db, u2.id) == []
    cur1 = svc.get_current(db, u1.id)
    assert cur1 is not None and cur1["co2_ppm"] == 999.0


def test_bad_numeric_values_tolerated(db):
    u = _make_user(db)
    # co2 是坏值 (字符串非数字) → 丢弃为 None; 其他正常字段照常入库, 不崩.
    row = svc.record_snapshot(
        db, u.id, {"co2_ppm": "not-a-number", "temperature_c": 21.0}
    )
    assert row.co2_ppm is None
    assert row.temperature_c == 21.0


def test_unknown_confidence_falls_back(db):
    u = _make_user(db)
    row = svc.record_snapshot(db, u.id, {"co2_ppm": 800, "confidence": "bogus"})
    assert row.confidence == "medium"


def test_low_confidence_preserved(db):
    u = _make_user(db)
    row = svc.record_snapshot(db, u.id, {"co2_ppm": 800, "confidence": "low"})
    assert row.confidence == "low"


def test_no_data_returns_none(db):
    u = _make_user(db)
    assert svc.get_current(db, u.id) is None
    assert svc.get_history(db, u.id) == []


# ─────────────────────────── API ───────────────────────────

def _headers(db, user: User):
    token = auth_service.create_access_token({"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


def test_api_ingest_and_current(client, db):
    u = _make_user(db)
    headers = _headers(db, u)
    resp = client.post(
        "/api/v1/environment/bedroom/snapshots",
        headers=headers,
        json={"co2_ppm": 920, "temperature_c": 23.0, "humidity_percent": 50},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "id" in body and body["room_id"] == "bedroom"

    cur = client.get("/api/v1/environment/bedroom/current", headers=headers)
    assert cur.status_code == 200, cur.text
    data = cur.json()
    assert data["co2_ppm"] == 920.0
    assert "stale" in data and data["stale"] is False


def test_api_history(client, db):
    u = _make_user(db)
    headers = _headers(db, u)
    now = datetime.now(timezone.utc)
    for ago in (120, 10):
        client.post(
            "/api/v1/environment/bedroom/snapshots",
            headers=headers,
            json={"co2_ppm": 800, "captured_at": (now - timedelta(minutes=ago)).isoformat()},
        )
    resp = client.get("/api/v1/environment/bedroom/history?days=7", headers=headers)
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert isinstance(rows, list) and len(rows) == 2
    assert all("captured_at" in r and "stale" in r for r in rows)


def test_api_requires_auth(client):
    assert client.get("/api/v1/environment/bedroom/current").status_code == 401
    assert client.get("/api/v1/environment/bedroom/history").status_code == 401
    assert (
        client.post(
            "/api/v1/environment/bedroom/snapshots", json={"co2_ppm": 800}
        ).status_code
        == 401
    )


def test_api_current_null_when_empty(client, db):
    u = _make_user(db)
    headers = _headers(db, u)
    resp = client.get("/api/v1/environment/bedroom/current", headers=headers)
    assert resp.status_code == 200
    assert resp.json() is None


# ─────────────────────── 隐私守门 (设计文档 §11) ───────────────────────

def test_bedroom_data_not_in_llm_prompt_blob():
    """卧室居住/睡眠环境数据绝不进通用 LLM 上下文.

    构造一个 twin → 生成 prompt blob → 断言里面没有任何卧室快照字段.
    这是反向护栏: 如果日后有人把 bedroom snapshot 接进 twin_to_prompt_blob,
    这条测试立刻变红.
    """
    from app.twin.formatter import twin_to_prompt_blob
    from app.twin.schema import HealthTwin, TwinMeta

    twin = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.now(timezone.utc)))
    blob = twin_to_prompt_blob(twin).lower()

    # 卧室快照的标志性字段不应出现在通用 LLM 上下文中.
    for forbidden in ("co2", "bed_presence", "卧室", "bedroom", "tvoc", "illuminance"):
        assert forbidden.lower() not in blob, (
            f"prompt blob 泄漏了卧室环境字段 {forbidden!r}: {blob[:200]}"
        )

    # formatter 不应 import / 引用 bedroom service (静态保证不接通).
    import app.twin.formatter as fmt
    src = open(fmt.__file__, encoding="utf-8").read().lower()
    assert "bedroom_environment" not in src
