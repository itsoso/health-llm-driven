"""药 / 补剂经 /agenda/complete 闭环完成(安全闸:此前 med-reminder「完成」只能 422)。

钉死时间驱动行动目录的完成闸:推送「完成」按钮拿 complete_ref={object_type,object_id}
POST /agenda/complete → 懒物化议程 HealthEvent → 双轨回写真实 MedicationLog → 翻生命周期。
药与补剂同存 medications 表(object_id 即 medication_id),都经 log_medication 写,无独立补剂路径。

覆盖(安全 re-review gate):
① done 往返 200 + 真落 MedicationLog(taken)(med 与 supplement 各一)
② 幂等:重复完成第二次 idempotent=True,仍只一条 MedicationLog(不虚高依从)
③ skipped:200 + agenda_status=skipped + 不写 taken 行;坏 skip_reason → 400
④ 跨用户隔离:完成别人的 med → 404(不跨用户写)
⑤ 脊柱 shape:可完成的 med 行动项 → can_complete=True + 物化 event_id
⑥ 不支持来源仍 fail loud:dispatcher 认不出的 object_type → 400(不静默假成功)
"""
from datetime import date

from app.models.medication import Medication, MedicationLog
from app.utils.timezone import get_china_today


def _seed_med(db, user_id: int, name: str = "雷贝拉唑", category: str = "处方药") -> Medication:
    med = Medication(user_id=user_id, name=name, category=category, is_active=True)
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


# ─────────────────────────── ① done 往返 + 真落库 ───────────────────────────

def test_complete_medication_done_writes_real_log(client, db, auth_user_and_headers):
    user, h = auth_user_and_headers
    med = _seed_med(db, user.id)

    r = client.post("/api/v1/agenda/complete", headers=h, json={
        "object_type": "medication", "object_id": med.id, "status": "done"})

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["object_type"] == "medication" and body["object_id"] == med.id
    assert body["agenda_status"] == "done"
    assert body["wrote"] is True
    assert isinstance(body["event_id"], int)
    # 真实领域写:今日 taken MedicationLog 落库。
    logs = _taken_logs(db, user.id, med.id)
    assert len(logs) == 1


def test_complete_medication_uses_the_agenda_user_day(
    client, db, auth_user_and_headers, monkeypatch,
):
    from app.api import agenda as agenda_api

    user, h = auth_user_and_headers
    med = _seed_med(db, user.id)
    user_day = date(2026, 7, 21)
    monkeypatch.setattr(agenda_api, "get_user_today", lambda _db, _uid: user_day)

    response = client.post("/api/v1/agenda/complete", headers=h, json={
        "object_type": "medication", "object_id": med.id, "status": "done"})

    assert response.status_code == 200, response.text
    log = db.query(MedicationLog).filter_by(
        user_id=user.id, medication_id=med.id,
    ).one()
    assert log.taken_date == user_day


def test_complete_supplement_done_writes_real_log(client, db, auth_user_and_headers):
    """补剂同存 medications 表 → 同经 log_medication;object_type 仅分类不分写路径。"""
    user, h = auth_user_and_headers
    supp = _seed_med(db, user.id, name="维生素D3", category="补剂")

    r = client.post("/api/v1/agenda/complete", headers=h, json={
        "object_type": "supplement", "object_id": supp.id, "status": "done"})

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["object_type"] == "supplement"
    assert body["agenda_status"] == "done" and body["wrote"] is True
    assert len(_taken_logs(db, user.id, supp.id)) == 1


def test_complete_medication_manual_track_forwards_actual_dosage(client, db, auth_user_and_headers):
    """手工轨带 actual_dosage → 透传进 MedicationLog(记用户报告的实际服量,非处方;R4)。

    防回归:统一路由若丢 value,用户填的实际剂量会被静默吞(依从事实失真)。
    """
    user, h = auth_user_and_headers
    med = _seed_med(db, user.id)

    r = client.post("/api/v1/agenda/complete", headers=h, json={
        "object_type": "medication", "object_id": med.id, "status": "done",
        "track": "manual", "value": {"actual_dosage": "半片"}})

    assert r.status_code == 200, r.text
    logs = _taken_logs(db, user.id, med.id)
    assert len(logs) == 1
    assert logs[0].actual_dosage == "半片"


# ─────────────────────────── ② 幂等(双击一次效果)───────────────────────────

