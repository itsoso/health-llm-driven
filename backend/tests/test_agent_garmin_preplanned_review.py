"""Canonical compound Garmin proposals cross real Pi and capability gateway."""
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.models.daily_health import WorkoutRecord
from app.models.user import GarminCredential
from app.services.agent_executor import AgentExecutor

PROMPT = '同步一下佳明的数据，获取到我最新的运动的数据，我跑了3公里，分析一下刚才跑的情况怎么样，给我一些建议。'


@pytest.mark.asyncio
@pytest.mark.parametrize('job_state', ['PENDING', 'SUCCESS', 'FAILURE', 'INVALID_STATE', 'missing_credentials', 'enqueue_error'])
@pytest.mark.parametrize('guessed_args', [
    {'record_type': 'garmin_sync'},
    {'record_type': 'garmin_sync', 'data': {'days': 7}},
])
async def test_canonical_sync_then_today_read_precedes_model_guess(db, auth_user_and_headers, monkeypatch, guessed_args, job_state, _model_reply=None, _capture=None):
    from app.services import agent_executor as ae
    from app.services import agent_garmin_sync_status as status
    from app.tasks.garmin_sync import sync_user_garmin_data
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    from app.services.agent_kernel.types import ExecutionContext
    # A real clock near midnight makes now-30m a previous-day activity.
    # Freeze the turn and fixture together; this test requires a completed run today.
    fixed_utc = datetime(2026, 10, 9, 4, tzinfo=timezone.utc)
    original_clock = ExecutionContext.now.__func__
    monkeypatch.setattr(ExecutionContext, 'now', classmethod(
        lambda cls, **kwargs: original_clock(cls, **{**kwargs, 'now_utc': fixed_utc})
    ))
    now = ExecutionContext.now(user_id=user.id, channel='typed').current_time
    if job_state != 'missing_credentials':
        db.add(GarminCredential(user_id=user.id, garmin_email='synthetic@example.invalid',
            encrypted_password='unused', sync_enabled=True, credentials_valid=True))
    row = WorkoutRecord(user_id=user.id, workout_date=now.date(), workout_type='running',
        source='garmin', distance_meters=3000, duration_seconds=1500, avg_heart_rate=127, max_heart_rate=143,
        start_time=(now-timedelta(minutes=30)).astimezone(timezone.utc),
        end_time=(now-timedelta(minutes=5)).astimezone(timezone.utc))
    db.add(row);db.commit()
    job_id = str(uuid4())
    enqueue = Mock(return_value=Mock(id=job_id), side_effect=RuntimeError('synthetic_enqueue_failure') if job_state == 'enqueue_error' else None)
    monkeypatch.setattr(sync_user_garmin_data, 'delay', enqueue)
    monkeypatch.setattr(status, '_read_task_meta', lambda _: {'task_id':job_id,'status':job_state,'result':{'status':'success','success_count':1,'error_count':0,'activities_count':1}})
    monkeypatch.setattr(ae.settings, 'health_evidence_runtime_enabled', True)
    dispatched = []
    original = executor._dispatch_tool_request
    async def dispatch(request, token):
        dispatched.append((request.tool_name, dict(request.arguments)))
        return await original(request, token)
    monkeypatch.setattr(executor, '_dispatch_tool_request', dispatch)
    seen = []
    async def stream(messages, tools):
        seen.append((messages,tools))
        if not executor._turn_sync_attempted and len(seen) == 1:
            yield {'type':'tool_calls','tool_calls':[{'id':'model-guessed-sync','type':'function',
                'function':{'name':'health_record','arguments':json.dumps(guessed_args)}}]}
            yield {'type':'finish','finish_reason':'tool_calls'}
        else:
            yield {'type':'content','text':_model_reply or '可以参考已保存的运动记录。'}
            yield {'type':'finish','finish_reason':'stop'}
    monkeypatch.setattr(executor,'_call_llm_stream',stream)
    async def unexpected_nonstream(*args, **kwargs):
        pytest.fail('closed Garmin review must not call a completion model')
    monkeypatch.setattr(executor,'_call_llm',unexpected_nonstream)
    events=[event async for event in executor.run_stream(user_id=user.id,channel='typed',message=PROMPT)]
    done=next(event['data'] for event in events if event.get('event')=='done')
    assert enqueue.call_count == (0 if job_state == 'missing_credentials' else 1)
    if enqueue.call_count:
        assert enqueue.call_args.args == (user.id,)
    assert [name for name,_ in dispatched] == ['health_record','health_query']
    assert dispatched[0][1] == {'record_type':'garmin_sync','data':{}}
    assert dispatched[1][1] == {'dimension':'workout','start_date':now.date().isoformat(),
        'end_date':now.date().isoformat(),'timezone':'Asia/Shanghai'}
    assert seen == []
    assert executor._turn_focused_read_result['record']['id']==row.id
    assert executor._turn_focused_read_result['freshness']=='existing_record_not_sync_proof'
    assert executor._turn_sync_status_result['job_success_verified'] is (job_state == 'SUCCESS')
    assert (done['turn_outcome']['status']=='complete') is (job_state == 'SUCCESS')
    if job_state == 'PENDING':
        assert done['turn_outcome']['status']=='partial'
    assert not executor._agent_kernel_capability_block_reasons
    assert db.query(WorkoutRecord).filter_by(user_id=user.id).count()==1
    from app.models.agent_conversation import AgentMessage
    saved = db.get(AgentMessage,done['message_id'])
    delivered = ''.join(e.get('data',{}).get('content','') for e in events if e.get('event')=='token')
    if _capture is not None:
        _capture.update(done=done, saved=saved.content, delivered=delivered, model_calls=len(seen))
    for body in (saved.content,delivered):
        assert '尚不能确认它就是你刚才的跑步' in body
        if job_state == 'SUCCESS':
            assert '同步任务已返回成功' in body
            assert '不能据此保证活动数据完整' in body
        elif job_state == 'FAILURE':
            assert '同步任务失败' in body
        elif job_state in {'missing_credentials','enqueue_error'}:
            assert '本轮同步没有取得已提交确认' in body
        else:
            assert '同步任务已提交，尚未核实完成' in body



