"""Subday reads require real event timestamps, never ingestion dates."""
from dataclasses import replace
from datetime import date, datetime
import pytest
from app.services.agent_kernel.read_task_scope import resolve_owned_read_scope
from app.services.agent_kernel.capability_policy import decide_tool_capability
from app.services.agent_kernel.types import ToolExecutionRequest, ExecutionContext
from tests.test_recent_workout_read_regression import snapshot

@pytest.mark.parametrize('text,period,day,kind', [
    ('分析上午的跑步', 'morning', '2026-10-10', 'running'),
    ('分析昨天上午的跑步', 'morning', '2026-10-09', 'running'),
    ('看看今天下午的骑行', 'afternoon', '2026-10-10', 'cycling'),
    ('昨晚的游泳怎么样？', 'evening', '2026-10-09', 'swimming'),
])
def test_subday_owned_scope(text, period, day, kind):
    turn = snapshot(text)
    scope = resolve_owned_read_scope(turn)
    assert scope is not None
    assert scope.query('workout')['start_date'] == day
    assert scope.workout_selection.period == period
    assert scope.workout_selection.workout_type == kind
    decision = decide_tool_capability(turn, ToolExecutionRequest('health_query', {'dimension':'workout'}))
    assert decision.action == 'allow', decision.reason

@pytest.mark.parametrize('zone,day', [('Asia/Shanghai','2026-10-10'), ('America/Los_Angeles','2026-10-09')])
def test_account_timezone(zone, day):
    turn = snapshot('分析上午的跑步')
    turn = replace(turn, context=replace(turn.context, timezone=zone))
    assert resolve_owned_read_scope(turn).query('workout')['start_date'] == day

@pytest.mark.parametrize('text', ['分析朋友上午的跑步','分析上午的跑步，仅看去年','不要分析上午的跑步','解释“分析上午的跑步”','分析上午的跑步并删除记录'])
def test_unconsumed_modifiers_block(text):
    assert resolve_owned_read_scope(snapshot(text)) is None


def test_real_timestamp_filters_not_business_day(db, auth_user_and_headers):
    from app.models.daily_health import WorkoutRecord, ExerciseRecord
    from app.models.user import User
    from app.services.agent_longitudinal_read import read_longitudinal_health_query
    from app.services.agent_query_window import parse_query_window
    user,_ = auth_user_and_headers
    other = User(name='Synthetic', email='subday-other@example.test'); db.add(other); db.flush()
    def row(stamp, *, owner=None, kind='running', day=date(2026,10,9)):
        return WorkoutRecord(user_id=owner or user.id, workout_date=day, workout_type=kind,
                             start_time=datetime.fromisoformat(stamp) if stamp else None)
    match = row('2026-10-10T01:00:00+00:00')
    db.add_all([match, row('2026-10-10T04:00:00+00:00'), row('2026-10-10T01:00:00+00:00', owner=other.id),
                row('2026-10-10T01:00:00+00:00', kind='cycling'), row(None, day=date(2026,10,10)),
                ExerciseRecord(user_id=user.id,record_date=date(2026,10,10),exercise_type='running')])
    db.commit()
    scope=resolve_owned_read_scope(snapshot('分析上午的跑步'))
    result=read_longitudinal_health_query(db,user.id,'workout',parse_query_window(scope.query('workout')),selection=scope.workout_selection)
    assert [r['id'] for r in result['records']] == [match.id]
    assert result['records'][0]['record_date'] == '2026-10-10'
    assert result['workout_selection']['period'] == 'morning'
    assert 'missing_event_time_excluded' in result['limitations']

@pytest.mark.parametrize('args', [
    {'owner_id':42}, {'start_date':'2020-01-01'}, {'workout_type':'cycling'},
    {'period':'evening'}, {'timezone':'UTC'}, {'dimension':'diet'},
])
def test_model_cannot_widen_frozen_selector(args):
    assert decide_tool_capability(snapshot('分析上午的跑步'),ToolExecutionRequest(
        'health_query',{'dimension':'workout',**args})).action == 'block'

@pytest.mark.parametrize('owner,envelope_owner', [(42,41),(0,0),(True,1)])
def test_identity_mismatch_blocks(owner,envelope_owner):
    turn=snapshot('分析上午的跑步')
    turn=replace(turn,context=replace(turn.context,user_id=owner),envelope=replace(turn.envelope,user_id=envelope_owner))
    assert resolve_owned_read_scope(turn) is None

