import pytest
from app.services.agent_kernel.health_semantics import health_read_has_nonself_subject

def test_bmi_self_not_foreign():
    assert not health_read_has_nonself_subject('帮我算我的 BMI')

@pytest.mark.parametrize('text', ['帮我算我的 BMI', '计算我的BMI', '我的BMI是多少？'])
def test_closed_bmi_scope(text):
    from app.services.agent_kernel.bmi_read_scope import is_bmi_read_request
    assert is_bmi_read_request(text)

@pytest.mark.parametrize('text', ['帮我算他的 BMI','不要计算我的BMI','他说“计算我的BMI”','计算我的BMI并查看全部记录','计算我朋友的BMI','计算我的BMI，昨天','假如计算我的BMI'])
def test_bmi_scope_rejects_other_goals(text):
    from app.services.agent_kernel.bmi_read_scope import is_bmi_read_request
    assert not is_bmi_read_request(text)

@pytest.mark.parametrize('args', [{'dimension':'bmi'}, {'dimension':'bmi','days':7}, {'dimension':'bmi','user_id':42}, {'dimension':'weight'}, {'dimension':'profile'}, {'dimension':'comprehensive'}])
def test_gateway_binds_only_bmi(args):
    from app.services.agent_kernel.types import AgentEnvelope, ExecutionContext, TurnSnapshot, ToolExecutionRequest
    from app.services.agent_kernel.intent_frame import build_intent_frame
    from app.services.agent_kernel.capability_policy import decide_tool_capability
    e = AgentEnvelope(user_id=41,channel='chat',text='帮我算我的 BMI')
    c = ExecutionContext.for_test(user_id=41,channel='chat')
    s = TurnSnapshot(e,c,build_intent_frame(e,c))
    assert (decide_tool_capability(s,ToolExecutionRequest('health_query',args)).action == 'allow') == (args == {'dimension':'bmi'})

@pytest.mark.asyncio
async def test_bmi_actual_stream_is_deterministic_owner_bound(db, auth_user_and_headers, monkeypatch):
    from datetime import date, timedelta
    from app.models.user_profile import UserProfile
    from app.models.weight import WeightRecord
    from app.services.agent_executor import AgentExecutor
    user, _ = auth_user_and_headers
    db.add(UserProfile(user_id=user.id,height_cm=175, current_weight_kg=999))
    db.add(WeightRecord(user_id=user.id,record_date=date.today()-timedelta(days=1),weight=70))
    db.add(WeightRecord(user_id=user.id,record_date=date.today()+timedelta(days=2),weight=90))
    db.commit()
    executor = AgentExecutor(db)
    async def no_model(*args, **kwargs):
        raise AssertionError('BMI must not call model')
        yield
    monkeypatch.setattr(executor, '_call_llm_stream', no_model)
    events = [event async for event in executor.run_stream(user_id=user.id,channel='typed',message='帮我算我的 BMI')]
    body = ''.join(e.get('data',{}).get('content','') for e in events if e.get('event')=='token')
    assert '22.86' in body
    assert '70' in body
    assert '999' not in body
    assert not executor._agent_kernel_capability_block_reasons
    done=next(e['data'] for e in events if e.get('event')=='done')
    assert done['turn_outcome']['status']=='complete'
    assert done.get('medical_citations')

@pytest.mark.parametrize('height', [None, 0, -1, float('inf')])
def test_missing_invalid_height_is_explicit(db, auth_user_and_headers, height):
    from datetime import date
    from app.models.user_profile import UserProfile
    from app.services.bmi_read import read_bmi, bmi_reply
    user, _ = auth_user_and_headers
    db.add(UserProfile(user_id=user.id,height_cm=height)); db.commit()
    result=read_bmi(db,user.id,date.today())
    assert result['status']=='missing_data'
    assert '无法计算' in bmi_reply(result)


def test_owner_isolation_and_no_undated_weight_fallback(db, auth_user_and_headers):
    from datetime import date
    from app.models.user import User
    from app.models.user_profile import UserProfile
    from app.models.weight import WeightRecord
    from app.services.bmi_read import read_bmi
    user, _=auth_user_and_headers
    other=User(name='BMI Other',username='bmi-other', email='bmi-other@example.invalid',hashed_password='unused')
    db.add(other);db.flush()
    db.add(UserProfile(user_id=user.id,height_cm=175,current_weight_kg=70))
    db.add(WeightRecord(user_id=other.id,record_date=date.today(),weight=99));db.commit()
    assert read_bmi(db,user.id,date.today()) == {'status':'missing_data','missing':['dated_weight']}

@pytest.mark.parametrize('owner', [None, True, 0, -1, 42])
def test_mismatched_or_invalid_context_owner_rejected(owner):
    from app.services.agent_kernel.types import AgentEnvelope, ExecutionContext, TurnSnapshot, ToolExecutionRequest
    from app.services.agent_kernel.intent_frame import build_intent_frame
    from app.services.agent_kernel.capability_policy import decide_tool_capability
    from dataclasses import replace
    e=AgentEnvelope(user_id=41,channel='chat',text='帮我算我的 BMI')
    c=replace(ExecutionContext.for_test(user_id=41,channel='chat'),user_id=owner)
    s=TurnSnapshot(e,c,build_intent_frame(e,c))
    assert decide_tool_capability(s,ToolExecutionRequest('health_query',{'dimension':'bmi'})).action=='block'

