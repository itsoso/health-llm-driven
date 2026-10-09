"""Synthetic evidence boundaries for a scoped existing-run review."""
import pytest
from app.services.agent_garmin_review_evidence import has_unsupported_garmin_claim, bounded_garmin_record_facts

@pytest.mark.parametrize('text', [
    '心率维持在最大心率的70%左右（按40岁估算）。',
    '心率区间稳定，无明显异常波动。',
    '整体来看，这次跑步数据正常，运动强度适中。',
    '当前配速适合作为日常有氧基础，可每周维持3-4次。',
    '可尝试每周缩短30秒-1分钟/公里配速。',
    '不能保证安全，但数据正常。',
    '年龄未知却心率稳定。',
    '无法判断风险不过本次运动安全。',
    '缺少证据仍然运动强度适中。',
])
def test_unsupported_personal_interpretations_are_detected(text):
    assert has_unsupported_garmin_claim(text)

@pytest.mark.parametrize('text', [
    '缺少年龄和最大心率依据，不能判断心率区间。',
    '只有平均和最高心率，无法判断心率稳定或有无异常波动。',
    '这些记录不代表数据正常，也不能保证运动安全。',
    '如不适请停止运动并就医。',
    '记录显示平均心率127，最高心率143。',
])
def test_explicit_uncertainty_is_not_a_positive_claim(text):
    assert not has_unsupported_garmin_claim(text)


def test_fallback_projects_only_finite_stored_metrics_with_display_precision():
    text=bounded_garmin_record_facts({'availability':'available','record':{
        'source':'garmin','start_time':'2026-10-09T08:00:00+00:00',
        'distance_meters':3123.456,'duration_seconds':1800,'avg_heart_rate':127.346,'max_heart_rate':143,
        'calories':True,'avg_pace_seconds_per_km':float('nan'),
        'invented_age':40}})
    assert '3.12' in text and '127.35' in text
    assert '40' not in text and 'nan' not in text and 'True' not in text
    assert '无法' in text and '年龄' in text
