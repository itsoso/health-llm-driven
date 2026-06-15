"""今日训练决策引擎 P0:decide() 纯函数 + 设备一致性聚合。

钉:① zone→灯映射 ② 急性病兜底 red(压过绿)③ ACWR risky 封顶到黄
④ 置信度(garmin+一致性 高 / computed+缺信号 低)⑤ 多设备 agreement 聚合、单设备→None。
"""
from types import SimpleNamespace

from app.services.recovery_decision import decide, device_agreement_index


def _rb(zone="moderate", score=70, source="computed", missing=None):
    return SimpleNamespace(zone=zone, score=score, source=source,
                           missing_components=missing or [])


def _acute(rest=False, ill=False, names=None):
    return SimpleNamespace(should_rest_from_training=rest, has_active_illness=ill,
                           illness_names=names or [], recent_symptoms=[])


def _beh(acwr="optimal"):
    return SimpleNamespace(acwr_zone=acwr)


# ── zone → 灯 ──────────────────────────────────────
def test_hard_zone_is_green():
    d = decide(_rb(zone="hard", score=88), _acute(), _beh())
    assert d.light == "green" and d.zone == "hard"


def test_light_zone_is_yellow():
    d = decide(_rb(zone="light", score=45), _acute(), _beh())
    assert d.light == "yellow"


def test_rest_zone_is_red():
    d = decide(_rb(zone="rest", score=20), _acute(), _beh())
    assert d.light == "red"


# ── 决策优先级 ──────────────────────────────────────
def test_acute_illness_overrides_green():
    # 恢复就绪度是绿,但急性病 → 必须 red
    d = decide(_rb(zone="hard", score=90), _acute(ill=True, names=["感冒"]), _beh())
    assert d.light == "red"
    assert any("急性病" in r or "休息" in r for r in d.reasons)


def test_acwr_overload_caps_green_to_yellow():
    # 用 exercise_recovery_service 实际产出的值(danger/overtraining),不是 schema 注释的 "risky"
    for z in ("danger", "overtraining", "risky"):
        d = decide(_rb(zone="hard", score=85), _acute(), _beh(acwr=z))
        assert d.light == "yellow", f"acwr={z} 应封顶到黄"
        assert any("ACWR" in r for r in d.reasons)


def test_acwr_under_keeps_green_with_note():
    for z in ("undertraining", "under"):
        d = decide(_rb(zone="hard", score=85), _acute(), _beh(acwr=z))
        assert d.light == "green"
        assert any("余量" in r for r in d.reasons)


def test_acwr_optimal_no_cap():
    d = decide(_rb(zone="hard", score=85), _acute(), _beh(acwr="optimal"))
    assert d.light == "green"


# ── 置信度 ──────────────────────────────────────
def test_confidence_high_garmin_plus_agreement():
    d = decide(_rb(source="garmin"), _acute(), _beh(), agreement_index=0.92)
    assert d.confidence == "high" and d.confidence_score >= 0.75
    assert d.agreement_index == 0.92


def test_confidence_low_computed_missing_no_agreement():
    d = decide(_rb(source="computed", missing=["hrv", "sleep_quality", "body_battery"]),
               _acute(), _beh(), agreement_index=None)
    assert d.confidence == "low" and d.confidence_score < 0.5
    assert d.missing_signals == ["hrv", "sleep_quality", "body_battery"]


def test_next_action_per_light():
    assert "休息" in decide(_rb(zone="rest"), _acute(), _beh()).next_action
    assert "Zone 2" in decide(_rb(zone="light"), _acute(), _beh()).next_action
    assert "计划" in decide(_rb(zone="hard"), _acute(), _beh()).next_action


# ── 设备一致性聚合(连库)────────────────────────────
def _garmin_row(db, user_id, source, **metrics):
    from datetime import date
    from app.models.daily_health import GarminData
    db.add(GarminData(user_id=user_id, record_date=date.today(), data_source=source, **metrics))


def test_agreement_index_two_sources(db):
    from tests.conftest import create_authenticated_user
    user, _ = create_authenticated_user(db)
    # 两源 HRV/RHR/睡眠接近 → 高一致性
    _garmin_row(db, user.id, "garmin", hrv=50.0, resting_heart_rate=52, total_sleep_duration=420)
    _garmin_row(db, user.id, "ringconn", hrv=52.0, resting_heart_rate=53, total_sleep_duration=430)
    db.commit()
    idx, detail = device_agreement_index(db, user.id)
    assert idx is not None and 0.0 <= idx <= 1.0
    assert "garmin" in detail["sources"] and "ringconn" in detail["sources"]
    assert set(detail["by_metric"]).issubset({"hrv", "resting_heart_rate", "total_sleep_duration", "spo2_avg"})


def test_agreement_index_single_source_is_none(db):
    from tests.conftest import create_authenticated_user
    user, _ = create_authenticated_user(db)
    _garmin_row(db, user.id, "garmin", hrv=50.0, resting_heart_rate=52, total_sleep_duration=420)
    db.commit()
    idx, _ = device_agreement_index(db, user.id)
    assert idx is None  # 单设备无从比一致性
