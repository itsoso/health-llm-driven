"""Synthetic target-day regressions; no production conversations or identifiers."""
from datetime import date, datetime, timezone

import pytest

from app.services.health_query_dimensions import normalize_health_query_args
from app.services.health_query_batch import validate_plan


def test_normalization_preserves_explicit_date_window_without_days_alias():
    args = normalize_health_query_args({
        'dimension': 'diet', 'start_date': '2031-04-02', 'end_date': '2031-04-02',
        'timezone': 'Asia/Shanghai', 'user_id': 999,
    })
    assert args == {'dimension': 'diet', 'start_date': '2031-04-02',
                    'end_date': '2031-04-02', 'timezone': 'Asia/Shanghai'}


def test_batch_rejects_calendar_window_instead_of_reading_recent_days():
    _, _, error = validate_plan({'queries': [{
        'dimension': 'sleep', 'start_date': '2031-04-02', 'end_date': '2031-04-02',
    }]}, valid_dimensions=frozenset({'sleep'}))
    assert error and '日期' in error


def test_calendar_day_is_user_local_and_last_night_is_wake_date():
    from app.services.agent_query_window import resolve_calendar_query_window
    now = datetime(2031, 4, 2, 17, tzinfo=timezone.utc)
    diet = resolve_calendar_query_window('昨天吃了什么', now, 'diet')
    sleep = resolve_calendar_query_window('昨晚睡眠如何', now, 'sleep')
    assert diet == {'start_date': '2031-04-02', 'end_date': '2031-04-02', 'timezone': 'Asia/Shanghai'}
    assert sleep['start_date'] == sleep['end_date'] == '2031-04-03'
    assert resolve_calendar_query_window('2031-04-01晚上的睡眠', now, 'sleep')['start_date'] == '2031-04-02'
    assert resolve_calendar_query_window('上周的饮食', now, 'diet') is None
    assert resolve_calendar_query_window('昨天和今天的饮食', now, 'diet') is None


def test_window_validation_rejects_partial_reverse_and_unbounded_inputs():
    from app.services.agent_query_window import parse_query_window
    for args in ({'start_date': '2031-04-01'},
                 {'start_date': '2031-04-02', 'end_date': '2031-04-01'},
                 {'start_date': '2031-01-01', 'end_date': '2031-04-02'},
                 {'start_date': '2031-04-01', 'end_date': '2031-04-02', 'timezone': 'Unknown/Zone'}):
        with pytest.raises(ValueError):
            parse_query_window(args)


@pytest.fixture
def owners(db):
    from app.models.user import User
    a = User(username='window-owner-a', email='window-a@example.test', name='Synthetic A', hashed_password='fixture')
    b = User(username='window-owner-b', email='window-b@example.test', name='Synthetic B', hashed_password='fixture')
    db.add_all([a, b])
    db.flush()
    return a.id, b.id


def window(start='2031-04-02', end='2031-04-02'):
    from app.services.agent_query_window import parse_query_window
    return parse_query_window({'start_date': start, 'end_date': end, 'timezone': 'Asia/Shanghai'})


def test_diet_returns_only_owner_and_inclusive_target_dates(db, owners):
    from app.models.daily_health import DietRecord
    from app.services.agent_query_window import read_calendar_health_query
    a, b = owners
    db.add_all([DietRecord(user_id=uid, record_date=date(2031, 4, day), meal_type='午餐', food_name=name)
                for uid, day, name in [(a,1,'outside'), (a,2,'first'), (a,3,'last'), (a,4,'outside'), (b,2,'other-owner')]])
    db.flush()
    result = read_calendar_health_query(db, a, 'diet', window(end='2031-04-03'))
    assert [r['food_name'] for r in result['records']] == ['first', 'last']
    assert result['availability'] == 'available'
    assert result['window']['end_date'] == '2031-04-03'
    empty = read_calendar_health_query(db, a, 'diet', window('2031-05-01','2031-05-01'))
    assert empty['availability'] == 'no_data' and empty['records'] == []
    with pytest.raises(ValueError):
        read_calendar_health_query(db, None, 'diet', window())


