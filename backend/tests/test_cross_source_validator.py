# -*- coding: utf-8 -*-
"""跨源异常检测回归。

钉:
  - 纯函数 flag_outliers:三源一源偏离 → 命中 + outlier_source 正确 + deviation_pct 符号;
    全源一致 → 无异常;单源 → 不产出;均值 0 → 不产出。
  - service detect_cross_source_anomalies:DB 取数 + user 隔离 + 排序。
  - specialist applies_to / run 基本用例(有异常产出、无异常空、缺 db 跳过)。
"""
from datetime import timedelta

from app.orchestrator.schema import Intent
from app.services.cross_source_validator import (
    REL_SPREAD_THRESHOLD,
    detect_cross_source_anomalies,
    flag_outliers,
)


# ───────────────── 纯函数 flag_outliers ─────────────────

def test_flag_three_sources_one_outlier_high():
    # garmin/apple-watch HRV ~50,ringconn 偏高很多 → ringconn 是 outlier
    out = flag_outliers("hrv", {"garmin": 50.0, "apple-watch": 49.0, "ringconn": 70.0})
    assert out is not None
    assert out["outlier_source"] == "ringconn"
    assert out["deviation_pct"] > 0          # 偏高
    assert out["rel_spread"] > REL_SPREAD_THRESHOLD
    assert "ringconn" in out["sources"] and out["metric"] == "hrv"


def test_flag_outlier_low_direction_sign():
    # ringconn HRV 明显偏低 → deviation_pct 为负
    out = flag_outliers("hrv", {"garmin": 50.0, "apple-watch": 52.0, "ringconn": 20.0})
    assert out is not None
    assert out["outlier_source"] == "ringconn"
    assert out["deviation_pct"] < 0


def test_flag_all_consistent_no_anomaly():
    out = flag_outliers("hrv", {"garmin": 50.0, "apple-watch": 49.5, "ringconn": 50.5})
    assert out is None  # 极差 1/均值 50 = 2% < 30% 且无 >2σ


def test_flag_single_source_no_anomaly():
    assert flag_outliers("hrv", {"garmin": 50.0}) is None


def test_flag_zero_mean_no_div_by_zero():
    assert flag_outliers("steps", {"garmin": 0.0, "apple-watch": 0.0}) is None


def test_flag_two_sources_uses_rel_spread():
    # 两源:无法算 σ,靠极差/均值。garmin 100 / apple 50 → spread 50 / mean 75 = 0.67 > 0.30
    out = flag_outliers("steps", {"garmin": 10000.0, "apple-watch": 5000.0})
    assert out is not None
    assert out["rel_spread"] > REL_SPREAD_THRESHOLD


def test_flag_trusted_source_follows_priority():
    # HRV 戒指优先 → 三源都在时 trusted=ringconn(即使 ringconn 是 outlier 仍按优先级)
    out = flag_outliers("hrv", {"garmin": 50.0, "apple-watch": 49.0, "ringconn": 75.0})
    assert out["trusted_source"] == "ringconn"


# ───────────────── service detect_cross_source_anomalies ─────────────────

def _add(db, **kw):
    from app.models.daily_health import GarminData
    db.add(GarminData(**kw))


def test_detect_three_source_anomaly_db(db):
    from app.utils.timezone import get_china_today
    today = get_china_today()
    # 三源 RHR:garmin/apple ~52,ringconn 偏离
    _add(db, user_id=1, record_date=today, data_source="garmin", resting_heart_rate=52)
    _add(db, user_id=1, record_date=today, data_source="apple-watch", resting_heart_rate=53)
    _add(db, user_id=1, record_date=today, data_source="ringconn", resting_heart_rate=80)
    db.commit()

    out = detect_cross_source_anomalies(db, 1, days=7)
    metrics = {a["metric"]: a for a in out}
    assert "resting_heart_rate" in metrics
    assert metrics["resting_heart_rate"]["outlier_source"] == "ringconn"


def test_detect_all_consistent_no_anomaly(db):
    from app.utils.timezone import get_china_today
    today = get_china_today()
    _add(db, user_id=2, record_date=today, data_source="garmin", hrv=50.0)
    _add(db, user_id=2, record_date=today, data_source="apple-watch", hrv=49.0)
    _add(db, user_id=2, record_date=today, data_source="ringconn", hrv=50.5)
    db.commit()
    assert detect_cross_source_anomalies(db, 2, days=7) == []


