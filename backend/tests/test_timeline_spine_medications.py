"""统一今日时间线脊柱:用药/补剂(medications 表)并入 + 时间感知 now-marker。

钉死(对应任务验收):
1. 药(在 medications 表,非协议)+ pending 补剂 → /timeline/today 以脊柱行返回,带真实
   时点(scheduled_for HH:MM)+ complete_ref {medication|supplement}。
2. now-marker:固定中国时刻(mock 下午)→ now 指向下午到点项,不是清晨称重/第一项。
3. 已全部服完(taken==total)→ 归 done(status=completed、不在 actionable)。
4. 不双份:schedule 上的药不另作为 daily-plan 行动重复出现(脊柱不调 planner)。
5. 时间排序:items 按 scheduled_for 升序(有时点在前),anytime 排其后。
6. 用户隔离:只返回调用者自己的药。
7. 既有消费者 shape 保留:旧 /timeline/today 字段仍在。

只读投影。完成走既有闭环(complete_ref + /timeline/events/{id}/complete),不 fork。
"""
from datetime import date, datetime, timezone

import pytest

from app.models.medication import Medication, MedicationLog
from app.services.today_timeline_service import build_today_spine


def _add_med(db, user_id, name, *, category, reminder, times_per_day=1,
             timing_relation=None, meal_anchor=None):
    m = Medication(
        user_id=user_id,
        name=name,
        category=category,
        times_per_day=times_per_day,
        reminder_times=[reminder] if reminder else None,
        timing_relation=timing_relation,
        meal_anchor=meal_anchor,
        is_active=True,
        start_date=date.today(),
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def _log_taken(db, user_id, med_id, hhmm):
    db.add(MedicationLog(
        user_id=user_id, medication_id=med_id,
        taken_date=date.today(), taken_time=hhmm, status="taken",
    ))
    db.commit()


# ───────────────── 1. 药+补剂进脊柱,带真实时点 + complete_ref ─────────────────

def test_medication_and_supplement_appear_with_times_and_ref(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    med = _add_med(db, user.id, "二甲双胍", category="处方药",
                   reminder="08:00", timing_relation="after_meal", meal_anchor="breakfast")
    supp = _add_med(db, user.id, "维生素D", category="supplement", reminder="13:00")

    spine = build_today_spine(db, user.id)

    by_ref = {
        (it["complete_ref"]["object_type"], it["complete_ref"]["object_id"]): it
        for it in spine["items"] if it.get("complete_ref")
    }
    med_item = by_ref.get(("medication", med.id))
    supp_item = by_ref.get(("supplement", supp.id))

    assert med_item is not None, "处方药应作为脊柱行动项出现"
    assert supp_item is not None, "补剂应作为脊柱行动项出现"

    # 真实时点(timing_solver 求解;有 reminder/anchor → 非 None)
    assert med_item["scheduled_for"], "用药项应带真实时点 HH:MM"
    assert supp_item["scheduled_for"], "补剂项应带真实时点 HH:MM"

    # 未服 → pending、可完成、复用既有闭环 ref
    assert med_item["status"] == "pending"
    assert med_item["can_complete"] is True
    assert med_item["complete_ref"] == {"object_type": "medication", "object_id": med.id}
    assert supp_item["complete_ref"] == {"object_type": "supplement", "object_id": supp.id}
    assert med_item["kind"] == "action"
    assert med_item["driver"] == "plan_driven"

    assert spine["counts"]["actionable"] >= 2


# ───────────────── 2. now-marker 时间感知:下午 → 指向下午项 ─────────────────

def test_now_marker_points_to_afternoon_due_not_morning(db, auth_user_and_headers, monkeypatch):
    """钉到下午 15:30(中国时间)→ now 是下午到点项,不是清晨用药/第一项(红绿)。"""
    import app.services.today_timeline_service as svc

    user, _ = auth_user_and_headers
    morning = _add_med(db, user.id, "晨药", category="处方药", reminder="08:00")
    afternoon = _add_med(db, user.id, "午后药", category="处方药", reminder="15:00")

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            # 2026-06-16 07:30 UTC = 15:30 Asia/Shanghai(无 user profile → 回退 OS=Asia/Shanghai)
            base = datetime(2026, 6, 16, 7, 30, tzinfo=timezone.utc)
            return base.astimezone(tz) if tz else base.replace(tzinfo=None)

    monkeypatch.setattr(svc, "datetime", FixedDateTime)

    spine = build_today_spine(db, user.id)

    now_id = spine["now"]
    assert now_id is not None
    now_item = next(it for it in spine["items"] if it["id"] == now_id)
    # 15:30 时,08:00 与 15:00 都已到点;now 取最接近当下(最晚已到点)→ 午后药,非晨药
    assert now_item["complete_ref"] == {"object_type": "medication", "object_id": afternoon.id}, \
        f"now 应指向下午到点项,实得 {now_item['title']}"


def test_now_marker_picks_next_upcoming_when_nothing_due_yet(db, auth_user_and_headers, monkeypatch):
    """清晨 06:00:还没到任何用药点 → now 指向下一个最近到点项(08:00),不是更晚的。"""
    import app.services.today_timeline_service as svc

    user, _ = auth_user_and_headers
    early = _add_med(db, user.id, "早八点药", category="处方药", reminder="08:00")
    _add_med(db, user.id, "晚药", category="处方药", reminder="20:00")

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            base = datetime(2026, 6, 15, 22, 0, tzinfo=timezone.utc)  # = 06:00 次日上海
            return base.astimezone(tz) if tz else base.replace(tzinfo=None)

    monkeypatch.setattr(svc, "datetime", FixedDateTime)

    spine = build_today_spine(db, user.id)
    now_item = next(it for it in spine["items"] if it["id"] == spine["now"])
    assert now_item["complete_ref"]["object_id"] == early.id, "未到点时 now 取下一个最近的"


# ───────────────── 3. 全部服完 → done,不在 actionable ─────────────────

def test_completed_medication_grouped_done_not_upcoming(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    med = _add_med(db, user.id, "已服药", category="处方药", reminder="08:00", times_per_day=1)
    _log_taken(db, user.id, med.id, "08:00")  # 1/1 完成

    spine = build_today_spine(db, user.id)
    item = next(it for it in spine["items"]
                if it.get("complete_ref") == {"object_type": "medication", "object_id": med.id})
    assert item["status"] == "completed"
    assert item["can_complete"] is False
    # 不计入 actionable
    assert all(
        not (it.get("complete_ref") == {"object_type": "medication", "object_id": med.id}
             and it["can_complete"])
        for it in spine["items"]
    )


def test_multidose_partial_is_still_pending(db, auth_user_and_headers):
    """每日 2 次只服 1 次 → 仍 pending(taken<total)。"""
    user, _ = auth_user_and_headers
    med = _add_med(db, user.id, "一天两次药", category="处方药", reminder="08:00", times_per_day=2)
    _log_taken(db, user.id, med.id, "08:00")  # 1/2

    spine = build_today_spine(db, user.id)
    item = next(it for it in spine["items"]
                if it.get("complete_ref") == {"object_type": "medication", "object_id": med.id})
    assert item["status"] == "pending"
    assert item["can_complete"] is True


# ───────────────── 4. 不双份:schedule 的药不另作 daily-plan 行动 ─────────────────

def test_medication_not_double_counted(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    med = _add_med(db, user.id, "唯一药", category="处方药", reminder="08:00")

    spine = build_today_spine(db, user.id)
    med_rows = [
        it for it in spine["items"]
        if it.get("complete_ref") == {"object_type": "medication", "object_id": med.id}
    ]
    assert len(med_rows) == 1, "同一药只应出现一行(不在 schedule 与 daily-plan 双份)"


# ───────────────── 5. 时间排序:scheduled_for 升序,anytime 在后 ─────────────────

def test_items_time_ordered_timed_before_anytime(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    _add_med(db, user.id, "晚药20点", category="处方药", reminder="20:00")
    _add_med(db, user.id, "早药06点", category="处方药", reminder="06:00")
    _add_med(db, user.id, "午药12点", category="处方药", reminder="12:00")

    spine = build_today_spine(db, user.id)
    timed = [it["scheduled_for"] for it in spine["items"] if it.get("scheduled_for")]
    # 有时点项严格升序
    assert timed == sorted(timed), f"带时点项应按时间升序,实得 {timed}"

    # 任何 anytime(无时点)项都排在所有有时点项之后
    seen_anytime = False
    for it in spine["items"]:
        if it.get("scheduled_for") is None:
            seen_anytime = True
        elif seen_anytime:
            pytest.fail("有时点项不应排在无时点(anytime)项之后")


# ───────────────── 6. 用户隔离 ─────────────────

def test_user_isolation(db, auth_user_and_headers):
    from tests.conftest import create_authenticated_user

    me, _ = auth_user_and_headers
    other, _ = create_authenticated_user(db)
    my_med = _add_med(db, me.id, "我的药", category="处方药", reminder="09:00")
    _add_med(db, other.id, "别人的药", category="处方药", reminder="09:00")

    spine = build_today_spine(db, me.id)
    refs = {
        (it["complete_ref"]["object_type"], it["complete_ref"]["object_id"])
        for it in spine["items"] if it.get("complete_ref")
    }
    assert ("medication", my_med.id) in refs
    # 别人的药 id 绝不出现
    other_med_ids = {
        it["complete_ref"]["object_id"]
        for it in spine["items"]
        if it.get("complete_ref") and it["complete_ref"]["object_type"] == "medication"
    }
    assert all(
        db.query(Medication).filter(Medication.id == mid, Medication.user_id == me.id).first()
        for mid in other_med_ids
    ), "脊柱只应含调用者自己的药"


# ───────────────── 7. 既有消费者 shape 保留 + 闭环可完成 ─────────────────

def test_existing_shape_preserved_with_meds(client, db, auth_user_and_headers):
    user, h = auth_user_and_headers
    _add_med(db, user.id, "API 测试药", category="处方药", reminder="08:00")

    r = client.get("/api/v1/timeline/today", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    # 既有顶层字段仍在 + 新增 now
    assert {"date", "current_window", "items", "past", "counts"} <= set(body.keys())
    assert "now" in body
    # 既有 item 字段仍在 + 新增 scheduled_for / driver 透传(response_model 未剥)
    med_item = next(it for it in body["items"]
                    if it.get("complete_ref")
                    and it["complete_ref"]["object_type"] == "medication")
    for key in ("id", "kind", "time_window", "title", "subtitle", "icon", "color",
                "status", "priority", "can_complete", "complete_ref", "event_id",
                "action_kind", "deep_link", "severity", "proof", "scheduled_for", "driver"):
        assert key in med_item, f"item 缺字段 {key}"
    # 可完成项已物化 first-class event_id → 可走闭环完成端点
    assert med_item["event_id"] is not None


def test_medication_closes_loop_via_complete_endpoint(client, db, auth_user_and_headers):
    """脊柱里的药 → 调 /timeline/events/{id}/complete done → 下次脊柱该项熄灭(不双写)。"""
    user, h = auth_user_and_headers
    med = _add_med(db, user.id, "闭环药", category="处方药", reminder="08:00")

    body1 = client.get("/api/v1/timeline/today", headers=h).json()
    item = next(it for it in body1["items"]
                if it.get("complete_ref") == {"object_type": "medication", "object_id": med.id})
    event_id = item["event_id"]
    assert event_id is not None

    r = client.post(f"/api/v1/timeline/events/{event_id}/complete",
                    headers=h, json={"status": "done"})
    assert r.status_code == 200, r.text

    # 二次读:该药项已熄灭(completed、不可再完成)
    body2 = client.get("/api/v1/timeline/today", headers=h).json()
    item2 = next(it for it in body2["items"]
                 if it.get("complete_ref") == {"object_type": "medication", "object_id": med.id})
    assert item2["status"] == "completed"
    assert item2["can_complete"] is False
