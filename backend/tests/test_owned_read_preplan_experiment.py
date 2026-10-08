"""Eval-only skipped planning call must still execute through real Pi/Gateway."""
import json
import hashlib
from pathlib import Path
import os
from dataclasses import replace
from datetime import timedelta

import pytest

from tests.test_agent_coherence_pi_trajectories import (
    clock as clock, owned_data as owned_data, _isolate_twin_cache as _isolate_twin_cache,
    script_executor,
)

QUERY = '分析我最近7天的睡眠和饮食记录。'
ANSWER = '本轮依据实际查到的记录回答，未覆盖的信息仍然未知。'


@pytest.mark.asyncio
@pytest.mark.parametrize('days', [1, 7, 31])
async def test_same_owned_queries_and_receipt_with_one_fewer_provider_call(db, owned_data, monkeypatch, clock, days):
    from eval.experimental_owned_read_preplan import install_owned_read_preplan
    from app.models.agent_conversation import AgentMessage
    from app.models.daily_health import DietRecord, GarminData

    results = []
    query = f'分析我最近{days}天的睡眠和饮食记录。'
    today = clock[0].date()
    start = today-timedelta(days=days-1)
    original_row_counts = (db.query(DietRecord).count(), db.query(GarminData).count())
    for candidate in (False, True):
        with monkeypatch.context() as patch:
            steps = [ANSWER] if candidate else [
                ('health_query_batch', {'queries': [
                    {'dimension': 'diet', 'days': days}, {'dimension': 'sleep', 'days': days},
                ]}), ANSWER]
            trace = script_executor(db, patch, steps)
            if candidate:
                install_owned_read_preplan(trace.executor)
            events = [event async for event in trace.executor.run_stream(
                owned_data.id, query, channel='typed', client_turn_id=f'preplan-{candidate}')]
            done = events[-1]['data']
            assert done['perf']['agent_kernel'] == 'pi'
            assert done['turn_outcome']['status'] == 'complete'
            assert not trace.unexpected
            assert len(trace.dispatches) == 1
            request = trace.dispatches[0]
            assert request.tool_name == 'health_query_batch'
            assert all(q.get('days') == days for q in request.arguments['queries'])
            assert all(q['start_date'] == start.isoformat() and q['end_date'] == today.isoformat()
                       for q in request.arguments['queries'])
            payload = json.loads(trace.results[0][1])
            by_dimension = {result['dimension']: result for result in payload['results']}
            sleep = by_dimension['sleep']['records']
            assert len(sleep) == 1
            assert sleep[0]['total_sleep_duration'] == 420
            assert sleep[0]['sleep_score'] == 80
            assert sleep[0]['record_date'] == today.isoformat()
            # Excludes the other owner's same-day row and our future row.
            diet = by_dimension['diet']['records']
            if days == 1:
                assert diet == []
                assert by_dimension['diet']['availability'] == 'no_data'
            else:
                assert [record['food_name'] for record in diet] == ['合成番茄']
            saved = db.get(AgentMessage, done['message_id'])
            assert saved.meta['turn_outcome'] == done['turn_outcome']
            assert (db.query(DietRecord).count(), db.query(GarminData).count()) == original_row_counts
            results.append((len(trace.calls), request.arguments,
                            payload, done['turn_outcome'],
                            ''.join(e.get('data', {}).get('content', '')
                                    for e in events if e.get('event') == 'token'), saved.content))
    assert results[0][0] == 2 and results[1][0] == 1
    assert results[0][1:3] == results[1][1:3]
    assert results[0][4:] == results[1][4:]
    if (path := os.environ.get('REVA_PREPLAN_EVIDENCE')) and days == 7:
        dialect = db.get_bind().dialect.name
        Path(path).write_text(json.dumps({
            'status': 'offline_pi_gateway_pass',
            'source_sha256': {name: hashlib.sha256((Path(__file__).resolve().parents[2]/name).read_bytes()).hexdigest()
                              for name in ('backend/eval/experimental_owned_read_preplan.py',
                                           'backend/app/services/agent_executor.py',
                                           'backend/tests/test_owned_read_preplan_experiment.py')},
            'case': 'owned_sleep_diet_seven_days',
            'database_dialect': dialect,
            'provider_calls': {'baseline': results[0][0], 'candidate': results[1][0]},
            'normalized_queries_identical': True, 'tool_results_identical': True,
            'streamed_answer_identical': True, 'owned_fixture_record_present': True,
            'persisted_answer_identical': True, 'health_record_counts_unchanged': True,
            'agent_kernel': 'pi',
            'candidate_disposition': 'eval_only',
            'limits': [f'Stub model, real Pi and Gateway with synthetic {dialect} fixtures.',
                       'Not API tokens, live quality or latency evidence.',
                       'PostgreSQL verification unavailable.' if dialect != 'postgresql' else
                       'Does not verify migrations, concurrent requests or production load.'],
        }, ensure_ascii=False, indent=2) + '\n')


