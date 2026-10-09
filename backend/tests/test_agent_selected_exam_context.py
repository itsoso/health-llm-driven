"""Selected report is a selector, never client-supplied medical evidence."""
import json
from datetime import date, timedelta

import pytest

from app.models.medical_exam import MedicalExam, MedicalExamItem
from app.services.agent_executor import AgentExecutor


def _exam(db, user_id, marker, day=None):
    row = MedicalExam(user_id=user_id, exam_date=day or date.today(), overall_assessment=marker)
    row.items = [MedicalExamItem(item_name=marker, value=1.25, unit='unit', reference_range='1-2')]
    db.add(row)
    db.commit()
    return row


@pytest.mark.asyncio
async def test_selected_exam_read_does_not_fall_back_to_latest(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    selected = _exam(db, user.id, 'SELECTED_REPORT', date.today()-timedelta(days=3))
    _exam(db, user.id, 'OTHER_REPORT')
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    executor._turn_selected_exam_id = selected.id
    result = await executor._exec_health_query('', {}, {'dimension': 'medical_exam'})
    assert 'SELECTED_REPORT' in result
    assert 'OTHER_REPORT' not in result


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['missing', 'future', 'foreign'])
async def test_selected_exam_unavailable_never_falls_back(db, auth_user_and_headers, kind):
    user, _ = auth_user_and_headers
    _exam(db, user.id, 'OWN_REPORT')
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    if kind == 'missing':
        selected_id = 999999
    elif kind == 'future':
        selected_id = _exam(db, user.id, 'FUTURE_REPORT', date.today()+timedelta(days=1)).id
    else:
        from app.models.user import User
        other = User(name='Synthetic user', username='selected_exam_other', email='selected_exam_other@example.test', hashed_password='synthetic')
        db.add(other)
        db.commit()
        selected_id = _exam(db, other.id, 'FOREIGN_REPORT').id
    executor._turn_selected_exam_id = selected_id
    result = await executor._exec_health_query('', {}, {'dimension': 'medical_exam'})
    assert result.startswith('Error:')
    assert all(marker not in result for marker in ['OWN_REPORT', 'FOREIGN_REPORT', 'FUTURE_REPORT'])


@pytest.mark.parametrize('raw, expected', [
    ({'from': 'medical-exam/12', 'overall_assessment': 'CLIENT_UNTRUSTED'}, 12),
    ({'from': 'medical-exam/not-an-id'}, 0),
    ({'from': 'medical-exam/-2'}, 0),
    ({'from': 'other-page/12'}, None),
    ({'from': 'exam-explain/12', 'summary': 'CLIENT_UNTRUSTED'}, 12),
    ({'from': 'exam-explain/-2'}, 0),
])
def test_selected_exam_context_parser(raw, expected):
    from app.services.agent_executor import _selected_exam_context_id
    assert _selected_exam_context_id(json.dumps(raw)) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("with_history", [False, True])
