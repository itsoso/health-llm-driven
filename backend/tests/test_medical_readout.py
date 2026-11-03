"""Stored medical facts can be shown before synthesis without parsing clinical prose."""
import json
from copy import deepcopy
from datetime import date, timedelta

import pytest

from app.models.family_health import MedicalIndicator
from app.services.agent_executor import AgentExecutor
from app.services.answer_evidence import build_answer_evidence
from app.services.genui.table_builder import build_table_from_tool_call


@pytest.mark.asyncio
async def test_owned_query_preserves_summary_and_exposes_dated_numeric_facts(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    today = date.today()
    from app.models.user import User
    other = User(username='medical_readout_other', email='medical_readout_other@example.invalid', name='Synthetic other', hashed_password='synthetic')
    db.add(other)
    db.flush()
    db.add_all([
        MedicalIndicator(user_id=user.id, name='Synthetic LDL', value=3.4567, unit='mmol/L', record_date=today-timedelta(days=200), reference_high=3.4),
        MedicalIndicator(user_id=user.id, name='Narrative', value_text='Do not infer medical conclusions', record_date=today),
        MedicalIndicator(user_id=user.id, name='Future', value=999, unit='x', record_date=today+timedelta(days=1)),
        MedicalIndicator(user_id=other.id, name='Foreign', value=777, unit='x', record_date=today),
    ])
    db.commit()
    ex = AgentExecutor(db)
    ex._current_user_id = user.id
    args = {'dimension': 'medical_exam', 'days': 7}
    result = await ex._exec_health_query('', {}, args)
    payload = json.loads(result)
    assert 'Do not infer medical conclusions' in payload['summary']
    assert 'Synthetic LDL' in payload['summary']
    assert payload['readout']['since'] == (today-timedelta(days=365)).isoformat()
    assert [r['name'] for r in payload['readout']['items']] == ['Synthetic LDL']
    assert payload['readout']['items'][0]['value'] == 3.4567
    block = build_table_from_tool_call('health_query', args, result)
    assert block and '3.46 mmol/L' == block['rows'][0]['value']
    assert '较旧' in block['rows'][0]['note']
    assert (today-timedelta(days=200)).isoformat() in block['rows'][0]['note']
    assert '未核验原始报告' in block['rows'][0]['note']
    assert '365' in block['footnote'] and '全部' not in block['title']
    evidence = build_answer_evidence(tool_calls=[('health_query', args, result)])
    assert evidence and '未核验原始报告' in evidence['basis'][0]['context']
    assert '777' not in json.dumps(evidence) and '999' not in json.dumps(evidence)


def payload():
    return {
        'schema': 'medical-readout.v1', 'status': 'success', 'summary': 'Clinical text is not a card input',
        'readout': {
            'query': {'days': 7, 'indicator': '', 'keyword': ''},
            'since': '2025-11-04', 'reference_date': '2026-11-04', 'window_days': 365,
            'items': [{'name': 'Synthetic LDL', 'value': 3.4567, 'unit': 'mmol/L', 'record_date': '2026-10-01', 'reference_low': None, 'reference_high': 3.4}],
        },
    }


def test_medical_card_uses_only_structured_facts_and_binds_query():
    p = payload()
    b = build_table_from_tool_call('health_query', {'dimension': 'medical_exam'}, json.dumps(p))
    assert b and b['rows'][0]['metric'] == 'Synthetic LDL'
    assert 'Clinical text' not in json.dumps(b)
    for args in ({'dimension':'medical_exam','indicator':'OTHER'}, {'dimension':'medical_exam','days':30}, {'dimension':'medical_exam','uploaded_days':1}, {'dimension':'medical_exam','start_date':'2026-11-01'}, {'dimension':'medical_exam','exam_id':99}):
        assert build_table_from_tool_call('health_query', args, json.dumps(p)) is None


@pytest.mark.parametrize('mutation', ['future','old','nested','bool','nan','inf','bad_date','bad_unit','bad_name','failed','version','wrong_window'])
def test_unverifiable_medical_projection_has_no_card_or_basis(mutation):
    p = deepcopy(payload())
    row = p['readout']['items'][0]
    if mutation == 'future': row['record_date'] = '2026-11-05'
    elif mutation == 'old': row['record_date'] = '2025-11-03'
    elif mutation == 'nested': row['value'] = {'value': 123}
    elif mutation == 'bool': row['value'] = True
    elif mutation == 'nan': row['value'] = float('nan')
    elif mutation == 'inf': row['value'] = float('inf')
    elif mutation == 'bad_date': row['record_date'] = 'today'
    elif mutation == 'bad_unit': row['unit'] = {'unit':'mg'}
    elif mutation == 'bad_name': row['name'] = ['nested']
    elif mutation == 'failed': p['status'] = 'failed'
    elif mutation == 'version': p['schema'] = 'unknown'
    else: p['readout']['since'] = '2026-11-01'
    result = json.dumps(p)
    assert build_table_from_tool_call('health_query', {'dimension':'medical_exam'}, result) is None
    evidence = build_answer_evidence(tool_calls=[('health_query', {'dimension':'medical_exam'}, result)])
    assert not evidence or not evidence['basis']


def test_medical_text_and_unselected_report_cannot_be_scraped_into_card():
    for result in ['Synthetic LDL: 3.4 mmol/L (2026-11-04)', json.dumps({'items':[{'name':'LDL','value':3.4}]})]:
        assert build_table_from_tool_call('health_query', {'dimension':'medical_exam'}, result) is None


@pytest.mark.asyncio
async def test_medical_facts_stream_before_next_model_and_survive_reload(db, auth_user_and_headers, monkeypatch):
    from app.models.agent_conversation import AgentMessage
    from app.services import agent_executor as ae
    from tests.test_agent_executor_completion_status import _stream_from

    user, _ = auth_user_and_headers
    db.add(MedicalIndicator(user_id=user.id, name='Synthetic LDL', value=3.4567, unit='mmol/L', record_date=date.today()-timedelta(days=10)))
    db.commit()
    ex = AgentExecutor(db)
    events, calls = [], []
    async def model(messages, tools):
        calls.append(messages)
        if len(calls) == 1:
            return {'content':'', 'finish_reason':'tool_calls', 'tool_calls':[{'id':'medical-read','type':'function','function':{'name':'health_query','arguments':json.dumps({'dimension':'medical_exam'})}}]}
        assert any(e.get('event') == 'answer_evidence' for e in events)
        assert any(e.get('event') == 'token' and 'metric_table' in str(e) for e in events)
        assert 'Synthetic LDL' in str(messages)
        assert 'medical-readout.v1' not in str(messages)
        return {'content':'已列出已存化验数据，记录日期见表格。原始报告尚未核验，参考数值不代表诊断。', 'finish_reason':'stop'}
    monkeypatch.setattr(ex, '_call_llm', model)
    monkeypatch.setattr(ex, '_call_llm_stream', _stream_from(model))
    monkeypatch.setattr(ae.settings, 'genui_table_enabled', True)
    monkeypatch.setattr(ae.settings, 'health_evidence_runtime_enabled', False)
    async for event in ex.run_stream(user_id=user.id, message='请查看我的体检报告，列出已存化验数据、日期和单位。', channel='typed', client_caps=['genui-table-v1']):
        events.append(event)
    done = next(e['data'] for e in events if e.get('event') == 'done')
    assert done['turn_outcome']['status'] == 'complete'
    assert len(calls) == 2
    early = next(e['data']['answer_evidence'] for e in events if e.get('event') == 'answer_evidence')
    saved = db.get(AgentMessage, done['message_id'])
    assert early == done['answer_evidence'] == saved.meta['answer_evidence']
    assert 'metric_table' in saved.content and '3.46 mmol/L' in saved.content
    assert '未核验原始报告' in saved.content


@pytest.mark.parametrize('field,value', [('success',False),('ok',False),('error','read_failed'),('truncated',True),('has_more',True),('next_cursor','cursor')])
def test_failure_or_incomplete_envelope_never_becomes_facts(field,value):
    p = payload()
    p[field] = value
    assert build_table_from_tool_call('health_query', {'dimension':'medical_exam'}, json.dumps(p)) is None


def test_display_row_limit_and_full_precision():
    p = payload()
    p['readout']['items'] = [dict(p['readout']['items'][0], name=f'Synthetic {i}', value=1.23456+i) for i in range(14)]
    b = build_table_from_tool_call('health_query', {'dimension':'medical_exam'}, json.dumps(p))
    assert len(b['rows']) == 12 and '12/14' in b['footnote']
    assert b['rows'][0]['value'] == '1.23 mmol/L'
    assert p['readout']['items'][0]['value'] == 1.23456


@pytest.mark.asyncio
async def test_default_reader_text_unchanged_and_missing_data_no_numeric_projection(db, auth_user_and_headers):
    from app.services.health_read import canonical_read
    user, _ = auth_user_and_headers
    db.add(MedicalIndicator(user_id=user.id, name='Synthetic', value=2.71828, unit='unit', record_date=date.today()))
    db.commit()
    old = canonical_read(db,user.id,'medical_exam')
    new = canonical_read(db,user.id,'medical_exam',medical_readout=True)
    assert json.loads(new)['summary'] == old
    empty = canonical_read(db,user.id,'medical_exam',indicator='NoSuchIndicator',medical_readout=True)
    assert '未找到' in empty
    assert build_table_from_tool_call('health_query',{'dimension':'medical_exam','indicator':'NoSuchIndicator'},empty) is None


def test_model_receives_original_summary_without_duplicate_readout_tokens():
    from app.services.agent_executor import _model_tool_result_content
    p = payload()
    args = {'dimension':'medical_exam'}
    raw = json.dumps(p)
    assert _model_tool_result_content('health_query', args, raw) == p['summary']
    assert _model_tool_result_content('other_tool', args, raw) == raw
    assert _model_tool_result_content('health_query', dict(args,indicator='OTHER'), raw) == raw
    p['status'] = 'failed'
    raw = json.dumps(p)
    assert _model_tool_result_content('health_query', args, raw) == raw
