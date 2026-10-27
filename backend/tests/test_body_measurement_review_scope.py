"""Body measurements product action: owned evidence, distinct date windows."""
from datetime import date
import json
from pathlib import Path

import pytest

from app.services.agent_kernel.capability_policy import decide_tool_capability
from app.services.agent_kernel.health_semantics import health_read_has_nonself_subject
from app.services.agent_kernel.read_task_scope import resolve_owned_read_scope
from app.services.agent_kernel.tool_gateway import ToolGateway
from app.services.agent_kernel.types import ToolExecutionRequest
from tests.test_sleep_calendar_owner_order import snapshot

REQUEST = '请基于我的体重和腰围记录，复盘趋势和代谢风险，结合今天饮食和运动给出调整建议。请说明我接下来还应该记录哪些数据。'
DIMENSIONS = ('weight', 'waist', 'diet', 'workout')


def expected(dimension):
    return {'dimension': dimension, 'start_date': '2026-09-27' if dimension in {'weight', 'waist'} else '2026-10-26',
            'end_date': '2026-10-26', 'timezone': 'Asia/Shanghai'}


@pytest.mark.parametrize('text', [REQUEST, REQUEST.replace('，', ', '), REQUEST.replace('我的', '本人的')])
def test_product_review_has_self_subject_and_bounded_queries(text):
    assert not health_read_has_nonself_subject(text)
    scope = resolve_owned_read_scope(snapshot(text))
    assert scope is not None
    assert scope.queries == tuple(expected(d) for d in DIMENSIONS)
    for d in DIMENSIONS:
        decision = decide_tool_capability(snapshot(text), ToolExecutionRequest('health_query', {'dimension': d}))
        assert decision.action == 'allow', decision.reason
        assert decision.normalized_args == expected(d)
    decision = decide_tool_capability(snapshot(text), ToolExecutionRequest('health_query_batch', {
        'queries': [{'dimension': d} for d in DIMENSIONS]}))
    assert decision.action == 'allow', decision.reason
    assert decision.normalized_args == {'queries': [expected(d) for d in DIMENSIONS]}


def test_mobile_product_prompt_stays_covered():
    import re
    source = (Path(__file__).resolve().parents[2] / 'mobile/app/body-measurements.tsx').read_text()
    prompt = re.search(r'prompt="([^"]*体重和腰围记录[^"]*)"', source).group(1)
    assert resolve_owned_read_scope(snapshot(prompt)) is not None


@pytest.mark.parametrize('text', [
    REQUEST.replace('我的', '张三的'), REQUEST.replace('我的', '我妈妈的'),
    REQUEST.replace('我的', '我和张三的'), REQUEST.replace('我的', '张三和我的'),
    REQUEST.replace('腰围记录', '张三的腰围记录'),
    REQUEST.replace('今天饮食', '今天张三的饮食'),
    '不要' + REQUEST, '如果需要，' + REQUEST, '解释例句：“' + REQUEST + '”',
    REQUEST + '再查询张三的睡眠。', REQUEST + '只看早餐。',
    REQUEST.replace('今天', '昨天'), REQUEST.replace('记录，', '记录，只看最近一年，'),
])
@pytest.mark.asyncio
async def test_modified_or_foreign_review_does_not_dispatch(text):
    calls = []
    async def dispatch(request):
        calls.append(request)
        return '{}'
    result = await ToolGateway(snapshot(text)).execute(ToolExecutionRequest('health_query_batch', {
        'queries': [{'dimension': d} for d in DIMENSIONS]}), dispatch)
    assert result.decision.action == 'block'
    assert not calls


@pytest.mark.parametrize('change', [
    {'user_id': 42}, {'owner_id': 42}, {'tenant_id': 42}, {'start_date': '2026-01-01'},
    {'end_date': '2026-10-27'}, {'timezone': 'UTC'}, {'dimension': 'sleep'},
    {'keyword': '张三'}, {'days': 365}, {'period': 'morning'},
])
@pytest.mark.parametrize('tool', ['health_query', 'health_query_batch'])
def test_model_cannot_expand_scope(change, tool):
    proposal = {**expected('weight'), **change}
    args = proposal if tool == 'health_query' else {'queries': [proposal]}
    assert decide_tool_capability(snapshot(REQUEST), ToolExecutionRequest(tool, args)).action == 'block'


