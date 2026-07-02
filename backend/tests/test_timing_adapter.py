"""medication/supplement → Item adapter 测试。用真 Medication 模型(防字段漂移)。
端到端验证 adapter→solver 跑通 + 螯合间隔生效。见 planning-methodology §5。
"""
from app.models.medication import Medication
from app.services.timing_adapter import medication_to_item, medications_to_items
from app.services.timing_solver import (
    ANCHOR_ANYTIME,
    ANCHOR_BEDTIME,
    ANCHOR_BEFORE_MEAL_30,
    DayContext,
    solve_day_schedule,
)

WIDE = dict(quiet_hours=("23:30", "05:00"))


def _med(**kw):
    return Medication(**kw)


def test_prescription_med_mapping():
    it = medication_to_item(_med(
        id=1, name="雷贝拉唑", category="处方药",
        timing_relation="before_meal_30", meal_anchor="breakfast",
        reminder_times=["07:00"]))
    assert it.id == "med:1"
    assert it.domain == "medication"
    assert it.anchor == ANCHOR_BEFORE_MEAL_30
    assert it.anchor_ref == "breakfast"
    assert it.fixed_time == "07:00"      # reminder_times → 固定时点
    assert it.deferrable is False        # 处方药必达
    assert it.severity == 70


def test_supplement_mapping():
    it = medication_to_item(_med(
        id=11, name="甘氨酸镁", category="supplement", timing_relation="bedtime"))
    assert it.domain == "supplement"
    assert it.anchor == ANCHOR_BEDTIME
    assert it.deferrable is True         # 补剂 timing 是优化,可顺延
    assert it.severity == 50
    assert it.fixed_time is None


def test_chinese_supplement_category_mapping():
    # 中文 category「补剂」必须归 supplement 域,否则脊柱投影/反向完成 ref 全按药展示
    for cat in ("补剂", "保健品", "膳食补充剂"):
        it = medication_to_item(_med(id=12, name="维生素D3", category=cat))
        assert it.domain == "supplement", cat
        assert it.deferrable is True


def test_no_timing_relation_is_anytime():
    it = medication_to_item(_med(id=2, name="某药", category="处方药"))
    assert it.anchor == ANCHOR_ANYTIME


def test_forbidden_reason_marks_hard_forbidden():
    it = medication_to_item(
        _med(id=3, name="维生素K", category="supplement"),
        forbidden_reason="维K×华法林直接拮抗")
    assert it.hard_forbidden is True
    assert "拮抗" in it.forbidden_reason


def test_chelation_calcium_iron_constraint_added():
    items = medications_to_items([
        _med(id=1, name="柠檬酸钙", category="supplement", timing_relation="with_meal", meal_anchor="dinner"),
        _med(id=2, name="铁剂(富马酸亚铁)", category="supplement", timing_relation="empty_stomach"),
    ])
    cal = next(it for it in items if it.id == "med:1")
    assert ("med:2", 2.0) in cal.interval_constraints


def test_levothyroxine_4h_from_calcium_and_iron():
    items = medications_to_items([
        _med(id=1, name="左甲状腺素钠片", category="处方药", timing_relation="empty_stomach"),
        _med(id=2, name="碳酸钙", category="supplement"),
        _med(id=3, name="铁剂", category="supplement"),
    ])
    levo = next(it for it in items if it.id == "med:1")
    assert ("med:2", 4.0) in levo.interval_constraints
    assert ("med:3", 4.0) in levo.interval_constraints


def test_forbidden_id_propagates_via_medications_to_items():
    items = medications_to_items(
        [_med(id=5, name="圣约翰草", category="supplement")],
        forbidden_reasons={5: "圣约翰草×处方药 CYP3A4 诱导"})
    assert items[0].hard_forbidden is True


def test_end_to_end_adapter_then_solver_spaces_calcium_iron():
    # adapter→solver 跑通:钙(08:00)与铁(08:30)经螯合约束被拉开≥2h
    items = medications_to_items([
        _med(id=1, name="柠檬酸钙", category="supplement", timing_relation="with_meal",
             meal_anchor="breakfast", reminder_times=["08:00"]),
        _med(id=2, name="铁剂", category="supplement", timing_relation="empty_stomach",
             reminder_times=["08:30"]),
    ])
    res = solve_day_schedule(items, DayContext(**WIDE))
    times = {s["id"]: s["time"] for s in res["scheduled"]}
    assert "med:1" in times and "med:2" in times

    def tom(t):
        h, m = t.split(":")
        return int(h) * 60 + int(m)
    assert abs(tom(times["med:1"]) - tom(times["med:2"])) >= 120
