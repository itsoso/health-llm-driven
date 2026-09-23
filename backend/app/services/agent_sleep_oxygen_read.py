"""Bounded oxygen observations; no latest-night substitution or apnea diagnosis."""
from collections import defaultdict

from sqlalchemy import func

from app.models.daily_health import GarminData, SpO2Sample
from app.services.device_source_priority import excluded_sources
from app.services.multi_source_merger import merge_rows
from app.services.agent_query_window import MAX_CALENDAR_ROWS, _bounded_result


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
    return _bounded_result({
        'dimension': 'spo2', 'window': window.as_dict(), 'records': records,
        'availability': 'partial' if records else 'no_data',
        'coverage': {'requested_days': (window.end_date - window.start_date).days + 1,
                     'days_with_data': len(records)},
        'excluded_sources': sorted(excluded_sources('spo2_min')),
        'limitations': ['sleep_interval_not_verified', 'missing_metric_is_unknown_not_abnormal',
                        'not_diagnostic_no_apnea_inference', 'sample_sources_not_combined'],
        'interpretation_note': '按记录日期提供血氧观测及数据来源，未验证每个采样均在睡眠期。'
            '不可将缺失当正常、采样数量当连续监测时长，或据此推算ODI/确诊睡眠呼吸暂停。'
            '已排除不用于血氧判断的设备来源；没有合格数据时应明确说明无法判断。',
    })