def test_identity_and_write_boundary():
    assert decide_tool_capability(snapshot(REQUEST, envelope_owner=42), ToolExecutionRequest(
        'health_query', {'dimension': 'weight'})).action == 'block'
    for tool, args in [('health_record', {'record_type': 'weight', 'data': {'weight': 70}}),
                       ('health_manage', {'operation': 'list', 'record_type': 'waist'}),
                       ('health_analysis', {'analysis_type': 'comprehensive'})]:
        assert decide_tool_capability(snapshot(REQUEST), ToolExecutionRequest(tool, args)).action == 'block'


@pytest.mark.asyncio
async def test_gateway_executor_reads_owned_rows_and_keeps_no_data(db):
    from app.models.user import User
    from app.models.weight import WeightRecord
    from app.models.waist import WaistRecord
    from app.services.agent_executor import AgentExecutor
    users = [User(name=f'Synthetic {i}', email=f'body-review-{i}@example.test') for i in range(2)]
    db.add_all(users); db.flush()
    for model, values in [(WeightRecord, {'weight': 72.346}), (WaistRecord, {'waist_cm': 86.789})]:
        for uid, day in [(users[0].id, date(2026,9,27)), (users[0].id, date(2026,10,26)),
                         (users[0].id, date(2026,9,26)), (users[0].id, date(2026,10,27)),
                         (users[1].id, date(2026,10,1))]:
            db.add(model(user_id=uid, record_date=day, **values))
    db.flush()
    turn = snapshot(REQUEST, owner=users[0].id, envelope_owner=users[0].id)
    executor = AgentExecutor(db)
    executor._current_user_id = users[0].id
    executor._agent_kernel_snapshot = turn
    executor._current_turn_user_message = REQUEST
    async def dispatch(request):
        return await executor._exec_health_query_batch('', {}, request.arguments)
    result = await ToolGateway(turn).execute(ToolExecutionRequest('health_query_batch', {
        'queries': [{'dimension': d} for d in DIMENSIONS]}), dispatch)
    assert result.decision.action == 'allow', result.decision.reason
    payload = json.loads(result.content)
    assert payload['status'] == 'success'
    by_dim = {r['dimension']: r for r in payload['results']}
    for d in ('weight','waist'):
        assert [r['record_date'] for r in by_dim[d]['records']] == ['2026-09-27','2026-10-26']
        assert by_dim[d]['window'] == {k:v for k,v in expected(d).items() if k != 'dimension'}
    assert by_dim['weight']['records'][0]['weight'] == 72.346
    assert by_dim['waist']['records'][0]['waist_cm'] == 86.789
    for d in ('diet', 'workout'):
        assert by_dim[d]['records'] == []
        assert by_dim[d]['availability'] == 'no_data'
    assert db.query(WeightRecord).count() == db.query(WaistRecord).count() == 5


