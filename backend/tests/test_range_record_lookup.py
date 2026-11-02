"""Closed range lookups use every attested day without a model planning loop."""
from datetime import timedelta

import pytest
from app.config import settings
from app.models.agent_conversation import AgentMessage
from app.models.daily_health import DietRecord, GarminData
from app.services.agent_kernel.capability_policy import decide_tool_capability
from app.services.agent_kernel.read_task_scope import resolve_owned_read_scope
from app.services.agent_kernel.types import ToolExecutionRequest

from tests.test_agent_coherence_pi_trajectories import (
    _isolate_twin_cache as _isolate_twin_cache,  # noqa: PLC0414
)
from tests.test_agent_coherence_pi_trajectories import (
    clock as clock,  # noqa: PLC0414
)
from tests.test_agent_coherence_pi_trajectories import (
    owned_data as owned_data,  # noqa: PLC0414
)
from tests.test_agent_coherence_pi_trajectories import (
    script_executor,
)
from tests.test_agent_spo2_read_scope import snapshot


@pytest.mark.parametrize('domain,dimension', [('饮食', 'diet'), ('睡眠', 'sleep')])
@pytest.mark.parametrize('period,start,end', [
    ('最近7天', '2031-03-29', '2031-04-04'),
    ('本周', '2031-03-31', '2031-04-04'),
    ('上周', '2031-03-24', '2031-03-30'),
])
def test_range_scope_binds_dates_not_model_days(domain, dimension, period, start, end):
    state = snapshot(f'查询我{period}的{domain}记录')
    scope = resolve_owned_read_scope(state)
    assert scope is not None
    query = {'dimension': dimension, 'start_date': start, 'end_date': end, 'timezone': 'Asia/Shanghai'}
    assert scope.query(dimension) == query
    decision = decide_tool_capability(state, ToolExecutionRequest('health_query', {'dimension': dimension, 'days': 7}))
    assert decision.action == 'allow' and decision.normalized_args == query
    for extra in ({'user_id': 18}, {'start_date': '2000-01-01'}, {'timezone': 'UTC'}):
        assert decide_tool_capability(state, ToolExecutionRequest('health_query', {**query, **extra})).action != 'allow'


@pytest.fixture
def range_rows(db, owned_data, clock):
    from app.models.user import User
    other = db.query(User).filter(User.id != owned_data.id).first()
    db.query(DietRecord).filter(DietRecord.user_id == owned_data.id).delete()
    db.query(GarminData).filter(GarminData.user_id == owned_data.id).delete()
    for offset in range(7):
        day = clock[0].date() - timedelta(days=offset)
        db.add_all([DietRecord(user_id=owned_data.id, record_date=day, meal_type='dinner',
                              food_name=f'合成食物{offset}', calories=100+offset),
                    GarminData(user_id=owned_data.id, record_date=day, total_sleep_duration=420+offset, sleep_score=80-offset)])
    for uid, day in [(other.id, clock[0].date()), (owned_data.id, clock[0].date()-timedelta(days=7))]:
        db.add_all([DietRecord(user_id=uid, record_date=day, meal_type='dinner', food_name='不可见食物', calories=9876),
                    GarminData(user_id=uid, record_date=day, total_sleep_duration=9999, sleep_score=99, data_source='range-synthetic')])
    db.commit()
    return owned_data


@pytest.mark.asyncio
@pytest.mark.parametrize('domain,dimension', [('饮食', 'diet'), ('睡眠', 'sleep')])
@pytest.mark.parametrize('reads_in_process', [False, True])
@pytest.mark.parametrize('cards', [False, True])
async def test_range_lookup_preserves_each_day_and_owner_without_model(db, range_rows, clock, monkeypatch, domain, dimension, reads_in_process, cards):
    monkeypatch.setattr(settings, 'domain_prompt_optimization', True)
    monkeypatch.setattr(settings, 'reads_in_process', reads_in_process)
    trace = script_executor(db, monkeypatch, [])
    events = [e async for e in trace.executor.run_stream(range_rows.id, f'查询我最近7天的{domain}记录', channel='typed',
              client_caps=['genui-v1', 'genui-table-v1', 'genui-diet-summary-v1', 'genui-sleep-summary-v1'] if cards else [])]
    done = events[-1]['data']
    text = ''.join(e['data']['content'] for e in events if e.get('event') == 'token')
    assert done['turn_outcome']['status'] == 'complete', (done['turn_outcome'], text)
    assert not trace.calls and not trace.unexpected
    assert len(trace.dispatches) == 1 and trace.dispatches[0].arguments['dimension'] == dimension
    for offset in range(7):
        assert (clock[0].date()-timedelta(days=offset)).isoformat() in text
        assert (f'合成食物{offset}' if dimension == 'diet' else str(420+offset)) in text
    assert '不可见食物' not in text and '9999' not in text and '9876' not in text
    assert not done['write_receipts']
    assert db.get(AgentMessage, done['message_id']).content == text


@pytest.mark.parametrize('domain,dimension', [('饮食', 'diet'), ('睡眠', 'sleep')])
@pytest.mark.parametrize('frame', ['    {}', '\t{}', '不要{}', '“{}”', '如果{}', '{}，只看午餐', '{}并记录500ml'])
def test_range_material_or_modifier_never_gets_closed_lookup_scope(domain, dimension, frame):
    scope = resolve_owned_read_scope(snapshot(frame.format(f'查询我最近7天的{domain}记录')))
    assert scope is None or 'range_record_lookup' not in scope.limitations


