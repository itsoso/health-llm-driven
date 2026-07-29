"""依从写回幂等的 DB 兜底回归(把 complete_protocol 的标准推广到兄弟端点)。

背景:complete_protocol 已用 (a) 唯一约束 + (b) 原子状态转移门控住「腕上一键完成 → 写一条
依从」的并发重复写(见 test_watch_action_concurrency.py)。但同样写 DDI/PGx 消费的依从表的
兄弟端点没有 DB 兜底:
  1. family-health POST /medications/{id}/take —— 读-检查-写,无唯一约束 → 并发双击落 2 条
  2. medication POST /logs(log_medication)—— 完全无去重
  3. 协议补剂分支 / supplements /records —— supplement_records 无唯一约束

修法:
  - MedicationLog 加 (medication_id, taken_date, COALESCE(taken_time,'')) 唯一索引
    (uq_medlog_med_date_time):NULL 折叠成同一槽去重「今日按日标记」,而 times_per_day>1 的
    多剂(不同 taken_time)是不同槽仍并存。
  - SupplementRecord 加 (supplement_id, record_date) 唯一约束(uq_supprec_supp_date)。
  - 各写入端点把读-检查-写改成「撞唯一约束 → 回滚重读 → 合并」的幂等收敛。

⚠️ SQLite 单连接限制(同 test_watch_action_concurrency 模块 docstring):conftest 的内存
SQLite 用 StaticPool,无法真起多线程测「两 session 并发读到无行」。这里覆盖的是
**约束本身**(插重复 → IntegrityError)与**端点的幂等收敛逻辑**(串行重复调用 → 恰好一条);
真并发竞态的正确性靠生产 PG 的唯一约束阻断 + 端点的 IntegrityError 回退推演。
"""
import uuid
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.medication import Medication, MedicationLog
from app.models.supplement import SupplementDefinition, SupplementRecord
from app.models.user import User
from app.services import health_protocol_service as proto_svc
from app.services.medication_service import medication_service


# ── fixtures ──────────────────────────────────────────────────────────
def _mk_user(db):
    u = User(username=f"adh_{uuid.uuid4().hex[:6]}", email=f"adh_{uuid.uuid4().hex[:6]}@x.com",
             hashed_password="x", name="adh", is_active=True, is_approved=True)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _mk_med(db, user_id, times_per_day=1):
    med = Medication(user_id=user_id, name="瑞舒伐他汀", dosage="10mg", times_per_day=times_per_day)
    db.add(med)
    db.commit()
    db.refresh(med)
    return med


def _mk_supp(db, user_id):
    sd = SupplementDefinition(user_id=user_id, name="维生素D3", dosage="5000IU",
                              timing="morning", is_active=True)
    db.add(sd)
    db.commit()
    db.refresh(sd)
    return sd