@pytest.mark.parametrize("prompt, context_prefix", [
    ('请基于我最新这份体检/化验报告，解释异常项、风险优先级和未来 30 天该做什么。', 'medical-exam'),
    ('请基于我这份体检/化验报告，解释异常项、风险优先级和未来30天该做什么。', 'medical-exam'),
    ('请基于这次体检异常解读，帮我按优先级梳理风险、行动、复查安排和需要向医生确认的问题。不要替代诊断或用药建议。', 'medical-exam'),
    ('请基于这次体检异常解读，帮我按优先级梳理风险、行动、复查安排和需要向医生确认的问题。不要替代诊断或用药建议。', 'exam-explain'),
])
async def test_selected_exam_stream_discards_client_payload_and_other_reports(db, auth_user_and_headers, monkeypatch, with_history, prompt, context_prefix):
    from app.models.agent_conversation import AgentMessage
    from app.services import agent_executor as ae
    user, _ = auth_user_and_headers
    selected = _exam(db, user.id, 'SELECTED_REPORT')
    _exam(db, user.id, 'UNRELATED_SERVER_REPORT')
    conversation_id = None
    old_message_ids = []
    if with_history:
        from app.models.agent_conversation import AgentConversation
        conversation = AgentConversation(user_id=user.id, title='Synthetic history')
        db.add(conversation)
        db.flush()
        old_messages = [
            AgentMessage(conversation_id=conversation.id, role='user', content='解释 UNRELATED_HISTORY_REPORT'),
            AgentMessage(conversation_id=conversation.id, role='assistant', content='UNRELATED_HISTORY_REPORT 与 CLIENT_OLD_SUMMARY', meta={
                'cards':[{'type':'metric_table','data':{'title':'UNRELATED_HISTORY_REPORT'}}],
                'answer_evidence':{'version':'answer-evidence.v1','basis':[{'observation':'UNRELATED_HISTORY_REPORT'}]},
            }),
        ]
        db.add_all(old_messages)
        db.commit()
        conversation_id = conversation.id
        old_message_ids = [item.id for item in old_messages]
    executor = AgentExecutor(db)
    from app.twin import builder as twin_builder
    def reject_unscoped_twin(*args, **kwargs):
        pytest.fail('selected report must not read the whole personal Twin')
    monkeypatch.setattr(twin_builder, 'build_twin', reject_unscoped_twin)
    from app.services.agent_conversation_service import AgentConversationService
    monkeypatch.setattr(AgentConversationService, 'build_actionable_references', reject_unscoped_twin)
    monkeypatch.setattr(executor, '_bind_read_task_reference', reject_unscoped_twin)
    from app.services import agent_read_task_continuation, diet_photo_correction, water_backfill, procedure_recipe_service
    monkeypatch.setattr(agent_read_task_continuation, 'load_read_task_reference', reject_unscoped_twin)
    monkeypatch.setattr(diet_photo_correction, 'build_correction_proposal', reject_unscoped_twin)
    monkeypatch.setattr(water_backfill, 'resolve_water_backfill_turn', reject_unscoped_twin)
    monkeypatch.setattr(procedure_recipe_service, 'match_trigger', reject_unscoped_twin)
    monkeypatch.setattr(executor, '_resolve_medication_batch_turn', reject_unscoped_twin)
    seen = []
    calls = 0
    async def completion(messages, tools):
        nonlocal calls
        seen.extend(messages)
        calls += 1
        if calls == 1:
            names = {tool['function']['name'] for tool in tools}
            assert names <= {'health_query', 'knowledge_search'}
            report_tool = next(tool['function'] for tool in tools if tool['function']['name'] == 'health_query')
            assert report_tool['parameters']['properties']['dimension']['enum'] == ['medical_exam']
            assert set(report_tool['parameters']['properties']) == {'dimension'}
        if calls == 1:
            return {'content': '', 'tool_calls': [{'id':'selected-report', 'type':'function', 'function': {'name':'health_query','arguments':json.dumps({'dimension':'medical_exam'})}}], 'finish_reason':'tool_calls'}
        return {'content': '已核对所选报告，参考范围不能单独用于诊断。', 'finish_reason':'stop'}
    async def stream(messages, tools):
        result = await completion(messages, tools)
        if result.get('tool_calls'):
            yield {'type':'tool_calls','tool_calls':result['tool_calls']}
        else:
            yield {'type':'content','text':result['content']}
        yield {'type':'finish','finish_reason':result['finish_reason']}
    monkeypatch.setattr(executor, '_call_llm', completion)
    monkeypatch.setattr(executor, '_call_llm_stream', stream)
    monkeypatch.setattr(ae.settings, 'health_evidence_runtime_enabled', True)
    events = [event async for event in executor.run_stream(
        user_id=user.id, channel='typed', conversation_id=conversation_id,
        message=prompt,
        extra_context=json.dumps({'from':f'{context_prefix}/{selected.id}', 'overall_assessment':'CLIENT_UNTRUSTED', 'multi_model':True}),
    )]
    done = next(e['data'] for e in events if e.get('event') == 'done')
    saved = db.get(AgentMessage, done['message_id'])
    serialized = json.dumps([seen, events, saved.meta, saved.content], ensure_ascii=False, default=str)
    assert 'CLIENT_UNTRUSTED' not in serialized
    assert 'UNRELATED_SERVER_REPORT' not in serialized
    assert 'UNRELATED_HISTORY_REPORT' not in serialized
    assert 'CLIENT_OLD_SUMMARY' not in serialized
    for old_id in old_message_ids:
        assert db.get(AgentMessage, old_id) is not None
    assert executor._current_turn_recent_messages == []
    assert executor._provider_history_references == ()
    assert 'SELECTED_REPORT' in json.dumps(seen, ensure_ascii=False)
    assert done['turn_outcome']['status'] == 'complete'
    assert 'health_query_not_requested' not in serialized


