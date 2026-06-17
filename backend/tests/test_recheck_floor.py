"""复查间隔下限护栏测试。核心安全:绝不把复查排得短于生物下限或医嘱。
见 docs/design/health-os/planning-methodology.md §4.4/§8。
"""
from app.services.recheck_floor import (
    DEFAULT_FLOOR_DAYS,
    clamp_recheck_interval,
)


def test_hba1c_too_soon_clamped_to_biological_floor():
    r = clamp_recheck_interval("HBA1C", proposed_days=30)
    assert r["was_clamped"] is True
    assert r["allowed_days"] == 84
    assert r["bound_by"] == "biological"


def test_clinician_order_not_shortened():
    # 医嘱 120d,系统建议 60d → 不得短于医嘱
    r = clamp_recheck_interval("LDL", proposed_days=60, clinician_days=120)
    assert r["was_clamped"] is True
    assert r["allowed_days"] == 120
    assert r["bound_by"] == "clinician"
    assert "医嘱" in r["reason"]


def test_clinician_floor_binds_over_biological():
    # 生物下限 42(LDL),医嘱 90 → 绑定下限取更长的 90
    r = clamp_recheck_interval("LDL", proposed_days=200, clinician_days=90)
    assert r["was_clamped"] is False  # 200 >= 90,放行
    assert r["allowed_days"] == 200


def test_proposed_above_floor_passes_unchanged():
    r = clamp_recheck_interval("HBA1C", proposed_days=90)
    assert r["was_clamped"] is False
    assert r["allowed_days"] == 90
    assert r["bound_by"] == "none"


def test_unknown_metric_conservative_default():
    r = clamp_recheck_interval("SOME_NOVEL_MARKER", proposed_days=3)
    assert r["was_clamped"] is True
    assert r["allowed_days"] == DEFAULT_FLOOR_DAYS
    assert r["known_metric"] is False
    assert "医生确认" in r["reason"]


def test_none_proposed_uses_binding_floor():
    r = clamp_recheck_interval("TSH", proposed_days=None)
    assert r["was_clamped"] is False
    assert r["allowed_days"] == 42  # TSH 生物下限
    assert r["bound_by"] == "none"


def test_longest_substring_match_no_short_code_collision():
    # "25-OH-D"(56)应命中自身而非被更短的子串误配
    r = clamp_recheck_interval("血清 25-OH-D", proposed_days=10)
    assert r["allowed_days"] == 56
    assert r["known_metric"] is True


def test_behavioral_metrics_two_week_floor():
    for code in ("WEIGHT", "SYSTOLIC_BP", "FASTING_GLUCOSE"):
        r = clamp_recheck_interval(code, proposed_days=5)
        assert r["allowed_days"] == 14, code


def test_zero_or_negative_clinician_ignored():
    r = clamp_recheck_interval("HBA1C", proposed_days=200, clinician_days=0)
    assert r["allowed_days"] == 200
    assert r["clinician_floor"] is None
