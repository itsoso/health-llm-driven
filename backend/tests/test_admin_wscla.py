"""test_admin_wscla —— WSCLA 看板 API 的响应形状与聚合正确性."""

from datetime import datetime, timedelta, timezone

import uuid
from app.models.action_card import ActionCard
from app.models.user import User
from app.services.auth import auth_service

# 固定宽窗口起点 —— 避免默认 window_start=_week_start(now) 在周一/月初把
# now-Nh 的测试数据切到上一周外(确定性边界红,见 docs MEMORY)。until 默认 now。
_WSCLA = "/api/v1/admin/wscla?since=2020-01-01T00:00:00Z"


def _admin_headers(db):
    admin = User(
        username=f"admin_{uuid.uuid4().hex[:8]}",
        email=f"admin_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        name="admin",
        is_admin=True,
        is_active=True,
        is_approved=True,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    token = auth_service.create_access_token({"sub": str(admin.id)})
    return admin, {"Authorization": f"Bearer {token}"}


def _regular_headers(db):
    u = User(
        username=f"u_{uuid.uuid4().hex[:8]}",
        email=f"u_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        name="normal",
        is_active=True,
        is_approved=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    token = auth_service.create_access_token({"sub": str(u.id)})
    return u, {"Authorization": f"Bearer {token}"}


def test_wscla_requires_admin(client, db):
    _, headers = _regular_headers(db)
    resp = client.get(_WSCLA, headers=headers)
    assert resp.status_code == 403


def test_wscla_empty_shape(client, db):
    _, headers = _admin_headers(db)
    resp = client.get(_WSCLA, headers=headers)
    assert resp.status_code == 200
    body = resp.json()

    assert "window" in body
    assert "metrics" in body
    assert "counts" in body
    assert "by_severity" in body
    assert "by_source_type" in body
    assert "recent_cards" in body

    m = body["metrics"]
    assert m["wscla_count"] == 0
    # 空数据时率为 None (分母 0), 不是 0.0
    assert m["suggestion_acceptance_rate"] is None
    assert m["verification_rate"] is None
    assert m["push_ctr"] is None
    assert m["safety_fp_rate"] is None

    assert body["counts"]["decided"] == 0
    assert body["recent_cards"] == []


def test_wscla_counts_closed_loop_only(client, db):
    admin, headers = _admin_headers(db)
    now = datetime.now(timezone.utc)

    def card(**kw):
        base = dict(user_id=admin.id, title="t", content="c")
        base.update(kw)
        c = ActionCard(**base)
        db.add(c)
        return c

    # 本周完整闭环 improved → 计入
    card(
        user_decision="accepted",
        completed_at=now - timedelta(days=1),
        graded_at=now,
        outcome="improved",
    )
    # 本周完整闭环 unchanged → 计入
    card(
        user_decision="accepted",
        completed_at=now - timedelta(days=1),
        graded_at=now - timedelta(hours=2),
        outcome="unchanged",
    )
    # 本周 worsened → 不计入
    card(
        user_decision="accepted",
        completed_at=now - timedelta(days=1),
        graded_at=now,
        outcome="worsened",
    )
    # 本周 declined → 不计入
    card(user_decision="declined", decided_at=now - timedelta(days=1))
    db.commit()

    resp = client.get(_WSCLA, headers=headers)
    assert resp.status_code == 200
    m = resp.json()["metrics"]
    assert m["wscla_count"] == 2


def test_wscla_acceptance_rate(client, db):
    admin, headers = _admin_headers(db)
    now = datetime.now(timezone.utc)

    def card(**kw):
        base = dict(user_id=admin.id, title="t", content="c")
        base.update(kw)
        db.add(ActionCard(**base))

    card(user_decision="accepted", decided_at=now - timedelta(hours=1))
    card(user_decision="accepted", decided_at=now - timedelta(hours=2))
    card(user_decision="declined", decided_at=now - timedelta(hours=3))
    card(user_decision="dismissed", decided_at=now - timedelta(hours=4))
    db.commit()

    resp = client.get(_WSCLA, headers=headers)
    body = resp.json()
    assert body["counts"]["decided"] == 4
    assert body["counts"]["accepted"] == 2
    assert body["metrics"]["suggestion_acceptance_rate"] == 0.5


def test_wscla_push_ctr(client, db):
    admin, headers = _admin_headers(db)
    now = datetime.now(timezone.utc)

    def card(**kw):
        base = dict(user_id=admin.id, title="t", content="c")
        base.update(kw)
        db.add(ActionCard(**base))

    card(push_sent_at=now - timedelta(minutes=30), push_clicked_at=now - timedelta(minutes=10))
    card(push_sent_at=now - timedelta(minutes=40), push_clicked_at=now - timedelta(minutes=5))
    card(push_sent_at=now - timedelta(minutes=50))  # 未点击
    card(push_sent_at=now - timedelta(minutes=60))  # 未点击
    db.commit()

    resp = client.get(_WSCLA, headers=headers)
    body = resp.json()
    assert body["counts"]["push_sent"] == 4
    assert body["counts"]["push_clicked"] == 2
    assert body["metrics"]["push_ctr"] == 0.5


def test_wscla_safety_fp_rate(client, db):
    admin, headers = _admin_headers(db)
    now = datetime.now(timezone.utc)

    def card(**kw):
        base = dict(user_id=admin.id, title="t", content="c", source_type="safety_alert")
        base.update(kw)
        db.add(ActionCard(**base))

    card(user_decision="accepted", decided_at=now - timedelta(hours=1))
    card(user_decision="false_positive", decided_at=now - timedelta(hours=2))
    card(user_decision="false_positive", decided_at=now - timedelta(hours=3))
    card(user_decision="dismissed", decided_at=now - timedelta(hours=4))
    db.commit()

    resp = client.get(_WSCLA, headers=headers)
    body = resp.json()
    assert body["counts"]["safety_decided"] == 4
    assert body["counts"]["safety_false_positive"] == 2
    assert body["metrics"]["safety_fp_rate"] == 0.5


def test_wscla_filter_by_user(client, db):
    admin, headers = _admin_headers(db)
    other, _ = _regular_headers(db)
    now = datetime.now(timezone.utc)

    def card(user_id, **kw):
        base = dict(user_id=user_id, title="t", content="c")
        base.update(kw)
        db.add(ActionCard(**base))

    card(
        admin.id,
        user_decision="accepted",
        completed_at=now - timedelta(days=1),
        graded_at=now,
        outcome="improved",
    )
    card(
        other.id,
        user_decision="accepted",
        completed_at=now - timedelta(days=1),
        graded_at=now,
        outcome="improved",
    )
    db.commit()

    # 不过滤
    resp = client.get(_WSCLA, headers=headers)
    assert resp.json()["metrics"]["wscla_count"] == 2

    # 只看 admin
    resp = client.get(
        f"/api/v1/admin/wscla?user_id={admin.id}&since=2020-01-01T00:00:00Z", headers=headers)
    assert resp.json()["metrics"]["wscla_count"] == 1
