"""A closed Garmin review projects facts instead of classifying arbitrary prose."""
from app.services.agent_garmin_review_evidence import bounded_garmin_record_facts


def test_facts_project_only_finite_stored_metrics_with_display_precision():
    text=bounded_garmin_record_facts({'availability':'available','record':{
        'source':'garmin','start_time':'2026-10-09T08:00:00+00:00',
        'distance_meters':3123.456,'duration_seconds':1800,'avg_heart_rate':127.346,'max_heart_rate':143,
        'calories':True,'avg_pace_seconds_per_km':float('nan'),
        'invented_age':40}})
    assert '3.12' in text and '127.35' in text
    assert '40' not in text and 'nan' not in text and 'True' not in text
    assert '无法' in text and '年龄' in text
    assert '不是完整的个体训练分析' in text
    assert '2026-10-09T08:00:00+00:00' in text
    assert '上午' not in text


def test_missing_record_cannot_be_presented_as_read_or_diagnosed():
    text=bounded_garmin_record_facts(None)
    assert '未取得可用于分析的完整运动记录' in text
    assert '距离：' not in text and '心率：' not in text
    assert '不是完整的个体训练分析' in text