@pytest.mark.parametrize('tamper', [None,'missing','naive','noon','kind','source','period','bounds'])
def test_completion_checks_event_time_and_metadata(tamper):
    from app.services.agent_kernel.types import ToolExecutionResult,CapabilityDecision
    from app.services.agent_composed_read_completion import evaluate_composed_read_completion
    scope=resolve_owned_read_scope(snapshot('分析上午的跑步'))
    query=scope.query('workout')
    row={'id':1,'record_date':'2026-10-10','workout_type':'running','record_kind':'workout_record',
         'source_table':'workout_records','event_start_time':'2026-10-10T09:00:00+08:00'}
    metadata={'workout_type':'running','expected_count':None,'matched_count':1,'event_identity':'unverified',
              'count_status':'unspecified','period':'morning','start_time':'2026-10-10T00:00:00+08:00',
              'end_time':'2026-10-10T12:00:00+08:00'}
    if tamper=='missing': row.pop('event_start_time')
    if tamper=='naive': row['event_start_time']='2026-10-10T09:00:00'
    if tamper=='noon': row['event_start_time']='2026-10-10T12:00:00+08:00'
    if tamper=='kind': row['workout_type']='cycling'
    if tamper=='source': row['record_kind']='exercise_record'
    if tamper=='period': metadata['period']='afternoon'
    if tamper=='bounds': metadata['end_time']='2026-10-11T00:00:00+08:00'
    payload={'dimension':'workout','window':{k:v for k,v in query.items() if k!='dimension'},
             'records':[row],'availability':'available','limitations':['missing_event_time_excluded'],
             'source_scope':'owned_actual_workout_records','workout_selection':metadata}
    result=evaluate_composed_read_completion(scope,[ToolExecutionResult('health_query',payload,
        decision=CapabilityDecision('allow','owned','health_query',query))])
    assert (not result.missing_dimensions) == (tamper is None)


@pytest.mark.asyncio
@pytest.mark.parametrize("has_record", [True, False])
@pytest.mark.parametrize("text,batch", [("分析上午的跑步", False),("分析上午的跑步", True)])
async def test_subday_screenshot_executor_and_saved_reply(
    db, auth_user_and_headers, isolated_agent_protocol_transport, monkeypatch, has_record, text, batch,
):
    import json
    from datetime import timedelta
    from app.models.agent_conversation import AgentMessage
    from app.models.daily_health import WorkoutRecord
    from app.models.user import User
    from app.services.agent_executor import AgentExecutor
    from app.twin.schema import HealthTwin, TwinMeta

    user, _ = auth_user_and_headers
    other = User(name="Synthetic other", email="recent-workout-other@example.test")
    db.add(other)
    db.flush()
    now = datetime.fromisoformat("2026-10-10T09:00:00+08:00")
    original_clock = ExecutionContext.now.__func__
    monkeypatch.setattr(ExecutionContext, "now", classmethod(
        lambda cls, **kwargs: original_clock(cls, **{**kwargs, "now_utc": now})))
    monkeypatch.setattr("app.twin.builder.build_twin", lambda _db, uid, **kwargs:
        HealthTwin(meta=TwinMeta(user_id=uid, generated_at=now)))
    own = WorkoutRecord(user_id=user.id, workout_date=now.date(),
                        workout_type='running', start_time=now.astimezone(__import__('datetime').timezone.utc), duration_seconds=1800)
    if has_record:
        db.add(own)
    db.add_all([
        WorkoutRecord(user_id=other.id, workout_date=now.date(), workout_type="walking"),
        WorkoutRecord(user_id=user.id, workout_date=now.date()-timedelta(days=1), workout_type="cycling"),
    ])
    db.commit()
    before = [(r.id, r.user_id, r.workout_date) for r in db.query(WorkoutRecord).order_by(WorkoutRecord.id)]
    executor = AgentExecutor(db)
    dispatch = executor._dispatch_tool_request
    calls, results = [], []

    async def provider(messages, tools):
        calls.append(tools)
        if len(calls) == 1:
            yield {"type": "tool_calls", "tool_calls": [{
                "id": "recent-workout-read", "type": "function", "function": {
                    "name": 'health_query_batch' if batch else 'health_query',
                    "arguments": json.dumps({'queries': [{'dimension': 'workout'}]} if batch else {'dimension': 'workout'}),
                }}]}
            yield {"type": "finish", "finish_reason": "tool_calls"}
        else:
            yield {"type": "content", "text": "已查询运动记录。"}
            yield {"type": "finish", "finish_reason": "stop"}

    async def observe(request, token):
        result = await dispatch(request, token)
        results.append((request, json.loads(result)))
        return result

    monkeypatch.setattr(executor, "_build_system_prompt", lambda *a, **k: "按工具证据回答。")
    monkeypatch.setattr(executor, "_build_system_knowledge_prompt_context", lambda *a, **k: "")
    monkeypatch.setattr(executor, "_call_llm_stream", provider)
    monkeypatch.setattr(executor, "_dispatch_tool_request", observe)
    events = [event async for event in executor.run_stream(
        user.id, text, client_turn_id=f"recent-workout-{has_record}-{batch}")]
    done = next(e["data"] for e in reversed(events) if e.get("event") == "done")
    saved = db.get(AgentMessage, done["message_id"])
    assert done["perf"]["agent_kernel"] == "pi"
    assert {t["function"]["name"] for t in calls[0]} <= {"health_query", "health_query_batch", "knowledge_search"}
    assert len(results) == 1
    request, payload = results[0]
    assert request.tool_name == ('health_query_batch' if batch else 'health_query')
    query = request.arguments['queries'][0] if batch else request.arguments
    payload = payload['results'][0] if batch else payload
    assert query["start_date"] == query["end_date"] == "2026-10-10"
    assert [r["id"] for r in payload["records"]] == (
        [own.id] if has_record else [])
    assert payload["availability"] == ("available" if has_record else "no_data")
    assert "只能查询当前登录用户" not in saved.content
    assert "上午" in saved.content and "实际开始时间" in saved.content
    assert '本轮数据查询未完成' not in saved.content
    assert '请明确要查看的数据类别和日期' not in saved.content
    assert done['turn_outcome']['status'] == 'complete'
    assert not done.get("write_receipts")
    assert [(r.id, r.user_id, r.workout_date) for r in db.query(WorkoutRecord).order_by(WorkoutRecord.id)] == before


