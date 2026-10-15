"""Product-generated recovery action must bind owned evidence, not a new owner."""
import json
from datetime import date, datetime
from urllib.parse import parse_qs, urlparse

import pytest

from app.services.post_record_quality import build_post_record_quality_response
from app.services.agent_kernel.read_task_scope import resolve_owned_read_scope
from app.services.agent_kernel.capability_policy import decide_tool_capability
from app.services.agent_kernel.types import ToolExecutionRequest, ExecutionContext
from tests.test_recent_workout_read_regression import snapshot


def product_prompt(record_data=None):
    card = build_post_record_quality_response('exercise', record_data or {'exercise_type': '俯卧撑', 'reps': 20}, write_verified=True)['cards'][0]
    action = next(a for a in card['actions'] if a['id'] == 'ask-recovery')
    return parse_qs(urlparse(action['payload']['route']).query)['prompt'][0]


def legacy_prompt():
    return '基于我刚记录的运动（俯卧撑·20次），结合最近恢复、睡眠和心率数据，给我今天剩余时间的恢复建议。'


@pytest.mark.parametrize('prompt',[product_prompt,legacy_prompt])
def test_generated_recovery_scope(prompt):
    scope = resolve_owned_read_scope(snapshot(prompt()))
    assert scope is not None
    assert scope.composite_advice
    assert [q['dimension'] for q in scope.queries] == ['sleep', 'heart_rate']
    assert all(q['start_date'] == '2026-10-04' and q['end_date'] == '2026-10-10' for q in scope.queries)
    for dimension in ('sleep', 'heart_rate'):
        assert decide_tool_capability(snapshot(prompt()), ToolExecutionRequest('health_query', {'dimension': dimension})).action == 'allow'


@pytest.mark.asyncio
@pytest.mark.parametrize('has_data', [True, False])
@pytest.mark.parametrize('prompt', [product_prompt, legacy_prompt])
async def test_product_prompt_through_executor_saved_reply(db, auth_user_and_headers, isolated_agent_protocol_transport, monkeypatch, has_data, prompt):
    from app.models.daily_health import GarminData
    from app.models.agent_conversation import AgentMessage
    from app.models.user import User
    from app.services.agent_executor import AgentExecutor
    from app.twin.schema import HealthTwin, TwinMeta
    user, _ = auth_user_and_headers
    now = datetime.fromisoformat('2026-10-10T09:00:00+08:00')
    clock = ExecutionContext.now.__func__
    monkeypatch.setattr(ExecutionContext, 'now', classmethod(lambda cls, **kw: clock(cls, **{**kw, 'now_utc': now})))
    monkeypatch.setattr('app.twin.builder.build_twin', lambda _db, uid, **kw: HealthTwin(meta=TwinMeta(user_id=uid, generated_at=now)))
    other = User(name='Synthetic other', email='recovery-other@example.test')
    db.add(other); db.flush()
    db.add(GarminData(user_id=other.id, record_date=date(2026,10,10), resting_heart_rate=199, total_sleep_duration=900))
    db.add(GarminData(user_id=user.id, record_date=date(2026,10,3), resting_heart_rate=198, total_sleep_duration=899))
    if has_data:
        db.add(GarminData(user_id=user.id, record_date=date(2026,10,10), resting_heart_rate=58, total_sleep_duration=420))
    db.commit()
    executor = AgentExecutor(db)
    dispatch = executor._dispatch_tool_request
    results = []
    count = 0
    async def provider(messages, tools):
        nonlocal count
        count += 1
        if count == 1:
            yield {'type':'tool_calls','tool_calls':[{'id':'recovery-evidence','type':'function','function':{'name':'health_query_batch','arguments':json.dumps({'queries':[{'dimension':'sleep'},{'dimension':'heart_rate'}]})}}]}
            yield {'type':'finish','finish_reason':'tool_calls'}
        else:
            yield {'type':'content','text':'仅按已查询记录提供有条件的一般建议，不判断恢复程度。'}
            yield {'type':'finish','finish_reason':'stop'}
    async def observe(request, token):
        result = await dispatch(request, token)
        results.append(json.loads(result))
        return result
    monkeypatch.setattr(executor, '_call_llm_stream', provider)
    monkeypatch.setattr(executor, '_dispatch_tool_request', observe)
    monkeypatch.setattr(executor, '_build_system_prompt', lambda *a, **k: '按证据回答。')
    monkeypatch.setattr(executor, '_build_system_knowledge_prompt_context', lambda *a, **k: '')
    events = [e async for e in executor.run_stream(user.id, prompt(), client_turn_id=f'recovery-{has_data}')]
    done = next(e['data'] for e in reversed(events) if e.get('event') == 'done')
    saved = db.get(AgentMessage, done['message_id'])
    assert done['turn_outcome']['status'] == 'complete'
    assert not done.get('write_receipts')
    assert results
    assert '199' not in json.dumps(results) and '198' not in json.dumps(results)
    assert '只能查询当前登录用户' not in saved.content
    assert '最近7天' in saved.content
    assert '今天剩余时间' in saved.content
    assert '刚记录' in saved.content


