"""health_manage 的 date 参数归一化 — 修「修改早餐」传字面 'today' → 422 的 bug。

founder 实测: health_manage(record_type='diet', operation='list', date='today') → 端点
把 'today' 当 start_date 解析 → 422 date_from_datetime_parsing → 修改失败。
"""
from datetime import date, datetime, timedelta, timezone

from app.services.agent_executor import _normalize_relative_date

BJ = timezone(timedelta(hours=8))


def test_today_resolves_to_iso_date():
    today = datetime.now(BJ).date()
    assert _normalize_relative_date("today") == today.isoformat()
    assert _normalize_relative_date("今天") == today.isoformat()
    assert _normalize_relative_date("今日") == today.isoformat()


def test_relative_words():
    today = datetime.now(BJ).date()
    assert _normalize_relative_date("昨天") == (today - timedelta(days=1)).isoformat()
    assert _normalize_relative_date("yesterday") == (today - timedelta(days=1)).isoformat()
    assert _normalize_relative_date("前天") == (today - timedelta(days=2)).isoformat()
    assert _normalize_relative_date("明天") == (today + timedelta(days=1)).isoformat()


def test_iso_date_passthrough():
    assert _normalize_relative_date("2026-07-13") == "2026-07-13"
    # 带时间的 ISO → 取日期部分
    assert _normalize_relative_date("2026-07-13T10:30:00") == "2026-07-13"


def test_date_and_datetime_objects():
    assert _normalize_relative_date(date(2026, 7, 13)) == "2026-07-13"
    assert _normalize_relative_date(datetime(2026, 7, 13, 8, 0)) == "2026-07-13"


def test_unparseable_returns_none_not_garbage():
    # 解析不出 → None (调用方不带日期过滤, 列近期; 绝不把垃圾当 start_date 发 → 避免 422)
    assert _normalize_relative_date("someday") is None
    assert _normalize_relative_date("") is None
    assert _normalize_relative_date(None) is None
    assert _normalize_relative_date("2026-13-99") is None  # 非法日期
