"""F5b — BID / 多剂闭环(complete_ref 剂量槽 slot)。

钉死:真多剂(reminder_times ≥2 个确定时点)的药,两剂各成独立脊柱行 / 各自闭环依从,
不被同日去重折成一次(F5b 前 under-count)。守 council 不变量:同槽再点幂等(至多一条
MedicationLog),确定性 taken_time 用 slot(非 wall-clock)。

覆盖(任务强制):
1. BID 两剂:reminder_times ["08:00","20:00"] → /timeline/today 两条 distinct slot 行 →
   两剂都完成 → 恰两条 MedicationLog(distinct taken_time)、两条都 done。
2. 同槽幂等:同一 slot 完成两次 → 一条 MedicationLog,第二次 idempotent(council 护栏)。
3. 每日一次回归:单时点(无 slot)→ 一行 / 一条 / 幂等,响应 dict 与改前一致(byte-identical)。
4. 跨剂隔离:完成 08:00 不会把 20:00 标 done。

单一核(complete_by_ref → complete_agenda_event),不 fork 完成路径。slot 走 JSON complete_ref,
无迁移。
"""
from datetime import date, datetime, timezone

from app.models.medication import Medication, MedicationLog
from app.utils.timezone import get_china_today


def _pin_morning_clock(monkeypatch):
    """钉脊柱时钟到清晨(上海 05:30)→ 08:00/20:00 时点都还没过 2h 宽限窗,status 恒 pending。

    此文件验「BID 两剂各成独立行 / 各自闭环」,与当下时刻无关;不钉时钟则墙钟到上午 10 点后
    08:00 槽会被 past-due 下沉逻辑(today_timeline_service._mark_overdue)翻 overdue,断言
    status=='pending' 随机红(CI UTC runner + TZ=Asia/Shanghai)。含时点断言必须钉死时钟。
    """
    import app.services.today_timeline_service as svc

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            base = datetime(2026, 6, 15, 21, 30, tzinfo=timezone.utc)  # = 次日 05:30 上海
            return base.astimezone(tz) if tz else base.replace(tzinfo=None)

    monkeypatch.setattr(svc, "datetime", FixedDateTime)


def _seed_bid(db, user_id: int, name: str = "二甲双胍",
              reminder_times=None, category: str = "处方药") -> Medication:
    """真多剂药:reminder_times 给 ≥2 个确定时点。"""
    if reminder_times is None:
        reminder_times = ["08:00", "20:00"]
    med = Medication(
        user_id=user_id, name=name, category=category,
        times_per_day=len(reminder_times), reminder_times=reminder_times,
        is_active=True, start_date=date.today(),
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
        .order_by(MedicationLog.taken_time.asc())
        .all()
    )


# ───────────────────── 1. BID 两剂:两行 distinct slot → 两条 log ─────────────────────

def test_bid_two_slots_two_spine_items_two_logs(db, auth_user_and_headers, monkeypatch):
    """reminder_times ["08:00","20:00"] → 脊柱两条 distinct slot 行 → 两剂各完成 →
    恰两条 MedicationLog(distinct taken_time),两条都 done(F5b 核心:依从不被折成一次)。"""
    from app.services.today_timeline_service import build_today_spine
    from app.services import timeline_agenda_service as tas

    _pin_morning_clock(monkeypatch)  # 钉清晨:两槽都未过期,验 pending / 两行独立完成
    user, _ = auth_user_and_headers
    med = _seed_bid(db, user.id, reminder_times=["08:00", "20:00"])

    spine = build_today_spine(db, user.id)
    bid_items = [
        it for it in spine["items"]
        if (it.get("complete_ref") or {}).get("object_type") == "medication"
        and (it.get("complete_ref") or {}).get("object_id") == med.id
    ]
    # 两条独立脊柱行,各带不同 slot。
    assert len(bid_items) == 2, f"BID 应出两条脊柱行,实得 {len(bid_items)}"
    slots = sorted((it["complete_ref"].get("slot")) for it in bid_items)
    assert slots == ["08:00", "20:00"], f"两行应各带 distinct slot,实得 {slots}"
    # 两行各自可完成、未服。
    assert all(it["status"] == "pending" and it["can_complete"] for it in bid_items)

    # 完成两剂(各带其 slot)。
    r1 = tas.complete_by_ref(db, user.id, "medication", med.id, slot="08:00")
    db.commit()
    r2 = tas.complete_by_ref(db, user.id, "medication", med.id, slot="20:00")
    db.commit()
    assert r1["agenda_status"] == "done" and r1["idempotent"] is False
    assert r2["agenda_status"] == "done" and r2["idempotent"] is False
    # 两条独立议程 HealthEvent(distinct event_id)。
    assert r1["event_id"] != r2["event_id"], "两剂应物化两条独立议程 HealthEvent"

    # 恰两条 taken MedicationLog,taken_time 分别落两个确定性槽。
    logs = _taken_logs(db, user.id, med.id)
    assert len(logs) == 2, f"BID 两剂应恰两条 taken log,实得 {len(logs)}"
    assert [l.taken_time for l in logs] == ["08:00", "20:00"], (
        f"taken_time 应为确定性 slot 槽(非 wall-clock),实得 {[l.taken_time for l in logs]}")

    # 再读脊柱:两行都熄灭(completed、不可再完成)。
    spine2 = build_today_spine(db, user.id)
    bid2 = [
        it for it in spine2["items"]
        if (it.get("complete_ref") or {}).get("object_id") == med.id
        and (it.get("complete_ref") or {}).get("object_type") == "medication"
    ]
    assert len(bid2) == 2
    assert all(it["status"] == "completed" and not it["can_complete"] for it in bid2)


