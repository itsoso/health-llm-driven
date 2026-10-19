"""Synthetic spoken intake questions must read only owned, recorded events."""
from dataclasses import replace

import pytest

from app.services.agent_kernel.capability_policy import decide_tool_capability
from app.services.agent_kernel.health_semantics import health_read_has_nonself_subject
from app.services.agent_kernel.read_task_scope import resolve_owned_read_scope
from app.services.agent_kernel.types import ToolExecutionRequest
from tests.test_recent_workout_read_regression import snapshot


@pytest.mark.parametrize('text', [
    '今天吃了什么样的补剂？', '我今天吃了什么补剂', '今天我服用了哪些补剂？',
    '昨天吃过啥补剂？', '本人昨日服用过什么营养补充剂？',
])
def test_spoken_question_binds_owned_calendar_intakes(text):
    turn = snapshot(text)
    assert not health_read_has_nonself_subject(text)
    scope = resolve_owned_read_scope(turn)
    day = '2026-10-09' if '昨' in text else '2026-10-10'
    expected = {'dimension': 'supplements', 'start_date': day,
                'end_date': day, 'timezone': 'Asia/Shanghai'}
    assert scope is not None
    assert scope.query('supplements') == expected
    for tool, args in [('health_query', {'dimension': 'supplements'}),
                       ('health_query_batch', {'queries': [{'dimension': 'supplements'}]})]:
        decision = decide_tool_capability(turn, ToolExecutionRequest(tool, args))
        assert decision.action == 'allow', decision.reason
        assert decision.normalized_args == (expected if tool == 'health_query' else {'queries': [expected]})


@pytest.mark.parametrize('text', [
    '妈妈今天吃了什么样的补剂？', '张三今天吃了什么补剂？',
    '我今天应该吃什么补剂？', '明天吃什么补剂？', '不要查询今天吃了什么补剂',
    '假如今天吃了什么补剂', '“今天吃了什么补剂”',
    '今天吃了什么补剂？再查询妈妈的睡眠', '今天吃了什么补剂？删除记录',
    '今天早上吃了什么补剂？', '今天吃了什么补剂，只看营养素甲',
])
def test_unconsumed_question_cannot_grant_daily_scope(text):
    assert decide_tool_capability(snapshot(text), ToolExecutionRequest(
        'health_query', {'dimension': 'supplements'})).action == 'block'


@pytest.mark.parametrize('args', [
    {'dimension': 'diet'}, {'dimension': 'supplements', 'user_id': 99},
    {'dimension': 'supplements', 'start_date': '2020-01-01'},
    {'dimension': 'supplements', 'days': 30},
    {'dimension': 'supplements', 'supplement_name': 'Synthetic A'},
])
async def test_model_cannot_expand_question_through_gateway(args):
    from app.services.agent_kernel.tool_gateway import ToolGateway
    calls = []
    async def dispatch(request):
        calls.append(request)
        return '{}'
    for mode in ('enforce', 'shadow'):
        result = await ToolGateway(replace(snapshot('今天吃了什么样的补剂？'), policy_mode=mode)).execute(
            ToolExecutionRequest('health_query', args), dispatch)
        assert result.decision.action == 'block'
    assert not calls


@pytest.mark.parametrize('zone,day', [('Asia/Shanghai', '2026-10-10'), ('America/Los_Angeles', '2026-10-09')])
def test_spoken_question_uses_authenticated_timezone(zone, day):
    turn = snapshot('今天吃了什么样的补剂？')
    turn = replace(turn, context=replace(turn.context, timezone=zone))
    assert resolve_owned_read_scope(turn).query('supplements')['start_date'] == day


@pytest.mark.parametrize('owner', [None, True, -1, 99])
def test_identity_mismatch_never_authorizes_question(owner):
    turn = snapshot('今天吃了什么样的补剂？')
    turn = replace(turn, context=replace(turn.context, user_id=owner))
    assert resolve_owned_read_scope(turn) is None
    assert decide_tool_capability(turn, ToolExecutionRequest(
        'health_query', {'dimension': 'supplements'})).action == 'block'


@pytest.mark.parametrize('panel', [False, True])
async def test_spoken_question_reads_real_owned_intakes_and_persists_answer(
    db, auth_user_and_headers, monkeypatch, isolated_agent_protocol_transport, panel,
):
    from datetime import timedelta
    import json
    from app.models.daily_health import SupplementIntake
    from app.models.supplement import SupplementDefinition, SupplementRecord
    from app.utils.timezone import get_china_today
    from tests.conftest import create_authenticated_user
    from tests.test_agent_read_repair_round_budget import batch_trace, consume
    user, _ = auth_user_and_headers
    other, _ = create_authenticated_user(db)
    today = get_china_today()
    definition = SupplementDefinition(user_id=user.id, name='Synthetic recorded', is_active=True)
    foreign = SupplementDefinition(user_id=other.id, name='Synthetic foreign', is_active=True)
    skipped = SupplementDefinition(user_id=user.id, name='Synthetic not taken', is_active=True)
    planned = SupplementDefinition(user_id=user.id, name='Synthetic plan only', is_active=True)
    db.add_all([definition, foreign, skipped, planned])
    db.flush()
    db.add_all([
        SupplementIntake(user_id=user.id, record_date=today, supplement_name='Synthetic intake', dosage=1.2345, unit='unit'),
        SupplementIntake(user_id=user.id, record_date=today - timedelta(days=1), supplement_name='Synthetic yesterday'),
        SupplementIntake(user_id=other.id, record_date=today, supplement_name='Synthetic other'),
        SupplementRecord(user_id=user.id, supplement_id=definition.id, record_date=today, taken=True),
        SupplementRecord(user_id=user.id, supplement_id=foreign.id, record_date=today, taken=True),
        SupplementRecord(user_id=user.id, supplement_id=skipped.id, record_date=today, taken=False),
    ])
    db.commit()
    answer = '本轮依据实际查到的记录回答，未覆盖的信息仍然未知。'
    trace = batch_trace(db, monkeypatch, [[('health_query', {'dimension': 'supplements'})], answer])
    done, saved = await consume(db, trace, user, panel=panel, query='今天吃了什么样的补剂？')
    assert done['completion_status'] == done['turn_outcome']['status'] == 'complete'
    assert len(trace.dispatches) == 1
    request = trace.dispatches[0]
    assert request.arguments == {'dimension': 'supplements', 'start_date': today.isoformat(),
                                 'end_date': today.isoformat(), 'timezone': 'Asia/Shanghai'}
    result = trace.results[0][1]
    payload = json.loads(result) if isinstance(result, str) else result
    assert {r['supplement_name'] for r in payload['records']} == {'Synthetic intake', 'Synthetic recorded'}
    assert '只能查询当前登录用户' not in saved.content
    assert not done['write_receipts']


@pytest.mark.parametrize('panel', [False, True])
async def test_prose_cannot_skip_actual_supplement_read(
    db, auth_user_and_headers, monkeypatch, isolated_agent_protocol_transport, panel,
):
    from tests.test_agent_read_repair_round_budget import batch_trace, consume
    user, _ = auth_user_and_headers
    trace = batch_trace(db, monkeypatch, [
        '沿用以前的背景，我已经知道今天服用情况。',
        '没有执行本轮查询，无法回答。',
        '没有执行本轮查询，无法回答。',
    ])
    done, saved = await consume(db, trace, user, panel=panel, query='今天吃了什么样的补剂？')
    assert done['turn_outcome']['status'] != 'complete'
    assert not trace.dispatches
    assert '沿用以前的背景' not in saved.content
