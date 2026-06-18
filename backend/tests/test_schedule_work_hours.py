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


def test_profile_put_accepts_work_hours_roundtrip(client, db, auth_user_and_headers):
    """PUT /profile/me 接受 work_start_time/work_end_time(显式 schema 字段,不静默丢)→ GET 读回。"""
    user, headers = auth_user_and_headers
    r = client.put("/api/v1/profile/me", headers=headers,
                   json={"work_start_time": "09:00", "work_end_time": "18:00"})
    assert r.status_code == 200, r.text
    assert r.json()["work_start_time"] == "09:00" and r.json()["work_end_time"] == "18:00"
    g = client.get("/api/v1/profile/me", headers=headers)
    assert g.json()["work_start_time"] == "09:00" and g.json()["work_end_time"] == "18:00"


def test_anytime_chelators_keep_interval():
    # 两个「随时」螯合项(钙×铁,间隔 2h)即便都无锚点,也须 ≥2h(此前只 +30 错开)。
    from app.services.timing_solver import _to_min
    ca = Item(id="ca", domain="supplement", title="钙", anchor=ANCHOR_ANYTIME, deferrable=True,
              interval_constraints=[("fe", 2.0)])
    fe = Item(id="fe", domain="supplement", title="铁", anchor=ANCHOR_ANYTIME, deferrable=True,
              interval_constraints=[("ca", 2.0)])
    out = solve_day_schedule([ca, fe], DayContext(wake="07:00", quiet_hours=("22:00", "08:30")))
    t = {s["id"]: _to_min(s["time"]) for s in out["scheduled"]}
    assert abs(t["ca"] - t["fe"]) >= 120, f"anytime 螯合间隔不足 2h: {out['scheduled']}"


def test_anytime_items_avoid_busy_block():
    # 日历忙碌块 12:00–13:00(无工作窗)→ 浮动项避开。
    ctx = DayContext(wake="07:00", quiet_hours=("22:00", "08:30"), busy=[("12:00", "13:00")])
    out = solve_day_schedule(_floats(8), ctx)
    for s in out["scheduled"]:
        assert not ("12:00" <= s["time"] < "13:00"), f"{s['id']} 落进忙碌块 {s['time']}"


def test_busy_and_work_blocks_both_avoided():
    ctx = DayContext(wake="07:00", quiet_hours=("22:00", "08:30"),
                     work_start="09:00", work_end="12:00", is_workday=True, busy=[("13:00", "14:00")])
    out = solve_day_schedule(_floats(10), ctx)
    for s in out["scheduled"]:
        t = s["time"]
        assert not ("09:00" <= t < "12:00"), f"工作窗内: {t}"
        assert not ("13:00" <= t < "14:00"), f"忙碌块内: {t}"


def test_dirty_busy_block_skipped_not_crash():
    # 脏忙碌块(end<=start / 非法)跳过,不炸求解。
    ctx = DayContext(wake="07:00", busy=[("18:00", "09:00"), ("bad", "x")])
    out = solve_day_schedule(_floats(2), ctx)
    assert len(out["scheduled"]) == 2
