"""Watch 一键完成的并发幂等 + 审计 + 提交原子性回归(安全审核 D1/S2)。

补 docs/design-watch-action-complete.md 之外的两条硬伤:
- D1(DANGEROUS): complete_protocol 的幂等只靠应用层读-改-写,并发双击两个 session
  都读到 was_completed=False → 同一剂落 2 条依从。修法 = (a) DB 唯一约束
  uq_hpe_protocol_date (protocol_id, event_date) + (b) 领域写由原子 UPDATE
  rowcount 门控。这里钉「门控逻辑」与「约束本身」。
- S2(should-fix): log_medication 中途自 commit 破坏 complete_protocol 的一次性提交;
  腕上完成依从缺审计旁路。

⚠️ SQLite 单连接限制:conftest 的内存 SQLite 用 StaticPool(全测试共享单连接),
**无法真起多线程并发**测「两 session 并发读到同一 was_completed」。生产是 PostgreSQL,
真并发下靠 (a) 唯一约束阻断重复 (protocol_id, event_date) event +
(b) `UPDATE ... WHERE status != 'completed'` 的原子状态转移(仅抢到转移的事务 rowcount==1
才落领域记录)兜底。本文件覆盖的是**门控逻辑**(预置 completed event → 不写第二条)
与**约束本身**(插重复 → IntegrityError),不是真并发竞态。
"""
import uuid
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.health_protocol import HealthProtocol, HealthProtocolEvent
from app.models.medication import Medication, MedicationLog
from app.models.supplement import SupplementDefinition, SupplementRecord
from app.models.user import User
from app.services import health_protocol_service as proto_svc


# ── fixtures ──────────────────────────────────────────────────────────
def _mk_user(db):
    u = User(username=f"wc_{uuid.uuid4().hex[:6]}", email=f"wc_{uuid.uuid4().hex[:6]}@x.com",
             hashed_password="x", name="wc", is_active=True, is_approved=True)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _med_protocol(db, user_id):
    med = Medication(user_id=user_id, name="瑞舒伐他汀", dosage="10mg")
    db.add(med)
    db.commit()
    db.refresh(med)
    return med, proto_svc.create_protocol_for_medication(db, user_id, med.id)


def _supp_protocol(db, user_id):
    sd = SupplementDefinition(user_id=user_id, name="维生素D3", dosage="5000IU",
                              timing="morning", is_active=True)
    db.add(sd)
    db.commit()
    db.refresh(sd)
    p = proto_svc.create_protocol(db, user_id, {
        "domain": "supplement", "name": "维生素D3 补剂", "mechanism": "fixed_container",
        "cadence": "daily", "can_default_complete": False,
        "source_model": "supplement_records", "source_id": sd.id,
    })
    return sd, p


