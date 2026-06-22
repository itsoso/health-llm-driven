"""P3(D1)复购检测测试 —— 消耗估算 / 剩余天数 / 阈值 / restock / IDOR / 扫描幂等 / confirm 不下单。

边界回归:reorder_nudge 的 confirm 只 acknowledge,绝不下单(无电商 skill 调用、不建 ReorderIntent
财务一等对象 —— 后者由 P5/D2 引入,P3 这条提醒路径与它完全隔离)。
"""
import uuid
from datetime import date, timedelta

import pytest

from app.models.supplement import SupplementDefinition, SupplementRecord
from app.models.supplement_inventory import SupplementInventory
from app.models.user import User
from app.models.write_intent import WriteIntent
from app.services import reorder_detection as rd
from app.services import write_intent_service as svc


# ─────────────────────────── fixtures / helpers ───────────────────────────

def _mk_user(db) -> User:
    u = User(
        username=f"ri_{uuid.uuid4().hex[:6]}",
        email=f"ri_{uuid.uuid4().hex[:6]}@x.com",
        hashed_password="x",
        name="ri",
        is_active=True,
        is_approved=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _mk_supp(db, user_id, name="维生素C") -> SupplementDefinition:
    s = SupplementDefinition(user_id=user_id, name=name, is_active=True)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _log_taken(db, user_id, supp_id, days_back: int):
    """为最近 days_back 天各落一条 taken=True 打卡。"""
    today = date.today()
    for i in range(days_back):
        db.add(SupplementRecord(
            user_id=user_id, supplement_id=supp_id,
            record_date=today - timedelta(days=i), taken=True,
        ))
    db.commit()


def _set_inventory(db, user_id, supp_id, units, **kw):
    inv = SupplementInventory(user_id=user_id, supplement_id=supp_id, units_remaining=units, **kw)
    db.add(inv)
    db.commit()
    return inv


def _headers(db, user) -> dict:
    from app.services.auth import auth_service
    return {"Authorization": f"Bearer {auth_service.create_access_token({'sub': str(user.id)})}"}


# ─────────────────────────── consumption estimation ───────────────────────

def test_estimate_uses_adherence_when_enough_logs():
    # 30 天里 15 天打卡 → 0.5 单位/天
    assert rd.estimate_daily_consumption(15, 30) == pytest.approx(0.5)


def test_estimate_falls_back_to_prescribed_when_too_few_logs():
    # 打卡不足 MIN_LOGS_FOR_ESTIMATE 但补剂仍 active → 回退默认每日 1 单位
    assert rd.estimate_daily_consumption(1, 30, has_active_definition=True) == 1.0


def test_estimate_none_when_no_basis():
    # 既无打卡也无活跃定义 → 无估算依据
    assert rd.estimate_daily_consumption(0, 30, has_active_definition=False) is None


def test_estimate_zero_window_guard():
    assert rd.estimate_daily_consumption(5, 0) is None


# ─────────────────────────── days_remaining math + status ─────────────────

def test_status_low_at_or_below_threshold():
    # 7 单位 / 1 per day = 7 天 = 阈值 → low
    st = rd.compute_status(7, 1.0)
    assert st.days_remaining == pytest.approx(7.0)
    assert st.status == "low"


def test_status_ok_above_threshold():
    st = rd.compute_status(20, 1.0)
    assert st.days_remaining == pytest.approx(20.0)
    assert st.status == "ok"


def test_status_fractional_days_remaining():
    # 10 单位 / 0.5 per day = 20 天(小数口径)
    st = rd.compute_status(5, 0.5)
    assert st.days_remaining == pytest.approx(10.0)
    assert st.status == "ok"


def test_status_unknown_when_units_missing():
    st = rd.compute_status(None, 1.0)
    assert st.status == "unknown" and st.days_remaining is None


def test_status_unknown_when_consumption_missing_or_zero():
    assert rd.compute_status(10, None).status == "unknown"
    assert rd.compute_status(10, 0.0).status == "unknown"


# ─────────────────────────── detect_for_user (DB wrapper) ─────────────────

def test_detect_unknown_when_no_inventory(db):
    u = _mk_user(db)
    s = _mk_supp(db, u.id)
    items = rd.detect_for_user(db, u.id)
    assert len(items) == 1
    it = items[0]
    assert it["supplement_id"] == s.id
    assert it["units_remaining"] is None
    assert it["status"] == "unknown"
    assert it["brand"] == "" and it["spec"] == ""


def test_detect_low_with_inventory_and_adherence(db):
    u = _mk_user(db)
    s = _mk_supp(db, u.id)
    _log_taken(db, u.id, s.id, 30)  # 每天都服 → ~1 单位/天
    _set_inventory(db, u.id, s.id, 5, brand="Now", spec="500mg")  # 5 天量
    items = rd.detect_for_user(db, u.id)
    it = items[0]
    assert it["status"] == "low"
    assert it["days_remaining"] == pytest.approx(5.0, abs=0.5)
    assert it["brand"] == "Now" and it["spec"] == "500mg"


def test_low_items_filters(db):
    u = _mk_user(db)
    s_low = _mk_supp(db, u.id, "镁")
    s_ok = _mk_supp(db, u.id, "锌")
    _log_taken(db, u.id, s_low.id, 30)
    _log_taken(db, u.id, s_ok.id, 30)
    _set_inventory(db, u.id, s_low.id, 3)
    _set_inventory(db, u.id, s_ok.id, 60)
    lows = rd.low_items_for_user(db, u.id)
    assert {it["supplement_id"] for it in lows} == {s_low.id}


# ─────────────────────────── API: inventory GET ───────────────────────────

def test_get_inventory_shape(client, db):
    u = _mk_user(db)
    s = _mk_supp(db, u.id)
    r = client.get("/api/v1/supplements/inventory", headers=_headers(db, u))
    assert r.status_code == 200
    body = r.json()
    assert "items" in body and len(body["items"]) == 1
    it = body["items"][0]
    for key in ("supplement_id", "name", "brand", "spec", "units_remaining",
                "daily_consumption", "days_remaining", "status"):
        assert key in it


# ─────────────────────────── API: restock ─────────────────────────────────

def test_restock_creates_and_adds(client, db):
    u = _mk_user(db)
    s = _mk_supp(db, u.id)
    h = _headers(db, u)
    r1 = client.post(f"/api/v1/supplements/inventory/{s.id}/restock",
                     json={"units_added": 30, "brand": "Now", "spec": "500mg", "package_units": 30}, headers=h)
    assert r1.status_code == 200
    assert r1.json()["units_remaining"] == 30
    assert r1.json()["brand"] == "Now"
    # 再补一次 → 累加(非覆盖)
    r2 = client.post(f"/api/v1/supplements/inventory/{s.id}/restock",
                     json={"units_added": 20}, headers=h)
    assert r2.json()["units_remaining"] == 50


def test_restock_units_added_required_400(client, db):
    u = _mk_user(db)
    s = _mk_supp(db, u.id)
    h = _headers(db, u)
    # 缺 units_added → 422(Pydantic 必填,无静默默认)
    r = client.post(f"/api/v1/supplements/inventory/{s.id}/restock", json={}, headers=h)
    assert r.status_code == 422
    # <=0 → 422
    r0 = client.post(f"/api/v1/supplements/inventory/{s.id}/restock", json={"units_added": 0}, headers=h)
    assert r0.status_code == 422
    rneg = client.post(f"/api/v1/supplements/inventory/{s.id}/restock", json={"units_added": -5}, headers=h)
    assert rneg.status_code == 422


def test_restock_idor_404(client, db):
    owner = _mk_user(db)
    s = _mk_supp(db, owner.id)
    attacker = _mk_user(db)
    r = client.post(f"/api/v1/supplements/inventory/{s.id}/restock",
                    json={"units_added": 10}, headers=_headers(db, attacker))
    assert r.status_code == 404
    # 攻击者库存未被创建
    assert db.query(SupplementInventory).filter(
        SupplementInventory.supplement_id == s.id).count() == 0


# ─────────────────────────── API: manual set (PUT) ────────────────────────

def test_manual_set_overwrites(client, db):
    u = _mk_user(db)
    s = _mk_supp(db, u.id)
    h = _headers(db, u)
    client.post(f"/api/v1/supplements/inventory/{s.id}/restock", json={"units_added": 30}, headers=h)
    r = client.put(f"/api/v1/supplements/inventory/{s.id}", json={"units_remaining": 12}, headers=h)
    assert r.status_code == 200
    assert r.json()["units_remaining"] == 12


def test_manual_set_idor_404(client, db):
    owner = _mk_user(db)
    s = _mk_supp(db, owner.id)
    attacker = _mk_user(db)
    r = client.put(f"/api/v1/supplements/inventory/{s.id}",
                   json={"units_remaining": 99}, headers=_headers(db, attacker))
    assert r.status_code == 404


# ─────────────────────────── generate_reorder_nudges idempotency ──────────

def test_generate_reorder_nudges_proposes_and_dedups(db):
    u = _mk_user(db)
    s = _mk_supp(db, u.id)
    _log_taken(db, u.id, s.id, 30)
    _set_inventory(db, u.id, s.id, 4)  # low
    n1 = svc.generate_reorder_nudges(db, u.id)
    assert n1 == 1
    # 同补剂当天再扫 → 不重复(防刷屏)
    n2 = svc.generate_reorder_nudges(db, u.id)
    assert n2 == 0
    pendings = [w for w in svc.list_pending(db, u.id) if w["kind"] == "reorder_nudge"]
    assert len(pendings) == 1
    wi = pendings[0]
    assert s.name in wi["title"]
    assert "补货" in wi["title"]


def test_generate_reorder_skips_ok_and_unknown(db):
    u = _mk_user(db)
    s_ok = _mk_supp(db, u.id, "锌")
    _log_taken(db, u.id, s_ok.id, 30)
    _set_inventory(db, u.id, s_ok.id, 90)  # ok
    s_unknown = _mk_supp(db, u.id, "钙")    # 无库存 → unknown
    assert svc.generate_reorder_nudges(db, u.id) == 0


# ─────────────────────────── scan task idempotency + no-dup ───────────────

def test_scan_reorder_idempotent_no_dup(db, monkeypatch):
    from app.tasks import reorder_scan

    u = _mk_user(db)
    s = _mk_supp(db, u.id)
    _log_taken(db, u.id, s.id, 30)
    _set_inventory(db, u.id, s.id, 3)  # low

    # SessionLocal → 测试 db;push 与稀缺门打桩(不实际推送)
    monkeypatch.setattr(reorder_scan, "SessionLocal", lambda: _ctx(db))
    monkeypatch.setattr("app.services.proactive_coordinator.can_notify_proactively",
                        lambda *a, **k: False)

    r1 = reorder_scan.scan_reorder_nudges()
    assert r1["proposed"] == 1
    # 再跑当日扫描 → 不重复建提议
    r2 = reorder_scan.scan_reorder_nudges()
    assert r2["proposed"] == 0
    assert db.query(WriteIntent).filter(
        WriteIntent.user_id == u.id, WriteIntent.kind == "reorder_nudge").count() == 1


# ─────────────────────────── confirm is no-op (NO ORDER) ──────────────────

def test_confirm_reorder_nudge_is_acknowledge_only(db, monkeypatch):
    """confirm reorder_nudge 只 acknowledge:不下单、不调任何电商/支付路径。"""
    u = _mk_user(db)
    s = _mk_supp(db, u.id)
    _log_taken(db, u.id, s.id, 30)
    _set_inventory(db, u.id, s.id, 2)
    svc.generate_reorder_nudges(db, u.id)
    wi = db.query(WriteIntent).filter(
        WriteIntent.user_id == u.id, WriteIntent.kind == "reorder_nudge").first()
    assert wi is not None

    res = svc.confirm(db, u.id, wi.id)
    assert res["status"] == "executed"
    assert res["executed_ref"] == "acknowledged"  # 仅确认知悉,无订单引用

    # P3 的 reorder_nudge confirm 路径绝不触碰财务一等对象:不建任何 ReorderIntent。
    # (ReorderIntent 由 P5/D2 引入,但 P3 这条「提醒」路径与它完全隔离 —— acknowledge-only。)
    from app.models.reorder_intent import ReorderIntent
    assert db.query(ReorderIntent).count() == 0


class _ctx:
    """把已有 test db 包成支持 with 的上下文(模拟 SessionLocal())。不关闭真 db。"""
    def __init__(self, db):
        self._db = db
    def __enter__(self):
        return self._db
    def __exit__(self, *a):
        return False