@pytest.mark.parametrize('day,hours', [('2026-03-08',11), ('2026-11-01',13)])
def test_morning_bounds_follow_dst(day,hours):
    from datetime import timezone
    from app.services.agent_longitudinal_read import RecentWorkoutSelection,workout_period_bounds
    from app.services.agent_query_window import QueryWindow
    start,end=workout_period_bounds(QueryWindow(date.fromisoformat(day),date.fromisoformat(day),'America/Los_Angeles'),
                                    RecentWorkoutSelection('running',period='morning'))
    assert (end.astimezone(timezone.utc)-start.astimezone(timezone.utc)).total_seconds()==hours*3600

@pytest.mark.parametrize('text',['分析明天上午的跑步','分析前天上午的跑步','分析上午的跑步和下午的骑行','分析昨天上午的跑步只看今天'])
def test_other_dates_and_mixed_periods_not_silently_consumed(text):
    assert resolve_owned_read_scope(snapshot(text)) is None

@pytest.mark.parametrize('period,stamp,include',[
    ('morning','2026-10-09T16:00:00+00:00',True),
    ('morning','2026-10-10T03:59:59+00:00',True),
    ('morning','2026-10-10T04:00:00+00:00',False),
    ('afternoon','2026-10-10T04:00:00+00:00',True),
    ('afternoon','2026-10-10T10:00:00+00:00',False),
    ('evening','2026-10-10T10:00:00+00:00',True),
    ('evening','2026-10-10T16:00:00+00:00',False),
])
def test_sql_half_open_local_boundaries(db,auth_user_and_headers,period,stamp,include):
    from app.models.daily_health import WorkoutRecord
    from app.services.agent_longitudinal_read import RecentWorkoutSelection,read_longitudinal_health_query
    from app.services.agent_query_window import QueryWindow
    user,_=auth_user_and_headers
    row=WorkoutRecord(user_id=user.id,workout_date=date(2026,10,9),workout_type='running',start_time=datetime.fromisoformat(stamp))
    db.add(row);db.commit()
    result=read_longitudinal_health_query(db,user.id,'workout',QueryWindow(date(2026,10,10),date(2026,10,10),'Asia/Shanghai'),
                                         selection=RecentWorkoutSelection('running',period=period))
    assert [r['id'] for r in result['records']] == ([row.id] if include else [])

@pytest.mark.parametrize('text', ['分析明天上午的跑步','分析今天上午的跑步并同步','分析上午的跑步并删除记录',
                                 '分析前天上午的跑步','分析昨天上午的跑步只看今天'])
def test_rejected_subday_cannot_fall_back_to_rolling_read(text):
    assert decide_tool_capability(snapshot(text),ToolExecutionRequest('health_query',{'dimension':'workout'})).action=='block'

@pytest.mark.parametrize('text', ['昨晚睡得怎样，是否适合锻炼', '今天上午睡眠如何，下午适合跑步吗？',
                                 '昨晚吃了什么，是否适合锻炼'])
def test_subday_reference_does_not_attach_sleep_or_diet_to_workout(text):
    from app.services.agent_longitudinal_read import has_recent_workout_reference
    assert not has_recent_workout_reference(text)
