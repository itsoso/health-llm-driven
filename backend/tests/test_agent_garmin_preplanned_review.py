"""Canonical compound Garmin proposals cross real Pi and capability gateway."""
import json
from datetime import timedelta, timezone
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.models.daily_health import WorkoutRecord
from app.models.user import GarminCredential
from app.services.agent_executor import AgentExecutor

PROMPT = '同步一下佳明的数据，获取到我最新的运动的数据，我跑了3公里，分析一下刚才跑的情况怎么样，给我一些建议。'


@pytest.mark.asyncio
@pytest.mark.parametrize('job_state', ['PENDING', 'SUCCESS', 'FAILURE', 'missing_credentials', 'enqueue_error'])
@pytest.mark.parametrize('guessed_args', [
    {'record_type': 'garmin_sync'},
    {'record_type': 'garmin_sync', 'data': {'days': 7}},
])
async def test_canonical_sync_then_today_read_precedes_model_guess(db, auth_user_and_headers, monkeypatch, guessed_args, job_state):
    from app.services import agent_executor as ae
    from app.services import agent_garmin_sync_status as status
    from app.tasks.garmin_sync import sync_user_garmin_data
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    now = executor._agent_kernel_reference_now()
    if job_state != 'missing_credentials':
        db.add(GarminCredential(user_id=user.id, garmin_email='synthetic@example.invalid',
            encrypted_password='unused', sync_enabled=True, credentials_valid=True))
    row = WorkoutRecord(user_id=user.id, workout_date=now.date(), workout_type='running',
        source='garmin', distance_meters=3000, duration_seconds=1500,
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
            yield {'type':'content','text':'同步已入队但尚未确认完成；今天已存记录不能证明就是刚才这次跑步，只能有条件地分析。'}
            yield {'type':'finish','finish_reason':'stop'}
    monkeypatch.setattr(executor,'_call_llm_stream',stream)
    events=[event async for event in executor.run_stream(user_id=user.id,channel='typed',message=PROMPT)]
    done=next(event['data'] for event in events if event.get('event')=='done')
    assert enqueue.call_count == (0 if job_state == 'missing_credentials' else 1)
    if enqueue.call_count:
        assert enqueue.call_args.args == (user.id,)
    assert [name for name,_ in dispatched] == ['health_record','health_query']
    assert dispatched[0][1] == {'record_type':'garmin_sync','data':{}}
    assert dispatched[1][1] == {'dimension':'workout','start_date':now.date().isoformat(),
        'end_date':now.date().isoformat(),'timezone':'Asia/Shanghai'}
    assert len(seen)==1
    assert not any(t.get('function',{}).get('name') in {'health_record','health_query'} for t in seen[0][1])
    assert executor._turn_focused_read_result['record']['id']==row.id
    assert executor._turn_focused_read_result['freshness']=='existing_record_not_sync_proof'
    assert executor._turn_sync_status_result['job_success_verified'] is (job_state == 'SUCCESS')
    assert (done['turn_outcome']['status']=='complete') is (job_state == 'SUCCESS')
    if job_state == 'PENDING':
        assert done['turn_outcome']['status']=='partial'
    assert not executor._agent_kernel_capability_block_reasons
    assert db.query(WorkoutRecord).filter_by(user_id=user.id).count()==1


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
@pytest.mark.parametrize('boundary', ['read_only', 'cross_owner_after_read'])
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
            if boundary=='cross_owner_after_read':args['user_id']=user.id+1000
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
