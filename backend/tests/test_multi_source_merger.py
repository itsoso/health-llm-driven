"""Phase 4: Twin builder 多源合并 — 同一日期不同源,各字段独立选源.

优先级策略由 device_source_priority 决定 (single source of truth);
本文件验证 merge_field/merge_rows wrapper 正确委托。
"""
from app.services.multi_source_merger import merge_field, merge_rows


class _Row:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)
    def __getattr__(self, name):
        return None  # 任何未设字段返回 None (Python 类似 SQLAlchemy 行为)


def test_merge_field_picks_highest_priority_source_for_hrv():
    """HRV 优先级: ringconn > garmin > apple-watch (戒指贴肤光路稳)."""
    rows = [
        _Row(data_source="garmin", hrv=45.0),
        _Row(data_source="apple-watch", hrv=48.0),
        _Row(data_source="ringconn", hrv=52.0),  # 最高优先级
    ]
    v, s = merge_field(rows, "hrv")
    assert v == 52.0
    assert s == "ringconn"


def test_merge_field_steps_prefers_watch_over_garmin():
    """步数 — Apple Watch 优先 (全天腕上佩戴 + 高采样)."""
    rows = [
        _Row(data_source="apple-watch", steps=8500),  # 优先
        _Row(data_source="garmin", steps=9200),
    ]
    v, s = merge_field(rows, "steps")
    assert v == 8500
    assert s == "apple-watch"


def test_merge_field_sleep_prefers_ring():
    """睡眠 — RingConn 戒指 > Garmin > Apple Watch."""
    rows = [
        _Row(data_source="garmin", sleep_score=72),
        _Row(data_source="ringconn", sleep_score=84),  # 优先
        _Row(data_source="apple-watch", sleep_score=78),
    ]
    v, s = merge_field(rows, "sleep_score")
    assert v == 84
    assert s == "ringconn"


def test_merge_field_resting_hr_prefers_apple_watch():
    """静息心率 — Apple Watch + RingConn 优先(用户指定,Garmin 仅 fallback)."""
    rows = [
        _Row(data_source="ringconn", resting_heart_rate=55),
        _Row(data_source="garmin", resting_heart_rate=52),
        _Row(data_source="apple-watch", resting_heart_rate=54),  # 优先
    ]
    v, s = merge_field(rows, "resting_heart_rate")
    assert v == 54
    assert s == "apple-watch"


def test_merge_field_falls_back_to_lower_priority_when_top_missing():
    """高优先级源没值时降级 (ringconn 缺 → garmin)."""
    rows = [
        _Row(data_source="ringconn", hrv=None),     # 戒指当晚没戴
        _Row(data_source="apple-watch", hrv=51.0),
        _Row(data_source="garmin", hrv=49.0),       # garmin 次优,中标
    ]
    v, s = merge_field(rows, "hrv")
    assert v == 49.0
    assert s == "garmin"


def test_merge_field_returns_none_when_no_source_has_value():
    rows = [
        _Row(data_source="garmin", hrv=None),
        _Row(data_source="apple-watch", hrv=None),
    ]
    v, s = merge_field(rows, "hrv")
    assert v is None
    assert s is None


def test_merge_field_unknown_source_used_as_last_resort():
    """白名单外 source (如 'fitbit')—仍可中标如果别的都没值."""
    rows = [
        _Row(data_source="fitbit", hrv=47.0),
    ]
    v, s = merge_field(rows, "hrv")
    assert v == 47.0
    assert s == "fitbit"


def test_merge_rows_returns_per_field_source_dict():
    """同 (user, date) 多行 — 每字段独立选源,sources dict 反映每字段实际中标源."""
    rows = [
        _Row(data_source="garmin", hrv=45.0, steps=9000, sleep_score=70),
        _Row(data_source="apple-watch", hrv=None, steps=9500, sleep_score=None),
        _Row(data_source="ringconn", hrv=52.0, steps=None, sleep_score=85),
    ]
    out = merge_rows(rows, ["hrv", "steps", "sleep_score"])
    assert out["values"]["hrv"] == 52.0          # ringconn
    assert out["values"]["steps"] == 9500        # apple-watch
    assert out["values"]["sleep_score"] == 85    # ringconn
    assert out["sources"]["hrv"] == "ringconn"
    assert out["sources"]["steps"] == "apple-watch"
    assert out["sources"]["sleep_score"] == "ringconn"


def test_merge_rows_single_garmin_row_back_compat():
    """只有 garmin 一行 (Phase 4 上线前的旧数据) — 不破坏."""
    rows = [_Row(data_source="garmin", hrv=48.0, steps=8000, sleep_score=75, resting_heart_rate=58)]
    out = merge_rows(rows, ["hrv", "steps", "sleep_score", "resting_heart_rate"])
    assert out["values"]["hrv"] == 48.0
    assert out["sources"]["hrv"] == "garmin"
    assert out["sources"]["resting_heart_rate"] == "garmin"


def test_merge_field_body_temp_prefers_ring():
    """体温偏差 - RingConn 戒指夜间持续监测最准."""
    rows = [
        _Row(data_source="apple-watch", body_temp_deviation_c=0.3),
        _Row(data_source="ringconn", body_temp_deviation_c=0.5),
    ]
    v, s = merge_field(rows, "body_temp_deviation_c")
    assert v == 0.5
    assert s == "ringconn"
