"""每日时点约束求解器测试。核心安全不变量:
- 硬禁忌(DDI/DSI/PGx)绝不排上时间轴(走 rejected/告警)
- Red 恢复不足绝不排力量
- 螯合间隔满足,多约束冲突取「更长者优先」
- 锚点落桩正确(空腹/餐前30/随餐/睡前/围训练)
- prescribed 固定剂量即使落静默窗也不被丢弃(R4 不漏给药)
- 复查每日配额、确定性
见 docs/design/health-os/planning-methodology.md §5。
"""
from app.services.timing_solver import (
    ANCHOR_AFTER_MEAL,
    ANCHOR_ANYTIME,
    ANCHOR_BEDTIME,
    ANCHOR_BEFORE_MEAL_30,
    ANCHOR_EMPTY_STOMACH,
    ANCHOR_PERI_WORKOUT_POST,
    ANCHOR_PERI_WORKOUT_PRE,
    ANCHOR_WITH_MEAL,
    GREEN,
    RED,
    DayContext,
    Item,
    solve_day_schedule,
)

# 宽白天静默窗(23:30–05:00),供间隔/配额测试避开晨间默认静默
WIDE = dict(quiet_hours=("23:30", "05:00"))


def _by_id(res):
    return {s["id"]: s for s in res["scheduled"]}


def _rej_ids(res):
    return {r["id"] for r in res["rejected"]}


def _gap(res, a, b):
    m = {s["id"]: s["time"] for s in res["scheduled"]}

    def tom(t):
        h, mm = t.split(":")
        return int(h) * 60 + int(mm)

    return abs(tom(m[a]) - tom(m[b]))


# ── 安全:硬禁忌 / Red+力量 ────────────────────────────────────────────────
def test_hard_forbidden_never_scheduled():
    it = Item(id="vitk", domain="supplement", title="维K", hard_forbidden=True,
              forbidden_reason="维K×华法林直接拮抗 → 走告警")
    res = solve_day_schedule([it], DayContext())
    assert "vitk" in _rej_ids(res)
    assert not res["scheduled"]
    assert "拮抗" in res["rejected"][0]["reason"]


def test_red_rejects_strength():
    it = Item(id="pushup", domain="movement", title="俯卧撑", requires_strength=True)
    res = solve_day_schedule([it], DayContext(readiness=RED))
    assert "pushup" in _rej_ids(res)
    assert not res["scheduled"]


def test_green_allows_strength():
    it = Item(id="pushup", domain="movement", title="俯卧撑", requires_strength=True)
    res = solve_day_schedule([it], DayContext(readiness=GREEN))
    assert "pushup" in _by_id(res)


# ── 锚点落桩 ────────────────────────────────────────────────────────────────
def test_anchor_placements():
    ctx = DayContext()  # 早餐07:30 晚餐18:30 起床07:00 睡22:30
    items = [
        Item(id="ppi", domain="medication", title="PPI", anchor=ANCHOR_BEFORE_MEAL_30, anchor_ref="breakfast"),
        Item(id="d3", domain="supplement", title="维D3", anchor=ANCHOR_WITH_MEAL, anchor_ref="dinner"),
        Item(id="mag", domain="supplement", title="镁", anchor=ANCHOR_BEDTIME),
        Item(id="iron", domain="supplement", title="铁", anchor=ANCHOR_EMPTY_STOMACH),
        Item(id="walk", domain="movement", title="午后步行", anchor=ANCHOR_AFTER_MEAL, anchor_ref="lunch"),
    ]
    s = _by_id(solve_day_schedule(items, ctx))
    assert s["ppi"]["time"] == "07:00"   # 07:30 - 30min
    assert s["d3"]["time"] == "18:30"    # 随晚餐
    assert s["mag"]["time"] == "21:45"   # 22:30 - 45min
    assert s["iron"]["time"] == "07:00"  # min(起床+15, 早餐-30)
    assert s["walk"]["time"] == "12:20"  # 午餐12:00 + 20min


def test_morning_fasting_med_not_shifted_by_quiet():
    # 默认静默窗 22:00–08:30 覆盖晨间;空腹药锚定真实作息,绝不被顺延到 08:30
    it = Item(id="levo", domain="medication", title="左甲状腺素", anchor=ANCHOR_EMPTY_STOMACH)
    s = _by_id(solve_day_schedule([it], DayContext()))
    assert s["levo"]["time"] == "07:00"


def test_peri_workout_placement():
    ctx = DayContext(workout_start="18:00", **WIDE)
    items = [
        Item(id="pre", domain="diet", title="练前碳水", anchor=ANCHOR_PERI_WORKOUT_PRE),
        Item(id="post", domain="diet", title="练后蛋白", anchor=ANCHOR_PERI_WORKOUT_POST),
    ]
    s = _by_id(solve_day_schedule(items, ctx))
    assert s["pre"]["time"] == "16:30"   # 18:00 - 90min
    assert s["post"]["time"] == "19:00"  # 18:00 + 60min


