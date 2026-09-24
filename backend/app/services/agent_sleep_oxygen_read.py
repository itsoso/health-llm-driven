"""Bounded oxygen observations; no latest-night substitution or apnea diagnosis."""
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func

from app.models.daily_health import GarminData, SpO2Sample, SleepLevelInterval
from app.services.device_source_priority import excluded_sources
from app.services.multi_source_merger import merge_rows
from app.services.agent_query_window import MAX_CALENDAR_ROWS, _bounded_result


def _night_samples(db, user_id, window, daily):
    """Bound epoch samples to one coherent daily sleep-clock source.

    Bare clock times lose timezone on some import paths. Require independent
    absolute interval bounds from the same owner/source/date to match before
    using the candidate window. Neither bounds nor sample counts prove asleep
    state/continuous coverage. Missing/conflicting provenance fails closed.
    """
    merged = merge_rows(daily, ('sleep_start_time', 'sleep_end_time'))
    start, end = (merged['values'].get(key) for key in ('sleep_start_time', 'sleep_end_time'))
    sources = merged['sources']
    if (window.timezone != 'Asia/Shanghai' or start is None or end is None or start == end
            or sources.get('sleep_start_time') != sources.get('sleep_end_time')):
        return [], ['sleep_interval_unavailable']
    zone = ZoneInfo(window.timezone)
    end_at = datetime.combine(window.end_date, end, zone)
    start_day = window.start_date - timedelta(days=1) if start > end else window.start_date
    start_at = datetime.combine(start_day, start, zone)
    if not timedelta(0) < end_at - start_at <= timedelta(hours=20):
        return [], ['sleep_interval_unavailable']
    start_ms, end_ms = int(start_at.timestamp() * 1000), int(end_at.timestamp() * 1000)
    intervals = (db.query(SleepLevelInterval).filter(
        SleepLevelInterval.user_id == user_id,
        SleepLevelInterval.record_date == window.end_date,
        SleepLevelInterval.source == sources['sleep_start_time'],
    ).order_by(SleepLevelInterval.start_epoch_ms).limit(MAX_CALENDAR_ROWS + 1).all())
    if len(intervals) > MAX_CALENDAR_ROWS:
        raise ValueError('calendar_query_result_limit_exceeded')
    if (not intervals or any(row.start_epoch_ms <= 0 or row.end_epoch_ms <= row.start_epoch_ms
                             for row in intervals)
            or min(row.start_epoch_ms for row in intervals) != start_ms
            or max(row.end_epoch_ms for row in intervals) != end_ms):
        return [], ['sleep_interval_unavailable', 'sleep_clock_timezone_not_attested']
    samples = (db.query(
        SpO2Sample.source, func.count(SpO2Sample.id).label('data_points'),
        func.min(SpO2Sample.spo2_value).label('min_spo2'),
        func.max(SpO2Sample.spo2_value).label('max_spo2'),
        func.avg(SpO2Sample.spo2_value).label('avg_spo2'),
    ).filter(
        SpO2Sample.user_id == user_id,
        SpO2Sample.record_date >= window.start_date - timedelta(days=1),
        SpO2Sample.record_date <= window.end_date,
        SpO2Sample.epoch_ms >= start_ms,
        SpO2Sample.epoch_ms <= end_ms,
        SpO2Sample.source.notin_(excluded_sources('spo2_min')),
    ).group_by(SpO2Sample.source).order_by(SpO2Sample.source)
      .limit(MAX_CALENDAR_ROWS + 1).all())
    if len(samples) > MAX_CALENDAR_ROWS:
        raise ValueError('calendar_query_result_limit_exceeded')
    summaries = [{'source': row.source, 'data_points': row.data_points,
                  'min_spo2': row.min_spo2, 'max_spo2': row.max_spo2,
                  'avg_spo2': float(row.avg_spo2)} for row in samples]
    rows = [{'record_date': window.end_date.isoformat(),
             'daily_metrics': dict.fromkeys(('spo2_avg', 'spo2_min', 'spo2_max')),
             'daily_sources': {}, 'sample_summaries': summaries}] if summaries else []
    return rows, ['sleep_clock_bounds_matched_absolute_intervals', 'samples_without_epoch_excluded']


