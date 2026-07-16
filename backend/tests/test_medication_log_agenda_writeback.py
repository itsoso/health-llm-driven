"""POST /medication/logs 反向完成链:用药打卡 → 翻时间线对应 HealthEvent(agenda_status)。

此前 `POST /medication/logs`(用药卡「已服」/ 用药页 / 手表都走这)只写 MedicationLog,
不完成时间线上对应的 HealthEvent → 待办计数 / 复盘完成率 / 手表 due 项账本分叉。

本闸钉死:
① 已服 → MedicationLog 恰 1 行 + HealthEvent agenda_status=done(环形被 skip_writeback 兜住,
   不落第二条依从行)。
② 补剂 category → 反向完成的 ref object_type='supplement'(而非 'medication')。
③ 多剂(reminder_times ≥2):taken_time=12:30 → 完成 12:30 剂次槽的事件,08:00 槽不动。
④ 完成链抛异常 → log 仍写入 + 响应 200 + warning 落日志(依从事实不因账本失败而 500)。
⑤ 当天无对应时间线事件(未物化/未排程)→ log 写入正常,懒物化后完成,无异常。

环形终止:complete_by_ref(skip_writeback=True) 只做原子 claim + 生命周期翻态,不经
complete_item 二次回写领域行 —— 同一「已服」永远只落一条 MedicationLog。
"""
from datetime import date, timedelta

from app.models.health_event import HealthEvent
from app.models.medication import Medication, MedicationLog
from app.models.user import User
from app.services import timeline_agenda_service as tas
from app.utils.timezone import get_china_today


def _seed_med(
    db, user_id: int, *, name: str = "雷贝拉唑", category: str = "处方药",
    reminder_times=None,
) -> Medication:
    med = Medication(
        user_id=user_id, name=name, category=category, is_active=True,
        reminder_times=reminder_times,
    )
    db.add(med)
    db.commit()
    db.refresh(med)
    return med


def _taken_logs(db, user_id: int, med_id: int):
    return (
        db.query(MedicationLog)
        .filter(
            MedicationLog.user_id == user_id,
            MedicationLog.medication_id == med_id,
            MedicationLog.taken_date == get_china_today(),
            MedicationLog.status == "taken",
        )
        .all()
    )


def _agenda_events(db, user_id: int, med_id: int, object_type: str):
    """该 med 的议程 HealthEvent(按 complete_ref.object_type + object_id 过滤)。"""
    rows = (
        db.query(HealthEvent)
        .filter(
            HealthEvent.user_id == user_id,
            HealthEvent.event_type == tas.AGENDA_EVENT_TYPE,
        )
        .all()
    )
    out = []
    for ev in rows:
        ref = ev.complete_ref or {}
        if ref.get("object_type") == object_type and ref.get("object_id") == med_id:
            out.append(ev)
    return out


# ─────────────────────────── ① 已服 → 恰 1 log + HealthEvent done ───────────────────────────