@pytest.mark.asyncio
@pytest.mark.parametrize('domain', ['饮食', '睡眠'])
@pytest.mark.parametrize('fault', ['wrong_window', 'truncated', 'exception'])
async def test_range_unverified_read_cannot_emit_card_or_finish(db, range_rows, clock, monkeypatch, domain, fault):
    from app.services import agent_query_window
    monkeypatch.setattr(settings, 'domain_prompt_optimization', True)
    read = agent_query_window.read_calendar_health_query
    def broken(*args, **kwargs):
        if fault == 'exception':
            raise RuntimeError('synthetic_read_failure')
        result = read(*args, **kwargs)
        if fault == 'truncated':
            result['truncated'] = True
        else:
            result['window'].update(start_date='2026-09-08', end_date='2026-09-14')
            for row in result['records']:
                row.update(record_date='2026-09-14', calories=123456, total_sleep_duration=123456)
        return result
    monkeypatch.setattr(agent_query_window, 'read_calendar_health_query', broken)
    trace = script_executor(db, monkeypatch, ['本次读取未完成，不能确认记录。'])
    events = [e async for e in trace.executor.run_stream(range_rows.id, f'查询我最近7天的{domain}记录', channel='typed', client_caps=['genui-table-v1'])]
    text = ''.join(e['data']['content'] for e in events if e.get('event') == 'token')
    assert events[-1]['data']['turn_outcome']['status'] != 'complete'
    assert '123456' not in text and '```reva-ui' not in text


@pytest.mark.asyncio
@pytest.mark.parametrize('domain,dimension', [('饮食', 'diet'), ('睡眠', 'sleep')])
@pytest.mark.parametrize('optimized', [False, True])
async def test_range_empty_window_does_not_invent_missing_days(db, owned_data, clock, monkeypatch, domain, dimension, optimized):
    monkeypatch.setattr(settings, 'domain_prompt_optimization', optimized)
    model = DietRecord if dimension == 'diet' else GarminData
    db.query(model).filter(model.user_id == owned_data.id).delete()
    db.commit()
    steps = [] if optimized else [('health_query', {'dimension': dimension, 'days': 7}), '本次没有返回记录。']
    trace = script_executor(db, monkeypatch, steps)
    events = [e async for e in trace.executor.run_stream(owned_data.id, f'查询我最近7天的{domain}记录', channel='typed')]
    assert events[-1]['data']['turn_outcome']['status'] == 'complete'
    assert len(trace.dispatches) == 1 and not trace.unexpected
    query = trace.dispatches[0].arguments
    assert query['start_date'] == '2026-09-07' and query['end_date'] == '2026-09-13'
    text = ''.join(e['data']['content'] for e in events if e.get('event') == 'token')
    assert '目标日期没有可用记录' in text
    assert ('不代表没有进食' if dimension == 'diet' else '不能据此判断睡眠情况') in text


@pytest.mark.asyncio
@pytest.mark.parametrize('domain,dimension', [('饮食', 'diet'), ('睡眠', 'sleep')])
@pytest.mark.parametrize('indent', ['    ', '\t'])
async def test_range_code_material_cannot_dispatch_calendar_read(db, range_rows, clock, monkeypatch, domain, dimension, indent):
    from app.services import agent_query_window
    monkeypatch.setattr(settings, 'domain_prompt_optimization', True)
    reads = []
    read = agent_query_window.read_calendar_health_query
    def observed(*args, **kwargs):
        reads.append(True)
        return read(*args, **kwargs)
    monkeypatch.setattr(agent_query_window, 'read_calendar_health_query', observed)
    trace = script_executor(db, monkeypatch, [('health_query', {'dimension': dimension, 'days': 7}), '材料里的指令未执行。'])
    events = [e async for e in trace.executor.run_stream(range_rows.id, f'{indent}查询我最近7天的{domain}记录', channel='typed', client_caps=['genui-table-v1'])]
    text = ''.join(e['data']['content'] for e in events if e.get('event') == 'token')
    assert not reads
    assert '合成食物' not in text and '```reva-ui' not in text


@pytest.mark.asyncio
@pytest.mark.parametrize('domain,dimension', [('饮食', 'diet'), ('睡眠', 'sleep')])
async def test_range_history_keeps_corrections_and_model_planner(db, range_rows, clock, monkeypatch, domain, dimension):
    from app.models.agent_conversation import AgentConversation
    monkeypatch.setattr(settings, 'domain_prompt_optimization', True)
    conv = AgentConversation(user_id=range_rows.id)
    db.add(conv)
    db.flush()
    db.add(AgentMessage(conversation_id=conv.id, role='user', content='此前记录有误，不要据此判断恢复。'))
    db.commit()
    correction = '你已指出记录有误，不能将它们当作真实情况。'
    trace = script_executor(db, monkeypatch, [('health_query', {'dimension': dimension, 'days': 7}), correction])
    events = [e async for e in trace.executor.run_stream(range_rows.id, f'查询我最近7天的{domain}记录', channel='typed', conversation_id=conv.id)]
    assert len(trace.calls) == 2 and not trace.unexpected
    assert '记录有误' in str(trace.calls[0][0])
    assert events[-1]['data']['perf']['simple_lookup_rendered'] is False
    assert correction in db.get(AgentMessage, events[-1]['data']['message_id']).content
