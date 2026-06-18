"""Write 层 v0 服务测试 —— 写意图账本(propose/confirm/dismiss/生成器/IDOR/fail-loud)。"""
import uuid
from datetime import date, timedelta

import pytest

from app.models.blood_pressure import BloodPressureRecord
from app.models.health_problem import HealthProblem
from app.models.intervention_cycle import InterventionCycle
from app.models.smart_reminder import SmartReminder
from app.models.user import User
from app.models.weight import WeightRecord
from app.models.write_intent import WriteIntent
from app.services import write_intent_service as svc


def _active_cycle(db, user_id):
    c = InterventionCycle(user_id=user_id, cycle_type="metabolic_90d", status="active", start_date=date.today())
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


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


# ─────────────────── measurement_prompt syscall (Phase 1) ───────────────────

def test_measurement_prompt_needs_active_cycle(db):
    u = _mk_user(db)
    assert svc.generate_measurement_prompts(db, u.id) == 0  # 无周期不提
    _active_cycle(db, u.id)
    assert svc.generate_measurement_prompts(db, u.id) == 2  # bp + 体重 各一
    kinds = [it["kind"] for it in svc.list_pending(db, u.id)]
    assert kinds.count("measurement_prompt") == 2


def test_measurement_prompt_skips_metric_measured_today(db):
    u = _mk_user(db)
    _active_cycle(db, u.id)
    from app.utils.timezone import get_china_today
    db.add(BloodPressureRecord(user_id=u.id, record_date=get_china_today(), systolic=120, diastolic=80))
    db.commit()
    svc.generate_measurement_prompts(db, u.id)
    titles = [it["title"] for it in svc.list_pending(db, u.id) if it["kind"] == "measurement_prompt"]
    assert any("体重" in t for t in titles)        # 体重今天没测 → 提
    assert not any("血压" in t for t in titles)     # 血压今天已测 → 不提


def test_measurement_prompt_no_same_day_renag(db):
    u = _mk_user(db)
    _active_cycle(db, u.id)
    assert svc.generate_measurement_prompts(db, u.id) == 2
    # 用户全部忽略 → 同日再跑不重复 nag
    for it in svc.list_pending(db, u.id):
        if it["kind"] == "measurement_prompt":
            svc.dismiss(db, u.id, it["id"])
    assert svc.generate_measurement_prompts(db, u.id) == 0


def test_confirm_measurement_prompt_creates_reminder(db):
    u = _mk_user(db)
    wi = svc.propose(db, u.id, kind="measurement_prompt", title="今天还没测血压",
                     description="现在测一下血压", source="measurement_gap",
                     target_type="measurement_bp", target_id=None, payload={"metric": "bp"})
    res = svc.confirm(db, u.id, wi.id)
    assert res["status"] == "executed"
    assert res["executed_ref"].startswith("smart_reminder:")
    rems = db.query(SmartReminder).filter(SmartReminder.user_id == u.id).all()
    assert len(rems) == 1 and "血压" in (rems[0].title or "")


# ─────────────────── recheck_due syscall (Phase 1) ───────────────────

def _cycle_ending(db, user_id, *, days_from_today, rechecked=False):
    from app.utils.timezone import get_china_today
    end = get_china_today() + timedelta(days=days_from_today)
    c = InterventionCycle(
        user_id=user_id, cycle_type="metabolic_90d", status="active",
        start_date=end - timedelta(days=90), planned_end_date=end,
    )
    if rechecked:
        c.latest_snapshot_id = 1
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def test_recheck_due_proposed_within_window(db):
    u = _mk_user(db)
    _cycle_ending(db, u.id, days_from_today=3)  # 3 天后到复查日
    assert svc.generate_recheck_due(db, u.id) == 1
    items = [it for it in svc.list_pending(db, u.id) if it["kind"] == "recheck_due"]
    assert len(items) == 1 and items[0]["title"] == "该复查了"


def test_recheck_due_not_proposed_when_far(db):
    u = _mk_user(db)
    _cycle_ending(db, u.id, days_from_today=30)  # 还早
    assert svc.generate_recheck_due(db, u.id) == 0


def test_recheck_due_skipped_when_already_rechecked(db):
    u = _mk_user(db)
    _cycle_ending(db, u.id, days_from_today=2, rechecked=True)  # 已复查 → 不再催首次
    assert svc.generate_recheck_due(db, u.id) == 0


def test_recheck_due_overdue_wording(db):
    u = _mk_user(db)
    _cycle_ending(db, u.id, days_from_today=-2)  # 逾期 2 天
    assert svc.generate_recheck_due(db, u.id) == 1
    it = [x for x in svc.list_pending(db, u.id) if x["kind"] == "recheck_due"][0]
    assert it["title"] == "复查已逾期"


def test_recheck_due_no_same_day_renag(db):
    u = _mk_user(db)
    _cycle_ending(db, u.id, days_from_today=1)
    assert svc.generate_recheck_due(db, u.id) == 1
    for it in svc.list_pending(db, u.id):
        if it["kind"] == "recheck_due":
            svc.dismiss(db, u.id, it["id"])
    assert svc.generate_recheck_due(db, u.id) == 0  # 同日忽略后不重复


