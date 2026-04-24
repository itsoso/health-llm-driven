"""P1b 行为关联规则单测。"""
from datetime import date, datetime, time, timedelta
from app.services.sleep.nocturnal_spo2_analyzer import NightAnalysis, DetectedEvent
from app.services.sleep.correlation_rules import (
    NightContext, run_rules,
    rule_ipratropium_late_dose, rule_ipratropium_skipped,
    rule_respiratory_depressant, rule_late_intense_training,
    rule_alcohol, rule_rhinitis_severe, rule_rem_concentrated,
    rule_high_pm25, rule_bedtime_magnesium_helps,
)


def _night(odi=5.0, events_count=10, events=None):
    return NightAnalysis(
        night_date=date(2026, 4, 23),
        odi=odi,
        events_count=events_count,
        min_spo2=87,
        avg_spo2=94,
        total_sleep_minutes=480,
        events=events or [],
    )


def _events_in_rem(n=6):
    ts = datetime(2026, 4, 23, 2, 0)
    return [
        DetectedEvent(
            start_ts=ts + timedelta(minutes=i*10),
            end_ts=ts + timedelta(minutes=i*10+1),
            duration_seconds=60,
            min_spo2=87,
            baseline_spo2=95,
            drop_magnitude=8,
            sleep_stage='rem',
        )
        for i in range(n)
    ]


class TestIpratropium:
    def test_late_dose_fires(self):
        """末次用药 14:00，入睡 23:30 → 9.5h > 8h 触发。"""
        ctx = NightContext(
            night_date=date(2026, 4, 23),
            med_logs=[{"name": "异丙托溴铵喷雾", "taken_time": "14:00", "status": "taken"}],
            sleep_start_ts=datetime(2026, 4, 23, 23, 30),
        )
        f = rule_ipratropium_late_dose(_night(odi=5), ctx)
        assert f is not None
        assert f.rule == "ipratropium_late_dose"
        assert f.severity == "warning"
        assert f.evidence["gap_hours"] > 8

    def test_on_time_dose_no_fire(self):
        """末次用药 22:00，入睡 23:30 → 1.5h，规则不触发。"""
        ctx = NightContext(
            night_date=date(2026, 4, 23),
            med_logs=[{"name": "异丙托溴铵", "taken_time": "22:00", "status": "taken"}],
            sleep_start_ts=datetime(2026, 4, 23, 23, 30),
        )
        assert rule_ipratropium_late_dose(_night(odi=5), ctx) is None

    def test_low_odi_no_fire(self):
        """ODI 低不触发（没问题就不给建议）。"""
        ctx = NightContext(
            night_date=date(2026, 4, 23),
            med_logs=[{"name": "异丙托溴铵", "taken_time": "14:00", "status": "taken"}],
            sleep_start_ts=datetime(2026, 4, 23, 23, 30),
        )
        assert rule_ipratropium_late_dose(_night(odi=1), ctx) is None

    def test_skipped_high_odi_fires(self):
        ctx = NightContext(
            night_date=date(2026, 4, 23),
            active_meds=[{"name": "异丙托溴铵喷雾"}],
            med_logs=[],  # 当日未服
        )
        f = rule_ipratropium_skipped(_night(odi=5), ctx)
        assert f is not None
        assert f.rule == "ipratropium_skipped_high_odi"


class TestAlcohol:
    def test_alcohol_first_half_fires(self):
        """1 份酒精 + 事件 80% 集中前半夜。"""
        sleep_start = datetime(2026, 4, 23, 23, 0)
        events = [
            DetectedEvent(
                start_ts=sleep_start + timedelta(hours=1),
                end_ts=sleep_start + timedelta(hours=1, minutes=2),
                duration_seconds=120, min_spo2=88, baseline_spo2=95, drop_magnitude=7,
            ),
            DetectedEvent(
                start_ts=sleep_start + timedelta(hours=2),
                end_ts=sleep_start + timedelta(hours=2, minutes=2),
                duration_seconds=120, min_spo2=88, baseline_spo2=95, drop_magnitude=7,
            ),
            DetectedEvent(
                start_ts=sleep_start + timedelta(hours=3),
                end_ts=sleep_start + timedelta(hours=3, minutes=2),
                duration_seconds=120, min_spo2=89, baseline_spo2=95, drop_magnitude=6,
            ),
            DetectedEvent(
                start_ts=sleep_start + timedelta(hours=6),
                end_ts=sleep_start + timedelta(hours=6, minutes=2),
                duration_seconds=120, min_spo2=91, baseline_spo2=95, drop_magnitude=4,
            ),
        ]
        ctx = NightContext(
            night_date=date(2026, 4, 23),
            diet_records=[{"food_items": "红酒", "alcohol_units": 1.5, "meal_type": "dinner"}],
            sleep_start_ts=sleep_start,
        )
        f = rule_alcohol(_night(odi=5, events_count=4, events=events), ctx)
        assert f is not None
        assert f.severity == "alert"

    def test_no_alcohol_no_fire(self):
        ctx = NightContext(night_date=date(2026, 4, 23), diet_records=[])
        assert rule_alcohol(_night(odi=5), ctx) is None


class TestRhinitis:
    def test_severe_rhinitis_fires(self):
        ctx = NightContext(night_date=date(2026, 4, 23), rhinitis_severity=7)
        f = rule_rhinitis_severe(_night(odi=5), ctx)
        assert f is not None
        assert f.rule == "rhinitis_secondary_osa"

    def test_mild_rhinitis_no_fire(self):
        ctx = NightContext(night_date=date(2026, 4, 23), rhinitis_severity=2)
        assert rule_rhinitis_severe(_night(odi=5), ctx) is None


