"""今日脊柱诚实计数(alert-fatigue 修复):

BUG 1 —— BID/TID(每日多次)用药把 rollup「待办」数吹高:
  展示层仍按时段保留可分别打卡的子项,但 counts["actionable"] 按 (medication_id, date)
  去重 —— 一种药当天算 1 个待办单位,不是 N 个时段。已完成口径与「未完成」对称
  (同一药按「有任一 slot 待办 → 未完成 1」/「全 slot 已服 → 完成 1」)。

BUG 2 —— past-due 待办从不下沉(status 'overdue' 永不置位):
  过了服药时点(超过 2h 宽限窗、按 Asia/Shanghai)且未完成的项 → status='overdue',
  且排序下沉到当前待办之后;合理窗口内(刚过一会儿)的不误判 overdue。

时钟全部钉死(CI 是 UTC runner,墙钟断言会 flake);中国时间用 UTC base + astimezone。
只读投影,不改用户实际用药 schedule,不动 R4(纯计数/展示/排序口径)。
"""
from datetime import date, datetime, timezone

import pytest

from app.models.medication import Medication, MedicationLog
from app.services.today_timeline_service import build_today_spine


def _add_med(db, user_id, name, *, category, reminder_times, times_per_day):
    """带显式 reminder_times 列表(BID/TID 需多个确定时点)。"""
    m = Medication(
        user_id=user_id,
        name=name,
        category=category,
        times_per_day=times_per_day,
        reminder_times=reminder_times,
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


def _fix_clock(monkeypatch, *, utc_hour, utc_minute=0, on_day=(2026, 6, 16)):
    """把 today_timeline_service.datetime.now 钉到固定 UTC 时刻。

    Asia/Shanghai = UTC+8:传 utc_hour=7 → 上海 15:00(下午,所有清晨/午间项已过点)。
    无 user profile → get_user_timezone 回退 OS(CI 已 export TZ=Asia/Shanghai)。
    """
    import app.services.today_timeline_service as svc

    y, mo, d = on_day

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            base = datetime(y, mo, d, utc_hour, utc_minute, tzinfo=timezone.utc)
            return base.astimezone(tz) if tz else base.replace(tzinfo=None)

    monkeypatch.setattr(svc, "datetime", FixedDateTime)


# ═══════════════════ BUG 1:BID/TID 不把 rollup 吹高 ═══════════════════

def test_multidose_med_counts_as_one_actionable_unit(db, auth_user_and_headers, monkeypatch):
    """一种 TID 药(3 时段全未服)+ 一种 QD 药 → actionable 计数 = 2(药的种类数),
    不是 4(3 时段 + 1)。展示层仍给 3 个可分别打卡的时段子项。"""
    # 早 08:00 → 上海时间上午;钉时钟到早上 07:00 上海(UTC 23:00 前一日),让所有项都还没到点,
    # 避免与 BUG 2 的 overdue 下沉/熄灭交叉污染本用例(本用例只验计数)。
    _fix_clock(monkeypatch, utc_hour=23, on_day=(2026, 6, 15))  # = 次日 07:00 上海

    user, _ = auth_user_and_headers
    tid = _add_med(db, user.id, "一天三次药", category="处方药",
                   reminder_times=["08:00", "13:00", "20:00"], times_per_day=3)
    qd = _add_med(db, user.id, "一天一次药", category="处方药",
                  reminder_times=["09:00"], times_per_day=1)

    spine = build_today_spine(db, user.id)

    # 展示层:TID 药仍展开为 3 个时段子项(可分别打卡)
    tid_rows = [
        it for it in spine["items"]
        if it.get("complete_ref")
        and it["complete_ref"].get("object_type") == "medication"
        and it["complete_ref"].get("object_id") == tid.id
    ]
    assert len(tid_rows) == 3, f"TID 展示层应保留 3 个时段子项,实得 {len(tid_rows)}"
    slots = {r["complete_ref"].get("slot") for r in tid_rows}
    assert slots == {"08:00", "13:00", "20:00"}, f"三个子项应各带独立 slot,实得 {slots}"

    # rollup:actionable 按药去重 —— TID 算 1、QD 算 1 → 共 2(不是 3+1=4)
    assert spine["counts"]["actionable"] == 2, (
        f"actionable 应按 (medication_id,date) 去重 = 药种类数 2,"
        f"实得 {spine['counts']['actionable']}(时段被当独立待办充数)"
    )


def test_multidose_partial_taken_still_one_actionable_and_shows_progress(
    db, auth_user_and_headers, monkeypatch,
):
    """TID 药服了 1/3 → 仍算 1 个待办单位(还有 2 时段未服);子项 subtitle 给 x/y 进度。"""
    _fix_clock(monkeypatch, utc_hour=23, on_day=(2026, 6, 15))  # 07:00 上海

    user, _ = auth_user_and_headers
    tid = _add_med(db, user.id, "三次药部分服", category="处方药",
                   reminder_times=["08:00", "13:00", "20:00"], times_per_day=3)
    _log_taken(db, user.id, tid.id, "08:00")  # 1/3

    spine = build_today_spine(db, user.id)

    # 仍是 1 个待办单位(有未服时段)
    assert spine["counts"]["actionable"] == 1, (
        f"部分服完的 TID 药仍算 1 个待办单位,实得 {spine['counts']['actionable']}"
    )

    # 子项进度用 x/y(诚实粒度,不是把每时段当独立待办)
    tid_rows = [
        it for it in spine["items"]
        if it.get("complete_ref")
        and it["complete_ref"].get("object_id") == tid.id
    ]
    assert any("1/3" in (r.get("subtitle") or "") for r in tid_rows), (
        f"多剂子项 subtitle 应含 today 进度 1/3,实得 "
        f"{[r.get('subtitle') for r in tid_rows]}"
    )


def test_multidose_all_taken_symmetric_completed_not_actionable(
    db, auth_user_and_headers, monkeypatch,
):
    """TID 药 3 时段全服 → actionable 计数不含它(0);已完成口径与未完成对称
    (按药算 1 个已完成单位,不是把已服时段各算一个)。"""
    _fix_clock(monkeypatch, utc_hour=23, on_day=(2026, 6, 15))  # 07:00 上海

    user, _ = auth_user_and_headers
    tid = _add_med(db, user.id, "三次药全服", category="处方药",
                   reminder_times=["08:00", "13:00", "20:00"], times_per_day=3)
    for hhmm in ("08:00", "13:00", "20:00"):
        _log_taken(db, user.id, tid.id, hhmm)

    spine = build_today_spine(db, user.id)

    # 全服完 → 该药不再计入 actionable
    assert spine["counts"]["actionable"] == 0, (
        f"全部时段已服的 TID 药不应计入 actionable,实得 {spine['counts']['actionable']}"
    )
    tid_rows = [
        it for it in spine["items"]
        if it.get("complete_ref") and it["complete_ref"].get("object_id") == tid.id
    ]
    assert tid_rows, "全服的多剂药仍应作为(已完成)子项出现,不凭空消失"
    assert all(r["status"] == "completed" for r in tid_rows), (
        f"全服时段子项应全 completed,实得 {[r['status'] for r in tid_rows]}"
    )
    assert all(r["can_complete"] is False for r in tid_rows), "已服子项不可再完成"


# ═══════════════════ BUG 2:past-due 下沉 + status overdue ═══════════════════

def test_pastdue_item_marked_overdue_and_sinks_below_current(
    db, auth_user_and_headers, monkeypatch,
):
    """钉到下午 15:00 上海:早 08:00 药(超 2h 宽限 → overdue)+ 15:30 药(当前项)。
    断言早药 status='overdue' 且排在当前 15:30 项之后(下沉);当前项不 overdue、在前。"""
    _fix_clock(monkeypatch, utc_hour=7, on_day=(2026, 6, 16))  # UTC 07:00 = 上海 15:00

    user, _ = auth_user_and_headers
    stale = _add_med(db, user.id, "清晨漏服药", category="处方药",
                     reminder_times=["08:00"], times_per_day=1)
    current = _add_med(db, user.id, "此刻药", category="处方药",
                       reminder_times=["15:30"], times_per_day=1)

    spine = build_today_spine(db, user.id)
    items = spine["items"]

    def _find(med_id):
        return next(
            it for it in items
            if it.get("complete_ref")
            and it["complete_ref"].get("object_id") == med_id
            and it["complete_ref"].get("object_type") == "medication"
        )

    stale_item = _find(stale.id)
    current_item = _find(current.id)

    # 08:00 已过 15:00 逾 7h(> 2h 宽限)→ overdue
    assert stale_item["status"] == "overdue", (
        f"清晨 08:00 项到下午 15:00 应判 overdue,实得 status={stale_item['status']}"
    )
    # 15:30(还没到 / 刚要到)→ 不是 overdue
    assert current_item["status"] != "overdue", (
        f"15:30 当前项不应 overdue,实得 status={current_item['status']}"
    )

    # counts 反映真实 overdue 数(此前恒 0)
    assert spine["counts"]["overdue"] == 1, (
        f"counts.overdue 应为 1,实得 {spine['counts']['overdue']}"
    )

    # 下沉:overdue 项排在当前(非 overdue)可完成项之后
    idx = {id(it): i for i, it in enumerate(items)}
    assert idx[id(stale_item)] > idx[id(current_item)], (
        "overdue 清晨项应下沉排到当前项之后(现在该做的浮在顶部)"
    )


def test_recent_item_within_grace_not_overdue(db, auth_user_and_headers, monkeypatch):
    """边界:07:00 药 + 钉到 08:00 上海(仅过 1h,< 2h 宽限)→ 不误判 overdue。
    避免早上刚过一会儿就把项打成过期。"""
    _fix_clock(monkeypatch, utc_hour=0, on_day=(2026, 6, 16))  # UTC 00:00 = 上海 08:00

    user, _ = auth_user_and_headers
    recent = _add_med(db, user.id, "刚过一小时药", category="处方药",
                      reminder_times=["07:00"], times_per_day=1)

    spine = build_today_spine(db, user.id)
    item = next(
        it for it in spine["items"]
        if it.get("complete_ref") and it["complete_ref"].get("object_id") == recent.id
    )
    assert item["status"] != "overdue", (
        f"07:00 项到 08:00 仅过 1h(< 2h 宽限)不应 overdue,实得 {item['status']}"
    )
    assert spine["counts"]["overdue"] == 0


def test_completed_pastdue_item_not_marked_overdue(db, auth_user_and_headers, monkeypatch):
    """已完成的过期时点项不该被标 overdue(只对未完成项标 + 下沉)。"""
    _fix_clock(monkeypatch, utc_hour=7, on_day=(2026, 6, 16))  # 上海 15:00

    user, _ = auth_user_and_headers
    med = _add_med(db, user.id, "清晨已服药", category="处方药",
                   reminder_times=["08:00"], times_per_day=1)
    _log_taken(db, user.id, med.id, "08:00")

    spine = build_today_spine(db, user.id)
    item = next(
        it for it in spine["items"]
        if it.get("complete_ref") and it["complete_ref"].get("object_id") == med.id
    )
    assert item["status"] == "completed", "已服项应保持 completed,不被 overdue 覆盖"
    assert spine["counts"]["overdue"] == 0
