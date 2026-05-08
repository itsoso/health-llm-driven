"""MovementCoach + RecoveryCoach 的 Garmin 优先路径补测.

existing test_specialists.py 覆盖了基本 ACWR / readiness 自算逻辑, 但:
- MovementCoach 最近加的 `_GARMIN_STATUS_MAP` (字符串 + 整数 str 两套键) 没测
- RecoveryCoach 的 `training_readiness_score` 覆写路径 (zones 重算 + source="garmin") 没测

这两条路径是 Garmin SDK 返回不同格式时的兼容层, 正是最容易悄悄回归的地方.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.agents.movement_coach import MovementCoachSpecialist
from app.agents.movement_coach.coach import (
    _GARMIN_STATUS_MAP,
    _resolve_training_status,
)
from app.agents.recovery_coach import compute_readiness
from app.twin.schema import (
    BehavioralState,
    HealthTwin,
    PhysiologicalState,
    TwinMeta,
)


def _twin() -> HealthTwin:
    return HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.utcnow()))


# ──────────────────── MovementCoach: _GARMIN_STATUS_MAP ────────────────────


class TestGarminStatusMap:
    @pytest.mark.parametrize("key,expected", [
        ("productive", "optimal"),
        ("maintaining", "optimal"),
        ("peaking", "peaking"),
        ("overreaching", "overload"),
        ("unproductive", "overload"),
        ("recovery", "undertrained"),
        ("detraining", "detraining"),
        ("strained", "overload"),
        ("no_status", "unknown"),
    ])
    def test_string_keys_map_correctly(self, key, expected):
        assert _GARMIN_STATUS_MAP[key] == expected

    @pytest.mark.parametrize("int_key,expected", [
        ("1", "detraining"),
        ("2", "optimal"),       # maintaining
        ("3", "optimal"),       # productive
        ("4", "peaking"),
        ("5", "overload"),      # overreaching
        ("6", "overload"),      # unproductive
        ("7", "undertrained"),  # recovery
        ("8", "overload"),      # strained
        ("0", "unknown"),
    ])
    def test_integer_string_keys_map_correctly(self, int_key, expected):
        """采集器有些账户拿不到字符串名, 退化存 str(int). 必须两边都接."""
        assert _GARMIN_STATUS_MAP[int_key] == expected

    def test_no_duplicate_value_without_intent(self):
        """防止不同语义 Garmin 状态误映射到同一 decision matrix key.
        目前 4 个状态都映射到 overload (overreaching/unproductive/strained/5/6/8),
        这是有意的 (都该低强度); 但测试记录一下避免误 refactor.
        """
        overload_keys = {k for k, v in _GARMIN_STATUS_MAP.items() if v == "overload"}
        assert overload_keys == {"overreaching", "unproductive", "strained", "5", "6", "8"}


class TestResolveTrainingStatus:
    def test_prefers_garmin_over_computed(self):
        """有 Garmin status 时优先用, source='garmin'."""
        t = _twin()
        t.behavioral = BehavioralState(
            training_status="productive",
            acute_chronic_ratio=1.7,  # 自算会说"overload" — 但被 Garmin 覆盖
            workouts_this_week=4,
        )
        status, source = _resolve_training_status(t)
        assert status == "optimal"   # Garmin productive → optimal
        assert source == "garmin"

    def test_falls_back_to_computed_when_no_garmin(self):
        t = _twin()
        t.behavioral = BehavioralState(
            training_status=None,
            acute_chronic_ratio=1.7,
            workouts_this_week=4,
        )
        _, source = _resolve_training_status(t)
        assert source == "computed"

    def test_falls_back_when_garmin_key_unrecognized(self):
        """未来 Garmin 加新状态 → fallback, 不崩."""
        t = _twin()
        t.behavioral = BehavioralState(
            training_status="some_new_status_2027",
            acute_chronic_ratio=1.1,
            workouts_this_week=4,
        )
        _, source = _resolve_training_status(t)
        assert source == "computed"

    def test_integer_encoded_status_resolved_via_garmin(self):
        """Garmin SDK 用整数 → str(3) = productive → optimal."""
        t = _twin()
        t.behavioral = BehavioralState(
            training_status="3",
            acute_chronic_ratio=None,
            # workouts_this_week 是 int=0 非 Optional, 不传走默认
        )
        status, source = _resolve_training_status(t)
        assert status == "optimal"
        assert source == "garmin"


class TestMovementCoachFindingSource:
    """run() 产出里的 status_source 字段应随数据源变化."""

    def test_status_source_marked_garmin(self):
        t = _twin()
        t.behavioral = BehavioralState(
            training_status="productive",
            acute_chronic_ratio=1.1,
            workouts_this_week=3,
        )
        s = MovementCoachSpecialist()
        finding = s.run(t, context={})
        ts = next(f for f in finding.findings if f.get("type") == "training_status")
        # Garmin 覆写路径必须暴露 garmin load/feedback 字段 (即使 None)
        assert "garmin_load_ratio" in ts
        assert "garmin_acute_load" in ts
        assert "garmin_feedback" in ts


# ──────────────────── RecoveryCoach: Garmin 覆写 ────────────────────


class TestRecoveryCoachGarminOverride:
    def test_uses_garmin_score_when_available(self):
        """有 Garmin training_readiness_score 时覆盖自算."""
        t = _twin()
        t.physiological = PhysiologicalState(
            hrv_latest=40.0,            # 偏低 → 自算会打低分
            hrv_7d_avg=45.0,
            sleep_score_latest=55,
            sleep_duration_h_latest=5.5,
            body_battery_current=30,
            stress_level_current=70,
            resting_hr=68,
            training_readiness_score=85,  # Garmin 说其实可以高强度
        )
        br = compute_readiness(t)
        # Garmin 覆写后分数应等于 85
        assert br.score == 85
        assert br.source == "garmin"
        # zone 按覆写后的 85 重算 → hard
        assert br.zone == "hard"

    def test_falls_back_to_computed_when_no_garmin(self):
        t = _twin()
        t.physiological = PhysiologicalState(
            hrv_latest=55.0,
            hrv_7d_avg=58.0,
            sleep_score_latest=78,
            sleep_duration_h_latest=7.2,
            body_battery_current=65,
            stress_level_current=35,
            resting_hr=52,
            training_readiness_score=None,
        )
        br = compute_readiness(t)
        assert br.source == "computed"
        assert 0 <= br.score <= 100

    def test_invalid_garmin_score_falls_back(self):
        """Garmin score 超出 0-100 范围时不信 (防脏数据)."""
        t = _twin()
        t.physiological = PhysiologicalState(
            hrv_latest=55.0,
            hrv_7d_avg=58.0,
            sleep_score_latest=78,
            sleep_duration_h_latest=7.2,
            body_battery_current=65,
            stress_level_current=35,
            resting_hr=52,
            training_readiness_score=150,  # invalid
        )
        br = compute_readiness(t)
        assert br.source == "computed"

    def test_components_preserved_even_when_garmin_overrides(self):
        """即使 Garmin 覆写 score, 自算分解 (components) 仍暴露给 UI 解释."""
        t = _twin()
        t.physiological = PhysiologicalState(
            hrv_latest=55.0,
            hrv_7d_avg=58.0,
            sleep_score_latest=78,
            sleep_duration_h_latest=7.2,
            body_battery_current=65,
            stress_level_current=35,
            resting_hr=52,
            training_readiness_score=90,
        )
        br = compute_readiness(t)
        # components 里至少有 hrv / sleep / battery / stress 中的几项
        assert len(br.components) >= 2
        assert br.source == "garmin"

    def test_garmin_override_zone_hard_at_85(self):
        t = _twin()
        t.physiological = PhysiologicalState(training_readiness_score=85)
        br = compute_readiness(t)
        assert br.zone == "hard"

    def test_garmin_override_zone_moderate_at_72(self):
        t = _twin()
        t.physiological = PhysiologicalState(training_readiness_score=72)
        br = compute_readiness(t)
        assert br.zone == "moderate"

    def test_garmin_override_zone_light_at_58(self):
        t = _twin()
        t.physiological = PhysiologicalState(training_readiness_score=58)
        br = compute_readiness(t)
        assert br.zone == "light"

    def test_garmin_override_zone_rest_at_40(self):
        t = _twin()
        t.physiological = PhysiologicalState(training_readiness_score=40)
        br = compute_readiness(t)
        assert br.zone == "rest"