def test_confirm_recheck_due_creates_reminder(db):
    u = _mk_user(db)
    c = _cycle_ending(db, u.id, days_from_today=0)
    svc.generate_recheck_due(db, u.id)
    wi_id = [x for x in svc.list_pending(db, u.id) if x["kind"] == "recheck_due"][0]["id"]
    res = svc.confirm(db, u.id, wi_id)
    assert res["status"] == "executed" and res["executed_ref"].startswith("smart_reminder:")
    assert db.query(SmartReminder).filter(SmartReminder.user_id == u.id).count() == 1


# ─────────────────── adherence_nudge syscall (Phase 1) ───────────────────

def _mk_med(db, user_id, name="二甲双胍"):
    from app.models.medication import Medication
    m = Medication(user_id=user_id, name=name, times_per_day=1, is_active=True)
    db.add(m); db.commit(); db.refresh(m)
    return m


def _mk_supp(db, user_id, name="鱼油"):
    from app.models.supplement import SupplementDefinition
    s = SupplementDefinition(user_id=user_id, name=name, is_active=True)
    db.add(s); db.commit(); db.refresh(s)
    return s


def test_adherence_nudge_proposes_med_and_supplement(db):
    u = _mk_user(db)
    _mk_med(db, u.id)
    _mk_supp(db, u.id)
    assert svc.generate_adherence_nudge(db, u.id) == 2
    titles = [it["title"] for it in svc.list_pending(db, u.id) if it["kind"] == "adherence_nudge"]
    assert any("二甲双胍" in t for t in titles) and any("鱼油" in t for t in titles)


def test_adherence_nudge_skips_already_taken(db):
    from app.models.medication import MedicationLog
    from app.models.supplement import SupplementRecord
    u = _mk_user(db)
    m = _mk_med(db, u.id)
    s = _mk_supp(db, u.id)
    db.add(MedicationLog(user_id=u.id, medication_id=m.id, taken_date=date.today(), status="taken"))
    db.add(SupplementRecord(user_id=u.id, supplement_id=s.id, record_date=date.today(), taken=True))
    db.commit()
    assert svc.generate_adherence_nudge(db, u.id) == 0  # 都已记录 → 不提


def test_confirm_adherence_nudge_writes_med_log(db):
    from app.models.medication import MedicationLog
    u = _mk_user(db)
    m = _mk_med(db, u.id)
    svc.generate_adherence_nudge(db, u.id)
    wi_id = [it for it in svc.list_pending(db, u.id) if it["kind"] == "adherence_nudge"][0]["id"]
    res = svc.confirm(db, u.id, wi_id)
    assert res["status"] == "executed" and res["executed_ref"].startswith("medication_log:")
    logs = db.query(MedicationLog).filter(
        MedicationLog.user_id == u.id, MedicationLog.medication_id == m.id,
        MedicationLog.taken_date == date.today(),
    ).all()
    assert len(logs) == 1 and logs[0].status == "taken"
    # 确认后已服 → 同日不再提
    assert svc.generate_adherence_nudge(db, u.id) == 0


def test_confirm_adherence_nudge_writes_supplement_record(db):
    from app.models.supplement import SupplementRecord
    u = _mk_user(db)
    s = _mk_supp(db, u.id)
    svc.generate_adherence_nudge(db, u.id)
    wi_id = [it for it in svc.list_pending(db, u.id) if it["kind"] == "adherence_nudge"][0]["id"]
    res = svc.confirm(db, u.id, wi_id)
    assert res["status"] == "executed" and res["executed_ref"].startswith("supplement_record:")
    rec = db.query(SupplementRecord).filter(
        SupplementRecord.user_id == u.id, SupplementRecord.supplement_id == s.id,
        SupplementRecord.record_date == date.today(),
    ).first()
    assert rec is not None and rec.taken is True


def test_adherence_nudge_no_same_day_renag(db):
    u = _mk_user(db)
    _mk_med(db, u.id)
    assert svc.generate_adherence_nudge(db, u.id) == 1
    for it in svc.list_pending(db, u.id):
        if it["kind"] == "adherence_nudge":
            svc.dismiss(db, u.id, it["id"])
    assert svc.generate_adherence_nudge(db, u.id) == 0  # 同日忽略后不重复


def test_adherence_nudge_idempotent_when_already_logged(db):
    """竞态:propose 后用户经别的路径(腕上一键/quick record)已按日标记,再 confirm 这条 intent
    → 执行幂等返回既有行,绝不落第二条虚高依从(DB uq + _execute reread 双保险)。"""
    from app.models.medication import MedicationLog
    u = _mk_user(db)
    m = _mk_med(db, u.id)
    wi = svc.propose(
        db, u.id, kind="adherence_nudge", title=f"今天还没记录:{m.name}",
        description="如果已经服用了,点确认记一笔(标记已服);没服就忽略。", source="adherence_gap",
        target_type="medication", target_id=m.id, payload={"item_type": "medication", "name": m.name},
    )
    # 另一路径先落了今天的按日标记(NULL 槽)
    db.add(MedicationLog(user_id=u.id, medication_id=m.id, taken_date=date.today(), taken_time=None, status="taken"))
    db.commit()

    res = svc.confirm(db, u.id, wi.id)
    assert res["status"] == "executed" and res["executed_ref"].startswith("medication_log:")
    logs = db.query(MedicationLog).filter(
        MedicationLog.user_id == u.id, MedicationLog.medication_id == m.id,
        MedicationLog.taken_date == date.today(), MedicationLog.taken_time.is_(None),
    ).all()
    assert len(logs) == 1  # 仍只 1 条,没有虚高
