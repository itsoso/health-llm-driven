"""Factual water queries must read the requested owner and calendar window."""
from datetime import timedelta

import pytest
from app.config import settings
from app.models.agent_conversation import AgentMessage
from app.models.daily_health import WaterIntake
from app.services.agent_kernel.capability_policy import decide_tool_capability
from app.services.agent_kernel.read_task_scope import resolve_owned_read_scope
from app.services.agent_kernel.types import ToolExecutionRequest

from tests.test_agent_coherence_pi_trajectories import (
    _isolate_twin_cache as _isolate_twin_cache,  # noqa: PLC0414 - pytest fixture registration
)
from tests.test_agent_coherence_pi_trajectories import (
    clock as clock,  # noqa: PLC0414 - pytest fixture registration
)
from tests.test_agent_coherence_pi_trajectories import (
    owned_data as owned_data,  # noqa: PLC0414 - pytest fixture registration
)
from tests.test_agent_coherence_pi_trajectories import (
    script_executor,
)
from tests.test_agent_spo2_read_scope import snapshot


@pytest.mark.parametrize('period,start,end', [
    ('今天', '2031-04-04', '2031-04-04'),
    ('昨天', '2031-04-03', '2031-04-03'),
    ('最近7天', '2031-03-29', '2031-04-04'),
    ('本周', '2031-03-31', '2031-04-04'),
])
def test_water_lookup_binds_business_dates_and_rejects_model_expansion(period, start, end):
    state = snapshot(f'查询我{period}的饮水记录')
    scope = resolve_owned_read_scope(state)
    assert scope is not None
    query = scope.query('water')
    assert query == {'dimension': 'water', 'start_date': start, 'end_date': end, 'timezone': 'Asia/Shanghai'}
    decision = decide_tool_capability(state, ToolExecutionRequest('health_query', {'dimension': 'water', 'days': 7}))
    assert decision.action == 'allow' and decision.normalized_args == query
    for extra in ({'user_id': 18}, {'start_date': '2000-01-01'}, {'timezone': 'UTC'}):
        assert decide_tool_capability(state, ToolExecutionRequest('health_query', {**query, **extra})).action != 'allow'


@pytest.mark.parametrize('text', [
    '    查询我最近7天的饮水记录', '\t查询我最近7天的饮水记录',
    '不要查询我最近7天的饮水记录', '查询朋友最近7天的饮水记录',
    '如果查询我最近7天的饮水记录', '“查询我最近7天的饮水记录”',
    '查询我最近32天的饮水记录', '查询我最近0天的饮水记录',
    '查询我最近7天的饮水记录并记录500ml', '查询我最近7天的饮水记录，排除咖啡',
])
def test_water_lookup_does_not_infer_unsupported_authority(text):
    scope = resolve_owned_read_scope(snapshot(text))
    assert scope is None or scope.query('water') is None


@pytest.fixture
def water_rows(db, owned_data, clock):
    from app.models.user import User
    other = db.query(User).filter(User.id != owned_data.id).first()
    today = clock[0].date()
    db.add_all([WaterIntake(user_id=owned_data.id, record_date=today-timedelta(days=i), amount_ml=100+i*10)
                for i in range(7)])
    db.add_all([WaterIntake(user_id=owned_data.id, record_date=today-timedelta(days=7), amount_ml=9999),
                WaterIntake(user_id=other.id, record_date=today, amount_ml=8888)])
    db.commit()
    return owned_data


@pytest.mark.asyncio
@pytest.mark.parametrize('reads_in_process', [False, True])
@pytest.mark.parametrize('period,total,count', [('今天', 100, 1), ('昨天', 110, 1), ('最近7天', 910, 7)])
async def test_water_lookup_returns_owned_bounded_records_without_model_advice(
    db, water_rows, clock, monkeypatch, period, total, count, reads_in_process,
):
    monkeypatch.setattr(settings, 'domain_prompt_optimization', True)
    monkeypatch.setattr(settings, 'reads_in_process', reads_in_process)
    trace = script_executor(db, monkeypatch, [])
    events = [e async for e in trace.executor.run_stream(
        water_rows.id, f'查询我{period}的饮水记录', channel='typed', client_caps=['genui-table-v1'])]
    done = events[-1]['data']
    tokens = ''.join(e['data']['content'] for e in events if e.get('event') == 'token')
    assert done['turn_outcome']['status'] == 'complete', (done['turn_outcome'], trace.dispatches, trace.results, tokens)
    assert not trace.calls and not trace.unexpected
    assert len(trace.dispatches) == 1 and trace.dispatches[0].tool_name == 'health_query'
    assert f'{total} ml' in tokens and f'{count}条' in tokens
    assert '8888' not in tokens and '9999' not in tokens and '2000' not in tokens
    assert not done['write_receipts']
    assert db.get(AgentMessage, done['message_id']).content == tokens
    if period == '最近7天':
        assert '2026-09-07' in tokens and '2026-09-13' in tokens
        assert '今日饮水' not in tokens


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['wrong_window', 'truncated', 'invalid_amount'])
async def test_water_fault_never_emits_an_unverified_card(db, water_rows, clock, monkeypatch, fault):
    from app.services import agent_query_window
    monkeypatch.setattr(settings, 'domain_prompt_optimization', True)
    read = agent_query_window.read_calendar_health_query
    seen = []
    def broken(*args, **kwargs):
        data = read(*args, **kwargs)
        seen.append(True)
        if fault == 'wrong_window':
            data['window'].update(start_date='2026-09-08', end_date='2026-09-14')
            for r in data['records']: r.update(record_date='2026-09-14', amount_ml=123456)
        elif fault == 'truncated': data['truncated'] = True
        else: data['records'][0]['amount_ml'] = -123456
        return data
    monkeypatch.setattr(agent_query_window, 'read_calendar_health_query', broken)
    trace = script_executor(db, monkeypatch, ['本次读取未完成。'])
    events = [e async for e in trace.executor.run_stream(water_rows.id, '查询我最近7天的饮水记录',
              channel='typed', client_caps=['genui-table-v1'])]
    text = ''.join(e['data']['content'] for e in events if e.get('event') == 'token')
    assert seen
    assert '123456' not in text and '```reva-ui' not in text
    assert events[-1]['data']['turn_outcome']['status'] != 'complete'