def test_log_taken_flips_agenda_event_done_single_log(client, db, auth_user_and_headers):
    """已服打卡 → MedicationLog 恰 1 行 + HealthEvent agenda_status=done(环形被幂等兜住)。"""
    user, h = auth_user_and_headers
    med = _seed_med(db, user.id)

    r = client.post("/api/v1/medication/logs", headers=h, json={
        "medication_id": med.id, "taken_time": "09:00", "status": "taken"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "taken"

    # 环形终止:依从事实恰一条,不因反向完成链二次写而虚高(否则污染 DDI/PGx/SafetyGuardian)。
    logs = _taken_logs(db, user.id, med.id)
    assert len(logs) == 1, "已服打卡只应落一条 taken MedicationLog"

    # 时间线账本翻 done。
    evs = _agenda_events(db, user.id, med.id, "medication")
    assert len(evs) == 1
    assert evs[0].agenda_status == "done", "打卡后对应 HealthEvent 必须翻 done"


# ─────────────────────────── ② 补剂 category → object_type='supplement' ───────────────────────────

def test_log_supplement_uses_supplement_object_type(client, db, auth_user_and_headers):
    """补剂反向完成的 ref object_type='supplement',不是 'medication'。

    category 权威映射走 timing_adapter._domain(与脊柱/day_schedule 同源),规范补剂 category
    是 'supplement'(见 test_day_schedule_service / test_timeline_spine_medications)——用同一
    映射保证本 ref 与脊柱物化的 HealthEvent ref 一致,懒物化去重才命中同一条。
    """
    user, h = auth_user_and_headers
    supp = _seed_med(db, user.id, name="维生素D3", category="supplement")

    r = client.post("/api/v1/medication/logs", headers=h, json={
        "medication_id": supp.id, "taken_time": "09:00", "status": "taken"})
    assert r.status_code == 200, r.text

    assert len(_taken_logs(db, user.id, supp.id)) == 1
    # ref object_type 必须是 supplement(env: category 权威映射 timing_adapter._domain)。
    supp_evs = _agenda_events(db, user.id, supp.id, "supplement")
    med_evs = _agenda_events(db, user.id, supp.id, "medication")
    assert len(supp_evs) == 1 and supp_evs[0].agenda_status == "done"
    assert med_evs == [], "补剂不应产生 object_type='medication' 的议程事件"


# ─────────────────────────── ③ 多剂:taken_time 定位对应剂次槽 ───────────────────────────

def test_multidose_completes_matching_slot_only(client, db, auth_user_and_headers):
    """多剂(08:00/12:30)药 taken_time=12:30 → 只完成 12:30 剂次槽,08:00 槽不受影响。"""
    user, h = auth_user_and_headers
    med = _seed_med(db, user.id, name="二甲双胍", reminder_times=["08:00", "12:30", "18:30"])

    r = client.post("/api/v1/medication/logs", headers=h, json={
        "medication_id": med.id, "taken_time": "12:30", "status": "taken"})
    assert r.status_code == 200, r.text
    assert len(_taken_logs(db, user.id, med.id)) == 1

    evs = _agenda_events(db, user.id, med.id, "medication")
    # 只产生 12:30 那一槽的议程事件,且翻 done。
    assert len(evs) == 1
    ev = evs[0]
    assert (ev.complete_ref or {}).get("slot") == "12:30", "必须完成 taken_time 对应的剂次槽"
    assert ev.agenda_status == "done"
    # 08:00 / 18:30 槽没有被物化/完成(未打卡的剂次不受影响)。
    slots_present = {(e.complete_ref or {}).get("slot") for e in evs}
    assert "08:00" not in slots_present and "18:30" not in slots_present


def test_multidose_unmatched_taken_time_falls_back_earliest_slot(client, db, auth_user_and_headers):
    """多剂药 taken_time 不命中任一排程剂次 → 回退最早排程槽(reminder_times[0])。"""
    user, h = auth_user_and_headers
    med = _seed_med(db, user.id, name="二甲双胍", reminder_times=["08:00", "20:00"])

    # taken_time=13:07 不在 {08:00,20:00} → 回退最早槽 08:00。
    r = client.post("/api/v1/medication/logs", headers=h, json={
        "medication_id": med.id, "taken_time": "13:07", "status": "taken"})
    assert r.status_code == 200, r.text

    evs = _agenda_events(db, user.id, med.id, "medication")
    assert len(evs) == 1
    assert (evs[0].complete_ref or {}).get("slot") == "08:00"
    assert evs[0].agenda_status == "done"


# ─────────────────────────── ④ 完成链抛异常 → log 仍写 + 200 + warning ───────────────────────────

def test_writeback_failure_does_not_break_log(client, db, auth_user_and_headers, monkeypatch, caplog):
    """反向完成链抛异常 → MedicationLog 仍写入 + 响应 200 + warning 落日志(不 500、不回滚 log)。"""
    import logging

    user, h = auth_user_and_headers
    med = _seed_med(db, user.id)

    # 桩掉 complete_by_ref 让其炸,模拟完成链失败(依从事实必须已落库、响应仍 200)。
    def _boom(*a, **k):
        raise RuntimeError("boom in agenda writeback")

    monkeypatch.setattr(tas, "complete_by_ref", _boom)

    with caplog.at_level(logging.WARNING):
        r = client.post("/api/v1/medication/logs", headers=h, json={
            "medication_id": med.id, "taken_time": "09:00", "status": "taken"})

    assert r.status_code == 200, r.text
    # log 是依从事实,完成链失败绝不拖垮打卡。
    assert len(_taken_logs(db, user.id, med.id)) == 1
    # fail-loud:warning 可查(不静默吞成 debug)。
    assert any(
        "agenda writeback failed" in rec.message for rec in caplog.records
    ), "完成链失败必须落 warning 日志(fail-loud 可查)"


# ─────────────────────────── ⑤ 无对应时间线事件 → 懒物化后完成,无异常 ───────────────────────────

def test_log_taken_no_preexisting_event_lazy_materializes(client, db, auth_user_and_headers):
    """当天无对应时间线事件(未排程/未物化)→ 打卡照常 200,懒物化后完成,不报错。"""
    user, h = auth_user_and_headers
    med = _seed_med(db, user.id)

    # 事前无任何该 med 的议程 HealthEvent。
    assert _agenda_events(db, user.id, med.id, "medication") == []

    r = client.post("/api/v1/medication/logs", headers=h, json={
        "medication_id": med.id, "taken_time": "09:00", "status": "taken"})
    assert r.status_code == 200, r.text

    assert len(_taken_logs(db, user.id, med.id)) == 1
    # complete_by_ref 懒物化出一条并翻 done。
    evs = _agenda_events(db, user.id, med.id, "medication")
    assert len(evs) == 1 and evs[0].agenda_status == "done"


# ────────────── ⑤b 生产路径:脊柱已物化的事件 → 复用翻 done,不建重复账本行 ──────────────

def test_log_taken_reuses_preexisting_spine_event(client, db, auth_user_and_headers):
    """真实首页路径:脊柱已物化一条 pending HealthEvent → 打卡复用它翻 done,不建第二条。"""
    from datetime import datetime

    from app.services import timeline_agenda_service as tas

    user, h = auth_user_and_headers
    med = _seed_med(db, user.id)

    # 模拟脊柱查看时已懒物化出的 pending 议程事件(单剂,无 slot)。
    ref = {"object_type": "medication", "object_id": med.id}
    tas.materialize_agenda_event(
        db, user.id, action_kind="medication", title=med.name,
        complete_ref=ref,
        scheduled_for=datetime.combine(get_china_today(), datetime.min.time()),
    )
    assert len(_agenda_events(db, user.id, med.id, "medication")) == 1

    r = client.post("/api/v1/medication/logs", headers=h, json={
        "medication_id": med.id, "taken_time": "09:00", "status": "taken"})
    assert r.status_code == 200, r.text

    evs = _agenda_events(db, user.id, med.id, "medication")
    assert len(evs) == 1, "打卡复用已存在的脊柱事件,不建重复账本行"
    assert evs[0].agenda_status == "done"
    assert len(_taken_logs(db, user.id, med.id)) == 1


# ─────────────────────────── ⑥ 幂等:重复打卡不虚高、不重复账本行 ───────────────────────────

def test_repeated_log_same_slot_stays_single_log_and_event(client, db, auth_user_and_headers):
    """同一剂重复打卡(同槽)→ 仍恰 1 条 taken + 1 条 HealthEvent(done),不虚高依从。"""
    user, h = auth_user_and_headers
    med = _seed_med(db, user.id)

    payload = {"medication_id": med.id, "taken_time": "09:00", "status": "taken"}
    r1 = client.post("/api/v1/medication/logs", headers=h, json=payload)
    r2 = client.post("/api/v1/medication/logs", headers=h, json=payload)
    assert r1.status_code == 200 and r2.status_code == 200, r2.text

    # log 层 uq_medlog 兜底同槽去重;完成链幂等(HealthEvent 终态短路)。
    assert len(_taken_logs(db, user.id, med.id)) == 1
    evs = _agenda_events(db, user.id, med.id, "medication")
    assert len(evs) == 1 and evs[0].agenda_status == "done"


def test_explicit_occurrence_date_is_persisted_without_completing_today_agenda(
    client, db, auth_user_and_headers,
):
    """跨午夜点击旧提醒:写到提醒发生日,不得误完成今天的议程。"""
    user, h = auth_user_and_headers
    med = _seed_med(db, user.id)
    occurrence_date = get_china_today() - timedelta(days=1)

    r = client.post("/api/v1/medication/logs", headers=h, json={
        "medication_id": med.id,
        "taken_date": occurrence_date.isoformat(),
        "taken_time": "23:59",
        "status": "taken",
    })

    assert r.status_code == 200, r.text
    assert r.json()["taken_date"] == occurrence_date.isoformat()
    row = db.query(MedicationLog).filter(
        MedicationLog.user_id == user.id,
        MedicationLog.medication_id == med.id,
        MedicationLog.taken_date == occurrence_date,
        MedicationLog.taken_time == "23:59",
    ).one()
    assert row.status == "taken"
    assert _agenda_events(db, user.id, med.id, "medication") == []


def test_log_rejects_medication_owned_by_another_user(client, db, auth_user_and_headers):
    """客户端 payload 里的 medication_id 必须再次按认证用户隔离。"""
    user, h = auth_user_and_headers
    other = User(
        username="watch_med_other",
        email="watch_med_other@example.com",
        hashed_password="x",
        name="watch_med_other",
        is_active=True,
        is_approved=True,
    )
    db.add(other)
    db.commit()
    foreign_med = _seed_med(db, other.id, name="foreign medication")

    r = client.post("/api/v1/medication/logs", headers=h, json={
        "medication_id": foreign_med.id,
        "taken_date": get_china_today().isoformat(),
        "taken_time": "08:30",
        "status": "taken",
    })

    assert r.status_code == 404
    assert db.query(MedicationLog).filter(
        MedicationLog.user_id == user.id,
        MedicationLog.medication_id == foreign_med.id,
    ).count() == 0