def test_bid_via_api_endpoint(client, db, auth_user_and_headers):
    """端到端经 /agenda/complete 透传 slot → 两剂各落库,响应 200。"""
    user, h = auth_user_and_headers
    med = _seed_bid(db, user.id, reminder_times=["08:00", "20:00"])

    r1 = client.post("/api/v1/agenda/complete", headers=h, json={
        "object_type": "medication", "object_id": med.id, "status": "done", "slot": "08:00"})
    r2 = client.post("/api/v1/agenda/complete", headers=h, json={
        "object_type": "medication", "object_id": med.id, "status": "done", "slot": "20:00"})
    assert r1.status_code == 200 and r2.status_code == 200, (r1.text, r2.text)
    assert r1.json()["wrote"] is True and r2.json()["wrote"] is True
    assert r1.json()["event_id"] != r2.json()["event_id"]

    logs = _taken_logs(db, user.id, med.id)
    assert len(logs) == 2, "经 API 的 BID 两剂应恰两条 taken log"
    assert [l.taken_time for l in logs] == ["08:00", "20:00"]


# ───────────────────── 2. 同槽幂等(council 护栏,保持绿) ─────────────────────

def test_same_slot_twice_idempotent_single_log(db, auth_user_and_headers):
    """同一 slot 完成两次 → 一条 MedicationLog,第二次 idempotent(同槽 uq_medlog 兜底)。"""
    from app.services import timeline_agenda_service as tas

    user, _ = auth_user_and_headers
    med = _seed_bid(db, user.id, reminder_times=["08:00", "20:00"])

    r1 = tas.complete_by_ref(db, user.id, "medication", med.id, slot="08:00")
    db.commit()
    r2 = tas.complete_by_ref(db, user.id, "medication", med.id, slot="08:00")
    db.commit()

    assert r1["idempotent"] is False
    assert r2["idempotent"] is True, "同槽第二次必须幂等(council 不变量)"
    assert r1["event_id"] == r2["event_id"], "同槽两次应命中同一议程 HealthEvent"

    logs = _taken_logs(db, user.id, med.id)
    assert len(logs) == 1, "同槽两次完成至多一条 taken log(依从不虚高)"
    assert logs[0].taken_time == "08:00"


# ───────────────────── 3. 每日一次回归(byte-identical,无 slot) ─────────────────────

def test_once_daily_single_item_no_slot_byte_identical(client, db, auth_user_and_headers):
    """单时点(reminder_times ["09:00"])→ 脊柱一行、无 slot 键、一条 log、幂等;
    /timeline/today 的 complete_ref 不含 slot(与 F5b 前逐字节相同)。"""
    from app.services.today_timeline_service import build_today_spine
    from app.services import timeline_agenda_service as tas

    user, h = auth_user_and_headers
    med = _seed_bid(db, user.id, name="每日一次药", reminder_times=["09:00"])

    spine = build_today_spine(db, user.id)
    rows = [
        it for it in spine["items"]
        if (it.get("complete_ref") or {}).get("object_id") == med.id
        and (it.get("complete_ref") or {}).get("object_type") == "medication"
    ]
    assert len(rows) == 1, "单时点应只出一条脊柱行"
    # 关键:complete_ref 逐字节 == 改前(无 slot 键,不是 slot:None)。
    assert rows[0]["complete_ref"] == {"object_type": "medication", "object_id": med.id}
    assert "slot" not in rows[0]["complete_ref"]

    # /timeline/today HTTP 响应:complete_ref 也不含 slot 键(model_serializer 省略)。
    body = client.get("/api/v1/timeline/today", headers=h).json()
    api_row = next(
        it for it in body["items"]
        if (it.get("complete_ref") or {}).get("object_id") == med.id
        and (it.get("complete_ref") or {}).get("object_type") == "medication"
    )
    assert api_row["complete_ref"] == {"object_type": "medication", "object_id": med.id}
    assert "slot" not in api_row["complete_ref"]

    # 完成(不传 slot)→ 一条 log,幂等。
    r1 = tas.complete_by_ref(db, user.id, "medication", med.id)
    db.commit()
    r2 = tas.complete_by_ref(db, user.id, "medication", med.id)
    db.commit()
    assert r1["idempotent"] is False and r2["idempotent"] is True
    assert r1["event_id"] == r2["event_id"]
    # complete_ref 在 service 返回里也无 slot 键。
    assert r1["complete_ref"] == {"object_type": "medication", "object_id": med.id}
    assert len(_taken_logs(db, user.id, med.id)) == 1


