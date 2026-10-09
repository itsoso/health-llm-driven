"""Synthetic end-to-end dispatch constraints for focused personal reads."""
import json
from datetime import date, datetime, timezone
import pytest
from app.models.medical_exam import MedicalExam
from app.services.agent_executor import AgentExecutor

MEDICAL = '我的双肩关节现在有什么样的状况？医院有没有做过核磁共振？诊断结果是怎么样的？'
GARMIN = '同步我的佳明数据，获取我最新的运动记录，我刚跑了3公里，分析我刚才的跑步，给我建议。'


@pytest.mark.asyncio
async def test_medical_dispatch_keeps_old_complete_narrative(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    narrative = '双肩MRI：' + '合成检查文字。' * 90 + 'FULL_NARRATIVE_END'
    db.add(MedicalExam(user_id=user.id, exam_date=date(2020, 1, 1),
                       exam_type='MRI', overall_assessment=narrative))
    db.commit()
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    executor._current_turn_user_message = MEDICAL
    raw = await executor._exec_health_query('', {}, {'dimension': 'medical_exam', 'keyword': '肩'})
    result = json.loads(raw)
    assert result['availability'] == 'available'
    assert result['reports'][0]['overall_assessment'] == narrative


@pytest.mark.asyncio
async def test_garmin_dispatch_empty_today_does_not_default_to_history(db, auth_user_and_headers, monkeypatch):
    user, _ = auth_user_and_headers
    from app.models.daily_health import WorkoutRecord
    db.add(WorkoutRecord(user_id=user.id, workout_date=date(2026, 10, 8),
                        workout_type='running', source='garmin', distance_meters=3000,
                        start_time=datetime(2026, 10, 8, 2, tzinfo=timezone.utc)))
    db.commit()
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    executor._current_turn_user_message = GARMIN
    monkeypatch.setattr(executor, '_agent_kernel_reference_now', lambda: datetime(2026, 10, 9, 8, tzinfo=timezone.utc))
    raw = await executor._exec_health_query('', {}, {'dimension': 'workout',
        'start_date': '2026-10-09', 'end_date': '2026-10-09', 'timezone': 'Asia/Shanghai'})
    result = json.loads(raw)
    assert result['availability'] == 'no_data'
    assert result['record'] is None
    completion = executor._composed_read_completion()
    assert completion is not None and not completion.complete


@pytest.mark.asyncio
@pytest.mark.parametrize('question', [MEDICAL, GARMIN])
async def test_stream_uses_only_current_owned_report_evidence(db, auth_user_and_headers, monkeypatch, question):
    from app.models.agent_conversation import AgentConversation, AgentMessage
    from app.services import agent_executor as ae
    from app.services.agent_conversation_service import AgentConversationService
    from app.twin import builder
    user, _ = auth_user_and_headers
    conv = AgentConversation(user_id=user.id, title='Synthetic')
    db.add(conv)
    db.flush()
    db.add(AgentMessage(conversation_id=conv.id, role='assistant', content='UNRELATED_HISTORY_PRIVATE'))
    db.add(MedicalExam(user_id=user.id, exam_date=date(2020, 1, 1), exam_type='MRI',
                       overall_assessment='双肩MRI：SYNTHETIC_OWNED_REPORT'))
    db.commit()
    executor = AgentExecutor(db)
    def forbidden(*args, **kwargs):
        pytest.fail('focused report turn must not preload unrelated personal data')
    monkeypatch.setattr(builder, 'build_twin', forbidden)
    monkeypatch.setattr(AgentConversationService, 'build_actionable_references', forbidden)
    monkeypatch.setattr(executor, '_bind_read_task_reference', forbidden)
    seen = []
    proposed = 0
    async def completion(messages, tools):
        nonlocal proposed
        seen.extend(messages)
        names = {tool['function']['name'] for tool in tools or []}
        assert names <= {'health_query', 'health_record', 'knowledge_search'}
        if not any(m.get('role') == 'tool' and 'availability' in str(m.get('content')) for m in messages):
            proposed += 1
            return {'content':'', 'tool_calls':[{'id':f'q{proposed}', 'type':'function',
                'function':{'name':'health_query', 'arguments':json.dumps({'dimension':'medical_exam' if question == MEDICAL else 'workout'})}}], 'finish_reason':'tool_calls'}
        return {'content':'仅根据已读取的报告文字解释，不能替代诊断。', 'finish_reason':'stop'}
    async def stream(messages, tools):
        result = await completion(messages, tools)
        if result.get('tool_calls'):
            yield {'type':'tool_calls', 'tool_calls':result['tool_calls']}
        else:
            yield {'type':'content', 'text':result['content']}
        yield {'type':'finish', 'finish_reason':result['finish_reason']}
    monkeypatch.setattr(executor, '_call_llm', completion)
    monkeypatch.setattr(executor, '_call_llm_stream', stream)
    monkeypatch.setattr(ae.settings, 'health_evidence_runtime_enabled', True)
    events = [event async for event in executor.run_stream(user_id=user.id, channel='typed',
        conversation_id=conv.id, message=question,
        extra_context=json.dumps({'data':'UNTRUSTED_CLIENT_HEALTH'}))]
    done = next(event['data'] for event in events if event.get('event') == 'done')
    context = json.dumps(seen, ensure_ascii=False)
    assert 'UNRELATED_HISTORY_PRIVATE' not in context
    assert 'UNTRUSTED_CLIENT_HEALTH' not in context
    if question == MEDICAL:
        assert 'SYNTHETIC_OWNED_REPORT' in context
        assert done['turn_outcome']['status'] == 'complete'
    else:
        assert executor._turn_sync_attempted
        assert not executor._turn_sync_queued  # no synthetic credential; honest precondition failure
        assert executor._turn_focused_read_result['availability'] == 'no_data'
        assert done['turn_outcome']['status'] != 'complete'


@pytest.mark.asyncio
@pytest.mark.parametrize('job_state', ['PENDING', 'SUCCESS', 'partial'])
async def test_sync_receipt_and_existing_run_remain_independent(db, auth_user_and_headers, monkeypatch, job_state):
    from unittest.mock import Mock
    from uuid import uuid4
    from datetime import timedelta
    from app.models.user import GarminCredential
    from app.models.daily_health import WorkoutRecord
    from app.services import agent_executor as ae
    from app.services import agent_garmin_sync_status as status
    from app.tasks.garmin_sync import sync_user_garmin_data
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    now = executor._agent_kernel_reference_now()
    db.add(GarminCredential(user_id=user.id, garmin_email='synthetic@example.test',
                           encrypted_password='unused-synthetic', sync_enabled=True, credentials_valid=True))
    db.add(WorkoutRecord(user_id=user.id, workout_date=now.date(), workout_type='running',
        source='garmin', distance_meters=3000, duration_seconds=1500,
        start_time=(now-timedelta(minutes=30)).astimezone(timezone.utc),
        end_time=(now-timedelta(minutes=5)).astimezone(timezone.utc)))
    db.commit()
    job_id = str(uuid4())
    enqueue = Mock(return_value=Mock(id=job_id))
    monkeypatch.setattr(sync_user_garmin_data, 'delay', enqueue)
    monkeypatch.setattr(status, '_read_task_meta', lambda _: {
        'task_id':job_id, 'status':'SUCCESS' if job_state == 'partial' else job_state,
        'result':{'status':'partial' if job_state == 'partial' else 'success',
                  'success_count':1, 'error_count':1 if job_state == 'partial' else 0,
                  'activities_count':1}})
    counter = 0
    async def completion(messages, tools):
        nonlocal counter
        counter += 1
        if counter <= 2:
            name, args = ('health_record', {'record_type':'garmin_sync','data':{}}) if counter == 1 else ('health_query', {'dimension':'workout'})
            return {'content':'','tool_calls':[{'id':f'step{counter}','type':'function',
                'function':{'name':name,'arguments':json.dumps(args)}}], 'finish_reason':'tool_calls'}
        return {'content':'记录可能早于本轮同步，尚不能确认是刚才这次跑步。', 'finish_reason':'stop'}
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
    events = [event async for event in executor.run_stream(user_id=user.id, message=GARMIN, channel='typed')]
    assert enqueue.call_count == 1
    assert enqueue.call_args.args[0] == user.id
    assert executor._turn_focused_read_result['availability'] == 'available'
    assert executor._turn_focused_read_result['freshness'] == 'existing_record_not_sync_proof'
    assert executor._turn_sync_status_result['job_success_verified'] is (job_state == 'SUCCESS')
    done = next(event['data'] for event in events if event.get('event') == 'done')
    assert (done['turn_outcome']['status'] == 'complete') is (job_state == 'SUCCESS')
    assert executor._sync_goal_outcomes()[0]['status'] == ('verified' if job_state == 'SUCCESS' else 'failed')


@pytest.mark.asyncio
async def test_selected_report_precedes_general_anatomy_scope(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    row = MedicalExam(user_id=user.id, exam_date=date(2020, 1, 1),
                      exam_type='MRI', overall_assessment='双肩MRI SELECTED_SYNTHETIC')
    db.add(row)
    db.commit()
    executor = AgentExecutor(db)
    executor._current_user_id = user.id
    executor._current_turn_user_message = MEDICAL
    executor._turn_selected_exam_id = row.id
    result = await executor._exec_health_query('', {}, {'dimension':'medical_exam'})
    assert 'SELECTED_SYNTHETIC' in result
    assert executor._focused_read_scopes() == (None, None)


@pytest.mark.asyncio
@pytest.mark.parametrize('availability', ['available', 'no_data', 'requires_selection'])
async def test_narrative_read_is_canonical_before_model_can_guess_keyword(db, auth_user_and_headers, monkeypatch, availability):
    from app.models.agent_conversation import AgentMessage
    from app.services import agent_executor as ae
    user, _ = auth_user_and_headers
    narrative = '双肩MRI：' + '合成报告段落。' * 100 + 'COMPLETE_NARRATIVE_TAIL'
    if availability == 'requires_selection':
        narrative += '合成' * 12000
    if availability != 'no_data':
        db.add(MedicalExam(user_id=user.id, exam_date=date(2020, 1, 1), exam_type='MRI', overall_assessment=narrative))
        db.commit()
    executor = AgentExecutor(db)
    dispatched = []
    original = executor._dispatch_tool_request
    async def dispatch(request, token):
        dispatched.append((request.tool_name, dict(request.arguments)))
        return await original(request, token)
    monkeypatch.setattr(executor, '_dispatch_tool_request', dispatch)
    seen = []
    async def stream(messages, tools):
        seen.append((messages, tools))
        if not any(m.get('role') == 'tool' and 'availability' in str(m.get('content')) for m in messages):
            # Reproduce the failed live shape: a semantically descriptive keyword
            # is not the server canonical keyword. Never relax the gateway for it.
            yield {'type':'tool_calls','tool_calls':[{'id':'model-guess','type':'function','function':{'name':'health_query','arguments':json.dumps({'dimension':'medical_exam','keyword':'双肩关节核磁共振'})}}]}
            yield {'type':'finish','finish_reason':'tool_calls'}
        else:
            text = ('已读取完整历史报告文本；OCR摘要未核验原始影像，不代表当前诊断。'
                    if availability == 'available' else '未能核验完整报告，需要补充或选择报告。')
            yield {'type':'content','text':text}
            yield {'type':'finish','finish_reason':'stop'}
    monkeypatch.setattr(executor, '_call_llm_stream', stream)
    monkeypatch.setattr(ae.settings, 'health_evidence_runtime_enabled', True)
    events=[e async for e in executor.run_stream(user_id=user.id,channel='typed',message=MEDICAL)]
    done=next(e['data'] for e in events if e.get('event')=='done')
    assert dispatched == [('health_query', {'dimension':'medical_exam','keyword':'肩'})]
    assert len(seen) == 1
    assert all((t.get('function') or {}).get('name') != 'health_query' for t in seen[0][1])
    assert executor._turn_focused_read_result['availability'] == availability
    assert (done['turn_outcome']['status']=='complete') == (availability == 'available')
    if availability == 'available':
        assert 'COMPLETE_NARRATIVE_TAIL' in str(seen[0][0])
        assert 'OCR摘要' in db.get(AgentMessage,done['message_id']).content
