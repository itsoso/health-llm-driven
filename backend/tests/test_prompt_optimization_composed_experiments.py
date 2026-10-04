"""P1/P2 together: real Pi, Gateway, DB reads and provider payload preparation.

Only provider responses and unrelated context blocks are synthetic. This is
not model quality, API usage, or a latency measurement.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import pytest

from app.models.agent_conversation import AgentMessage
from app.models.daily_health import DietRecord, GarminData
from app.services import agent_executor as ae
from tests.test_agent_coherence_pi_trajectories import (
    clock as clock, owned_data as owned_data, _isolate_twin_cache as _isolate_twin_cache,
)
from tests.test_agent_diet_synthesis_projection import _context_sentinels

QUERY = '分析我最近7天的睡眠和饮食记录。'
ANSWER = '根据本轮查询到的记录回答；未提供的指标仍然未知，记录不能代表完整健康状态。'


@pytest.mark.parametrize('data_state', ['available', 'empty', 'read_failure'])
async def test_combined_candidates_preserve_provider_evidence_and_saved_answer(db, owned_data, monkeypatch, caplog, data_state):
    from eval.experimental_owned_read_preplan import install_owned_read_preplan
    from eval.experimental_read_synthesis import build_read_synthesis_parts

    runs = {}
    if data_state == 'empty':
        db.query(DietRecord).filter_by(user_id=owned_data.id).delete()
        db.query(GarminData).filter_by(user_id=owned_data.id).delete()
        db.commit()
    elif data_state == 'read_failure':
        def fail_read(*args, **kwargs):
            raise RuntimeError('synthetic_read_unavailable')
        monkeypatch.setattr('app.services.agent_longitudinal_read.read_longitudinal_health_query', fail_read)
    counts = (db.query(DietRecord).count(), db.query(GarminData).count())
    for variant, p1, p2 in (('baseline', False, False), ('p1', True, False),
                           ('p2', False, True), ('combined', True, True)):
        with monkeypatch.context() as patch:
            _context_sentinels(patch)
            patch.setattr(ae.settings, 'domain_prompt_optimization', True)
            patch.setattr(ae.settings, 'agent_base_url', None)
            patch.setattr(ae.settings, 'agent_api_key', None)
            patch.setattr(ae.settings, 'task_tiered_routing', True)
            patch.setattr('app.services.llm.task_routing.pick_model_id_by_tier', lambda *a, **k: 'qwen3.8-max-preview')
            executor = ae.AgentExecutor(db)
            patch.setattr(executor, '_build_system_knowledge_prompt_context', lambda *a, **k: 'SYNTHETIC_KB_CONTEXT')
            calls, requests, receipts = [], [], []
            actual_dispatch = executor._dispatch_tool_request

            async def dispatch(request, token):
                requests.append(request)
                result = await actual_dispatch(request, token)
                receipts.append(result)
                return result

            patch.setattr(executor, '_dispatch_tool_request', dispatch)

            class Provider:
                provider_name = 'synthetic'
                def __init__(self, model='qwen3.8-max-preview'):
                    self.model = model

                async def chat_stream(self, **kwargs):
                    calls.append(deepcopy(kwargs))
                    assert len(calls) <= 2, 'Unexpected retry must not be hidden by the fixture'
                    prior_result = any(m.get('role') == 'tool' for m in kwargs['messages'])
                    if kwargs.get('tools') and not prior_result:
                        yield {'type': 'tool_calls', 'tool_calls': [{
                            'id': 'synthetic-model-read', 'type': 'function', 'function': {
                                'name': 'health_query_batch', 'arguments': json.dumps({'queries': [
                                    {'dimension': 'diet', 'days': 7}, {'dimension': 'sleep', 'days': 7},
                                ]})}}]}
                        yield {'type': 'finish', 'finish_reason': 'tool_calls'}
                    else:
                        yield {'type': 'content', 'text': (
                            '本轮查询失败，无法确认睡眠和饮食记录，请稍后重试。'
                            if data_state == 'read_failure' else ANSWER)}
                        yield {'type': 'finish', 'finish_reason': 'stop'}

            patch.setattr('app.services.llm.factory.create_provider_for_model_id', lambda model_id, **k: Provider(model_id))
            for factory in ('create_provider_for_user', 'get_llm_provider'):
                patch.setattr('app.services.llm.factory.'+factory, lambda *a, **k: Provider())
            if p1:
                patch.setattr('app.services.agent_prompt_sections.build_base_prompt_parts', build_read_synthesis_parts)
            if p2:
                install_owned_read_preplan(executor)
            events = [event async for event in executor.run_stream(
                owned_data.id, QUERY, channel='typed', client_turn_id='composed-'+variant,
                extra_context=json.dumps({'model_id': 'qwen3.8-max-preview'}))]
            done = next(e['data'] for e in reversed(events) if e.get('event') == 'done')
            saved = db.get(AgentMessage, done['message_id'])
            streamed = ''.join(e['data'].get('content', '') for e in events if e.get('event') == 'token')
            assert done['perf']['agent_kernel'] == 'pi'
            if data_state == 'read_failure':
                assert done['turn_outcome']['status'] != 'complete'
            else:
                assert done['turn_outcome']['status'] == 'complete'
            assert saved.meta['turn_outcome'] == done['turn_outcome']
            assert saved.content == streamed
            # Existing tool recovery retries a transient read failure once;
            # candidates must preserve that budget, not hide or multiply it.
            assert len(requests) == (2 if data_state == 'read_failure' else 1)
            assert all(request.tool_name == 'health_query_batch' for request in requests)
            assert all(request.arguments == requests[0].arguments for request in requests)
            assert not done['write_receipts']
            assert len(calls) == ((0 if p2 else 1) if data_state == 'read_failure' else (1 if p2 else 2))
            if data_state == 'read_failure':
                assert '查询失败' in saved.content or '未完成' in saved.content
                assert all(receipt.startswith('Error:') for receipt in receipts)
            else:
                assert not calls[-1].get('tools')
                assert 'read_evidence' in calls[-1]['messages'][1]['content']
            assert (db.query(DietRecord).count(), db.query(GarminData).count()) == counts
            assert not any('Pi agent failed' in record.getMessage() for record in caplog.records)
            runs[variant] = dict(calls=calls, query=requests[0].arguments, receipts=receipts,
                                 saved=saved.content, outcome=done['turn_outcome'], completion=done['completion_status'])
    baseline = runs['baseline']
    for variant in ('p1', 'p2', 'combined'):
        candidate = runs[variant]
        assert candidate['query'] == baseline['query']
        assert candidate['receipts'] == baseline['receipts']
        assert candidate['saved'] == baseline['saved']
        assert candidate['outcome'] == baseline['outcome']
        assert candidate['completion'] == baseline['completion']
        if data_state != 'read_failure':
            assert candidate['calls'][-1]['messages'][1:] == baseline['calls'][-1]['messages'][1:]
        if data_state != 'read_failure':
            assert candidate['calls'][-1]['max_tokens'] == baseline['calls'][-1]['max_tokens']
    assert runs['p1']['calls'][0] == baseline['calls'][0]
    if data_state != 'read_failure':
        assert runs['p2']['calls'][-1] == baseline['calls'][-1]
        assert runs['combined']['calls'][-1] == runs['p1']['calls'][-1]
        assert len(runs['combined']['calls'][-1]['messages'][0]['content']) < len(baseline['calls'][-1]['messages'][0]['content'])
    else:
        # Exhausted full-scope failures terminate from the authoritative
        # receipts above. There is no model synthesis of failed evidence.
        assert [len(run['calls']) for run in runs.values()] == [1, 1, 0, 0]
        assert all(run['completion'] == 'error' for run in runs.values())
    if (directory := os.environ.get('REVA_COMPOSED_EXPERIMENT_PAYLOADS')) and data_state == 'available':
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        for variant in ('p1', 'p2', 'combined'):
            (target/f'{variant}.json').write_text(json.dumps([
                {'enabled': False, 'calls': baseline['calls']},
                {'enabled': True, 'calls': runs[variant]['calls']},
            ], ensure_ascii=False, indent=2)+'\n')