def test_complete_medication_idempotent_single_log(client, db, auth_user_and_headers):
    """双击 / 重放完成 → 第二次 idempotent=True,且只一条 MedicationLog(不二次写)。"""
    user, h = auth_user_and_headers
    med = _seed_med(db, user.id)

    r1 = client.post("/api/v1/agenda/complete", headers=h, json={
        "object_type": "medication", "object_id": med.id, "status": "done"})
    assert r1.status_code == 200 and r1.json()["idempotent"] is False

    r2 = client.post("/api/v1/agenda/complete", headers=h, json={
        "object_type": "medication", "object_id": med.id, "status": "done"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["idempotent"] is True
    # 第二次不二次回写:仍恰好一条 taken 行(否则虚高依从污染 DDI/PGx)。
    assert len(_taken_logs(db, user.id, med.id)) == 1


def test_domain_write_idempotent_across_minute_boundary(db, auth_user_and_headers):
    """对抗:两次完成的领域写跨分钟(taken_time 槽不同时本会各落一条)→ 仍恰好一条 taken。

    复现 safety review 抓的 HIGH:此前 taken_time 用 wall-clock now,跨分钟两写绕过
    uq_medlog_med_date_time → 两条 MedicationLog → 虚高依从。修法是 taken_time 取议程
    项 scheduled_for 的确定性槽(同项两次完成必落同一槽,DB 唯一约束兜住)。
    这里在 complete_item 层直打两次(同一确定性 slot),验只落一条。
    """
    from app.services import agenda_service

    user, _ = auth_user_and_headers
    med = _seed_med(db, user.id)

    # 同一确定性槽(模拟同一议程项的 scheduled_for "09:00"),两次领域写。
    r1 = agenda_service.complete_item(
        db, user.id, "medication", med.id, taken_time="09:00")
    db.commit()
    assert r1["wrote"] is True

    # 第二次同槽写 → uq_medlog_med_date_time 撞 → log_medication 重读返回既有行,不落第二条。
    # (commit=True 路径有 IntegrityError 重读兜底;此处显式走 commit=True 默认。)
    from app.services.medication_service import medication_service
    log2 = medication_service.log_medication(
        db, user.id, med.id, taken_time="09:00", status="taken")
    assert log2.id == r1["log_id"], "同槽重写必须重读既有行,不得落第二条"
    assert len(_taken_logs(db, user.id, med.id)) == 1


def test_two_agenda_events_same_med_second_completion_fails_loud(db, auth_user_and_headers):
    """对抗:并发物化出两条同 med 同日议程行(无 DB 唯一约束的残留缝隙)。

    完成第一条 → 落一条 taken;完成第二条(同 scheduled_for → 同确定性槽)→ 领域唯一约束撞
    → 422(AgendaCompleteError),整事务回滚,**不**翻 done、**不**落第二条 taken。
    即:就算议程层漏防出两行,领域层 DB 唯一约束 + fail-loud 仍守住「至多一条依从」。
    """
    from datetime import datetime

    import pytest

    from app.models.health_event import HealthEvent
    from app.services import timeline_agenda_service as tas

    user, _ = auth_user_and_headers
    med = _seed_med(db, user.id)
    ref = {"object_type": "medication", "object_id": med.id}
    sched = datetime(2026, 6, 22, 9, 0, 0)

    # 直接造两条同 ref 同 scheduled_for 的 pending 议程行(绕过 find 去重,模拟并发竞态)。
    def _mk():
        ev = HealthEvent(
            user_id=user.id, event_type=tas.AGENDA_EVENT_TYPE, source="agenda",
            agenda_status="pending", action_kind="medication", complete_ref=ref,
            scheduled_for=sched, event_time=sched, association_only=False,
        )
        db.add(ev)
        db.commit()
        db.refresh(ev)
        return ev

    ev1, ev2 = _mk(), _mk()

    r1 = tas.complete_agenda_event(db, user.id, ev1.id, status="done")
    assert r1["agenda_status"] == "done"
    logs1 = _taken_logs(db, user.id, med.id)
    assert len(logs1) == 1
    # F4 回归闸:taken_time 必须是议程项 scheduled_for 的确定性槽("09:00"),不是 wall-clock now。
    # 把 _slot_time 改回 now() 后这条断言会红(测试在 09:00 之外的时刻跑时 now() != "09:00")。
    assert logs1[0].taken_time == sched.strftime("%H:%M") == "09:00", (
        "taken_time 必须取 scheduled_for 的确定性槽(非 wall-clock now);"
        "若 _slot_time 退回 now() 此断言变红")

    # 第二条:同槽 → 领域唯一约束撞 → 422 fail-loud,不落第二条 taken。
    with pytest.raises(tas.AgendaCompleteError):
        tas.complete_agenda_event(db, user.id, ev2.id, status="done")
    db.refresh(ev2)
    assert ev2.agenda_status == "pending", "回写失败必须不翻 done(fail-loud)"
    assert len(_taken_logs(db, user.id, med.id)) == 1, "至多一条依从,不得虚高"


def test_slot_straddles_minute_boundary_single_taken(db, auth_user_and_headers, monkeypatch):
    """F4 钟表跨界硬闸:第一次完成在 08:59:5x、第二次在 09:00:0x(wall-clock 跨分钟),但
    两次都是 **同一议程事件**(同 scheduled_for)→ 必须恰一条 taken。

    若 _slot_time 退回 wall-clock now():两次 taken_time 分别落 "08:59" / "09:00" 两个不同
    uq_medlog 槽 → 两条 taken(虚高依从)→ 本测试红。确定性槽则两次都落 scheduled_for 的
    "09:00",同槽幂等 → 恰一条。
    """
    from datetime import datetime

    import app.utils.timezone as tz
    from app.models.health_event import HealthEvent
    from app.services import timeline_agenda_service as tas

    user, _ = auth_user_and_headers
    med = _seed_med(db, user.id)
    ref = {"object_type": "medication", "object_id": med.id}
    sched = datetime(2026, 6, 22, 9, 0, 0)  # 议程项代表时点 09:00

    ev = HealthEvent(
        user_id=user.id, event_type=tas.AGENDA_EVENT_TYPE, source="agenda",
        agenda_status="pending", action_kind="medication", complete_ref=ref,
        scheduled_for=sched, event_time=sched, association_only=False,
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)

    # 钟表桩:把 wall-clock 钉在 08:59:55(≠ scheduled_for 的 09:00)。若 _slot_time 退回
    # get_china_now(),taken_time 会落 "08:59" → 下面的 "09:00" 断言变红。确定性槽不受钟表影响。
    monkeypatch.setattr(tz, "get_china_now", lambda: datetime(2026, 6, 22, 8, 59, 55))

    r1 = tas.complete_agenda_event(db, user.id, ev.id, status="done")
    assert r1["agenda_status"] == "done"
    logs = _taken_logs(db, user.id, med.id)
    assert len(logs) == 1
    assert logs[0].taken_time == "09:00", (
        "taken_time 必须是 scheduled_for 的确定性槽 09:00,不随 wall-clock(此处桩成 08:59)漂;"
        "_slot_time 退回 now() → 此断言红")

    # 时间推进过分钟边界后再次完成同一事件 → 议程终态短路(幂等),仍恰一条 taken(确定性槽)。
    monkeypatch.setattr(tz, "get_china_now", lambda: datetime(2026, 6, 22, 9, 0, 5))
    r2 = tas.complete_agenda_event(db, user.id, ev.id, status="done")
    assert r2["idempotent"] is True
    logs = _taken_logs(db, user.id, med.id)
    assert len(logs) == 1, "同议程项跨分钟两次完成必恰一条 taken(确定性槽)"
    assert logs[0].taken_time == "09:00"


def test_lazy_materialize_pins_scheduled_for_to_midnight(db, auth_user_and_headers, monkeypatch):
    """F5a 哨兵:complete_by_ref 懒物化时 scheduled_for 钉到「当日 00:00」稳定 token,
    不随 wall-clock 小时漂。

    回归前的 hour-级整点 token:两个并发首物化跨整点边界(10:59 vs 11:00)算出不同
    scheduled_for → 两条议程行 / 两个 medlog 槽 → 依从重计。钉午夜后,同日同 ref 的懒物化
    恒得同一 scheduled_for(00:00)。本测试断言 scheduled_for 的 minute/second 归零且 hour=0
    —— 若退回 .replace(minute=0,...)(仍带当前 hour),hour!=0 时此断言红。
    """
    from datetime import datetime

    import app.utils.timezone as tz
    from app.services import timeline_agenda_service as tas

    user, _ = auth_user_and_headers
    med = _seed_med(db, user.id)

    # wall-clock 钉在 10:59:30(非整点 0 时)→ 若仍按整点 token,scheduled_for.hour 会是 10。
    # complete_by_ref 现按中国时区(get_china_now/get_china_today)取 today-basis,故桩这两个
    # (而非 get_user_now)—— 二者钉到同一天,否则 find 会错日落空、本哨兵失效。
    monkeypatch.setattr(tz, "get_china_now", lambda: datetime(2026, 6, 22, 10, 59, 30))
    monkeypatch.setattr(tz, "get_china_today", lambda: datetime(2026, 6, 22, 10, 59, 30).date())

    tas.complete_by_ref(db, user.id, "medication", med.id, status="done")

    ev = tas.find_agenda_event(
        db, user.id, {"object_type": "medication", "object_id": med.id},
        tz.get_china_today(),
    )
    assert ev is not None
    assert ev.scheduled_for.hour == 0, (
        f"F5a:懒物化 scheduled_for 必须钉到当日 00:00(稳定 token),实得 "
        f"{ev.scheduled_for!r};退回整点 token → hour=10 此断言红")
    assert ev.scheduled_for.minute == 0 and ev.scheduled_for.second == 0


# ─────────────────────────── ③ skipped(不回写)───────────────────────────

def test_complete_medication_skipped_no_writeback(client, db, auth_user_and_headers):
    user, h = auth_user_and_headers
    med = _seed_med(db, user.id)

    r = client.post("/api/v1/agenda/complete", headers=h, json={
        "object_type": "medication", "object_id": med.id,
        "status": "skipped", "skip_reason": "no_supply"})

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["agenda_status"] == "skipped"
    assert body["skip_reason"] == "no_supply"
    assert body["wrote"] is False
    # skipped 不写 taken 行(漏服不能记成依从)。
    assert len(_taken_logs(db, user.id, med.id)) == 0


def test_complete_skipped_bad_reason_400(client, db, auth_user_and_headers):
    user, h = auth_user_and_headers
    med = _seed_med(db, user.id)
    r = client.post("/api/v1/agenda/complete", headers=h, json={
        "object_type": "medication", "object_id": med.id,
        "status": "skipped", "skip_reason": "因为我不想吃"})
    assert r.status_code == 400


def test_complete_skipped_requires_reason(client, db, auth_user_and_headers):
    user, h = auth_user_and_headers
    med = _seed_med(db, user.id)

    r = client.post("/api/v1/agenda/complete", headers=h, json={
        "object_type": "medication", "object_id": med.id,
        "status": "skipped"})

    assert r.status_code == 400
    assert "skip_reason" in r.text


# ─────────────────────────── ④ 跨用户隔离 ───────────────────────────

def test_complete_other_users_medication_404(client, db, auth_user_and_headers):
    """完成别人的 med object_id → 404(不 200、不跨用户写),get_medication 按 user 过滤。"""
    owner, _ = auth_user_and_headers
    med = _seed_med(db, owner.id)

    # 另起一个用户 + token,用其 header 去完成 owner 的 med。
    from app.services.auth import auth_service
    from app.models.user import User

    attacker = User(username="attacker_ac", email="attacker_ac@test.com",
                    hashed_password="x", name="他者", is_active=True, is_approved=True)
    db.add(attacker)
    db.commit()
    db.refresh(attacker)
    token = auth_service.create_access_token({"sub": str(attacker.id)})
    h_attacker = {"Authorization": f"Bearer {token}"}

    r = client.post("/api/v1/agenda/complete", headers=h_attacker, json={
        "object_type": "medication", "object_id": med.id, "status": "done"})

    assert r.status_code == 404, r.text
    # 没有任何 taken 行被写(无论 owner 还是 attacker)。
    assert len(_taken_logs(db, owner.id, med.id)) == 0
    assert len(_taken_logs(db, attacker.id, med.id)) == 0


# ─────────────────────────── ⑤ 脊柱 shape(可完成 + 物化)───────────────────────────

def test_medication_spine_item_can_complete_and_materializes(db, auth_user_and_headers):
    """流经 _map_agenda_item 的 pending med 行动项 → can_complete=True + 物化 event_id。

    钉的是闸本身的两处改动:① _map_agenda_item 把 medication/supplement 纳入 can_complete;
    ② _attach_event_ids 对其同样物化 first-class HealthEvent(generalize 自 health_protocol)。
    (agenda_service.today() 当前把药当 health_protocol 发,不发裸 medication 源;故在
    _map_agenda_item 层直喂 medication-源 item 验改动,不依赖尚不存在的裸 med 议程生产者。)
    """
    from datetime import datetime

    from app.services import today_timeline_service as tts

    user, _ = auth_user_and_headers
    med = _seed_med(db, user.id)

    raw = {
        "type": "medication",
        "title": med.name,
        "status": "pending",
        "time_window": "morning",
        "priority": 50,
        "source": {"object_type": "medication", "object_id": med.id},
    }
    item = tts._map_agenda_item(raw)
    assert item["can_complete"] is True
    assert item["complete_ref"] == {"object_type": "medication", "object_id": med.id}

    tts._attach_event_ids(db, user.id, [item], datetime.now())
    assert isinstance(item["event_id"], int), "可完成的 med 行动项必须物化出 event_id"
    assert item["can_complete"] is True  # 尚未完成 → 仍可完成


# ─────────────────────────── ⑥ 不支持来源仍 fail loud ───────────────────────────

def test_complete_unsupported_type_400_no_silent_success(client, db, auth_user_and_headers):
    """dispatcher 认不出的 object_type → 400(不静默假成功、不凭空物化议程行)。"""
    _, h = auth_user_and_headers
    r = client.post("/api/v1/agenda/complete", headers=h, json={
        "object_type": "health_problem", "object_id": 1, "status": "done"})
    assert r.status_code == 400, r.text


# ─────────────── F1: skip 与 done 同校验(不给非法 ref 物化幻影议程行)───────────────

def _agenda_event_count(db, user_id: int) -> int:
    from app.models.health_event import HealthEvent
    from app.services import timeline_agenda_service as tas
    return (
        db.query(HealthEvent)
        .filter(
            HealthEvent.user_id == user_id,
            HealthEvent.event_type == tas.AGENDA_EVENT_TYPE,
        )
        .count()
    )


def test_skip_foreign_medication_404_no_phantom_event(client, db, auth_user_and_headers):
    """F1:skip 别人的 med → 404(物化前先验所有权),且不凭空物化议程 HealthEvent。"""
    owner, _ = auth_user_and_headers
    med = _seed_med(db, owner.id)

    from app.services.auth import auth_service
    from app.models.user import User

    attacker = User(username="attacker_f1", email="attacker_f1@test.com",
                    hashed_password="x", name="他者", is_active=True, is_approved=True)
    db.add(attacker)
    db.commit()
    db.refresh(attacker)
    token = auth_service.create_access_token({"sub": str(attacker.id)})
    h_attacker = {"Authorization": f"Bearer {token}"}

    before = _agenda_event_count(db, attacker.id)
    r = client.post("/api/v1/agenda/complete", headers=h_attacker, json={
        "object_type": "medication", "object_id": med.id, "status": "skipped",
        "skip_reason": "no_supply"})

    assert r.status_code == 404, r.text
    # 不给外人 ref 物化任何议程行(此前 skip 漏先验会落幻影行)。
    assert _agenda_event_count(db, attacker.id) == before
    # owner 侧也无任何 skipped MedicationLog 被写。
    from app.models.medication import MedicationLog
    assert db.query(MedicationLog).filter(
        MedicationLog.medication_id == med.id).count() == 0


def test_skip_nonexistent_medication_404(client, db, auth_user_and_headers):
    """F1:skip 不存在的 med id → 404(物化前先验存在性)。"""
    user, h = auth_user_and_headers
    before = _agenda_event_count(db, user.id)
    r = client.post("/api/v1/agenda/complete", headers=h, json={
        "object_type": "medication", "object_id": 999999, "status": "skipped",
        "skip_reason": "forgot"})
    assert r.status_code == 404, r.text
    assert _agenda_event_count(db, user.id) == before


def test_skip_unsupported_type_400_no_phantom_event(client, db, auth_user_and_headers):
    """F1:skip 不支持的 object_type → 400(不静默物化议程行)。"""
    user, h = auth_user_and_headers
    before = _agenda_event_count(db, user.id)
    r = client.post("/api/v1/agenda/complete", headers=h, json={
        "object_type": "health_problem", "object_id": 1, "status": "skipped",
        "skip_reason": "no_time"})
    assert r.status_code == 400, r.text
    assert _agenda_event_count(db, user.id) == before


# ─────────────── F2: skip 写源行 + 后 done supersede ───────────────

def _all_logs(db, user_id: int, med_id: int):
    return (
        db.query(MedicationLog)
        .filter(
            MedicationLog.user_id == user_id,
            MedicationLog.medication_id == med_id,
            MedicationLog.taken_date == get_china_today(),
        )
        .all()
    )


def test_skip_writes_source_skip_log(client, db, auth_user_and_headers):
    """F2:经 /agenda/complete skip 一味 med → 落一条 MedicationLog(status=skipped)源行。

    此前 skip 只翻 HealthEvent 生命周期、不写源行 → today_status 仍 pending → re-nag。
    """
    user, h = auth_user_and_headers
    med = _seed_med(db, user.id)

    r = client.post("/api/v1/agenda/complete", headers=h, json={
        "object_type": "medication", "object_id": med.id,
        "status": "skipped", "skip_reason": "no_supply"})
    assert r.status_code == 200, r.text
    assert r.json()["agenda_status"] == "skipped"
    assert r.json()["wrote"] is False  # skip 不是依从完成

    logs = _all_logs(db, user.id, med.id)
    assert len(logs) == 1
    assert logs[0].status == "skipped"
    assert logs[0].skip_reason == "no_supply"
    # 不写 taken(漏服不能记成依从)。
    assert len(_taken_logs(db, user.id, med.id)) == 0


def test_skip_then_done_same_day_supersedes_to_taken(client, db, auth_user_and_headers):
    """F2 supersede(Claude B + Codex 共同要求):8am 跳过、9am 实服 → 必须能记成 taken。

    源行(MedicationLog)同槽只一条,终态 taken,无双行、无 422。
    """
    user, h = auth_user_and_headers
    med = _seed_med(db, user.id)

    r1 = client.post("/api/v1/agenda/complete", headers=h, json={
        "object_type": "medication", "object_id": med.id,
        "status": "skipped", "skip_reason": "no_supply"})
    assert r1.status_code == 200 and r1.json()["agenda_status"] == "skipped"

    # 后到的真实 done 必须 supersede 掉 skip,不被议程终态短路、不被源唯一约束 422。
    r2 = client.post("/api/v1/agenda/complete", headers=h, json={
        "object_type": "medication", "object_id": med.id, "status": "done"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["agenda_status"] == "done"
    assert r2.json()["wrote"] is True

    logs = _all_logs(db, user.id, med.id)
    assert len(logs) == 1, "skip→done 同槽 supersede:源行恰一条,不双行"
    assert logs[0].status == "taken", "先跳后服必须记成已服"


def test_done_then_skip_does_not_downgrade(client, db, auth_user_and_headers):
    """F2 边界:已 done 不可被随后的 skip 降级成漏服(守 R4:已服不可改写)。"""
    user, h = auth_user_and_headers
    med = _seed_med(db, user.id)

    r1 = client.post("/api/v1/agenda/complete", headers=h, json={
        "object_type": "medication", "object_id": med.id, "status": "done"})
    assert r1.status_code == 200 and r1.json()["agenda_status"] == "done"

    r2 = client.post("/api/v1/agenda/complete", headers=h, json={
        "object_type": "medication", "object_id": med.id,
        "status": "skipped", "skip_reason": "forgot"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["agenda_status"] == "done", "已 done 拒绝降级成 skipped(幂等返回 done)"

    logs = _all_logs(db, user.id, med.id)
    assert len(logs) == 1 and logs[0].status == "taken"


def test_skip_before_reminder_not_recollected(db, auth_user_and_headers):
    """F2:协议在到点推送前被 skip → today_status 翻 skipped → _collect_timed_items 不再收集
    (no re-nag)。这是 skip 写源行(HealthProtocolEvent)带来的跨视图一致。"""
    from app.services.protocol_templates import seed_behavior_protocols
    from app.services import timeline_agenda_service as tas
    from app.tasks.event_reminders import _collect_timed_items
    from datetime import date

    user, _ = auth_user_and_headers
    seed_behavior_protocols(db, user.id, keys=["nasal_wash_morning"])
    from app.models.health_protocol import HealthProtocol
    p = next(
        pp for pp in db.query(HealthProtocol).filter(HealthProtocol.user_id == user.id).all()
        if (pp.implied_quantity or {}).get("template_key") == "nasal_wash_morning"
    )

    # 推送前 skip(经统一 /agenda/complete 路径 → 写 HealthProtocolEvent skipped 源行)。
    tas.complete_by_ref(
        db, user.id, "health_protocol", p.id, status="skipped", skip_reason="no_time")
    db.commit()

    items = _collect_timed_items(db, user.id, date.today())
    proto = [it for it in items if it["kind"] == "protocol"]
    assert proto == [], "skip 后协议不应再被提醒桥收集(today_status 已 skipped)"
