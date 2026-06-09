"""Unit tests for the pure per-metric source priority module."""
from app.services.device_source_priority import (
    DEFAULT_PRIORITY,
    METRIC_SOURCE_PRIORITY,
    merge_daily_by_priority,
    pick_value,
    priority_for,
)


class _Row:
    """轻量 stand-in for GarminData ORM row."""
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)
    def __getattr__(self, name):
        return None


# ── priority table sanity ──

def test_sleep_spo2_hrv_prefer_ring():
    for metric in ("total_sleep_duration", "sleep_score", "spo2_avg", "spo2_min", "hrv"):
        assert priority_for(metric)[0] == "ringconn", metric


def test_activity_metrics_prefer_watch():
    for metric in ("steps", "distance_meters", "active_calories", "avg_heart_rate"):
        assert priority_for(metric)[0] == "apple-watch", metric


def test_garmin_proprietary_prefer_garmin():
    for metric in ("resting_heart_rate", "body_battery_current", "stress_level",
                   "training_readiness_score", "training_status", "vo2max_running", "load_ratio"):
        assert priority_for(metric)[0] == "garmin", metric


def test_unknown_metric_uses_default_priority():
    assert priority_for("some_new_metric") == DEFAULT_PRIORITY
    assert DEFAULT_PRIORITY[0] == "garmin"


# ── pick_value ──

def test_pick_value_single_source():
    rows = [_Row(data_source="garmin", hrv=48.0)]
    assert pick_value(rows, "hrv") == (48.0, "garmin")


def test_pick_value_two_sources_overlapping_picks_priority():
    rows = [
        _Row(data_source="apple-watch", hrv=50.0),
        _Row(data_source="ringconn", hrv=55.0),
    ]
    assert pick_value(rows, "hrv") == (55.0, "ringconn")


def test_pick_value_missing_preferred_falls_back():
    rows = [
        _Row(data_source="ringconn", hrv=None),
        _Row(data_source="garmin", hrv=49.0),
        _Row(data_source="apple-watch", hrv=51.0),
    ]
    # ringconn(top) 缺值 → garmin(次优) 中标
    assert pick_value(rows, "hrv") == (49.0, "garmin")


def test_pick_value_empty():
    assert pick_value([], "hrv") == (None, None)


def test_pick_value_all_null():
    rows = [_Row(data_source="garmin", hrv=None), _Row(data_source="ringconn", hrv=None)]
    assert pick_value(rows, "hrv") == (None, None)


def test_pick_value_last_resort_unknown_source():
    rows = [_Row(data_source="fitbit", hrv=47.0)]  # 不在任何优先级表
    assert pick_value(rows, "hrv") == (47.0, "fitbit")


# ── merge_daily_by_priority ──

def test_merge_single_source_equals_that_row():
    """back-compat: 单行合并 == 该行 (旧 garmin-only 用户行为不变)."""
    rows = [_Row(data_source="garmin", hrv=48.0, steps=8000, resting_heart_rate=58, sleep_score=75)]
    merged = merge_daily_by_priority(rows, ["hrv", "steps", "resting_heart_rate", "sleep_score"])
    assert merged["hrv"] == 48.0
    assert merged["steps"] == 8000
    assert merged["resting_heart_rate"] == 58
    assert merged["sleep_score"] == 75
    assert merged["_source_by_metric"]["hrv"] == "garmin"


def test_merge_two_sources_overlapping():
    rows = [
        _Row(data_source="garmin", hrv=45.0, steps=9200, resting_heart_rate=52, sleep_score=70),
        _Row(data_source="apple-watch", hrv=48.0, steps=8500, resting_heart_rate=54, sleep_score=78),
        _Row(data_source="ringconn", hrv=52.0, steps=None, resting_heart_rate=55, sleep_score=85),
    ]
    merged = merge_daily_by_priority(rows, ["hrv", "steps", "resting_heart_rate", "sleep_score"])
    assert merged["hrv"] == 52.0                  # ring
    assert merged["steps"] == 8500                # watch
    assert merged["resting_heart_rate"] == 52     # garmin
    assert merged["sleep_score"] == 85            # ring
    sm = merged["_source_by_metric"]
    assert sm["hrv"] == "ringconn"
    assert sm["steps"] == "apple-watch"
    assert sm["resting_heart_rate"] == "garmin"
    assert sm["sleep_score"] == "ringconn"


def test_merge_missing_preferred_falls_back():
    rows = [
        _Row(data_source="apple-watch", steps=8500),   # watch 是 steps 首选但缺其他
        _Row(data_source="garmin", steps=None, resting_heart_rate=53),
    ]
    merged = merge_daily_by_priority(rows, ["steps", "resting_heart_rate"])
    assert merged["steps"] == 8500
    assert merged["resting_heart_rate"] == 53


def test_merge_empty():
    merged = merge_daily_by_priority([], ["hrv", "steps"])
    assert merged.get("hrv") is None
    assert merged.get("steps") is None
    assert merged["_source_by_metric"] == {}


def test_merge_default_metrics_covers_all_priority_keys():
    rows = [_Row(data_source="garmin", **{k: 1 for k in METRIC_SOURCE_PRIORITY})]
    merged = merge_daily_by_priority(rows)
    for k in METRIC_SOURCE_PRIORITY:
        assert merged[k] == 1


def test_merge_accepts_dict_rows():
    rows = [
        {"data_source": "ringconn", "hrv": 53.0},
        {"data_source": "garmin", "hrv": 47.0},
    ]
    merged = merge_daily_by_priority(rows, ["hrv"])
    assert merged["hrv"] == 53.0
    assert merged["_source_by_metric"]["hrv"] == "ringconn"
