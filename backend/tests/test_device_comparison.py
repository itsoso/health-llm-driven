# -*- coding: utf-8 -*-
"""双设备一致性对比回归。

钉:≥2 源才比;同指标 by_source/diff/agreement;单源不比;db 分组按 data_source;端点鉴权。
"""
from datetime import timedelta

from app.services.device_comparison_service import compare_sources, device_comparison


def test_compare_two_sources():
    out = compare_sources({
        "garmin": {"hrv": 50.0, "resting_heart_rate": 52, "sleep_score": 80},
        "apple_watch": {"hrv": 46.0, "resting_heart_rate": 54, "sleep_score": 80},
    })
    by = {c["metric"]: c for c in out}
    assert by["hrv"]["by_source"] == {"garmin": 50.0, "apple_watch": 46.0}
    assert by["hrv"]["diff"] == 4.0
    assert by["hrv"]["agreement"] < 1.0          # 有差异
    assert by["sleep_score"]["agreement"] == 1.0  # 完全一致
    assert by["sleep_score"]["diff"] == 0


def test_single_source_no_comparison():
    out = compare_sources({"garmin": {"hrv": 50.0}})
    assert out == []  # 只有一台 → 不比


def test_metric_only_in_one_source_skipped():
    out = compare_sources({
        "garmin": {"hrv": 50.0, "vo2max_running": 48.0},
        "apple_watch": {"hrv": 49.0},  # 无 vo2max
    })
    metrics = {c["metric"] for c in out}
    assert "hrv" in metrics and "vo2max_running" not in metrics


def test_device_comparison_db_groups_by_source(db):
    from app.models.daily_health import GarminData
    from app.utils.timezone import get_china_today
    today = get_china_today()
    db.add(GarminData(user_id=1, record_date=today, data_source="garmin", hrv=50.0, resting_heart_rate=52))
    db.add(GarminData(user_id=1, record_date=today, data_source="apple_watch", hrv=46.0, resting_heart_rate=55))
    db.add(GarminData(user_id=1, record_date=today - timedelta(days=1), data_source="garmin", hrv=52.0))
    db.commit()

    out = device_comparison(db, 1, days=7)
    assert set(out["sources"]) == {"garmin", "apple_watch"}
    hrv = next(c for c in out["comparisons"] if c["metric"] == "hrv")
    # garmin 均值 (50+52)/2=51, apple_watch 46 → 都在
    assert hrv["by_source"]["apple_watch"] == 46.0
    assert hrv["by_source"]["garmin"] == 51.0


def test_device_comparison_single_source_note(db):
    from app.models.daily_health import GarminData
    from app.utils.timezone import get_china_today
    db.add(GarminData(user_id=2, record_date=get_china_today(), data_source="garmin", hrv=50.0))
    db.commit()
    out = device_comparison(db, 2, days=7)
    assert out["comparisons"] == [] and "≥2" in out["note"]


def test_endpoint_requires_auth(client):
    r = client.get("/api/v1/devices/compare")
    assert r.status_code in (401, 403)


# ── /devices/sources/summary ──

def test_sources_summary_per_source_coverage_and_latest(db):
    from app.models.daily_health import GarminData
    from app.services.device_comparison_service import sources_summary
    from app.utils.timezone import get_china_today

    today = get_china_today()
    # apple-watch: 2 天覆盖, 最新 today (steps=8800 latest)
    db.add(GarminData(user_id=7, record_date=today, data_source="apple-watch", steps=8800, resting_heart_rate=54))
    db.add(GarminData(user_id=7, record_date=today - timedelta(days=1), data_source="apple-watch", steps=7000))
    # ringconn: 1 天覆盖
    db.add(GarminData(user_id=7, record_date=today, data_source="ringconn", hrv=61.0, spo2_avg=97.0))
    db.commit()

    out = sources_summary(db, 7, days=30)
    assert out["window_days"] == 30
    srcs = {s["data_source"]: s for s in out["sources"]}
    assert srcs["apple-watch"]["days_covered"] == 2
    assert srcs["ringconn"]["days_covered"] == 1
    # 按 days_covered 降序 → apple-watch 在前
    assert out["sources"][0]["data_source"] == "apple-watch"
    assert srcs["apple-watch"]["latest_date"] == today.isoformat()
    # metrics: 最近一天的非空值
    assert srcs["apple-watch"]["metrics"]["steps"] == 8800
    assert srcs["ringconn"]["metrics"]["hrv"] == 61.0
    assert srcs["ringconn"]["metrics"]["spo2_avg"] == 97.0


def test_sources_summary_latest_nonnull_picks_most_recent(db):
    from app.models.daily_health import GarminData
    from app.services.device_comparison_service import sources_summary
    from app.utils.timezone import get_china_today

    today = get_china_today()
    # 最新一天 steps 为空, 上一天有 → 取上一天的值 (most-recent non-null)
    db.add(GarminData(user_id=8, record_date=today, data_source="garmin", hrv=40.0))
    db.add(GarminData(user_id=8, record_date=today - timedelta(days=1), data_source="garmin", steps=5000))
    db.commit()

    out = sources_summary(db, 8, days=30)
    g = out["sources"][0]
    assert g["metrics"]["hrv"] == 40.0
    assert g["metrics"]["steps"] == 5000
    # 最近一天视图必须是同一天的真实快照，不能混入前一天的步数。
    assert g["latest_day_metrics"] == {"hrv": 40.0}


def test_sources_summary_endpoint_requires_auth(client):
    r = client.get("/api/v1/devices/sources/summary")
    assert r.status_code in (401, 403)
