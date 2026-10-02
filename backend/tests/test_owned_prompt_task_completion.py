"""Synthetic production-shaped requests exercise the authenticated read boundary."""
import json

import pytest

from app.services.agent_kernel.tool_gateway import ToolGateway
from app.services.agent_kernel.types import ToolExecutionRequest
from tests.test_longitudinal_read_scope_policy import snapshot, decide
from tests.test_agent_coherence_pi_trajectories import (
    _isolate_twin_cache as _isolate_twin_cache, clock as clock, owned_data as owned_data,
)

INSIGHT = '给我一些建议，洞察我最近三周的睡眠 运动 补剂 饮食等数据'
PLAN = '基于我的检查报告帮我规划运动'


@pytest.mark.parametrize('text,dimension', [(INSIGHT, 'sleep'), (PLAN, 'medical_exam')])
def test_clear_self_request_uses_authenticated_scope(text, dimension):
    turn = snapshot(text)
    assert turn.context.user_id == turn.envelope.user_id == 41
    result = decide({'dimension': dimension}, text)
    assert result.action == 'allow', result.reason
    if dimension == 'sleep':
        assert result.normalized_args == {'dimension': 'sleep', 'days': 21,
            'start_date': '2026-08-24', 'end_date': '2026-09-13', 'timezone': 'Asia/Shanghai'}
    else:
        assert result.normalized_args == {'dimension': 'medical_exam'}


@pytest.mark.parametrize('text,dimension', [(INSIGHT, 'sleep'), (PLAN, 'medical_exam')])
@pytest.mark.parametrize('mutate', [
    lambda s: s.replace('我最近', '张三最近').replace('我的检查', '张三的检查'),
    lambda s: s.replace('我最近', '我朋友最近').replace('我的检查', '我朋友的检查'),
    lambda s: '不要' + s,
    lambda s: '假如' + s,
    lambda s: '解释例句：“' + s + '”',
    lambda s: s + '，只看检查之后',
])
async def test_unknown_owners_cancelled_quoted_and_restricted_reads_never_dispatch(text, dimension, mutate):
    calls = []
    async def dispatch(request):
        calls.append(request)
        return '{}'
    result = await ToolGateway(snapshot(mutate(text))).execute(
        ToolExecutionRequest('health_query', {'dimension': dimension}), dispatch)
    assert result.decision.action == 'block'
    assert not calls


@pytest.mark.parametrize('text,dimension', [(INSIGHT, 'sleep'), (PLAN, 'medical_exam')])
@pytest.mark.parametrize('extra', [{'user_id': 42}, {'owner_id': 41}, {'tenant_id': 42},
                                 {'days': 30}, {'start_date': '2020-01-01'}])
def test_model_cannot_supply_owner_or_expand_requested_dates(text, dimension, extra):
    assert decide({'dimension': dimension, **extra}, text).action == 'block'


@pytest.mark.parametrize('text', [INSIGHT, PLAN])
def test_scope_does_not_grant_unrequested_data_or_writes(text):
    assert decide({'dimension': 'genetic'}, text).action == 'block'
    assert decide({'record_type': 'weight', 'data': {'weight': 70}}, text, tool='health_record').action == 'block'


@pytest.mark.parametrize('text,queries', [
    (INSIGHT, [{'dimension': d} for d in ('diet', 'sleep', 'workout', 'supplements')]),
    (PLAN, [{'dimension': 'medical_exam'}]),
])
async def test_stream_executes_real_owned_adapter_and_persists_read_evidence(db, monkeypatch, owned_data, clock, text, queries):
    from tests.test_agent_read_repair_round_budget import batch_trace, consume, ANSWER
    trace = batch_trace(db, monkeypatch, [[('health_query_batch', {'queries': queries})], ANSWER])
    done, saved = await consume(db, trace, owned_data, query=text)
    assert len(trace.dispatches) == 1, (done, saved.content)
    actual = trace.dispatches[0].arguments['queries']
    assert {q['dimension'] for q in actual} == {q['dimension'] for q in queries}
    assert done['turn_outcome']['status'] == 'complete', done['turn_outcome']
    if text == INSIGHT:
        payload = json.loads(trace.results[0][1])
        sleep = next(row for row in payload['results'] if row['dimension'] == 'sleep')
        assert [row['sleep_score'] for row in sleep['records']] == [80]
        assert all(query['start_date'] == '2026-08-24' and query['end_date'] == '2026-09-13'
                   for query in actual)
