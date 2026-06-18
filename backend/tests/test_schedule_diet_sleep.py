"""智能日程 D1(三餐+营养)+ D2(睡眠卫生)测试。

覆盖:
  - 三餐 diet 项在 ctx.meals 时点产出(纯函数 + e2e)
  - 围训练餐对齐到训练结束后 ≤60min
  - nutrition_prescription:蛋白目标(weight×load)+ 基因 note(fuel_strategist 复用)
  - sleep wind-down + caffeine cutoff,慢 CYP1A2 → 截止更早
  - fail-soft:twin/fuel 失败 → 纯餐项 / 默认睡眠卫生,不崩
"""
from types import SimpleNamespace

import pytest

from app.services.schedule_diet_sleep import (
    align_post_workout_meal,
    meal_items,
    nutrition_prescription,
    sleep_items,
    sleep_prescription,
)
from app.services.day_schedule_service import schedule_from_medications
from app.services.timing_solver import DayContext


def _t(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


# ── D1 餐项(纯函数)──────────────────────────────────────────────────────
def test_meal_items_at_meal_times():
    ctx = DayContext()  # breakfast 07:30 / lunch 12:00 / dinner 18:30
    items = meal_items(ctx)
    by_id = {it.id: it for it in items}
    assert set(by_id) == {"meal:breakfast", "meal:lunch", "meal:dinner"}
    assert by_id["meal:breakfast"].fixed_time == "07:30"
    assert by_id["meal:lunch"].fixed_time == "12:00"
    assert by_id["meal:dinner"].fixed_time == "18:30"
    for it in items:
        assert it.domain == "diet"
        assert it.deferrable is False
        assert it.severity == 45


def test_meal_items_carry_nutrition_prescription():
    ctx = DayContext()
    rx = {"kcal_target": 2400, "protein_g": 130, "protein_per_meal_g": 43,
          "gene_note": "FTO 风险型:每餐保证蛋白", "carb_timing": "围训练加碳水"}
    items = meal_items(ctx, rx)
    bf = next(it for it in items if it.id == "meal:breakfast")
    assert bf.prescription["protein_g"] == 130
    assert bf.prescription["kcal_target"] == 2400
    # 非围训练餐(无 workout_start)→ carb_timing 被剥掉,避免每餐都喊碳水
    assert "carb_timing" not in bf.prescription


def test_meal_items_e2e_in_schedule():
    rx = {"kcal_target": 2200, "protein_g": 120, "protein_per_meal_g": 40}
    res = schedule_from_medications([], nutrition_rx=rx)
    diet = {s["id"]: s for s in res["scheduled"] if s["domain"] == "diet"}
    assert set(diet) == {"meal:breakfast", "meal:lunch", "meal:dinner"}
    assert diet["meal:lunch"]["time"] == "12:00"
    assert diet["meal:lunch"]["prescription"]["protein_g"] == 120


# ── D1 围训练餐对齐 ────────────────────────────────────────────────────────
def test_post_workout_meal_shift_within_60min():
    # 训练 16:30 开始 40min → 结束 17:10。晚餐默认 18:30(>结束+60=18:10)→ 应被拉近。
    ctx = DayContext()
    ctx.workout_start = "16:30"
    align_post_workout_meal(ctx, workout_minutes=40)
    end = _t("16:30") + 40
    dinner = _t(ctx.meals["dinner"])
    assert 0 <= dinner - end <= 60, f"dinner {ctx.meals['dinner']} not within 60min of workout end"


def test_post_workout_meal_already_in_window_not_moved():
    # 训练 11:00 + 40 → 结束 11:40。午餐 12:00 已落在 [11:40, 12:40] → 不动。
    ctx = DayContext()
    ctx.workout_start = "11:00"
    align_post_workout_meal(ctx, workout_minutes=40)
    assert ctx.meals["lunch"] == "12:00"


def test_align_noop_without_workout():
    ctx = DayContext()
    before = dict(ctx.meals)
    align_post_workout_meal(ctx)
    assert ctx.meals == before


def test_post_workout_meal_anchors_meds_after_shift():
    # 锻炼后餐被移动 → 锚定该餐的随餐补剂应跟着移动(顺序:对齐 → meds 锚定)。
    from app.models.medication import Medication
    meds = [Medication(id=1, name="鱼油", category="supplement",
                       timing_relation="with_meal", meal_anchor="dinner")]
    profile = SimpleNamespace(
        usual_wake_time="07:00", usual_sleep_time="23:00",
        workout_pref_window="evening", workout_target_minutes=40,
        work_start_time=None, work_end_time=None,
    )
    # evening 窗会排锻炼并设 ctx.workout_start;晚餐被拉到训练后。
    res = schedule_from_medications(meds, profile=profile)
    sched = {s["id"]: s for s in res["scheduled"]}
    if "workout:today" in sched and "meal:dinner" in sched:
        # 鱼油锚 dinner → 与晚餐同/近时点
        assert abs(_t(sched["med:1"]["time"]) - _t(sched["meal:dinner"]["time"])) <= 30


# ── D1 营养处方(DB 层,真 twin)────────────────────────────────────────────
def _twin_with(weight_kg=None, load_7d=None, tdee=None, gene_variants=None):
    """构造一个可控 HealthTwin(monkeypatch build_twin 用),隔离 nutrition/sleep 逻辑。"""
    from datetime import datetime
    from app.twin.schema import (
        HealthTwin, TwinMeta, BodyCompositionState, BehavioralState, GeneticContext,
    )
    t = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.utcnow()))
    t.body_composition = BodyCompositionState(weight_kg=weight_kg, tdee_kcal=tdee)
    t.behavioral = BehavioralState(training_load_7d=load_7d)
    if gene_variants:
        t.genetic = GeneticContext(has_profile=True, nutrition_variants=gene_variants)
    return t