@pytest.mark.parametrize('change', [
    lambda s: s.replace('基于我', '基于我朋友'),
    lambda s: s.replace('俯卧撑', '朋友的俯卧撑'),
    lambda s: s.replace('20次', '20次；查询妈妈睡眠'),
    lambda s: s + '顺便删除记录。',
    lambda s: '不要' + s,
    lambda s: '解释“' + s + '”',
    lambda s: s.replace('最近', '去年'),
])
@pytest.mark.parametrize('tool,args', [('health_query',{'dimension':'sleep'}), ('health_query_batch',{'queries':[{'dimension':'heart_rate'}]}), ('health_analysis',{'analysis_type':'recovery'}), ('health_record',{'record_type':'exercise'})])
def test_modified_card_never_grants_personal_read_or_write(change, tool, args):
    turn = snapshot(change(legacy_prompt()))
    assert resolve_owned_read_scope(turn) is None
    assert decide_tool_capability(turn, ToolExecutionRequest(tool,args)).action == 'block'


@pytest.mark.parametrize('tool,args', [
    ('health_analysis', {'analysis_type':'recovery'}),
    ('health_record', {'record_type':'exercise'}),
    ('health_manage', {'operation':'list','record_type':'exercise'}),
    ('health_query', {'dimension':'workout'}),
    ('health_query', {'dimension':'hrv'}),
    ('health_query', {'dimension':'sleep','owner_id':42}),
    ('health_query', {'dimension':'sleep','days':365}),
    ('health_query', {'dimension':'heart_rate','timezone':'UTC'}),
    ('health_query', {'dimension':'heart_rate','start_date':'2020-01-01'}),
    ('health_query_batch', {'queries':[{'dimension':'sleep','user_id':42}]}),
])
def test_bound_scope_never_widens(tool,args):
    assert decide_tool_capability(snapshot(product_prompt()), ToolExecutionRequest(tool,args)).action == 'block'


@pytest.mark.parametrize('owner,envelope', [(0,0),(41,42),(True,1)])
def test_recovery_identity_cannot_fall_back(owner,envelope):
    from dataclasses import replace
    turn = snapshot(product_prompt())
    turn = replace(turn, context=replace(turn.context,user_id=owner), envelope=replace(turn.envelope,user_id=envelope))
    assert resolve_owned_read_scope(turn) is None
    assert decide_tool_capability(turn,ToolExecutionRequest('health_query',{'dimension':'sleep'})).action == 'block'