@pytest.mark.asyncio
@pytest.mark.parametrize('has_data', [True, False])
async def test_product_review_saved_reply(db, auth_user_and_headers, isolated_agent_protocol_transport, monkeypatch, has_data):
    from datetime import datetime
    from app.models.weight import WeightRecord
    from app.models.waist import WaistRecord
    from app.models.agent_conversation import AgentMessage
    from app.services.agent_executor import AgentExecutor
    from app.services.agent_kernel.types import ExecutionContext
    from app.twin.schema import HealthTwin, TwinMeta
    user, _ = auth_user_and_headers
    now = datetime.fromisoformat('2026-10-26T11:35:00+08:00')
    clock = ExecutionContext.now.__func__
    monkeypatch.setattr(ExecutionContext, 'now', classmethod(lambda cls, **kw: clock(cls, **{**kw, 'now_utc': now})))
    monkeypatch.setattr('app.twin.builder.build_twin', lambda _db, uid, **kw: HealthTwin(meta=TwinMeta(user_id=uid, generated_at=now)))
    if has_data:
        db.add(WeightRecord(user_id=user.id, record_date=now.date(), weight=72.346))
        db.add(WaistRecord(user_id=user.id, record_date=now.date(), waist_cm=86.789))
    db.commit()
    executor = AgentExecutor(db)
    dispatch = executor._dispatch_tool_request
    results = []
    count = 0
    async def provider(messages, tools):
        nonlocal count
        count += 1
        if count == 1:
            yield {'type':'tool_calls','tool_calls':[{'id':'body-review','type':'function','function':{
                'name':'health_query_batch','arguments':json.dumps({'queries':[{'dimension':d} for d in DIMENSIONS]})}}]}
            yield {'type':'finish','finish_reason':'tool_calls'}
        else:
            yield {'type':'content','text':'记录不足，暂不能判断趋势或代谢风险。建议后续保持同样条件测量，记录饮食和运动。'}
            yield {'type':'finish','finish_reason':'stop'}
    async def observe(request, token):
        result = await dispatch(request, token)
        results.append(json.loads(result))
        return result
    monkeypatch.setattr(executor, '_call_llm_stream', provider)
    monkeypatch.setattr(executor, '_dispatch_tool_request', observe)
    monkeypatch.setattr(executor, '_build_system_prompt', lambda *a, **k: '按证据回答。')
    monkeypatch.setattr(executor, '_build_system_knowledge_prompt_context', lambda *a, **k: '')
    events = [e async for e in executor.run_stream(user.id, REQUEST, client_turn_id=f'body-review-{has_data}')]
    done = next(e['data'] for e in reversed(events) if e.get('event') == 'done')
    saved = db.get(AgentMessage, done['message_id'])
    assert done['turn_outcome']['status'] == 'complete'
    assert not done.get('write_receipts')
    assert len(results) == 1
    assert '只能查询当前登录用户' not in saved.content
    assert '最近30天' in saved.content
    assert '今天' in saved.content
    if has_data:
        assert '72.35' in saved.content and '86.79' in saved.content
        assert '72.346' not in saved.content and '86.789' not in saved.content
    assert db.query(WeightRecord).count() == db.query(WaistRecord).count() == int(has_data)


@pytest.mark.parametrize('mode', ['enforce', 'shadow'])
@pytest.mark.asyncio
async def test_gateway_identity_rejection_never_dispatches_in_shadow(mode):
    from dataclasses import replace
    calls = []
    async def dispatch(request):
        calls.append(request)
        return '{}'
    turn = replace(snapshot(REQUEST, envelope_owner=42), policy_mode=mode)
    result = await ToolGateway(turn).execute(ToolExecutionRequest('health_query', {'dimension': 'waist'}), dispatch)
    assert result.decision.action == 'block'
    assert not calls


def test_today_uses_account_timezone_and_utc_boundary():
    from dataclasses import replace
    from datetime import datetime
    turn = snapshot(REQUEST)
    turn = replace(turn, context=replace(turn.context, current_time=datetime.fromisoformat('2026-10-26T17:30:00+00:00')))
    scope = resolve_owned_read_scope(turn)
    assert scope.query('weight')['start_date'] == '2026-09-28'
    assert scope.query('waist')['end_date'] == '2026-10-27'
    assert scope.query('diet')['start_date'] == scope.query('workout')['start_date'] == '2026-10-27'


def test_tool_schema_and_validator_expose_waist():
    from app.services.tool_schema_registry import HEALTH_TOOLS
    from app.services.llm.tool_validator import validate_tool_call
    schema = next(t['function'] for t in HEALTH_TOOLS if t['function']['name'] == 'health_query')
    assert 'waist' in schema['parameters']['properties']['dimension']['enum']
    result = validate_tool_call('health_query', expected('waist'))
    assert result["error"] is None, result
