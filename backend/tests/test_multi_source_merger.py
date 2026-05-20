"""Phase 4: Twin builder 多源合并 — 同一日期不同源,各字段独立选源."""
from app.services.multi_source_merger import merge_field, merge_rows


class _Row:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)
    def __getattr__(self, name):
        return None  # 任何未设字段返回 None (Python 类似 SQLAlchemy 行为)


def test_merge_field_picks_highest_priority_source_for_hrv():
    """HRV 优先级: ringconn > oura > apple-watch > garmin."""
    rows = [
        _Row(data_source="garmin", hrv=45.0),
        _Row(data_source="apple-watch", hrv=48.0),
        _Row(data_source="ringconn", hrv=52.0),  # 最高优先级
    ]
    v, s = merge_field(rows, "hrv")
    assert v == 52.0
    assert s == "ringconn"


def test_merge_field_steps_prefers_garmin_over_watch():
    """步数 / 卡路里 — Garmin 优先 (户外 GPS 准)."""
    rows = [
        _Row(data_source="apple-watch", steps=8500),
        _Row(data_source="garmin", steps=9200),  # 优先
    ]
    v, s = merge_field(rows, "steps")
    assert v == 9200
    assert s == "garmin"


def test_merge_field_sleep_prefers_oura():
    """睡眠 — Oura 戒指 > Apple Watch > Garmin."""
    rows = [
        _Row(data_source="garmin", sleep_score=72),
        _Row(data_source="oura", sleep_score=84),  # 优先
        _Row(data_source="apple-watch", sleep_score=78),
    ]
    v, s = merge_field(rows, "sleep_score")
    assert v == 84
    assert s == "oura"


def test_merge_field_falls_back_to_lower_priority_when_top_missing():
    """高优先级源没值时降级."""
    rows = [
        _Row(data_source="oura", hrv=None),       # 戒指当晚没戴
        _Row(data_source="apple-watch", hrv=51.0),  # 表 fallback
        _Row(data_source="garmin", hrv=49.0),
    ]
    v, s = merge_field(rows, "hrv")
    assert v == 51.0
    assert s == "apple-watch"


def test_merge_field_returns_none_when_no_source_has_value():
    rows = [
        _Row(data_source="garmin", hrv=None),
        _Row(data_source="apple-watch", hrv=None),
    ]
    v, s = merge_field(rows, "hrv")
    assert v is None
    assert s is None


def test_merge_field_unknown_source_used_as_last_resort():
    """白名单外 source (如 'unknown')—仍可中标如果别的都没值."""
    rows = [
        _Row(data_source="unknown", hrv=47.0),
    ]
    v, s = merge_field(rows, "hrv")
    assert v == 47.0
    assert s == "unknown"


def test_merge_rows_returns_per_field_source_dict():
    """同 (user, date) 多行 — 每字段独立选源,sources dict 反映每字段实际中标源."""
    rows = [
        _Row(data_source="garmin", hrv=45.0, steps=9000, sleep_score=70),
        _Row(data_source="oura", hrv=None, steps=None, sleep_score=85),
        _Row(data_source="ringconn", hrv=52.0, steps=None, sleep_score=None),
    ]
    out = merge_rows(rows, ["hrv", "steps", "sleep_score"])
    assert out["values"]["hrv"] == 52.0
    assert out["values"]["steps"] == 9000
    assert out["values"]["sleep_score"] == 85
    assert out["sources"]["hrv"] == "ringconn"
    assert out["sources"]["steps"] == "garmin"
    assert out["sources"]["sleep_score"] == "oura"


def test_merge_rows_single_garmin_row_back_compat():
    """只有 garmin 一行 (Phase 4 上线前的旧数据) — 不破坏."""
    rows = [_Row(data_source="garmin", hrv=48.0, steps=8000, sleep_score=75, resting_heart_rate=58)]
    out = merge_rows(rows, ["hrv", "steps", "sleep_score", "resting_heart_rate"])
    assert out["values"]["hrv"] == 48.0
    assert out["sources"]["hrv"] == "garmin"
    assert out["sources"]["resting_heart_rate"] == "garmin"


def test_merge_field_body_temp_prefers_oura():
    """体温偏差 - Oura 夜间持续监测最准."""
    rows = [
        _Row(data_source="apple-watch", body_temp_deviation_c=0.3),
        _Row(data_source="oura", body_temp_deviation_c=0.5),
    ]
    v, s = merge_field(rows, "body_temp_deviation_c")
    assert v == 0.5
    assert s == "oura"
