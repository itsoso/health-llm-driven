"""Write 层 v0 服务测试 —— 写意图账本(propose/confirm/dismiss/生成器/IDOR/fail-loud)。"""
import uuid
from datetime import date, timedelta

import pytest

from app.models.health_problem import HealthProblem
from app.models.smart_reminder import SmartReminder
from app.models.user import User
from app.models.write_intent import WriteIntent
from app.services import write_intent_service as svc


def _mk_user(db) -> User:
    u = User(
        username=f"wi_{uuid.uuid4().hex[:6]}",
        email=f"wi_{uuid.uuid4().hex[:6]}@x.com",
        hashed_password="x",
        name="wi",
        is_active=True,
        is_approved=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _due_problem(db, user_id: int, *, name="胃溃疡", overdue=True):
    nd = (date.today() - timedelta(days=2)) if overdue else (date.today() + timedelta(days=3))
    p = HealthProblem(
        user_id=user_id,
        name=name,
        risk_level="P1",
        status="active",
        follow_up={"next_due": nd.isoformat(), "cadence": "P3M", "what_to_check": "复查胃镜"},
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def test_propose_idempotent(db):
    u = _mk_user(db)
    a = svc.propose(db, u.id, kind="checkup_reminder", title="复查", description="d",
                    source="test", target_type="health_problem", target_id=1, payload={})
    assert a is not None
    dup = svc.propose(db, u.id, kind="checkup_reminder", title="复查", description="d",
                      source="test", target_type="health_problem", target_id=1, payload={})
    assert dup is None  # 同 (user,kind,target) 已有 pending → 不重复
    assert len(svc.list_pending(db, u.id)) == 1


def test_generate_followup_recall_proposes_and_is_idempotent(db):
    u = _mk_user(db)
    p = _due_problem(db, u.id)
    n = svc.generate_followup_recall(db, u.id)
    assert n == 1
    items = svc.list_pending(db, u.id)
    assert len(items) == 1
    it = items[0]
    assert it["kind"] == "checkup_reminder"
    assert it["target_type"] == "health_problem" and it["target_id"] == p.id
    assert it["trust_tier"] == "manual_confirm"
    # 再跑一次 → 不重复(已有 pending)
    assert svc.generate_followup_recall(db, u.id) == 0
    assert len(svc.list_pending(db, u.id)) == 1


def test_confirm_executes_creates_reminder(db):
    u = _mk_user(db)
    wi = svc.propose(db, u.id, kind="checkup_reminder", title="复查胃镜", description="查胃镜",
                     source="test", target_type="health_problem", target_id=7,
                     payload={"what_to_check": "查胃镜", "next_due": date.today().isoformat()})
    res = svc.confirm(db, u.id, wi.id)
    assert res["status"] == "executed" and res["idempotent"] is False
    assert res["executed_ref"].startswith("smart_reminder:")
    rems = db.query(SmartReminder).filter(SmartReminder.user_id == u.id).all()
    assert len(rems) == 1 and rems[0].title == "复查胃镜"
    assert db.query(WriteIntent).get(wi.id).status == "executed"
    # 不再出现在待确认列表
    assert svc.list_pending(db, u.id) == []


def test_confirm_idempotent_no_double_reminder(db):
    u = _mk_user(db)
    wi = svc.propose(db, u.id, kind="checkup_reminder", title="复查", description=None,
                     source="test", target_type="health_problem", target_id=8, payload={})
    svc.confirm(db, u.id, wi.id)
    again = svc.confirm(db, u.id, wi.id)
    assert again["idempotent"] is True and again["status"] == "executed"
    assert db.query(SmartReminder).filter(SmartReminder.user_id == u.id).count() == 1


def test_dismiss(db):
    u = _mk_user(db)
    wi = svc.propose(db, u.id, kind="checkup_reminder", title="复查", description=None,
                     source="test", target_type="health_problem", target_id=9, payload={})
    res = svc.dismiss(db, u.id, wi.id)
    assert res["status"] == "dismissed"
    assert svc.list_pending(db, u.id) == []
    # dismiss 后不产生提醒
    assert db.query(SmartReminder).filter(SmartReminder.user_id == u.id).count() == 0


def test_idor_other_user_cannot_confirm_or_dismiss(db):
    a = _mk_user(db)
    b = _mk_user(db)
    wi = svc.propose(db, a.id, kind="checkup_reminder", title="复查", description=None,
                     source="test", target_type="health_problem", target_id=10, payload={})
    with pytest.raises(LookupError):
        svc.confirm(db, b.id, wi.id)
    with pytest.raises(LookupError):
        svc.dismiss(db, b.id, wi.id)
    # A 的意图仍 pending、未执行
    assert db.query(WriteIntent).get(wi.id).status == "pending"


def test_unknown_kind_fails_loud_and_stays_pending(db):
    u = _mk_user(db)
    wi = svc.propose(db, u.id, kind="bogus_kind", title="x", description=None,
                     source="test", target_type="t", target_id=1, payload={})
    with pytest.raises(ValueError):
        svc.confirm(db, u.id, wi.id)
    # 执行失败整体回滚 → 状态退回 pending,绝不假装成功
    db.expire_all()
    assert db.query(WriteIntent).get(wi.id).status == "pending"