class TestREMConcentrated:
    def test_rem_majority_fires(self):
        events = _events_in_rem(n=6)
        n = _night(odi=6, events_count=6, events=events)
        ctx = NightContext(night_date=date(2026, 4, 23))
        f = rule_rem_concentrated(n, ctx)
        assert f is not None
        assert f.severity == "alert"

    def test_mixed_stages_no_fire(self):
        ev_rem = _events_in_rem(n=2)
        ev_light = [
            DetectedEvent(start_ts=datetime(2026,4,23,3,i), end_ts=datetime(2026,4,23,3,i+1),
                          duration_seconds=60, min_spo2=89, baseline_spo2=95, drop_magnitude=6, sleep_stage='light')
            for i in range(30, 35)
        ]
        n = _night(odi=6, events_count=7, events=ev_rem + ev_light)
        ctx = NightContext(night_date=date(2026, 4, 23))
        assert rule_rem_concentrated(n, ctx) is None


class TestLateIntenseTraining:
    def test_late_hiit_fires(self):
        sleep_start = datetime(2026, 4, 23, 23, 0)
        ctx = NightContext(
            night_date=date(2026, 4, 23),
            workouts=[{
                "workout_type": "HIIT",
                "end_time": sleep_start - timedelta(hours=1, minutes=30),
                "duration_min": 30,
                "hr_max_pct": 0.92,
            }],
            sleep_start_ts=sleep_start,
        )
        f = rule_late_intense_training(_night(odi=5), ctx)
        assert f is not None
        assert f.severity == "warning"

    def test_morning_hiit_no_fire(self):
        sleep_start = datetime(2026, 4, 23, 23, 0)
        ctx = NightContext(
            night_date=date(2026, 4, 23),
            workouts=[{
                "workout_type": "HIIT",
                "end_time": sleep_start - timedelta(hours=12),
                "duration_min": 30,
                "hr_max_pct": 0.92,
            }],
            sleep_start_ts=sleep_start,
        )
        assert rule_late_intense_training(_night(odi=5), ctx) is None


class TestHighPM25:
    def test_high_pm25_fires(self):
        ctx = NightContext(night_date=date(2026, 4, 23), air_quality_pm25=120)
        f = rule_high_pm25(_night(odi=5), ctx)
        assert f is not None

    def test_low_pm25_no_fire(self):
        ctx = NightContext(night_date=date(2026, 4, 23), air_quality_pm25=20)
        assert rule_high_pm25(_night(odi=5), ctx) is None


class TestRunRulesOrdering:
    def test_alerts_before_warnings(self):
        sleep_start = datetime(2026, 4, 23, 23, 0)
        events = _events_in_rem(n=6)
        n = _night(odi=6, events_count=6, events=events)
        ctx = NightContext(
            night_date=date(2026, 4, 23),
            med_logs=[{"name": "异丙托溴铵", "taken_time": "14:00", "status": "taken"}],
            diet_records=[{"food_items": "红酒", "alcohol_units": 1.5}],
            sleep_start_ts=sleep_start,
        )
        findings = run_rules(n, ctx)
        severities = [f.severity for f in findings]
        # alert 必须在 warning 之前
        if "alert" in severities and "warning" in severities:
            first_alert = severities.index("alert")
            first_warning = severities.index("warning")
            assert first_alert < first_warning


class TestSevereHypoxia:
    def test_very_severe(self):
        from app.services.sleep.correlation_rules import rule_severe_hypoxia
        n = NightAnalysis(night_date=date(2026,4,16), odi=1.4, events_count=12,
                          min_spo2=74, avg_spo2=91, total_sleep_minutes=500, events=[])
        f = rule_severe_hypoxia(n, NightContext(night_date=date(2026,4,16)))
        assert f is not None
        assert f.severity == "alert"
        assert "74" in f.hypothesis

    def test_moderate_hypoxia(self):
        from app.services.sleep.correlation_rules import rule_severe_hypoxia
        n = NightAnalysis(night_date=date(2026,4,16), odi=1.0, events_count=3,
                          min_spo2=86, avg_spo2=95, total_sleep_minutes=480, events=[])
        f = rule_severe_hypoxia(n, NightContext(night_date=date(2026,4,16)))
        assert f is not None
        assert f.severity == "warning"

    def test_normal_no_fire(self):
        from app.services.sleep.correlation_rules import rule_severe_hypoxia
        n = NightAnalysis(night_date=date(2026,4,16), odi=0.5, events_count=2,
                          min_spo2=92, avg_spo2=96, total_sleep_minutes=480, events=[])
        assert rule_severe_hypoxia(n, NightContext(night_date=date(2026,4,16))) is None


class TestHighODI:
    def test_mild_odi(self):
        from app.services.sleep.correlation_rules import rule_high_odi
        n = _night(odi=7.0, events_count=55)
        f = rule_high_odi(n, NightContext(night_date=date(2026,4,16)))
        assert f is not None
        assert f.severity == "warning"
        assert "轻度" in f.hypothesis

    def test_moderate_odi(self):
        from app.services.sleep.correlation_rules import rule_high_odi
        n = _night(odi=18.0, events_count=140)
        f = rule_high_odi(n, NightContext(night_date=date(2026,4,16)))
        assert f is not None
        assert f.severity == "alert"
        assert "中度" in f.hypothesis

    def test_under_threshold_no_fire(self):
        from app.services.sleep.correlation_rules import rule_high_odi
        n = _night(odi=3.0, events_count=25)
        assert rule_high_odi(n, NightContext(night_date=date(2026,4,16))) is None