def test_goal_guard_allows_only_canonical_closed_owned_sync():
    from app.services.agent_executor import _normalize_goal_guarded_tool_calls
    from app.services.agent_kernel.types import GoalSpec
    goal=GoalSpec(kind='answer',domain='metric',operation='analyze',
        prohibited_operations=('create','update','delete'))
    call={'id':'synthetic-sync','type':'function','function':{'name':'health_record',
        'arguments':json.dumps({'record_type':'garmin_sync','data':{}})}}
    assert _normalize_goal_guarded_tool_calls([call],goal,original_user_message=PROMPT)==[call]
    assert _normalize_goal_guarded_tool_calls([call],goal)==[]


@pytest.mark.parametrize('text,args', [
    ('', {'record_type':'garmin_sync','data':{}}),
    (PROMPT.replace('我最新','朋友最新'), {'record_type':'garmin_sync','data':{}}),
    ('不要'+PROMPT, {'record_type':'garmin_sync','data':{}}),
    ('“'+PROMPT+'”', {'record_type':'garmin_sync','data':{}}),
    (PROMPT, {'record_type':'garmin_sync','data':{'days':7}}),
    (PROMPT, {'record_type':'garmin_sync','data':{},'user_id':99}),
    (PROMPT, {'record_type':'garmin_sync'}),
    (PROMPT, {'record_type':'exercise','data':{'duration':30}}),
])
def test_goal_guard_sync_exception_cannot_authorize_other_mutations(text,args):
    from app.services.agent_executor import _normalize_goal_guarded_tool_calls
    from app.services.agent_kernel.types import GoalSpec
    goal=GoalSpec(kind='answer',domain='metric',operation='analyze',
        prohibited_operations=('create','update','delete'))
    call={'id':'synthetic-rejected','type':'function','function':{'name':'health_record',
        'arguments':json.dumps(args)}}
    assert _normalize_goal_guarded_tool_calls([call],goal,original_user_message=text)==[]