def test_nutrition_prescription_protein_and_gene(db, monkeypatch):
    import app.twin.builder as builder
    twin = _twin_with(
        weight_kg=70.0, load_7d=50, tdee=2400,
        gene_variants=[{"gene_name": "FTO", "result_label": "risk", "risk_level": "high",
                        "genotype": "TT"}],
    )
    monkeypatch.setattr(builder, "build_twin", lambda *a, **k: twin)
    rx = nutrition_prescription(db, 1)
    assert rx is not None
    # 70kg × 1.4(低活动)= 98g;per-meal ~33g
    assert rx["protein_g"] == 98
    assert rx["protein_per_meal_g"] == 33
    assert rx["kcal_target"] == 2400
    # FTO 风险型 → 基因 note 命中(fuel_strategist _gene_nudges 复用)
    assert "FTO" in (rx.get("gene_note") or "")


def test_nutrition_prescription_high_load_higher_protein(db, monkeypatch):
    import app.twin.builder as builder
    twin = _twin_with(weight_kg=70.0, load_7d=300)  # >200 → 1.8 g/kg
    monkeypatch.setattr(builder, "build_twin", lambda *a, **k: twin)
    rx = nutrition_prescription(db, 1)
    assert rx["protein_g"] == 126  # 70 × 1.8


def test_nutrition_prescription_failsoft_returns_none(db, monkeypatch):
    # build_twin imported inside the function → patch the builder module symbol.
    import app.twin.builder as builder
    monkeypatch.setattr(builder, "build_twin",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("twin boom")))
    rx = nutrition_prescription(db, 999)
    assert rx is None  # fail-soft → None, no crash


def test_failsoft_schedule_still_emits_plain_meals():
    # nutrition_rx=None(取数失败模拟)→ 纯餐项仍产出,不崩。
    res = schedule_from_medications([], nutrition_rx=None, sleep_rx=None)
    diet = [s for s in res["scheduled"] if s["domain"] == "diet"]
    assert len(diet) == 3
    for s in diet:
        assert s.get("prescription") is None