def test_sleep_never_substitutes_old_night_and_preserves_unknown_stages(db, owners):
    from app.models.daily_health import GarminData
    from app.services.agent_query_window import read_calendar_health_query
    a, b = owners
    db.add_all([
        GarminData(user_id=a, record_date=date(2031,4,1), data_source='garmin', sleep_score=91, total_sleep_duration=440),
        GarminData(user_id=b, record_date=date(2031,4,2), data_source='garmin', sleep_score=88, total_sleep_duration=430),
        GarminData(user_id=a, record_date=date(2031,4,2), data_source='garmin', steps=100),
    ])
    db.flush()
    result = read_calendar_health_query(db, a, 'sleep', window())
    assert result['availability'] == 'no_data' and result['records'] == []
    db.add(GarminData(user_id=a, record_date=date(2031,4,2), data_source='apple_health', sleep_score=70, total_sleep_duration=380))
    db.flush()
    result = read_calendar_health_query(db, a, 'sleep', window())
    assert result['availability'] == 'partial'
    assert len(result['records']) == 1
    row = result['records'][0]
    assert row['record_date'] == '2031-04-02'
    assert row['rem_sleep_duration'] is None
    assert row['sources']['total_sleep_duration'] == 'apple_health'
    assert 'sync_status_unknown' in result['limitations']


def test_resolver_accepts_explicit_weekday_and_bounded_date_range():
    from app.services.agent_query_window import resolve_calendar_query_window
    now = datetime(2031, 4, 10, 3, tzinfo=timezone.utc)  # Thursday in Beijing.
    assert resolve_calendar_query_window('本周一吃了什么', now, 'diet')['start_date'] == '2031-04-07'
    assert resolve_calendar_query_window('上周三的睡眠', now, 'sleep')['start_date'] == '2031-04-02'
    span = resolve_calendar_query_window('2031-04-01到2031-04-03的饮食', now, 'diet')
    assert span['start_date'] == '2031-04-01' and span['end_date'] == '2031-04-03'
    assert resolve_calendar_query_window('2031-04-01和2031-04-03对比', now, 'diet') is None
    assert resolve_calendar_query_window('2031-01-01到2031-04-03的饮食', now, 'diet') is None
    assert resolve_calendar_query_window('2031-04-12的饮食', now, 'diet') is None


def test_read_failure_is_not_reported_as_no_data():
    from app.services.agent_query_window import read_calendar_health_query
    class BrokenDatabase:
        def query(self, *args):
            raise RuntimeError('synthetic unavailable')
    with pytest.raises(RuntimeError, match='synthetic unavailable'):
        read_calendar_health_query(BrokenDatabase(), 17, 'diet', window())


@pytest.mark.parametrize('text', ['昨天至明天的饮食', '2031-04-01至4月3日的饮食',
                                  '截至2031-04-01的饮食', '最近七天到2031-04-01的饮食'])
def test_partial_time_expression_never_authorizes_a_different_window(text):
    from app.services.agent_query_window import resolve_calendar_query_window
    assert resolve_calendar_query_window(text, datetime(2031,4,10,tzinfo=timezone.utc), 'diet') is None


def test_result_budget_fails_explicitly_instead_of_truncating(db, owners, monkeypatch):
    from app.models.daily_health import DietRecord
    from app.services import agent_query_window as query
    a, _ = owners
    db.add_all([DietRecord(user_id=a, record_date=date(2031,4,2), meal_type='午餐', food_name='Synthetic meal') for _ in range(3)])
    db.flush()
    monkeypatch.setattr(query, 'MAX_CALENDAR_ROWS', 2, raising=False)
    with pytest.raises(ValueError, match='缩小'):
        query.read_calendar_health_query(db, a, 'diet', window())


def test_large_field_budget_is_explicit_and_missing_nutrition_remains_unknown(db, owners, monkeypatch):
    from app.models.daily_health import DietRecord
    from app.services import agent_query_window as query
    a, _ = owners
    db.add(DietRecord(user_id=a, record_date=date(2031,4,2), meal_type='午餐', food_name='Synthetic food'))
    db.flush()
    result = query.read_calendar_health_query(db, a, 'diet', window())
    assert result['records'][0]['calories'] is None
    assert result['records'][0]['protein'] is None
    monkeypatch.setattr(query, 'MAX_CALENDAR_RESULT_CHARS', 20, raising=False)
    with pytest.raises(ValueError, match='缩小'):
        query.read_calendar_health_query(db, a, 'diet', window())