def read_sleep_oxygen_window(db, user_id, window):
    """Caller validates owner/window; both queries independently retain them.

    Daily device summaries and sampled observations are different evidence. Do
    not merge sources' samples, infer continuous coverage, or manufacture ODI
    from irregular samples. record_date alone cannot attest the sleep interval.
    """
    daily = (db.query(GarminData).filter(
        GarminData.user_id == user_id, GarminData.record_date >= window.start_date,
        GarminData.record_date <= window.end_date,
    ).order_by(GarminData.record_date, GarminData.id).limit(MAX_CALENDAR_ROWS + 1).all())
    if len(daily) > MAX_CALENDAR_ROWS:
        raise ValueError('calendar_query_result_limit_exceeded')
    if window.period == 'sleep_night':
        records, limitations = _night_samples(db, user_id, window, daily)
        return _oxygen_result(window, records, limitations)
    samples = (db.query(
        SpO2Sample.record_date, SpO2Sample.source,
        func.count(SpO2Sample.id).label('data_points'),
        func.min(SpO2Sample.spo2_value).label('min_spo2'),
        func.max(SpO2Sample.spo2_value).label('max_spo2'),
        func.avg(SpO2Sample.spo2_value).label('avg_spo2'),
    ).filter(
        SpO2Sample.user_id == user_id, SpO2Sample.record_date >= window.start_date,
        SpO2Sample.record_date <= window.end_date,
        SpO2Sample.source.notin_(excluded_sources('spo2_min')),
    ).group_by(SpO2Sample.record_date, SpO2Sample.source)
      .order_by(SpO2Sample.record_date, SpO2Sample.source).limit(MAX_CALENDAR_ROWS + 1).all())
    if len(daily) > MAX_CALENDAR_ROWS or len(samples) > MAX_CALENDAR_ROWS:
        raise ValueError('calendar_query_result_limit_exceeded: 记录较多，请缩小查询日期范围。')
    daily_by_day, samples_by_day = defaultdict(list), defaultdict(list)
    for row in daily:
        daily_by_day[row.record_date].append(row)
    for row in samples:
        samples_by_day[row.record_date].append({
            'source': row.source, 'data_points': row.data_points,
            'min_spo2': row.min_spo2, 'max_spo2': row.max_spo2, 'avg_spo2': float(row.avg_spo2),
        })
    records = []
    for day in sorted(daily_by_day.keys() | samples_by_day.keys()):
        merged = merge_rows(daily_by_day[day], ('spo2_avg', 'spo2_min', 'spo2_max'))
        if not samples_by_day[day] and all(value is None for value in merged['values'].values()):
            continue
        records.append({'record_date': day.isoformat(), 'daily_metrics': merged['values'],
                        'daily_sources': merged['sources'], 'sample_summaries': samples_by_day[day]})
    return _oxygen_result(window, records)


def _oxygen_result(window, records, limitations=()):
    return _bounded_result({
        'dimension': 'spo2', 'window': window.as_dict(), 'records': records,
        'date_attribution': 'wake_date' if window.period == 'sleep_night' else 'record_date',
        'source_scope': 'owned_daily_spo2_summaries_and_samples',
        'sync_status': 'unknown',
        'availability': 'partial' if records else 'no_data',
        'coverage': {'requested_days': (window.end_date - window.start_date).days + 1,
                     'days_with_data': len(records)},
        'excluded_sources': sorted(excluded_sources('spo2_min')),
        'limitations': ['sleep_interval_not_verified', 'missing_metric_is_unknown_not_abnormal',
                        'not_diagnostic_no_apnea_inference', 'sample_sources_not_combined',
                        'daily_summary_not_sleep_episode', 'sample_coverage_unknown',
                        'sync_status_unknown', *limitations],
        'interpretation_note': '按记录日期提供血氧观测及数据来源，未验证每个采样均在睡眠期。'
            '不可将缺失当正常、采样数量当连续监测时长，或据此推算ODI/确诊睡眠呼吸暂停。'
            '已排除不用于血氧判断的设备来源；没有合格数据时应明确说明无法判断。',
    })
