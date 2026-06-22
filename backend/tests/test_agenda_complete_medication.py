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
    assert len(_taken_logs(db, user.id, med.id)) == 1

    # 第二条:同槽 → 领域唯一约束撞 → 422 fail-loud,不落第二条 taken。
    with pytest.raises(tas.AgendaCompleteError):
        tas.complete_agenda_event(db, user.id, ev2.id, status="done")
    db.refresh(ev2)
    assert ev2.agenda_status == "pending", "回写失败必须不翻 done(fail-loud)"
    assert len(_taken_logs(db, user.id, med.id)) == 1, "至多一条依从,不得虚高"


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