@pytest.mark.asyncio
@pytest.mark.parametrize('boundary', ['read_only', 'owned_no_model_surface'])
async def test_pi_cannot_dispatch_sync_outside_turn_boundary(db,auth_user_and_headers,monkeypatch,boundary):
    from app.services import agent_executor as ae
    from app.services import agent_garmin_sync_status as status
    from app.tasks.garmin_sync import sync_user_garmin_data
    user,_=auth_user_and_headers
    db.add(GarminCredential(user_id=user.id,garmin_email='synthetic@example.invalid',
        encrypted_password='unused',sync_enabled=True,credentials_valid=True))
    db.commit()
    enqueue=Mock(return_value=Mock(id=str(uuid4())))
    monkeypatch.setattr(sync_user_garmin_data,'delay',enqueue)
    monkeypatch.setattr(status,'_read_task_meta',lambda job: {'task_id':job,'status':'PENDING'})
    monkeypatch.setattr(ae.settings,'health_evidence_runtime_enabled',True)
    executor=AgentExecutor(db);proposals=[];dispatched=[]
    original=executor._dispatch_tool_request
    async def dispatch(request,token):
        dispatched.append((request.tool_name,dict(request.arguments)))
        return await original(request,token)
    monkeypatch.setattr(executor,'_dispatch_tool_request',dispatch)
    async def stream(messages,tools):
        if not proposals:
            args={'record_type':'garmin_sync','data':{}}
            if boundary=='owned_no_model_surface':args['user_id']=user.id+1000
            proposals.append(args)
            yield {'type':'tool_calls','tool_calls':[{'id':'boundary-attempt','type':'function',
                'function':{'name':'health_record','arguments':json.dumps(args)}}]}
            yield {'type':'finish','finish_reason':'tool_calls'}
        else:
            yield {'type':'content','text':'同步状态未确认，无法完成本次同步核验。'}
            yield {'type':'finish','finish_reason':'stop'}
    monkeypatch.setattr(executor,'_call_llm_stream',stream)
    events=[e async for e in executor.run_stream(user_id=user.id,channel='typed',message=PROMPT,
        read_only_tools=boundary=='read_only')]
    done=next(e['data'] for e in events if e.get('event')=='done')
    assert done['turn_outcome']['status']!='complete'
    assert all('user_id' not in args for _,args in dispatched)
    if boundary=='read_only':
        assert enqueue.call_count==0
        assert not any(name=='health_record' for name,_ in dispatched)
        assert not executor._turn_sync_attempted
    else:
        assert enqueue.call_count==1
        assert enqueue.call_args.args==(user.id,)
        assert sum(name=='health_record' for name,_ in dispatched)==1
        assert proposals == []



@pytest.mark.asyncio
@pytest.mark.parametrize('model_text', [
    '年龄未知，所以按40岁估算。',
    '全程没有异常。',
    '最大心率未知，所以每周增加3次。',
    '缺少年龄、最大心率和连续心率曲线，不能据此推断运动安全。',
])
async def test_closed_garmin_projects_facts_without_any_model_analysis(db,auth_user_and_headers,monkeypatch,model_text):
    captured={}
    await test_canonical_sync_then_today_read_precedes_model_guess(
        db,auth_user_and_headers,monkeypatch,{'record_type':'garmin_sync'},'PENDING',
        _model_reply=model_text,_capture=captured)
    assert captured['model_calls']==0
    for reply in (captured['saved'],captured['delivered']):
        assert model_text not in reply
        assert '127' in reply and '143' in reply
        assert '年龄' in reply and '最大心率' in reply and ('心率曲线' in reply or '连续心率' in reply)
        assert all(claim not in reply for claim in ('40岁','全程没有异常','每周增加3次'))
    assert captured['done']['turn_outcome']['status']=='partial'


@pytest.mark.asyncio
@pytest.mark.parametrize('tool,args', [
    ('health_record',{'record_type':'garmin_sync','data':{},'user_id':99}),
    ('health_query',{'dimension':'workout','user_id':99}),
])
async def test_closed_garmin_gateway_rejects_cross_owner_arguments(tool,args):
    from app.services.agent_kernel.tool_gateway import ToolGateway
    from app.services.agent_kernel.types import AgentEnvelope,ExecutionContext,TurnSnapshot,ToolExecutionRequest
    from app.services.agent_kernel.intent_frame import build_intent_frame
    envelope=AgentEnvelope(user_id=41,channel='typed',text=PROMPT)
    context=ExecutionContext.for_test(user_id=41,channel='typed')
    snapshot=TurnSnapshot(envelope,context,build_intent_frame(envelope,context),policy_mode='enforce')
    called=[]
    async def dispatch(request):
        called.append(request)
        return '{}'
    result=await ToolGateway(snapshot).execute(ToolExecutionRequest(tool,args),dispatch)
    assert result.decision.action=='block'
    assert called==[]