@pytest.mark.parametrize('query', [
    '查询我朋友最近7天的睡眠和饮食记录。',
    '不要查询我最近7天的睡眠和饮食记录。',
    '假如查询我最近7天的睡眠和饮食记录。',
    '查询我最近7天的睡眠和饮食记录，然后帮我记350毫升水。',
    '查询我最近7天的睡眠和饮食记录，给我用药建议。',
    '继续查询我最近7天的睡眠和饮食记录。',
])
async def test_unknown_or_mixed_task_reaches_original_provider(db, owned_data, monkeypatch, query):
    from eval.experimental_owned_read_preplan import install_owned_read_preplan

    trace = script_executor(db, monkeypatch, [ANSWER])
    executor = trace.executor
    executor._current_user_id = owned_data.id
    executor._current_turn_user_message = query
    executor._start_agent_kernel_turn(user_id=owned_data.id, message=query, channel='typed')
    install_owned_read_preplan(executor)
    events = [event async for event in executor._call_llm_stream(
        [{'role': 'user', 'content': query}], [{'function': {'name': 'health_query_batch'}}])]
    assert len(trace.calls) == 1
    assert not any(e['type'] == 'tool_calls' for e in events)


@pytest.mark.parametrize('boundary', ['owner', 'context_owner', 'envelope_text', 'attachment', 'pending', 'removed_tool', 'prior_tool', 'reentry'])
async def test_preplanning_preserves_owner_scope_and_iteration_boundaries(db, owned_data, monkeypatch, boundary):
    from eval.experimental_owned_read_preplan import install_owned_read_preplan

    trace = script_executor(db, monkeypatch, [ANSWER, ANSWER])
    executor = trace.executor
    executor._current_user_id = owned_data.id
    executor._current_turn_user_message = QUERY
    executor._start_agent_kernel_turn(user_id=owned_data.id, message=QUERY, channel='typed')
    tools = [{'function': {'name': 'health_query_batch'}}]
    messages = [{'role': 'user', 'content': QUERY}]
    if boundary == 'owner':
        executor._current_user_id += 1
    elif boundary == 'context_owner':
        snapshot = executor._agent_kernel_snapshot
        executor._agent_kernel_snapshot = replace(snapshot, context=replace(snapshot.context, user_id=owned_data.id+1))
    elif boundary == 'envelope_text':
        snapshot = executor._agent_kernel_snapshot
        executor._agent_kernel_snapshot = replace(snapshot, envelope=replace(snapshot.envelope, text='不同的原话'))
    elif boundary == 'attachment':
        executor._current_turn_has_attachment = True
    elif boundary == 'pending':
        executor._agent_kernel_pending_confirmation_tools = ['health_record']
    elif boundary == 'removed_tool':
        tools = []
    elif boundary == 'prior_tool':
        messages.append({'role': 'tool', 'content': '{}', 'tool_call_id': 'prior'})
    install_owned_read_preplan(executor)
    if boundary == 'reentry':
        first = [e async for e in executor._call_llm_stream(messages, tools)]
        assert any(e['type'] == 'tool_calls' for e in first)
    events = [e async for e in executor._call_llm_stream(messages, tools)]
    assert len(trace.calls) == 1
    assert not any(e['type'] == 'tool_calls' for e in events)


def test_no_runtime_import():
    root = Path(__file__).resolve().parents[1] / 'app'
    assert not any('experimental_owned_read_preplan' in path.read_text() for path in root.rglob('*.py'))