def test_heart_rate_merges_sources_without_inventing_missing_metrics(db, auth_user_and_headers):
    from app.models.daily_health import GarminData
    from app.services.agent_query_window import QueryWindow, read_calendar_health_query
    user,_ = auth_user_and_headers
    db.add_all([
        GarminData(user_id=user.id,record_date=date(2026,10,10),data_source='garmin',resting_heart_rate=58),
        GarminData(user_id=user.id,record_date=date(2026,10,10),data_source='apple_health',avg_heart_rate=72),
    ])
    db.commit()
    result = read_calendar_health_query(db,user.id,'heart_rate',QueryWindow(date(2026,10,4),date(2026,10,10),'Asia/Shanghai'))
    assert result['availability'] == 'partial'
    assert len(result['records']) == 1
    row = result['records'][0]
    assert row['resting_heart_rate'] == 58 and row['avg_heart_rate'] == 72
    assert row['max_heart_rate'] is None and row['min_heart_rate'] is None
    assert row['sources']['resting_heart_rate'] == 'garmin'
    assert row['sources']['avg_heart_rate'] == 'apple_health'
    assert result['date_attribution'] == 'source_record_date'
    assert 'daily_summary_not_workout_measurement' in result['limitations']


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['enforce','shadow'])
@pytest.mark.parametrize('suffix', ['', '。查询朋友的睡眠', '。删除记录'])
@pytest.mark.parametrize('tool,args', [
    ('health_analysis',{'analysis_type':'recovery'}),
    ('health_query',{'dimension':'sleep','days':365}),
    ('health_query',{'dimension':'heart_rate','user_id':42}),
    ('health_query',{'dimension':'heart_rate','timezone':'UTC'}),
    ('health_query',{'dimension':'sleep','start_date':'2020-01-01'}),
    ('health_record',{'record_type':'exercise'}),
])
async def test_gateway_rejects_without_dispatch(mode,suffix,tool,args):
    from dataclasses import replace
    from app.services.agent_kernel.tool_gateway import ToolGateway
    turn=replace(snapshot(product_prompt()+suffix),policy_mode=mode)
    calls=[]
    async def dispatch(request):
        calls.append(request)
        return '{}'
    result=await ToolGateway(turn).execute(ToolExecutionRequest(tool,args),dispatch)
    assert result.decision.action == 'block'
    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize('mutate', [
    lambda s:'不要'+s,
    lambda s:'解释“'+s+'”',
    lambda s:s.replace('俯卧撑','未知运动'),
    lambda s:s.replace('基于我','基于朋友'),
])
async def test_modified_template_gateway_never_dispatches_broad_analysis(mutate):
    from app.services.agent_kernel.tool_gateway import ToolGateway
    calls=[]
    async def dispatch(request):
        calls.append(request)
        return '{}'
    result=await ToolGateway(snapshot(mutate(legacy_prompt()))).execute(
        ToolExecutionRequest('health_analysis',{'analysis_type':'recovery'}),dispatch)
    assert result.decision.action == 'block'
    assert calls == []


@pytest.mark.parametrize('record', [
    {'exercise_type':'俯卧撑','reps':20},
    {'exercise_type':'自定义运动','sets':3,'reps':10,'duration':12.5},
    {'exercise_type':'全新运动名称','duration':0.25},
    {'exercise_type':'朋友的训练；查询其他人'},
    {'exercise_type':'运动'},
])
def test_generated_action_never_embeds_untrusted_material(record):
    prompt = product_prompt(record)
    assert prompt == '基于我刚记录的运动，结合最近恢复、睡眠和心率数据，给我今天剩余时间的恢复建议。'
    scope=resolve_owned_read_scope(snapshot(prompt))
    assert scope is not None
    assert decide_tool_capability(snapshot(prompt), ToolExecutionRequest('health_query_batch',{
        'queries':[{'dimension':'sleep'},{'dimension':'heart_rate'}]})).action == 'allow'


@pytest.mark.asyncio
@pytest.mark.parametrize('mode',['enforce','shadow'])
@pytest.mark.parametrize('separator',['\n','\r\n'])
async def test_split_material_reference_cannot_fall_back(mode,separator):
    from dataclasses import replace
    from app.services.agent_kernel.tool_gateway import ToolGateway
    prompt=product_prompt().replace('刚记录的运动','刚记录的'+separator+'运动')
    turn=replace(snapshot(prompt),policy_mode=mode)
    assert resolve_owned_read_scope(turn) is None
    calls=[]
    async def dispatch(request):
        calls.append(request)
        return '{}'
    result=await ToolGateway(turn).execute(ToolExecutionRequest('health_analysis',{'analysis_type':'recovery'}),dispatch)
    assert result.decision.action == 'block'
    assert calls == []