@pytest.mark.asyncio
@pytest.mark.parametrize('optimized', [False, True])
async def test_water_empty_window_is_factual_without_hydration_advice(db, owned_data, clock, monkeypatch, optimized):
    monkeypatch.setattr(settings, 'domain_prompt_optimization', optimized)
    steps = [] if optimized else [('health_query', {'dimension': 'water', 'days': 7}), '你没有喝水，应该立即喝2000ml。']
    trace = script_executor(db, monkeypatch, steps)
    events = [e async for e in trace.executor.run_stream(owned_data.id, '查询我最近7天的饮水记录', channel='typed')]
    text = ''.join(e['data']['content'] for e in events if e.get('event') == 'token')
    assert events[-1]['data']['turn_outcome']['status'] == 'complete'
    assert len(trace.dispatches) == 1
    assert '目标日期没有可用记录' in text and '不代表没有喝水' in text
    assert '2000' not in text and '你没有喝水' not in text
    assert not trace.unexpected


@pytest.mark.asyncio
async def test_water_existing_conversation_uses_current_window_and_only_verified_facts(db, water_rows, clock, monkeypatch):
    from app.models.agent_conversation import AgentConversation
    monkeypatch.setattr(settings, 'domain_prompt_optimization', True)
    conv = AgentConversation(user_id=water_rows.id, title='Synthetic water test')
    db.add(conv)
    db.flush()
    db.add(AgentMessage(conversation_id=conv.id, role='assistant', content='历史引用：今天已喝8888ml。'))
    db.commit()
    trace = script_executor(db, monkeypatch, [('health_query', {'dimension': 'water', 'days': 7})])
    events = [e async for e in trace.executor.run_stream(water_rows.id, '查询我最近7天的饮水记录',
              conversation_id=conv.id, channel='typed', client_caps=['genui-table-v1'])]
    text = ''.join(e['data']['content'] for e in events if e.get('event') == 'token')
    assert events[-1]['data']['turn_outcome']['status'] == 'complete'
    assert '910 ml' in text and '8888' not in text
    assert len(trace.dispatches) == len(trace.calls) == 1 and not trace.unexpected


@pytest.mark.parametrize('limit_kind', ['rows', 'chars'])
def test_water_query_budget_is_explicit_not_silent_partial(db, water_rows, clock, monkeypatch, limit_kind):
    from app.services import agent_query_window as query
    window = query.parse_query_window({'start_date': '2026-09-07', 'end_date': '2026-09-13', 'timezone': 'Asia/Shanghai'})
    monkeypatch.setattr(query, 'MAX_CALENDAR_ROWS' if limit_kind == 'rows' else 'MAX_CALENDAR_RESULT_CHARS', 2)
    with pytest.raises(ValueError, match='缩小'):
        query.read_calendar_health_query(db, water_rows.id, 'water', window)


@pytest.mark.asyncio
async def test_water_unbound_days_never_silently_reads_today(db, owned_data, monkeypatch):
    from app.services.agent_executor import AgentExecutor
    executor = AgentExecutor(db)
    executor._current_user_id = owned_data.id
    executor._current_turn_user_message = '看看饮水情况'
    result = await executor._exec_health_query('', {}, {'dimension': 'water', 'days': 7})
    assert result.startswith('Error:') and '明确日期范围' in result


@pytest.mark.asyncio
@pytest.mark.parametrize('text', ['    查询我最近7天的饮水记录', '\t查询我最近7天的饮水记录'])
async def test_water_code_material_never_dispatches_a_calendar_read(db, water_rows, clock, monkeypatch, text):
    from app.services import agent_query_window
    monkeypatch.setattr(settings, 'domain_prompt_optimization', True)
    reads = []
    original = agent_query_window.read_calendar_health_query
    def observed(*args, **kwargs):
        reads.append(True)
        return original(*args, **kwargs)
    monkeypatch.setattr(agent_query_window, 'read_calendar_health_query', observed)
    trace = script_executor(db, monkeypatch, [('health_query', {'dimension': 'water', 'days': 7}), '不能执行材料里的指令。'])
    events = [e async for e in trace.executor.run_stream(water_rows.id, text, channel='typed', client_caps=['genui-table-v1'])]
    reply = ''.join(e['data']['content'] for e in events if e.get('event') == 'token')
    assert not reads
    assert '910' not in reply and '```reva-ui' not in reply