# ── D1.a 唯一约束本身 ────────────────────────────────────────────────
def test_unique_constraint_blocks_duplicate_protocol_date(db):
    """同 (protocol_id, event_date) 第二条终态事件 → IntegrityError(模型级唯一约束)。

    create_all 由模型声明带上 uq_hpe_protocol_date,测试库自动有;迁移 SQL 给生产。
    """
    user = _mk_user(db)
    _, p = _med_protocol(db, user.id)
    today = date.today()
    db.add(HealthProtocolEvent(user_id=user.id, protocol_id=p.id,
                               event_date=today, status="completed", track="protocol"))
    db.commit()
    db.add(HealthProtocolEvent(user_id=user.id, protocol_id=p.id,
                               event_date=today, status="completed", track="protocol"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


# ── D1.b 原子门控:预置 completed event → 不写第二条领域记录 ──────────
def test_pre_completed_event_does_not_write_second_med_log(db):
    """预置一条 status=completed 的 event,再 complete_protocol → 不落第二条 MedicationLog。

    钉原子 UPDATE 门:`WHERE status != 'completed'` rowcount==0(已是 completed)→ 跳过领域写。
    旧实现(was_completed = ev.status=='completed')在串行下也成立,但并发下两 session
    都读 False。这里以「门控逻辑」覆盖该不变量(SQLite 单连接限制见模块 docstring)。
    """
    user = _mk_user(db)
    med, p = _med_protocol(db, user.id)
    today = date.today()
    # 预置已完成事件(模拟另一个并发请求已抢到状态转移并落了记录)
    db.add(HealthProtocolEvent(user_id=user.id, protocol_id=p.id,
                               event_date=today, status="completed", track="protocol"))
    db.add(MedicationLog(user_id=user.id, medication_id=med.id, taken_date=today,
                         taken_time="08:00", status="taken", notes="via protocol"))
    db.commit()

    proto_svc.complete_protocol(db, p.id, user.id, track="protocol")

    logs = db.query(MedicationLog).filter(MedicationLog.user_id == user.id).all()
    assert len(logs) == 1, f"门控失效:已 completed 还重复写,落了 {len(logs)} 条"


def test_pre_completed_event_does_not_write_second_supplement(db):
    """补剂分支同样门控:预置 completed → 不落第二条 SupplementRecord。"""
    user = _mk_user(db)
    sd, p = _supp_protocol(db, user.id)
    today = date.today()
    db.add(HealthProtocolEvent(user_id=user.id, protocol_id=p.id,
                               event_date=today, status="completed", track="protocol"))
    db.add(SupplementRecord(user_id=user.id, supplement_id=sd.id, record_date=today,
                            taken=True, notes="via protocol"))
    db.commit()

    proto_svc.complete_protocol(db, p.id, user.id, track="protocol")

    recs = db.query(SupplementRecord).filter(SupplementRecord.user_id == user.id).all()
    assert len(recs) == 1, "补剂门控失效:已 completed 还重复写"


def test_complete_protocol_first_call_writes_and_flips_status(db):
    """门控不误伤正常首次完成:pending → completed + 落 1 条记录(回归基线)。"""
    user = _mk_user(db)
    med, p = _med_protocol(db, user.id)
    ev = proto_svc.complete_protocol(db, p.id, user.id, track="protocol")
    assert ev is not None and ev.status == "completed"
    logs = db.query(MedicationLog).filter(MedicationLog.user_id == user.id).all()
    assert len(logs) == 1


def test_complete_protocol_skipped_then_completed_writes_once(db):
    """先 skip(非完成终态)再 complete → 翻成 completed 且落 1 条(不被门控误跳)。"""
    user = _mk_user(db)
    med, p = _med_protocol(db, user.id)
    proto_svc.skip_protocol(db, p.id, user.id, reason="forgot")
    ev = proto_svc.complete_protocol(db, p.id, user.id, track="protocol")
    assert ev.status == "completed"
    logs = db.query(MedicationLog).filter(MedicationLog.user_id == user.id).all()
    assert len(logs) == 1, "skip→complete 应落恰好 1 条"


# ── S2.1 log_medication commit 形参不破坏既有调用方 ──────────────────
def test_log_medication_default_commits(db):
    """默认 commit=True:既有调用方行为不变(立即可在新 session 读到)。"""
    from app.services.medication_service import medication_service
    user = _mk_user(db)
    med = Medication(user_id=user.id, name="二甲双胍", dosage="500mg")
    db.add(med)
    db.commit()
    db.refresh(med)
    log = medication_service.log_medication(
        db, user_id=user.id, medication_id=med.id, taken_time="09:00", status="taken")
    assert log.id is not None
    # 默认提交:rollback 不应抹掉它
    db.rollback()
    assert db.query(MedicationLog).filter(MedicationLog.id == log.id).first() is not None


def test_log_medication_no_commit_only_flushes(db):
    """commit=False:只 flush 拿到 id,提交权交还调用方(协议路径用)。rollback 抹掉。"""
    from app.services.medication_service import medication_service
    user = _mk_user(db)
    med = Medication(user_id=user.id, name="二甲双胍", dosage="500mg")
    db.add(med)
    db.commit()
    db.refresh(med)
    log = medication_service.log_medication(
        db, user_id=user.id, medication_id=med.id, taken_time="09:00",
        status="taken", commit=False)
    assert log.id is not None, "flush 后应有 id"
    db.rollback()
    assert db.query(MedicationLog).filter(MedicationLog.id == log.id).first() is None, \
        "commit=False 时未提交,rollback 应抹掉"


# ── S2.2 旁路审计:腕上一键完成用药/补剂落一条 audit ────────────────
def test_watch_complete_writes_audit_for_medication(db):
    """完成用药协议 → 落一条 watch_complete audit,含 protocol_id + linked_record_id。"""
    from app.models.agent_audit_log import AgentAuditLog
    user = _mk_user(db)
    med, p = _med_protocol(db, user.id)
    proto_svc.complete_protocol(db, p.id, user.id, track="protocol")
    rows = db.query(AgentAuditLog).filter(
        AgentAuditLog.user_id == user.id,
        AgentAuditLog.action == "watch_complete",
    ).all()
    assert len(rows) == 1, "腕上完成依从应留一条审计(取证 + 可追溯)"
    detail = rows[0].result_detail or {}
    assert detail.get("protocol_id") == p.id
    assert detail.get("linked_record_id") is not None
    assert detail.get("source_model") == "medication_logs"


def test_watch_complete_writes_audit_for_supplement(db):
    from app.models.agent_audit_log import AgentAuditLog
    user = _mk_user(db)
    sd, p = _supp_protocol(db, user.id)
    proto_svc.complete_protocol(db, p.id, user.id, track="protocol")
    rows = db.query(AgentAuditLog).filter(
        AgentAuditLog.user_id == user.id,
        AgentAuditLog.action == "watch_complete",
    ).all()
    assert len(rows) == 1
    assert (rows[0].result_detail or {}).get("source_model") == "supplement_records"


def test_audit_not_written_when_no_domain_record(db):
    """无 source_model(协议自身即记录)→ 无领域记录 → 不落 watch_complete 审计。"""
    from app.models.agent_audit_log import AgentAuditLog
    user = _mk_user(db)
    p = proto_svc.create_protocol(db, user.id, {
        "domain": "mood", "name": "情绪打卡", "cadence": "daily",
        "can_default_complete": False,
    })  # 无 source_model
    proto_svc.complete_protocol(db, p.id, user.id, track="protocol")
    rows = db.query(AgentAuditLog).filter(
        AgentAuditLog.user_id == user.id,
        AgentAuditLog.action == "watch_complete",
    ).all()
    assert rows == [], "无领域记录不该留 watch_complete 审计"


def test_domain_write_failure_rolls_back_status(db, monkeypatch):
    """R12 不假装完成:领域写在原子 UPDATE 置 completed 之后炸 → 整事务回滚,
    event 不能停在 completed-无记录 的半成品态。
    """
    import app.services.health_protocol_service as svc
    user = _mk_user(db)
    sd, p = _supp_protocol(db, user.id)

    def _boom(*a, **k):
        raise RuntimeError("domain write boom")

    monkeypatch.setattr(svc, "_write_domain_record", _boom)
    with pytest.raises(RuntimeError):
        svc.complete_protocol(db, p.id, user.id, track="protocol")
    db.rollback()
    # 没有 completed event 残留,也没有补剂记录
    evs = db.query(HealthProtocolEvent).filter(
        HealthProtocolEvent.protocol_id == p.id,
        HealthProtocolEvent.status == "completed").all()
    assert evs == [], "领域写失败却把 event 留成 completed = 假装完成(R12 违背)"
    recs = db.query(SupplementRecord).filter(SupplementRecord.user_id == user.id).all()
    assert recs == []


def test_audit_failure_does_not_break_completion(db, monkeypatch):
    """审计是旁路:写 audit 抛错也不能影响主流程(完成仍成功 + 领域记录已落)。"""
    import app.agents.audit as audit_mod
    user = _mk_user(db)
    med, p = _med_protocol(db, user.id)

    def _boom(*a, **k):
        raise RuntimeError("audit boom")

    monkeypatch.setattr(audit_mod, "log_watch_complete", _boom)
    ev = proto_svc.complete_protocol(db, p.id, user.id, track="protocol")
    assert ev is not None and ev.status == "completed"
    logs = db.query(MedicationLog).filter(MedicationLog.user_id == user.id).all()
    assert len(logs) == 1, "审计失败不该回滚领域记录"
