"""工作时间窗 → timing-solver 浮动项避开工作时段 + /schedule/today 端点(cut 6 接活)。"""
import datetime

from app.services.timing_solver import (
    Item, DayContext, solve_day_schedule, ANCHOR_ANYTIME, ANCHOR_WITH_MEAL,
)
from app.services.day_schedule_service import _day_context


def _floats(n):
    return [Item(id=f"x{i}", domain="supplement", title=f"灵活{i}",
                 anchor=ANCHOR_ANYTIME, deferrable=True) for i in range(n)]


def test_anytime_items_avoid_work_block():
    ctx = DayContext(work_start="09:00", work_end="18:00", is_workday=True,
                     wake="07:00", quiet_hours=("22:00", "08:30"))
    out = solve_day_schedule(_floats(4), ctx)
    for s in out["scheduled"]:
        assert not ("09:00" <= s["time"] < "18:00"), f"{s['id']} 落进工作时段 {s['time']}"


def test_anytime_items_fill_day_without_work_hours():
    # 对照组:不设工作窗 → 浮动项会排进上午(说明工作窗确实改变了行为)。
    ctx = DayContext(is_workday=True, wake="07:00", quiet_hours=("22:00", "08:30"))
    out = solve_day_schedule(_floats(4), ctx)
    times = [s["time"] for s in out["scheduled"]]
    assert any("09:00" <= t < "12:00" for t in times)


def test_non_workday_does_not_avoid_work():
    ctx = DayContext(work_start="09:00", work_end="18:00", is_workday=False,
                     wake="07:00", quiet_hours=("22:00", "08:30"))
    out = solve_day_schedule(_floats(3), ctx)
    times = [s["time"] for s in out["scheduled"]]
    assert any("09:00" <= t < "12:00" for t in times)  # 非工作日不避工作窗


def test_anchored_item_unaffected_by_work():
    # 锚点项(随早餐 07:30,在上班前)不受工作窗影响,正常排。
    ctx = DayContext(work_start="09:00", work_end="18:00", is_workday=True,
                     meals={"breakfast": "07:30", "lunch": "12:00", "dinner": "18:30"})
    out = solve_day_schedule(
        [Item(id="m", domain="medication", title="随餐药", anchor=ANCHOR_WITH_MEAL, anchor_ref="breakfast")],
        ctx,
    )
    assert out["scheduled"][0]["time"] == "07:30"


def test_day_context_reads_profile_work_hours():
    class P:
        usual_wake_time = "07:00"
        usual_sleep_time = "23:00"
        work_start_time = "09:30"
        work_end_time = "18:30"
    ctx = _day_context(P())
    assert ctx.work_start == "09:30" and ctx.work_end == "18:30"


def test_schedule_today_endpoint(client, db, auth_user_and_headers):
    from app.models.medication import Medication
    from app.models.user_profile import UserProfile
    user, headers = auth_user_and_headers
    db.add(Medication(user_id=user.id, name="维生素D", times_per_day=1, is_active=True))
    db.add(UserProfile(user_id=user.id, usual_wake_time="07:00", usual_sleep_time="23:00",
                       work_start_time="09:00", work_end_time="18:00"))
    db.commit()

    r = client.get("/api/v1/schedule/today", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) >= {"scheduled", "rejected", "deferred"}
    assert isinstance(body["scheduled"], list)