def test_detect_single_source_no_anomaly(db):
    from app.utils.timezone import get_china_today
    _add(db, user_id=3, record_date=get_china_today(), data_source="garmin", hrv=50.0)
    db.commit()
    assert detect_cross_source_anomalies(db, 3, days=7) == []


def test_detect_user_isolation(db):
    from app.utils.timezone import get_china_today
    today = get_china_today()
    # user 4 有跨源异常
    _add(db, user_id=4, record_date=today, data_source="garmin", hrv=50.0)
    _add(db, user_id=4, record_date=today, data_source="ringconn", hrv=90.0)
    # user 5 只有一源,且值不同 — 不应混入 user 4
    _add(db, user_id=5, record_date=today, data_source="garmin", hrv=10.0)
    db.commit()

    out4 = detect_cross_source_anomalies(db, 4, days=7)
    assert any(a["metric"] == "hrv" for a in out4)
    out5 = detect_cross_source_anomalies(db, 5, days=7)
    assert out5 == []  # user5 单源,无跨源


# ───────────────── specialist ─────────────────

def _twin(user_id=1, sources=("garmin", "ringconn")):
    from datetime import UTC, datetime
    from app.twin.schema import HealthTwin, TwinMeta
    return HealthTwin(
        meta=TwinMeta(
            user_id=user_id,
            generated_at=datetime.now(UTC),
            data_sources=list(sources),
        )
    )


def test_specialist_applies_on_recovery_intent_with_garmin():
    from app.agents.cross_source_validator.specialist import CrossSourceValidatorSpecialist
    sp = CrossSourceValidatorSpecialist()
    intent = Intent(raw_query="我恢复得怎么样", categories=["recovery"])
    assert sp.applies_to(intent, _twin(sources=["garmin", "ringconn"])) is True


def test_specialist_not_applies_without_garmin():
    from app.agents.cross_source_validator.specialist import CrossSourceValidatorSpecialist
    sp = CrossSourceValidatorSpecialist()
    intent = Intent(raw_query="我恢复得怎么样", categories=["recovery"])
    assert sp.applies_to(intent, _twin(sources=["labs", "genetic"])) is False


def test_specialist_applies_on_device_keyword():
    from app.agents.cross_source_validator.specialist import CrossSourceValidatorSpecialist
    sp = CrossSourceValidatorSpecialist()
    intent = Intent(raw_query="我的手表数据准吗", categories=["knowledge"])
    assert sp.applies_to(intent, _twin(sources=["garmin"])) is True


def test_specialist_run_emits_finding_on_anomaly(db):
    from app.agents.cross_source_validator.specialist import CrossSourceValidatorSpecialist
    from app.utils.timezone import get_china_today
    today = get_china_today()
    _add(db, user_id=9, record_date=today, data_source="garmin", hrv=50.0)
    _add(db, user_id=9, record_date=today, data_source="apple-watch", hrv=49.0)
    _add(db, user_id=9, record_date=today, data_source="ringconn", hrv=80.0)
    db.commit()

    sp = CrossSourceValidatorSpecialist()
    f = sp.run(_twin(user_id=9), {"db": db})
    assert f.specialist_name == "cross_source_validator"
    assert len(f.findings) >= 1
    assert f.findings[0]["metric"] == "hrv"
    assert f.findings[0]["outlier_source"] == "ringconn"
    assert f.raw["anomaly_count"] >= 1


def test_specialist_run_empty_when_consistent(db):
    from app.agents.cross_source_validator.specialist import CrossSourceValidatorSpecialist
    from app.utils.timezone import get_china_today
    today = get_china_today()
    _add(db, user_id=10, record_date=today, data_source="garmin", hrv=50.0)
    _add(db, user_id=10, record_date=today, data_source="ringconn", hrv=50.4)
    db.commit()

    sp = CrossSourceValidatorSpecialist()
    f = sp.run(_twin(user_id=10), {"db": db})
    assert f.findings == []
    assert f.raw["anomaly_count"] == 0


def test_specialist_run_skips_without_db():
    from app.agents.cross_source_validator.specialist import CrossSourceValidatorSpecialist
    sp = CrossSourceValidatorSpecialist()
    f = sp.run(_twin(user_id=11), {})  # 无 db
    assert f.findings == []
    assert f.raw.get("skipped") == "no_db"


def test_specialist_registered_in_registry():
    from app.orchestrator.specialists import get_specialist
    assert get_specialist("cross_source_validator") is not None
