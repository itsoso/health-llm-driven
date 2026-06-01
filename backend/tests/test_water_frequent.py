"""GET /daily-health/water/me/frequent —— 常用饮水组合聚合的回归测试 (一键记录)."""
import uuid
from datetime import date, timedelta

import pytest

from app.models.user import User
from app.models.daily_health import WaterIntake


@pytest.fixture
def auth(client, db):
    user = User(
        username=f"wfreq_{uuid.uuid4().hex[:6]}",
        email=f"wfreq_{uuid.uuid4().hex[:6]}@x.com",
        hashed_password="x",
        name="wfreq",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    from app.services.auth import auth_service
    token = auth_service.create_access_token({"sub": str(user.id)})
    return user, {"Authorization": f"Bearer {token}"}


def _water(db, user_id, amount_ml, drink_type, days_ago):
    db.add(WaterIntake(
        user_id=user_id,
        record_date=date.today() - timedelta(days=days_ago),
        amount_ml=amount_ml,
        drink_type=drink_type,
    ))
    db.commit()


def _get(client, headers, **params):
    resp = client.get("/api/v1/daily-health/water/me/frequent", headers=headers, params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_empty_when_no_records(client, auth, db):
    _user, headers = auth
    assert _get(client, headers) == []


def test_groups_by_amount_and_drink_type(client, auth, db):
    user, headers = auth
    for d in range(3):
        _water(db, user.id, 250, "水", d)        # (250,水) ×3
    for d in range(2):
        _water(db, user.id, 350, "咖啡", d)       # (350,咖啡) ×2
    _water(db, user.id, 250, "茶", 0)             # (250,茶) ×1 — 与 (250,水) 不同组合

    items = _get(client, headers)
    assert items[0]["amount_ml"] == 250
    assert items[0]["drink_type"] == "水"
    assert items[0]["count"] == 3
    assert items[1]["amount_ml"] == 350 and items[1]["count"] == 2
    # 三个不同组合
    assert len(items) == 3


def test_skips_nonpositive_amount(client, auth, db):
    user, headers = auth
    _water(db, user.id, 0, "水", 0)
    _water(db, user.id, 200, "水", 0)
    items = _get(client, headers)
    assert [i["amount_ml"] for i in items] == [200]


def test_respects_limit_and_window(client, auth, db):
    user, headers = auth
    for amt in (100, 200, 300, 400, 500):
        _water(db, user.id, amt, "水", 0)
    _water(db, user.id, 999, "水", 200)  # 超窗口
    items = _get(client, headers, limit=3, days=30)
    assert len(items) == 3
    assert all(i["amount_ml"] != 999 for i in items)


def test_user_isolation(client, auth, db):
    user, headers = auth
    other = User(
        username=f"other_{uuid.uuid4().hex[:6]}",
        email=f"other_{uuid.uuid4().hex[:6]}@x.com",
        hashed_password="x", name="o", is_active=True, is_approved=True,
    )
    db.add(other)
    db.commit()
    db.refresh(other)
    _water(db, other.id, 999, "别人的水", 0)
    _water(db, user.id, 250, "我的水", 0)
    items = _get(client, headers)
    assert [i["amount_ml"] for i in items] == [250]


def test_requires_auth(client):
    resp = client.get("/api/v1/daily-health/water/me/frequent")
    assert resp.status_code in (401, 403)
