"""GET /supplements/me/frequent —— 最常打卡补剂聚合的回归测试 (一键打卡)."""
import uuid
from datetime import date, timedelta

import pytest

from app.models.user import User
from app.models.supplement import SupplementDefinition, SupplementRecord


@pytest.fixture
def auth(client, db):
    user = User(
        username=f"sfreq_{uuid.uuid4().hex[:6]}",
        email=f"sfreq_{uuid.uuid4().hex[:6]}@x.com",
        hashed_password="x",
        name="sfreq",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    from app.services.auth import auth_service
    token = auth_service.create_access_token({"sub": str(user.id)})
    return user, {"Authorization": f"Bearer {token}"}


def _def(db, user_id, name, *, active=True, dosage="100mg", timing="morning"):
    d = SupplementDefinition(
        user_id=user_id, name=name, dosage=dosage, timing=timing, is_active=active,
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


def _taken(db, user_id, supplement_id, days_ago, *, taken=True):
    db.add(SupplementRecord(
        user_id=user_id,
        supplement_id=supplement_id,
        record_date=date.today() - timedelta(days=days_ago),
        taken=taken,
    ))
    db.commit()


def _get(client, headers, **params):
    resp = client.get("/api/v1/supplements/me/frequent", headers=headers, params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_empty_when_no_records(client, auth, db):
    _user, headers = auth
    assert _get(client, headers) == []


def test_orders_by_taken_count_desc(client, auth, db):
    user, headers = auth
    vd = _def(db, user.id, "维生素D")
    o3 = _def(db, user.id, "Omega-3")
    for d in range(3):
        _taken(db, user.id, vd.id, d)      # 3 次
    for d in range(2):
        _taken(db, user.id, o3.id, d)      # 2 次

    items = _get(client, headers)
    assert [i["name"] for i in items] == ["维生素D", "Omega-3"]
    assert items[0]["count"] == 3
    assert items[0]["dosage"] == "100mg"
    assert items[0]["timing"] == "morning"


def test_only_counts_taken_true(client, auth, db):
    user, headers = auth
    vd = _def(db, user.id, "维生素D")
    _taken(db, user.id, vd.id, 0, taken=True)
    _taken(db, user.id, vd.id, 1, taken=False)  # 未服用不计
    items = _get(client, headers)
    assert items[0]["count"] == 1


def test_inactive_definition_excluded(client, auth, db):
    user, headers = auth
    stopped = _def(db, user.id, "已停用补剂", active=False)
    _taken(db, user.id, stopped.id, 0)
    assert _get(client, headers) == []


def test_respects_limit_and_window(client, auth, db):
    user, headers = auth
    for i in range(5):
        d = _def(db, user.id, f"补剂{i}")
        _taken(db, user.id, d.id, 0)
    old = _def(db, user.id, "太久以前")
    _taken(db, user.id, old.id, 200)  # 超出 30 天窗口

    items = _get(client, headers, limit=3, days=30)
    assert len(items) == 3
    assert all(i["name"] != "太久以前" for i in items)


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
    od = _def(db, other.id, "别人的补剂")
    _taken(db, other.id, od.id, 0)
    md = _def(db, user.id, "我的补剂")
    _taken(db, user.id, md.id, 0)

    items = _get(client, headers)
    assert [i["name"] for i in items] == ["我的补剂"]


def test_requires_auth(client):
    resp = client.get("/api/v1/supplements/me/frequent")
    assert resp.status_code in (401, 403)
