# -*- coding: utf-8 -*-
"""激活漏斗(Phase3 P1 增长仪表)回归。

钉:各级 distinct 用户数 + 相邻转化 + 北极星(improved);去标识;admin 鉴权。
"""
import uuid
from datetime import date as _date


def _user(db, admin=False):
    from app.models.user import User
    u = User(username=f"u_{uuid.uuid4().hex[:8]}", email=f"u_{uuid.uuid4().hex[:8]}@x.com",
             hashed_password="x", name="u", birth_date=_date(1990, 1, 1), gender="男",
             is_active=True, is_approved=True, is_admin=admin)
    db.add(u); db.commit(); db.refresh(u)
    return u


def _card(db, user_id, decision=None, outcome=None):
    from app.models.action_card import ActionCard
    db.add(ActionCard(user_id=user_id, title="t", content="x", metric_key="weight",
                      user_decision=decision, outcome=outcome))
    db.commit()


def test_funnel_counts_and_conversions(db):
    from app.services.activation_funnel_service import activation_funnel
    # 4 注册用户;u1 全程到 improved,u2 到 graded(unchanged),u3 仅 accepted,u4 仅建档
    u1, u2, u3, u4 = _user(db), _user(db), _user(db), _user(db)
    _card(db, u1.id, decision="accepted", outcome="improved")
    _card(db, u2.id, decision="adjusted", outcome="unchanged")
    _card(db, u3.id, decision="accepted")
    _card(db, u4.id)  # 有卡但未决策

    f = activation_funnel(db)
    fn = f["funnel"]
    assert fn["registered"] == 4
    assert fn["activated"] == 4          # 4 人都有卡
    assert fn["accepted"] == 3           # u1,u2,u3
    assert fn["graded"] == 2             # u1,u2
    assert fn["improved"] == 1           # u1
    assert f["north_star_users"] == 1
    assert f["conversions"]["accepted->graded"] == round(2 / 3, 3)
    assert f["overall_register_to_improved"] == round(1 / 4, 4)
    assert "user_id" not in str(f)       # 去标识


def test_funnel_empty(db):
    from app.services.activation_funnel_service import activation_funnel
    f = activation_funnel(db)
    assert f["funnel"]["registered"] == 0
    assert f["overall_register_to_improved"] is None


def test_funnel_endpoint_requires_admin(client, auth_user_and_headers):
    user, headers = auth_user_and_headers
    r = client.get("/api/v1/admin/observability/funnel", headers=headers)
    assert r.status_code == 403


def test_funnel_endpoint_ok_for_admin(client, db):
    from app.services.auth import auth_service
    admin = _user(db, admin=True)
    token = auth_service.create_access_token({"sub": str(admin.id)})
    r = client.get("/api/v1/admin/observability/funnel",
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200 and "funnel" in r.json()