@pytest.mark.asyncio
@pytest.mark.parametrize('height', [None, 175])
async def test_missing_bmi_data_requests_input_without_model(db, auth_user_and_headers, monkeypatch, height):
    from app.services.agent_executor import AgentExecutor
    user,_=auth_user_and_headers
    if height is not None:
        from app.models.user_profile import UserProfile
        db.add(UserProfile(user_id=user.id,height_cm=height));db.commit()
    executor=AgentExecutor(db)
    async def no_model(*args,**kwargs):
        raise AssertionError('BMI must not call model')
        yield
    monkeypatch.setattr(executor,'_call_llm_stream',no_model)
    events=[e async for e in executor.run_stream(user_id=user.id,channel='typed',message='帮我算我的 BMI')]
    done=next(e['data'] for e in events if e.get('event')=='done')
    assert done['turn_outcome']['status']=='waiting_for_user'
    body=''.join(e.get('data',{}).get('content','') for e in events if e.get('event')=='token')
    assert '无法计算' in body

@pytest.mark.asyncio
@pytest.mark.parametrize('args', [{'dimension':'bmi','days':1}, {'dimension':'bmi','owner_id':41}, {'dimension':'bmi','start_date':'2026-10-20'}])
async def test_adapter_rejects_extra_scope_before_database(db, auth_user_and_headers, args):
    from unittest.mock import Mock
    from app.services.agent_executor import AgentExecutor
    user,_=auth_user_and_headers
    executor=AgentExecutor(db)
    executor._start_agent_kernel_turn(user_id=user.id,message='帮我算我的 BMI',channel='typed')
    executor._current_user_id=user.id
    executor._current_turn_user_message='帮我算我的 BMI'
    executor.db=Mock()
    assert (await executor._exec_health_query('',{},args)).startswith('Error:')
    executor.db.query.assert_not_called()

@pytest.mark.parametrize('invalid_weight', [float('nan'), float('inf'), -5])
def test_pg_invalid_latest_weight_is_excluded(db, auth_user_and_headers, invalid_weight):
    from datetime import date, timedelta
    from app.models.user_profile import UserProfile
    from app.models.weight import WeightRecord
    from app.services.bmi_read import read_bmi
    if db.bind.dialect.name != 'postgresql':
        pytest.skip('NaN ordering is PostgreSQL-specific')
    user,_=auth_user_and_headers
    db.add(UserProfile(user_id=user.id,height_cm=175))
    db.add(WeightRecord(user_id=user.id,record_date=date(2026,10,19),weight=70))
    db.add(WeightRecord(user_id=user.id,record_date=date(2026,10,20),weight=invalid_weight))
    db.commit()
    result=read_bmi(db,user.id,date(2026,10,20))
    assert result['weight_kg']==70
    assert result['weight_date']=='2026-10-19'


def test_same_day_weights_sort_by_created_at_then_id(db, auth_user_and_headers):
    from datetime import date, datetime, timezone
    from app.models.user_profile import UserProfile
    from app.models.weight import WeightRecord
    from app.services.bmi_read import read_bmi
    user,_=auth_user_and_headers
    db.add(UserProfile(user_id=user.id,height_cm=175))
    for weight, hour in [(70,10),(71,11),(72,11),(99,9)]:
        db.add(WeightRecord(user_id=user.id,record_date=date(2026,10,20),weight=weight,
            created_at=datetime(2026,10,20,hour,tzinfo=timezone.utc)))
        db.flush()
    db.commit()
    assert read_bmi(db,user.id,date(2026,10,20))['weight_kg']==72


@pytest.mark.asyncio
async def test_adapter_uses_account_local_date_across_utc_boundary(db, auth_user_and_headers):
    from datetime import date, datetime, timezone
    from dataclasses import replace
    from zoneinfo import ZoneInfo
    from app.models.user_profile import UserProfile
    from app.models.weight import WeightRecord
    from app.services.agent_executor import AgentExecutor
    user,_=auth_user_and_headers
    db.add(UserProfile(user_id=user.id,height_cm=175))
    db.add(WeightRecord(user_id=user.id,record_date=date(2026,10,19),weight=70))
    db.add(WeightRecord(user_id=user.id,record_date=date(2026,10,20),weight=71))
    db.commit()
    executor=AgentExecutor(db)
    snapshot=executor._start_agent_kernel_turn(user_id=user.id,message='帮我算我的 BMI',channel='typed')
    utc_now=datetime(2026,10,19,18,tzinfo=timezone.utc)
    context=replace(snapshot.context,current_time=utc_now.astimezone(ZoneInfo('Asia/Shanghai')),timezone='Asia/Shanghai')
    executor._agent_kernel_snapshot=replace(snapshot,context=context)
    executor._current_user_id=user.id
    executor._current_turn_user_message='帮我算我的 BMI'
    import json
    result=json.loads(await executor._exec_health_query('',{}, {'dimension':'bmi'}))
    assert result['weight_date']=='2026-10-20'
    assert result['weight_kg']==71


@pytest.mark.asyncio
async def test_db_failure_does_not_claim_complete_or_call_model(db, auth_user_and_headers, monkeypatch):
    from app.services.agent_executor import AgentExecutor
    from app.services import bmi_read
    user,_=auth_user_and_headers
    executor=AgentExecutor(db)
    def failed_read(*args,**kwargs):
        raise RuntimeError('synthetic_database_unavailable')
    monkeypatch.setattr(bmi_read,'read_bmi',failed_read)
    model_calls=[]
    async def no_model(*args,**kwargs):
        model_calls.append(True)
        raise AssertionError('BMI failure must not call model')
        yield
    monkeypatch.setattr(executor,'_call_llm_stream',no_model)
    events=[e async for e in executor.run_stream(user_id=user.id,channel='typed',message='帮我算我的 BMI')]
    done=next(e['data'] for e in events if e.get('event')=='done')
    assert done['turn_outcome']['status']!='complete'
    assert executor._turn_bmi_result is None
    assert model_calls == []
