"""Early and final card projection must match the authorized read window."""
import json

import pytest
from app.services.agent_executor import _genui_readout_fences


def call(dimension='sleep'):
    query = {'dimension': dimension, 'start_date': '2026-09-07',
             'end_date': '2026-09-13', 'timezone': 'Asia/Shanghai'}
    row = {'record_date': '2026-09-13', 'total_sleep_duration': 420, 'sleep_score': 80}
    if dimension == 'diet':
        row = {'record_date': '2026-09-13', 'food_items': 'Synthetic meal', 'calories': 200}
    payload = {'dimension': dimension, 'window': {k: v for k, v in query.items() if k != 'dimension'},
               'availability': 'partial', 'records': [row], 'limitations': []}
    return query, payload


def fences(calls):
    return _genui_readout_fences(calls, table_on=True, diet_summary_on=True,
                                sleep_summary_on=True, medication_list_on=False)


@pytest.mark.parametrize('failure', ['shifted_window', 'truncated', 'failed', 'wrong_dimension', 'missing_bounds'])
def test_calendar_card_rejects_self_consistent_but_unattested_result(failure):
    query, payload = call()
    if failure == 'shifted_window':
        payload['window'].update(start_date='2026-09-14', end_date='2026-09-14')
        payload['records'][0].update(record_date='2026-09-14', total_sleep_duration=123456)
    elif failure == 'truncated':
        payload['truncated'] = True
    elif failure == 'failed':
        payload['status'] = 'failed'
    elif failure == 'wrong_dimension':
        payload['dimension'] = 'diet'
    else:
        query = {'dimension': 'sleep', 'days': 7}
    assert fences([('health_query', query, json.dumps(payload))]) == []


def test_batch_keeps_verified_sibling_and_rejects_shifted_result():
    sleep, bad = call()
    diet, good = call('diet')
    bad['window'].update(start_date='2026-09-14', end_date='2026-09-14')
    bad['records'][0].update(record_date='2026-09-14', total_sleep_duration=123456)
    text = '\n'.join(fences([('health_query_batch', {'queries': [sleep, diet]},
                              json.dumps({'status': 'success', 'results': [bad, good]}))]))
    assert 'Synthetic meal' in text
    assert '123456' not in text and '2026-09-14' not in text


def test_bound_payload_cannot_smuggle_legacy_unbound_sleep_summary():
    query, payload = call()
    payload['daily_data'] = [{'date': '2026-09-14', 'total_sleep_duration': 123456}]
    text = '\n'.join(fences([('health_query', query, json.dumps(payload))]))
    assert 'metric_table' in text and '420' in text
    assert '123456' not in text and 'sleep_summary' not in text


@pytest.mark.parametrize('marker', ['truncated', 'has_more', 'next_cursor'])
def test_batch_truncation_never_relabels_partial_envelope_as_complete(marker):
    query, payload = call()
    assert fences([('health_query_batch', {'queries': [query]},
                   json.dumps({'status': 'success', 'results': [payload], marker: True}))]) == []


def test_bound_query_cannot_accept_legacy_daily_summary_without_window():
    query, _ = call('diet')
    payload = {'record_date': query['end_date'], 'total_calories': 123456,
               'meals': [{'food_items': 'Unverified meal', 'calories': 123456}]}
    assert fences([('health_query', query, json.dumps(payload))]) == []


@pytest.mark.parametrize('status', ['pending', 'processing', 'unknown', None, False, {}])
def test_nonterminal_batch_cannot_promote_children_to_completed_reads(status):
    query, payload = call()
    envelope = {'results': [payload]}
    if status is not None:
        envelope['status'] = status
    assert fences([('health_query_batch', {'queries': [query]}, json.dumps(envelope))]) == []