def test_peri_without_workout_falls_back_not_dropped():
    it = Item(id="pre", domain="diet", title="练前碳水", anchor=ANCHOR_PERI_WORKOUT_PRE)
    res = solve_day_schedule([it], DayContext())  # 无 workout
    assert "pre" in _by_id(res)  # 仍排上(退化到 fallback),不丢


# ── 处方固定时点 vs 静默窗(R4 不漏给药)───────────────────────────────────
def test_prescribed_fixed_time_in_quiet_stays():
    it = Item(id="night_med", domain="medication", title="夜间药",
              fixed_time="23:00", deferrable=False)
    res = solve_day_schedule([it], DayContext())  # quiet 22:00–08:30
    s = _by_id(res)
    assert s["night_med"]["time"] == "23:00"  # 处方必达,绝不顺延/丢弃
    assert not res["deferred"]


def test_floating_nudge_in_quiet_shifted_out():
    it = Item(id="water", domain="diet", title="补水提醒",
              anchor=ANCHOR_ANYTIME, fixed_time="23:30", deferrable=True)
    s = _by_id(solve_day_schedule([it], DayContext()))
    assert s["water"]["time"] == "08:30"  # 浮动 nudge 顺延到静默窗结束


# ── 螯合间隔约束 ────────────────────────────────────────────────────────────
def test_interval_calcium_iron_2h():
    items = [
        Item(id="iron", domain="supplement", title="铁", fixed_time="10:00", deferrable=False, severity=70),
        Item(id="cal", domain="supplement", title="钙", fixed_time="10:30", deferrable=True, severity=40,
             interval_constraints=[("iron", 2.0)]),
    ]
    res = solve_day_schedule(items, DayContext(**WIDE))
    assert _gap(res, "cal", "iron") >= 120  # 低优先的钙让步,间隔≥2h


def test_longer_interval_wins():
    # 左甲状腺素×铁 ≥4h 优先于 钙×铁 ≥2h
    items = [
        Item(id="levo", domain="medication", title="左甲状腺素", fixed_time="08:00", deferrable=False, severity=90),
        Item(id="iron", domain="supplement", title="铁", fixed_time="08:15", deferrable=True, severity=50,
             interval_constraints=[("levo", 4.0)]),
        Item(id="cal", domain="supplement", title="钙", fixed_time="08:20", deferrable=True, severity=40,
             interval_constraints=[("iron", 2.0)]),
    ]
    res = solve_day_schedule(items, DayContext(**WIDE))
    assert _gap(res, "iron", "levo") >= 240
    assert _gap(res, "cal", "iron") >= 120


def test_interval_holds_for_anytime_items():
    # 两个无锚点(anytime)螯合项也必须满足 ≥2h 间隔 —— 不能只靠 +30min 错开。
    # 回归:之前 anytime 项在间隔 pass 时还是 None 被跳过,只隔 30min。
    items = [
        Item(id="cal", domain="supplement", title="钙", anchor=ANCHOR_ANYTIME, severity=40,
             interval_constraints=[("iron", 2.0)]),
        Item(id="iron", domain="supplement", title="铁", anchor=ANCHOR_ANYTIME, severity=70),
    ]
    res = solve_day_schedule(items, DayContext(**WIDE))
    assert "cal" in _by_id(res) and "iron" in _by_id(res)  # 两项都排上
    assert _gap(res, "cal", "iron") >= 120  # 间隔≥2h,与锚点无关


# ── 复查配额 / 确定性 ──────────────────────────────────────────────────────
def test_recheck_daily_cap():
    items = [
        Item(id=f"chk{i}", domain="checkup", title=f"复查{i}",
             fixed_time="10:00", deferrable=True, severity=90 - i * 10)
        for i in range(4)
    ]
    res = solve_day_schedule(items, DayContext(daily_recheck_cap=2, **WIDE))
    sched = [s for s in res["scheduled"] if s["domain"] == "checkup"]
    assert len(sched) == 2
    deferred = {d["id"] for d in res["deferred"]}
    assert {"chk2", "chk3"} <= deferred  # severity 低的两条顺延


def test_deterministic():
    def build():
        return [Item(id=f"x{i}", domain="supplement", title=str(i), anchor=ANCHOR_ANYTIME) for i in range(6)]
    assert solve_day_schedule(build(), DayContext()) == solve_day_schedule(build(), DayContext())


def test_empty_input():
    res = solve_day_schedule([], DayContext())
    assert res == {"scheduled": [], "rejected": [], "deferred": []}