def _auth(db, user):
    from app.services.auth import auth_service
    token = auth_service.create_access_token({"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


# ══════════════════════════════════════════════════════════════════════
# 1. MedicationLog 唯一约束本身(DB 兜底)
# ══════════════════════════════════════════════════════════════════════
def test_medlog_duplicate_null_time_blocked(db):
    """两条同 (药, 日期, taken_time=NULL) 的「今日按日标记」→ 第二条 IntegrityError。

    这正是 family /take 的并发双击:taken_time 都为 NULL,COALESCE(taken_time,'') 折叠成
    同一槽 → 第二条撞唯一约束(否则同一剂落 2 条虚高依从)。
    """
    user = _mk_user(db)
    med = _mk_med(db, user.id)
    today = date.today()
    db.add(MedicationLog(user_id=user.id, medication_id=med.id, taken_date=today, status="taken"))
    db.commit()
    db.add(MedicationLog(user_id=user.id, medication_id=med.id, taken_date=today, status="taken"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_medlog_duplicate_same_time_blocked(db):
    """两条同 (药, 日期, "08:00") → 第二条 IntegrityError(/logs 同剂重复提交去重)。"""
    user = _mk_user(db)
    med = _mk_med(db, user.id)
    today = date.today()
    db.add(MedicationLog(user_id=user.id, medication_id=med.id, taken_date=today,
                         taken_time="08:00", status="taken"))
    db.commit()
    db.add(MedicationLog(user_id=user.id, medication_id=med.id, taken_date=today,
                         taken_time="08:00", status="taken"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_medlog_multidose_distinct_times_allowed(db):
    """times_per_day>1 的多剂(08:00 / 20:00 不同 taken_time)是不同槽 → 并存(不误伤)。

    这是唯一索引必须含 taken_time 的原因:若只按 (药, 日期) 去重,合法的一日两次会被阻断。
    """
    user = _mk_user(db)
    med = _mk_med(db, user.id, times_per_day=2)
    today = date.today()
    db.add(MedicationLog(user_id=user.id, medication_id=med.id, taken_date=today,
                         taken_time="08:00", status="taken"))
    db.add(MedicationLog(user_id=user.id, medication_id=med.id, taken_date=today,
                         taken_time="20:00", status="taken"))
    db.commit()  # 不应抛
    logs = db.query(MedicationLog).filter(MedicationLog.medication_id == med.id).all()
    assert len(logs) == 2

    # 而且 NULL 槽与具体时点槽互不冲突(按日标记可与多剂并存,各自仍去重)
    db.add(MedicationLog(user_id=user.id, medication_id=med.id, taken_date=today, status="taken"))
    db.commit()
    assert db.query(MedicationLog).filter(MedicationLog.medication_id == med.id).count() == 3


# ══════════════════════════════════════════════════════════════════════
# 2. medication_service.log_medication 幂等收敛(commit=True 路径)
# ══════════════════════════════════════════════════════════════════════
def test_log_medication_idempotent_on_duplicate(db):
    """同 (药, 日期, 时点) 第二次 log_medication → 不抛、返回既有行、库里恰好一条。"""
    user = _mk_user(db)
    med = _mk_med(db, user.id)
    first = medication_service.log_medication(
        db, user_id=user.id, medication_id=med.id, taken_time="08:00", status="taken")
    second = medication_service.log_medication(
        db, user_id=user.id, medication_id=med.id, taken_time="08:00", status="taken")
    assert second.id == first.id, "重复写应幂等收敛到既有行,而非新建"
    logs = db.query(MedicationLog).filter(MedicationLog.medication_id == med.id).all()
    assert len(logs) == 1


def test_log_medication_distinct_times_not_deduped(db):
    """不同时点是两剂,不该被幂等合并(回归:别把多剂当重复吞掉)。"""
    user = _mk_user(db)
    med = _mk_med(db, user.id, times_per_day=2)
    a = medication_service.log_medication(
        db, user_id=user.id, medication_id=med.id, taken_time="08:00", status="taken")
    b = medication_service.log_medication(
        db, user_id=user.id, medication_id=med.id, taken_time="20:00", status="taken")
    assert a.id != b.id
    assert db.query(MedicationLog).filter(MedicationLog.medication_id == med.id).count() == 2


# ══════════════════════════════════════════════════════════════════════
# 3. family-health /take 端点幂等(读-改-写 + IntegrityError 回退)
# ══════════════════════════════════════════════════════════════════════
def test_family_take_idempotent(client, db):
    """重复 POST /family-health/medications/{id}/take → 200 且只落一条 taken。"""
    user = _mk_user(db)
    med = _mk_med(db, user.id)
    headers = _auth(db, user)
    url = f"/api/v1/family-health/medications/{med.id}/take"
    r1 = client.post(url, headers=headers)
    r2 = client.post(url, headers=headers)
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text
    logs = db.query(MedicationLog).filter(MedicationLog.medication_id == med.id).all()
    assert len(logs) == 1
    assert logs[0].status == "taken"


# ══════════════════════════════════════════════════════════════════════
# 4. SupplementRecord 唯一约束 + /records 端点幂等
# ══════════════════════════════════════════════════════════════════════
def test_supprec_duplicate_blocked(db):
    """两条同 (补剂, 日期) → 第二条 IntegrityError;不同日期则允许。"""
    user = _mk_user(db)
    sd = _mk_supp(db, user.id)
    today = date.today()
    db.add(SupplementRecord(user_id=user.id, supplement_id=sd.id, record_date=today, taken=True))
    db.commit()
    db.add(SupplementRecord(user_id=user.id, supplement_id=sd.id, record_date=today, taken=True))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_supplement_records_endpoint_idempotent(client, db):
    """重复 POST /supplements/records 同 (补剂, 日期) → 200 且只落一条。"""
    user = _mk_user(db)
    sd = _mk_supp(db, user.id)
    headers = _auth(db, user)
    today = date.today().isoformat()
    body = {"supplement_id": sd.id, "user_id": user.id, "record_date": today, "taken": True}
    r1 = client.post("/api/v1/supplements/records", json=body, headers=headers)
    r2 = client.post("/api/v1/supplements/records", json=body, headers=headers)
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text
    recs = db.query(SupplementRecord).filter(SupplementRecord.supplement_id == sd.id).all()
    assert len(recs) == 1
    assert recs[0].taken is True


# ══════════════════════════════════════════════════════════════════════
# 5. 协议补剂完成 不被「同日已有打卡」无辜 500(新约束下的 upsert)
# ══════════════════════════════════════════════════════════════════════
def test_protocol_supplement_completion_upserts_existing_day_record(db, monkeypatch):
    """用户先在补剂页勾过今日打卡(taken=False),再完成补剂协议 → 不撞唯一约束,
    翻成 taken=True 且库里恰好一条(而非协议盲插第二条撞约束 500)。
    """
    user = _mk_user(db)
    sd = _mk_supp(db, user.id)
    # Protocol completion keys the record by the user's local calendar day,
    # not by the date of the server running this test.
    protocol_day = date(2031, 1, 2)
    monkeypatch.setattr(
        proto_svc,
        "get_user_today",
        lambda _db, _user_id: protocol_day,
    )
    # 同日已有一条打卡(未服),模拟用户先在补剂页操作过
    db.add(
        SupplementRecord(
            user_id=user.id,
            supplement_id=sd.id,
            record_date=protocol_day,
            taken=False,
        )
    )
    db.commit()

    p = proto_svc.create_protocol(db, user.id, {
        "domain": "supplement", "name": "维生素D3 补剂", "mechanism": "fixed_container",
        "cadence": "daily", "can_default_complete": False,
        "source_model": "supplement_records", "source_id": sd.id,
    })
    ev = proto_svc.complete_protocol(db, p.id, user.id, track="protocol")
    assert ev is not None and ev.status == "completed"

    recs = db.query(SupplementRecord).filter(SupplementRecord.supplement_id == sd.id).all()
    assert len(recs) == 1, "协议完成应 upsert 既有同日记录,不该再插一条撞唯一约束"
    assert recs[0].record_date == protocol_day
    assert recs[0].taken is True, "协议完成应把既有记录翻成 taken"
    assert ev.value["linked_record_id"] == recs[0].id
