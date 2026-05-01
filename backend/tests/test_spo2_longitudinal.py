"""Nocturnal SpO2 longitudinal 聚合测试."""
from datetime import date, datetime, timedelta, timezone
import pytest

from app.models.daily_health import GarminData
from app.models.nocturnal_spo2_event import NocturnalSpO2Event
from app.services.sleep.nocturnal_spo2_longitudinal import (
    build_longitudinal, _severity_from_odi,
)


def _mk_event(user_id, night_date, min_spo2=88, drop=6, stage="rem"):
    start = datetime.combine(night_date, datetime.min.time(), tzinfo=timezone.utc) \
        + timedelta(hours=2)
    return NocturnalSpO2Event(
        user_id=user_id,
        night_date=night_date,
        start_ts=start,
        end_ts=start + timedelta(seconds=30),
        duration_seconds=30,
        min_spo2=min_spo2,
        baseline_spo2=min_spo2 + drop,
        drop_magnitude=drop,
        concurrent_hr_delta=3,
        concurrent_respiration_rate=14,
        sleep_stage=stage,
    )


def _mk_garmin(user_id, record_date, sleep_min=480):
    return GarminData(
        user_id=user_id, record_date=record_date,
        total_sleep_duration=sleep_min,
    )


class TestSeverity:
    def test_buckets(self):
        assert _severity_from_odi(None) == "unknown"
        assert _severity_from_odi(3.0) == "normal"
        assert _severity_from_odi(5.0) == "mild"
        assert _severity_from_odi(14.9) == "mild"
        assert _severity_from_odi(15.0) == "moderate"
        assert _severity_from_odi(29.9) == "moderate"
        assert _severity_from_odi(30.0) == "severe"


class TestBuildLongitudinal:
    def test_empty(self, db):
        result = build_longitudinal(db, user_id=1, days=30)
        assert result["nights"] == []
        assert result["pattern"]["covered_nights"] == 0
        assert result["pattern"]["avg_odi"] is None
        assert result["pattern"]["pattern_flags"] == []

    def test_single_night_with_sleep(self, db):
        night = date.today() - timedelta(days=1)
        # 3 个事件 + 8h 睡眠 → ODI 0.375 → normal
        for _ in range(3):
            db.add(_mk_event(1, night, min_spo2=91))
        db.add(_mk_garmin(1, night, sleep_min=480))
        db.commit()

        r = build_longitudinal(db, 1, days=30)
        assert len(r["nights"]) == 1
        n = r["nights"][0]
        assert n["events_count"] == 3
        assert n["odi"] == 0.38
        assert n["severity"] == "normal"
        assert n["min_spo2"] == 91
        assert n["total_sleep_minutes"] == 480

    def test_pattern_flags_frequent_desaturation(self, db):
        """≥50% 夜 ODI≥5, ≥7 夜."""
        for i in range(10):
            night = date.today() - timedelta(days=i + 1)
            # 8 events / 8h = ODI 1.0  → below 5
            # 用 50 events / 8h = 6.25 来模拟 "频繁氧降"
            for _ in range(50):
                db.add(_mk_event(1, night, min_spo2=88))
            db.add(_mk_garmin(1, night, sleep_min=480))
        db.commit()

        r = build_longitudinal(db, 1, days=30)
        p = r["pattern"]
        assert p["covered_nights"] == 10
        assert p["nights_with_odi"] == 10
        assert p["pct_nights_odi_ge_5"] == 1.0
        assert "frequent_desaturation" in p["pattern_flags"]

    def test_rem_predominant_flag(self, db):
        """总事件≥20 且 REM≥40% 时触发."""
        for i in range(5):
            night = date.today() - timedelta(days=i + 1)
            for _ in range(8):
                db.add(_mk_event(1, night, stage="rem"))
            for _ in range(2):
                db.add(_mk_event(1, night, stage="deep"))
            db.add(_mk_garmin(1, night, sleep_min=480))
        db.commit()

        r = build_longitudinal(db, 1, days=30)
        p = r["pattern"]
        assert p["pct_events_in_rem"] == 0.8
        assert "rem_predominant" in p["pattern_flags"]

    def test_notable_hypoxia_flag(self, db):
        """≥25% 夜 min_spo2 < 90 且至少 7 夜有数据."""
        for i in range(10):
            night = date.today() - timedelta(days=i + 1)
            # 前 4 夜有严重 desat, 后 6 夜 OK
            spo2 = 85 if i < 4 else 94
            db.add(_mk_event(1, night, min_spo2=spo2))
            db.add(_mk_garmin(1, night, sleep_min=480))
        db.commit()

        r = build_longitudinal(db, 1, days=30)
        p = r["pattern"]
        assert p["pct_nights_min_spo2_below_90"] == 0.4
        assert "notable_hypoxia" in p["pattern_flags"]

    def test_no_sleep_duration_no_odi(self, db):
        """无 GarminData 睡眠时长 → odi=None, severity=unknown."""
        night = date.today() - timedelta(days=1)
        db.add(_mk_event(1, night))
        db.commit()

        r = build_longitudinal(db, 1, days=30)
        n = r["nights"][0]
        assert n["odi"] is None
        assert n["severity"] == "unknown"

    def test_window_respected(self, db):
        """超过 days 窗口的夜不该出现."""
        old = date.today() - timedelta(days=100)
        recent = date.today() - timedelta(days=2)
        db.add(_mk_event(1, old))
        db.add(_mk_garmin(1, old, sleep_min=480))
        db.add(_mk_event(1, recent))
        db.add(_mk_garmin(1, recent, sleep_min=480))
        db.commit()

        r = build_longitudinal(db, 1, days=30)
        dates = [n["night_date"] for n in r["nights"]]
        assert recent.isoformat() in dates
        assert old.isoformat() not in dates

    def test_scoped_per_user(self, db):
        night = date.today() - timedelta(days=1)
        db.add(_mk_event(1, night))
        db.add(_mk_event(2, night))
        db.add(_mk_garmin(1, night))
        db.commit()
        r1 = build_longitudinal(db, 1, days=30)
        r2 = build_longitudinal(db, 2, days=30)
        assert r1["nights"][0]["events_count"] == 1
        assert r2["nights"][0]["events_count"] == 1
