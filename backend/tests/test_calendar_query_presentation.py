"""Calendar results must retain target dates through GenUI and evidence."""
import json

import pytest

from app.services.answer_evidence import build_answer_evidence, normalize_answer_evidence
from app.services.genui.table_builder import build_table_from_tool_call


def payload(dimension, records, availability='partial'):
    return {'dimension': dimension,
            'window': {'start_date': '2031-04-02', 'end_date': '2031-04-03', 'timezone': 'Asia/Shanghai'},
            'records': records, 'availability': availability,
            'limitations': ['sync_status_unknown', 'missing_metric_is_unknown_not_abnormal'] if dimension == 'sleep' else []}


def compile_result(data):
    result = json.dumps(data, ensure_ascii=False)
    args = {'dimension': data['dimension'], **data['window']}
    return (build_table_from_tool_call('health_query', args, result),
            build_answer_evidence(tool_calls=[('health_query', args, result)]))


def test_sleep_records_compile_to_dated_table_and_evidence_with_limits():
    data = payload('sleep', [{'record_date': '2031-04-02', 'sleep_score': 73,
                              'total_sleep_duration': 392, 'deep_sleep_duration': None,
                              'rem_sleep_duration': None}])
    block, evidence = compile_result(data)
    assert block['rows'] == [{'date': '2031-04-02', 'dur': '392 分钟', 'score': '73'}]
    assert '2031-04-02' in block['footnote'] and '2031-04-03' in block['footnote']
    assert 'Asia/Shanghai' in block['footnote']
    assert '2031-04-02' in evidence['basis'][0]['label']
    detail = evidence['limitations'][0]['detail']
    assert '2031-04-02' in detail and '同步' in detail
    assert '缺失' in detail
    assert normalize_answer_evidence(evidence) == evidence


def test_diet_uses_history_title_dates_and_never_zero_fills_nutrition():
    data = payload('diet', [
        {'record_date': '2031-04-02', 'meal_type': 'lunch', 'food_name': '合成餐甲', 'calories': None, 'protein': None},
        {'record_date': '2031-04-03', 'meal_type': 'lunch', 'food_items': '合成餐乙', 'calories': 323.4567, 'protein': 12.4567},
    ], 'available')
    block, evidence = compile_result(data)
    assert block['title'] == '饮食记录'
    assert block['rows'][0]['date'] == '2031-04-02'
    assert block['rows'][1]['date'] == '2031-04-03'
    assert '0 kcal' not in json.dumps(block, ensure_ascii=False)
    assert '323.46' in json.dumps(block, ensure_ascii=False)
    assert '12.46' in json.dumps(block, ensure_ascii=False)
    assert any('2031-04-02' in item['label'] for item in evidence['basis'])
    assert any('2031-04-03' in item['label'] for item in evidence['basis'])


def test_no_data_ignores_any_stale_legacy_rows_and_compiles_limitation():
    data = payload('sleep', [], 'no_data')
    data['daily_data'] = [{'date': '2031-04-01', 'sleep_score': 99}]
    block, evidence = compile_result(data)
    assert block is None
    assert evidence['basis'] == []
    assert '2031-04-02' in evidence['limitations'][0]['detail']
    assert '2031-04-01' not in json.dumps(evidence)


@pytest.mark.parametrize('bad_date', ['2031-04-01', '2031-04-04', 'invalid'])
def test_out_of_window_record_cannot_enter_table_or_evidence(bad_date):
    data = payload('sleep', [{'record_date': bad_date, 'sleep_score': 99}])
    block, evidence = compile_result(data)
    assert block is None
    assert not evidence or evidence['basis'] == []


def test_large_table_discloses_partial_display_and_evidence_limits():
    data = payload('diet', [{'record_date': '2031-04-02', 'meal_type': 'snack', 'food_name': '合成点心'} for _ in range(15)], 'available')
    block, evidence = compile_result(data)
    assert len(block['rows']) == 12
    assert '12' in block['footnote'] and '15' in block['footnote']
    assert any('部分' in item['detail'] for item in evidence['limitations'])


def test_unrecognized_limits_and_nested_health_payloads_are_not_exposed():
    data = payload('sleep', [{'record_date': '2031-04-02', 'sleep_score': 73}])
    data['limitations'].append({'private_detail': 'SYNTHETIC_PRIVATE_PAYLOAD'})
    data['limitations'].append('SYNTHETIC_PRIVATE_PAYLOAD')
    data['records'][0]['notes'] = 'SYNTHETIC_PRIVATE_PAYLOAD'
    _, evidence = compile_result(data)
    assert 'SYNTHETIC_PRIVATE_PAYLOAD' not in json.dumps(evidence)


def test_database_target_day_remains_bound_through_json_table_and_evidence(db):
    from datetime import date
    from app.models.daily_health import GarminData
    from app.models.user import User
    from app.services.agent_query_window import parse_query_window, read_calendar_health_query
    user = User(username='calendar-presentation-user', name='Synthetic User',
                email='calendar-presentation@example.test', hashed_password='fixture')
    db.add(user)
    db.flush()
    db.add_all([
        GarminData(user_id=user.id, record_date=date(2031,4,1), data_source='garmin', sleep_score=99),
        GarminData(user_id=user.id, record_date=date(2031,4,2), data_source='garmin', sleep_score=67),
    ])
    db.flush()
    target = parse_query_window({'start_date': '2031-04-02', 'end_date': '2031-04-02'})
    result = read_calendar_health_query(db, user.id, 'sleep', target)
    block, evidence = compile_result(result)
    assert block['rows'] == [{'date': '2031-04-02', 'score': '67'}]
    assert '99' not in json.dumps(evidence)
    assert evidence['limitations'] and normalize_answer_evidence(evidence) == evidence