@pytest.mark.asyncio
async def test_selected_report_alternate_lab_tool_has_same_owner_scope(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    selected = _exam(db, user.id, 'SELECTED_REPORT')
    _exam(db, user.id, 'OTHER_REPORT')
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    executor._turn_selected_exam_id = selected.id
    result = await executor._exec_query_lab_indicators('', {}, {'name':'OTHER_REPORT', 'since':'2000-01-01'})
    assert 'SELECTED_REPORT' in result
    assert 'OTHER_REPORT' not in result


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome_status', ['failed', 'partial', 'complete'])
async def test_terminal_card_delivery_uses_actual_outcome(db, auth_user_and_headers, monkeypatch, outcome_status):
    from app.models.agent_conversation import AgentMessage
    from app.services import agent_executor as ae
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    monkeypatch.setattr(executor, '_build_system_prompt', lambda *a, **k:'SYS')
    monkeypatch.setattr(executor, '_build_system_knowledge_prompt_context', lambda *a, **k:'')
    monkeypatch.setattr(executor, '_build_system_knowledge_evidence_card', lambda *a, **k:None)
    async def completion(messages, tools):
        executor._turn_contextual_diet_cards = [{'type':'diet_draft', 'data':{'recorded':False, 'food_names':['SYNTHETIC']}, 'actions':[]}]
        return {'content':'这一轮的处理已结束。', 'finish_reason':'stop'}
    async def stream(messages, tools):
        result = await completion(messages, tools)
        yield {'type':'content', 'text':result['content']}
        yield {'type':'finish', 'finish_reason':'stop'}
    monkeypatch.setattr(executor, '_call_llm', completion)
    monkeypatch.setattr(executor, '_call_llm_stream', stream)
    original = ae.classify_agent_turn_outcome
    def classify(**kwargs):
        result = original(**kwargs)
        return {**result, 'status':outcome_status, 'category':'tool_blocked' if outcome_status=='failed' else 'success'}
    monkeypatch.setattr(ae, 'classify_agent_turn_outcome', classify)
    events = [e async for e in executor.run_stream(user_id=user.id,message='你好，聊聊今天',channel='typed')]
    done = next(e['data'] for e in events if e.get('event') == 'done')
    saved = db.get(AgentMessage, done['message_id'])
    if outcome_status == 'failed':
        assert done['cards'] == []
        assert saved.meta['cards'] == []
        assert not done.get('answer_evidence')
        assert not saved.meta.get('answer_evidence')
    else:
        assert done['cards']
        assert saved.meta['cards']


@pytest.mark.asyncio
@pytest.mark.parametrize('tool,args', [
    ('realtime_search', {'query':'synthetic latest guideline'}),
    ('health_analysis', {'analysis_type':'orchestrator', 'question':'analyze'}),
    ('health_manage', {'record_type':'diet','operation':'list'}),
    ('health_query', {'dimension':'genetic'}),
    ('health_query_batch', {'queries':[{'dimension':'medical_exam'},{'dimension':'sleep'}]}),
    ('query_genetic_profile', {}),
    ('supplement_guide', {}),
    ('intervention_cycle', {'operation':'list'}),
])
async def test_selected_report_blocks_alternate_personal_read_before_dispatch(db, auth_user_and_headers, monkeypatch, tool, args):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    executor._current_turn_user_message = '请基于我最新这份体检/化验报告，解释异常项、风险优先级和未来 30 天该做什么。'
    executor._turn_selected_exam_id = 1
    async def forbidden(*a, **k):
        pytest.fail('selected report scope must block before personal tool dispatch')
    monkeypatch.setattr(executor, '_execute_tool_impl', forbidden)
    result = await executor._execute_tool(tool, args, None)
    assert json.loads(result)['error_code'] == 'selected_report_scope_required'


@pytest.mark.asyncio
@pytest.mark.parametrize('query, emergency', [
    ('请结合这份体检报告，解释我最近腰痛该怎么办。', False),
    ('我腰痛伴排尿困难和会阴麻木，请结合这份报告告诉我怎么办。', True),
])
async def test_selected_report_mixed_clinical_turn_keeps_safety_without_unscoped_reads(db, auth_user_and_headers, monkeypatch, query, emergency):
    from app.services import agent_executor as ae
    from app.twin import builder as twin_builder
    user, _ = auth_user_and_headers
    selected = _exam(db, user.id, 'SELECTED_REPORT')
    executor = AgentExecutor(db)
    def reject_unscoped(*a, **k):
        pytest.fail('selected report may not load all personal health records')
    monkeypatch.setattr(twin_builder, 'build_twin', reject_unscoped)
    monkeypatch.setattr(ae.settings, 'health_evidence_runtime_enabled', True)
    async def completion(messages, tools):
        return {'content':'目前证据不足，不能进行个性化判断。', 'finish_reason':'stop'}
    async def stream(messages, tools):
        yield {'type':'content','text':'目前证据不足，不能进行个性化判断。'}
        yield {'type':'finish','finish_reason':'stop'}
    monkeypatch.setattr(executor, '_call_llm', completion)
    monkeypatch.setattr(executor, '_call_llm_stream', stream)
    events = [e async for e in executor.run_stream(user_id=user.id,message=query,channel='typed',extra_context=json.dumps({'from':f'medical-exam/{selected.id}'}))]
    done = next(e['data'] for e in events if e.get('event') == 'done')
    text = ''.join(e['data'].get('content','') for e in events if e.get('event')=='token')
    assert '未执行所选报告与症状的联合解读' in text
    assert done['turn_outcome']['status'] != 'complete'
    assert done.get('cards') == []
    from app.models.agent_conversation import AgentMessage
    assert db.get(AgentMessage, done['message_id']).meta.get('cards') == []
    if emergency:
        assert '急诊' in text


@pytest.mark.parametrize('status', ['failed', 'blocked', 'reconciliation_required'])
def test_citations_never_readded_to_unsuccessful_terminal(db, auth_user_and_headers, monkeypatch, status):
    from app.services import medical_citation_policy
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    def forbidden(*a, **k):
        pytest.fail('failed terminal must not compile new medical citations')
    monkeypatch.setattr(medical_citation_policy, 'build_medical_citation_bundle', forbidden)
    event = {'event':'done','data':{'completion_status':'complete','turn_outcome':{'status':status}}}
    assert executor._attach_medical_citations_to_terminal_event(event,user_id=user.id,user_message='解释体检报告') == event