# ── D2 睡眠卫生(纯函数)────────────────────────────────────────────────────
def test_sleep_items_winddown_and_caffeine():
    ctx = DayContext()  # sleep 22:30
    items = sleep_items(ctx, {"caffeine_cutoff_hours": 6})
    by_id = {it.id: it for it in items}
    assert set(by_id) == {"sleep:winddown", "sleep:caffeine_cutoff"}
    assert by_id["sleep:winddown"].domain == "sleep"
    # caffeine cutoff = sleep - 6h = 16:30
    assert by_id["sleep:caffeine_cutoff"].fixed_time == "16:30"


def test_sleep_caffeine_cutoff_default_when_unknown():
    ctx = DayContext()
    items = sleep_items(ctx, None)  # fail-soft → default 8h
    cutoff = next(it for it in items if it.id == "sleep:caffeine_cutoff")
    # sleep 22:30 - 8h = 14:30
    assert cutoff.fixed_time == "14:30"


def test_sleep_items_e2e():
    ctx_over = {"sleep": "23:00"}
    res = schedule_from_medications([], sleep_rx={"caffeine_cutoff_hours": 9},
                                    ctx_overrides=ctx_over)
    sleep = {s["id"]: s for s in res["scheduled"] if s["domain"] == "sleep"}
    assert "sleep:winddown" in sleep
    assert "sleep:caffeine_cutoff" in sleep
    # winddown = sleep - 45 = 22:15
    assert sleep["sleep:winddown"]["time"] == "22:15"
    # cutoff = 23:00 - 9h = 14:00
    assert sleep["sleep:caffeine_cutoff"]["time"] == "14:00"


# ── D2 睡眠处方(DB 层,基因驱动)────────────────────────────────────────────
def _twin_with_caffeine(metab_label):
    """构造带 CYP1A2 变异的 twin,跑 build_gene_config → gene_config.caffeine_metabolism。"""
    from datetime import datetime
    from app.twin.schema import HealthTwin, TwinMeta, GeneticContext
    from app.twin.gene_config import build_gene_config
    t = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.utcnow()))
    t.genetic = GeneticContext(
        has_profile=True,
        total_variants=1,
        nutrition_variants=[{"gene_name": "CYP1A2", "result_label": metab_label,
                             "genotype": "AC", "risk_level": "info"}],
    )
    t.gene_config = build_gene_config(t)
    return t


def test_sleep_prescription_slow_cyp1a2_earlier_cutoff(db, monkeypatch):
    import app.twin.builder as builder
    twin_slow = _twin_with_caffeine("slow metabolizer")
    twin_fast = _twin_with_caffeine("fast metabolizer")
    assert twin_slow.gene_config.caffeine_metabolism == "slow"

    monkeypatch.setattr(builder, "build_twin", lambda *a, **k: twin_slow)
    rx_slow = sleep_prescription(db, 1)
    monkeypatch.setattr(builder, "build_twin", lambda *a, **k: twin_fast)
    rx_fast = sleep_prescription(db, 1)

    assert rx_slow is not None and rx_fast is not None
    # slow → 更久提前量(更早截止)
    assert rx_slow["caffeine_cutoff_hours"] > rx_fast["caffeine_cutoff_hours"]
    assert rx_slow["caffeine_cutoff_hours"] == 9
    assert rx_fast["caffeine_cutoff_hours"] == 6
    assert rx_slow.get("gene_note")  # 慢代谢带基因说明


def test_sleep_prescription_failsoft(db, monkeypatch):
    import app.twin.builder as builder
    monkeypatch.setattr(builder, "build_twin",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    rx = sleep_prescription(db, 12345)
    assert rx is None  # fail-soft

    # sleep_items still emits with default cutoff (no crash)
    items = sleep_items(DayContext(), rx)
    cutoff = next(it for it in items if it.id == "sleep:caffeine_cutoff")
    assert cutoff.prescription["cutoff_hours"] == 8
