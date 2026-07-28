"""Workout 集成到 Twin + movement_coach 的测试."""
from datetime import UTC, date, datetime, timedelta

import pytest

from app.models.daily_health import WorkoutRecord
from app.twin.schema import WorkoutSummary, HealthTwin, TwinMeta, BehavioralState


def _mk_user(db):
    from app.models.user import User
    u = User(name="test")
    db.add(u); db.commit()
    return u


class TestWorkoutSummarySchema:
    def test_workout_summary_optional_fields(self):
        """所有字段可选, 即使只有日期和类型也能创建."""
        w = WorkoutSummary(workout_date="2026-04-30", workout_type="running")
        assert w.duration_min is None
        assert w.hr_zone_minutes is None

    def test_workout_summary_full(self):
        w = WorkoutSummary(
            workout_date="2026-04-30", workout_type="running",
            duration_min=45.0, distance_km=8.5, calories=420,
            avg_hr=152, max_hr=178, hr_zone_dominant=3,
            hr_zone_minutes={"z2": 10.0, "z3": 25.0, "z4": 10.0},
            training_effect_aerobic=3.2, perceived_exertion=6, feeling="good",
        )
        assert w.hr_zone_dominant == 3
        assert w.hr_zone_minutes["z3"] == 25.0


class TestTwinBuilderFillsWorkouts:
    """直接测 _fill_training_load 里的 workout_summary 段,
    绕过 build_twin (SQLite 测试 schema 对部分新 column 不同步, 非本次改动问题)."""

    def _fill(self, db, user_id):
        """调用 _fill_training_load 填充 twin, 返回 twin."""
        from app.twin.builder import _fill_training_load
        twin = HealthTwin(meta=TwinMeta(user_id=user_id, generated_at=datetime.now(UTC)))
        twin.behavioral = BehavioralState()
        sources: set = set()
        _fill_training_load(db, user_id, twin, sources)
        return twin, sources

    def test_empty_user_no_workouts(self, db):
        u = _mk_user(db)
        twin, _ = self._fill(db, u.id)
        assert twin.behavioral.recent_workouts == []

    def test_recent_workout_populated(self, db):
        """最近 7 天的 WorkoutRecord 应该进 twin.behavioral.recent_workouts."""
        u = _mk_user(db)
        db.add(WorkoutRecord(
            user_id=u.id, workout_date=date.today() - timedelta(days=2),
            workout_type="running",
            duration_seconds=45 * 60, distance_meters=8500,
            avg_heart_rate=152, max_heart_rate=178,
            hr_zone_2_seconds=600, hr_zone_3_seconds=1500, hr_zone_4_seconds=600,
            training_effect_aerobic=3.2, perceived_exertion=6, feeling="good",
            calories=420,
        ))
        db.commit()
        twin, sources = self._fill(db, u.id)
        assert len(twin.behavioral.recent_workouts) == 1
        w = twin.behavioral.recent_workouts[0]
        assert w.workout_type == "running"
        assert w.duration_min == 45.0
        assert w.distance_km == 8.5
        assert w.avg_hr == 152
        assert w.hr_zone_dominant == 3  # z3 最长
        assert w.hr_zone_minutes == {"z2": 10.0, "z3": 25.0, "z4": 10.0}
        assert w.training_effect_aerobic == 3.2
        assert "workout" in sources

    def test_sparse_training_does_not_publish_reliable_acwr(self, db):
        """只有近期一次训练、没有三周慢性基线时，Twin 必须标记 ACWR 不可靠。"""
        u = _mk_user(db)
        db.add(WorkoutRecord(
            user_id=u.id,
            workout_date=date.today() - timedelta(days=1),
            workout_type="walking",
            duration_seconds=30 * 60,
            avg_heart_rate=110,
            training_load=20,
        ))
        db.commit()

        twin, _ = self._fill(db, u.id)

        assert twin.behavioral.training_load_7d > 0
        assert twin.behavioral.acute_chronic_ratio is None
        assert twin.behavioral.acwr_reliable is False

    def test_old_workout_excluded(self, db):
        """10 天前的不进 (cutoff = 7 天)."""
        u = _mk_user(db)
        db.add(WorkoutRecord(
            user_id=u.id, workout_date=date.today() - timedelta(days=10),
            workout_type="running", duration_seconds=1800,
        ))
        db.commit()
        twin, _ = self._fill(db, u.id)
        assert twin.behavioral.recent_workouts == []

    def test_ordered_desc_by_date(self, db):
        u = _mk_user(db)
        for i in [5, 1, 3]:
            db.add(WorkoutRecord(
                user_id=u.id, workout_date=date.today() - timedelta(days=i),
                workout_type=f"t{i}", duration_seconds=1200,
            ))
        db.commit()
        twin, _ = self._fill(db, u.id)
        assert len(twin.behavioral.recent_workouts) == 3
        types = [w.workout_type for w in twin.behavioral.recent_workouts]
        assert types == ["t1", "t3", "t5"]


class TestMovementCoachReadsWorkouts:
    def test_recent_workout_detail_in_findings(self):
        """movement_coach 应该在 findings 里输出 recent_workout_detail."""
        from app.agents.movement_coach.coach import MovementCoachSpecialist
        twin = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.now(UTC)))
        twin.behavioral = BehavioralState()
        twin.behavioral.recent_workouts = [
            WorkoutSummary(
                workout_date="2026-04-28", workout_type="running",
                duration_min=45.0, avg_hr=152, hr_zone_dominant=3,
                perceived_exertion=7,
                hr_zone_minutes={"z3": 25.0, "z4": 15.0, "z5": 5.0},
                training_effect_aerobic=3.2,
            ),
        ]
        coach = MovementCoachSpecialist()
        result = coach.run(twin, {"readiness_zone": "go"})
        detail = next(f for f in result.findings if f.get("type") == "recent_workout_detail")
        assert detail["count"] == 1
        assert detail["high_intensity_minutes_7d"] == 20.0  # z4+z5 = 15+5
        assert detail["avg_perceived_exertion"] == 7.0

    def test_no_workouts_no_detail_finding(self):
        """没 workout 时, findings 里不出现 recent_workout_detail."""
        from app.agents.movement_coach.coach import MovementCoachSpecialist
        twin = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.now(UTC)))
        twin.behavioral = BehavioralState()
        coach = MovementCoachSpecialist()
        result = coach.run(twin, {})
        kinds = [f.get("type") for f in result.findings]
        assert "recent_workout_detail" not in kinds
