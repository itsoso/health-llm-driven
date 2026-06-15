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
    # 用 ringconn(任何指标都不被排除)→ 每个 priority key 都能解析;garmin 血氧已整源剔除。
    rows = [_Row(data_source="ringconn", **{k: 1 for k in METRIC_SOURCE_PRIORITY})]
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


# ── 安全下限指标:worst-value(跨源最小),不让正常读数掩盖危险低值 ──

def test_spo2_picks_worst_value_not_preferred_source():
    """戒指(优先源) spo2 正常,手表低 → 必须取手表的低值,否则掩盖低氧风险。"""
    rows = [
        _Row(data_source="ringconn", spo2_avg=96.0, spo2_min=95.0),
        _Row(data_source="apple-watch", spo2_avg=87.0, spo2_min=82.0),
    ]
    v_avg, src_avg = pick_value(rows, "spo2_avg")
    assert v_avg == 87.0, "spo2_avg 应取跨源最小,而非戒指 96"
    assert src_avg == "apple-watch"
    v_min, src_min = pick_value(rows, "spo2_min")
    assert v_min == 82.0
    assert src_min == "apple-watch"


def test_spo2_worst_value_via_merge():
    rows = [
        {"data_source": "ringconn", "spo2_avg": 96.0, "spo2_min": 94.0},
        {"data_source": "apple-watch", "spo2_avg": 88.0, "spo2_min": 80.0},
    ]
    merged = merge_daily_by_priority(rows, ["spo2_avg", "spo2_min"])
    assert merged["spo2_avg"] == 88.0
    assert merged["spo2_min"] == 80.0
    assert merged["_source_by_metric"]["spo2_min"] == "apple-watch"


def test_spo2_excludes_garmin_even_if_only_source():
    """血氧整源剔除 Garmin(腕式反射不准):garmin-only → 无血氧(None),不采纳。"""
    rows = [_Row(data_source="garmin", spo2_avg=97.0, spo2_min=93.0)]
    assert pick_value(rows, "spo2_avg") == (None, None)
    assert pick_value(rows, "spo2_min") == (None, None)


def test_spo2_garmin_low_does_not_override_ringconn():
    """Garmin 假性低值不得经 worst-value 压过 RingConn:取 RingConn 值,garmin 被排除。"""
    rows = [
        _Row(data_source="ringconn", spo2_avg=96.0, spo2_min=95.0),
        _Row(data_source="garmin", spo2_avg=85.0, spo2_min=80.0),  # 不准的低值,应被剔除
    ]
    assert pick_value(rows, "spo2_avg") == (96.0, "ringconn")
    assert pick_value(rows, "spo2_min") == (95.0, "ringconn")


def test_spo2_apple_watch_still_counts_for_worst_value():
    """只排 Garmin:Apple Watch 的真实低值仍按 worst-value 采纳(不误伤其他源)。"""
    rows = [
        _Row(data_source="ringconn", spo2_avg=96.0, spo2_min=95.0),
        _Row(data_source="apple-watch", spo2_avg=88.0, spo2_min=82.0),
    ]
    assert pick_value(rows, "spo2_avg") == (88.0, "apple-watch")


def test_garmin_excluded_only_for_spo2_not_hrv():
    """排除是按指标的:HRV 等仍可用 Garmin 作 fallback。"""
    rows = [_Row(data_source="garmin", hrv=49.0)]
    assert pick_value(rows, "hrv") == (49.0, "garmin")


def test_spo2_all_none_returns_none():
    rows = [_Row(data_source="ringconn"), _Row(data_source="garmin")]
    assert pick_value(rows, "spo2_avg") == (None, None)