def test_once_daily_api_response_dict_unchanged(client, db, auth_user_and_headers):
    """/agenda/complete 单剂响应顶层 dict 键集与改前一致(无 slot 泄漏到响应顶层)。"""
    user, h = auth_user_and_headers
    med = Medication(user_id=user.id, name="单剂", category="处方药", is_active=True)
    db.add(med)
    db.commit()
    db.refresh(med)

    r = client.post("/api/v1/agenda/complete", headers=h, json={
        "object_type": "medication", "object_id": med.id, "status": "done"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) == {
        "object_type", "object_id", "event_id", "agenda_status",
        "skip_reason", "wrote", "idempotent", "source_write",
    }, f"单剂响应顶层键集应与改前一致,实得 {sorted(body.keys())}"
    assert "slot" not in body


# ───────────────────── 4. 跨剂隔离 ─────────────────────

def test_completing_morning_does_not_mark_evening(db, auth_user_and_headers, monkeypatch):
    """完成 08:00 不会把 20:00 标 done(两剂独立议程行)。"""
    from app.services.today_timeline_service import build_today_spine
    from app.services import timeline_agenda_service as tas

    _pin_morning_clock(monkeypatch)
    user, _ = auth_user_and_headers
    med = _seed_bid(db, user.id, reminder_times=["08:00", "20:00"])

    tas.complete_by_ref(db, user.id, "medication", med.id, slot="08:00")
    db.commit()

    spine = build_today_spine(db, user.id)
    by_slot = {
        it["complete_ref"].get("slot"): it
        for it in spine["items"]
        if (it.get("complete_ref") or {}).get("object_id") == med.id
        and (it.get("complete_ref") or {}).get("object_type") == "medication"
    }
    assert by_slot["08:00"]["status"] == "completed", "已完成的晨剂应熄灭"
    assert by_slot["08:00"]["can_complete"] is False
    assert by_slot["20:00"]["status"] == "pending", "未完成的晚剂仍 pending(跨剂隔离)"
    assert by_slot["20:00"]["can_complete"] is True

    logs = _taken_logs(db, user.id, med.id)
    assert len(logs) == 1 and logs[0].taken_time == "08:00", "只应有晨剂一条 taken log"


def test_multidose_slot_done_detection_robust_to_zero_pad(db, auth_user_and_headers):
    """安全评审 A1:reminder_times 非零填充("8:00")时,该槽已服日志("08:00" 或 "8:00")
    仍按分钟数归一化判 done(纯 UI 显示侧 robust;不影响计数,权威态由 HealthEvent 覆盖)。"""
    from app.services.today_spine_meds import _multidose_items

    med_id = 99
    s = {"title": "BID药", "domain": "medication", "time": "8:00"}
    st = {
        "name": "BID药", "timing_label": None,
        "logs": [{"time": "08:00", "status": "taken", "id": 1}],  # 零填充存储
    }
    items = _multidose_items("medication", med_id, s, st, ["8:00", "20:00"])  # 非零填充槽
    by_slot = {it["complete_ref"]["slot"]: it for it in items}
    assert by_slot["8:00"]["status"] == "completed", "归一化后非零填充槽应判 done"
    assert by_slot["8:00"]["can_complete"] is False
    assert by_slot["20:00"]["status"] == "pending"


def test_bid_reminder_emits_two_complete_refs_with_slots(db, auth_user_and_headers):
    """提醒桥:BID 药 → _collect_timed_items 出两条带各自 slot 的 complete_ref。"""
    from app.tasks.event_reminders import _collect_timed_items

    user, _ = auth_user_and_headers
    med = _seed_bid(db, user.id, reminder_times=["08:00", "20:00"])

    items = _collect_timed_items(db, user.id, date.today())
    med_items = [
        it for it in items
        if (it.get("complete_ref") or {}).get("object_id") == med.id
        and (it.get("complete_ref") or {}).get("object_type") == "medication"
    ]
    assert len(med_items) == 2, f"BID 提醒应出两条,实得 {len(med_items)}"
    slots = sorted(it["complete_ref"].get("slot") for it in med_items)
    assert slots == ["08:00", "20:00"]
    # item_key 各自独立(SentEventReminder 去重不互撞)。
    keys = {it["item_key"] for it in med_items}
    assert len(keys) == 2, f"两剂 item_key 应各自独立,实得 {keys}"
