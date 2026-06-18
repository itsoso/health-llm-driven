"""每日时点日程服务测试。纯核心(无 DB)+ 薄 DB 包装 smoke。
见 docs/design/health-os/planning-methodology.md §5。
"""
from types import SimpleNamespace

from app.models.medication import Medication
from app.services.day_schedule_service import (
    _day_context,
    build_day_schedule,
    schedule_from_medications,
)


def _med(**kw):
    return Medication(**kw)


def _t(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


# ── 纯核心 ────────────────────────────────────────────────────────────────
def test_realistic_regimen_schedules():
    # 创始人式组合:PPI 餐前 / 镁睡前 / 钙·铁(螯合)
    meds = [
        _med(id=1, name="雷贝拉唑", category="处方药", timing_relation="before_meal_30",
             meal_anchor="breakfast", reminder_times=["07:00"]),
        _med(id=2, name="甘氨酸镁", category="supplement", timing_relation="bedtime"),
        _med(id=3, name="柠檬酸钙", category="supplement", timing_relation="with_meal",
             meal_anchor="breakfast", reminder_times=["08:00"]),
        _med(id=4, name="铁剂", category="supplement", timing_relation="empty_stomach",
             reminder_times=["08:15"]),
    ]
    res = schedule_from_medications(meds, ctx_overrides={"quiet_hours": ("23:30", "05:00")})
    times = {s["title"]: s["time"] for s in res["scheduled"]}
    assert times["雷贝拉唑"] == "07:00"          # 处方固定时点
    # 钙×铁螯合 ≥2h
    assert abs(_t(times["柠檬酸钙"]) - _t(times["铁剂"])) >= 120


def test_profile_drives_bedtime():
    prof = SimpleNamespace(usual_wake_time="08:00", usual_sleep_time="23:30")
    meds = [_med(id=1, name="镁", category="supplement", timing_relation="bedtime")]
    res = schedule_from_medications(meds, profile=prof)
    # D1/D2 现在也会排三餐+睡眠卫生 → 定位镁这一项,不依赖位置。
    mg = next(s for s in res["scheduled"] if s["id"] == "med:1")
    assert mg["time"] == "22:45"  # 23:30 - 45min


def test_late_wake_shifts_breakfast_anchor():
    prof = SimpleNamespace(usual_wake_time="09:00", usual_sleep_time="23:30")
    ctx = _day_context(prof)
    assert ctx.meals["breakfast"] == "09:30"  # 晚起者早餐 = 起床+30
    # 餐前30min 的药随之到 09:00
    meds = [_med(id=1, name="PPI", category="处方药", timing_relation="before_meal_30",
                 meal_anchor="breakfast")]
    res = schedule_from_medications(meds, profile=prof)
    ppi = next(s for s in res["scheduled"] if s["id"] == "med:1")
    assert ppi["time"] == "09:00"


def test_forbidden_reason_rejects():
    meds = [_med(id=7, name="维生素K", category="supplement")]
    res = schedule_from_medications(meds, forbidden_reasons={7: "维K×华法林直接拮抗"})
    # 维K 被拒排;D1/D2 仍排三餐+睡眠(它们与 med 无关)→ 只断言 med 不在 scheduled。
    assert not any(s["id"] == "med:7" for s in res["scheduled"])
    assert res["rejected"][0]["id"] == "med:7"


def test_empty_profile_uses_defaults():
    ctx = _day_context(None)
    assert ctx.wake == "07:00" and ctx.sleep == "22:30"


# ── 薄 DB 包装 ──────────────────────────────────────────────────────────────
def test_build_day_schedule_filters_inactive(db):
    db.add(_med(user_id=1, name="甘氨酸镁", category="supplement", timing_relation="bedtime", is_active=True))
    db.add(_med(user_id=1, name="已停药", category="处方药", is_active=False))
    db.commit()
    res = build_day_schedule(db, user_id=1)
    titles = [s["title"] for s in res["scheduled"]]
    assert "甘氨酸镁" in titles
    assert "已停药" not in titles  # is_active=False 被过滤
