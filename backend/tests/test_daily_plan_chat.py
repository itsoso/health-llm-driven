"""Daily-plan chat reads persisted owner/date snapshots without rebuilding."""
from dataclasses import replace
from datetime import date, datetime, timedelta
import re
from sqlalchemy import event
import pytest

from app.services.agent_kernel.types import AgentEnvelope, ExecutionContext, TurnSnapshot
from app.services.agent_kernel.intent_frame import build_intent_frame


def snapshot(text='给我今日计划'):
    envelope = AgentEnvelope(user_id=1, channel='typed', text=text)
    context = ExecutionContext(user_id=1, channel='typed', timezone='Asia/Shanghai',
        current_time=datetime.fromisoformat('2026-10-09T16:05:00+00:00'))
    return TurnSnapshot(envelope, context, build_intent_frame(envelope, context))


def test_today_is_bound_to_turn_owner_and_local_date():
    from app.services.daily_plan_chat import resolve_daily_plan_request
    assert resolve_daily_plan_request(snapshot()) == (1, date(2026, 10, 10))
    mismatched = replace(snapshot(), envelope=replace(snapshot().envelope, user_id=2))
    assert resolve_daily_plan_request(mismatched) is None


@pytest.mark.parametrize('text', ['不要给我今日计划', '他说“给我今日计划”', '给我老婆今日计划',
    '给我今日计划并保存', '给我今日计划，顺便查询所有病历', '给我明日计划',
    '生成并执行今日计划'])
def test_extra_authority_is_not_inferred(text):
    from app.services.daily_plan_chat import resolve_daily_plan_request
    assert resolve_daily_plan_request(snapshot(text)) is None


def add_plan(db, owner, day, title):
    from app.models.daily_operating_plan import DailyOperatingPlan
    from app.models.user import User
    if db.get(User, owner) is None:
        db.add(User(id=owner, name=f'Synthetic owner {owner}'))
        db.flush()
    row = DailyOperatingPlan(user_id=owner, plan_date=day, status='active',
        actions=[{'title': title, 'why': '已保存的行动理由', 'when': 'today'}])
    db.add(row)
    db.commit()
    return row.id


def test_snapshot_is_owner_date_scoped_and_does_not_write(db):
    from app.services.daily_plan_chat import read_daily_plan_snapshot, render_daily_plan_snapshot
    add_plan(db, 1, date(2026, 10, 9), '昨天的安排')
    add_plan(db, 2, date(2026, 10, 10), '另一人的安排')
    own_id = add_plan(db, 1, date(2026, 10, 10), '今晚提早准备休息')
    sql = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        sql.append(statement)
    event.listen(db.get_bind(), 'before_cursor_execute', capture)
    try:
        result = read_daily_plan_snapshot(db, 1, date(2026, 10, 10))
    finally:
        event.remove(db.get_bind(), 'before_cursor_execute', capture)
    assert result['id'] == own_id
    reply = render_daily_plan_snapshot(result)
    assert '今晚提早准备休息' in reply
    assert '昨天的安排' not in reply and '另一人的安排' not in reply
    assert '已保存' in reply and '未重新' in reply
    assert all(s.lstrip().upper().startswith('SELECT') for s in sql)


def test_missing_snapshot_is_not_no_actions_or_automatic_generation(db):
    from app.services.daily_plan_chat import read_daily_plan_snapshot, render_daily_plan_snapshot
    result = read_daily_plan_snapshot(db, 1, date(2026, 10, 10))
    assert result['found'] is False
    assert '没有已保存' in render_daily_plan_snapshot(result)


def test_database_failure_is_not_missing_snapshot():
    from unittest.mock import MagicMock
    from sqlalchemy.exc import SQLAlchemyError
    from app.services.daily_plan_chat import read_daily_plan_snapshot
    db = MagicMock()
    db.query.side_effect = SQLAlchemyError('synthetic')
    with pytest.raises(SQLAlchemyError):
        read_daily_plan_snapshot(db, 1, date(2026, 10, 10))

from tests.test_agent_coherence_pi_trajectories import (
    _isolate_twin_cache as _isolate_twin_cache,
    clock as clock, owned_data as owned_data, script_executor,
)


@pytest.mark.asyncio
@pytest.mark.parametrize('health_runtime', [False, True])
async def test_real_stream_returns_plan_and_persists_read_evidence_without_model(db, monkeypatch, owned_data, clock, health_runtime):
    from app.config import settings
    monkeypatch.setattr(settings, 'health_evidence_runtime_enabled', health_runtime)
    from app.models.agent_conversation import AgentMessage
    from uuid import uuid4
    plan_id = add_plan(db, owned_data.id, clock[0].date(), '今晚提早准备休息')
    trace = script_executor(db, monkeypatch, [])
    events = [e async for e in trace.executor.run_stream(
        owned_data.id, '给我今日计划', channel='typed', client_turn_id=str(uuid4()))]
    done = next(e['data'] for e in reversed(events) if e['event'] == 'done')
    saved = db.get(AgentMessage, done['message_id'])
    assert '今晚提早准备休息' in saved.content
    assert saved.meta['daily_plan_read']['id'] == plan_id
    assert done['write_receipts'] == []
    assert done['model_call_count'] == 0
    assert not trace.calls
    assert saved.meta['turn_outcome'] == done['turn_outcome']


@pytest.mark.asyncio
@pytest.mark.parametrize('fail', [False, True])
async def test_stream_missing_or_failed_is_honest(db, monkeypatch, owned_data, clock, fail):
    from sqlalchemy.exc import SQLAlchemyError
    from app.models.agent_conversation import AgentMessage
    from uuid import uuid4
    trace = script_executor(db, monkeypatch, [])
    if fail:
        def broken(*args):
            raise SQLAlchemyError('synthetic failure')
        monkeypatch.setattr('app.services.daily_plan_chat.read_daily_plan_snapshot', broken)
    events = [e async for e in trace.executor.run_stream(
        owned_data.id, '给我今日计划', channel='typed', client_turn_id=str(uuid4()))]
    done = next(e['data'] for e in reversed(events) if e['event'] == 'done')
    saved = db.get(AgentMessage, done['message_id'])
    assert ('读取失败' if fail else '没有已保存') in saved.content
    assert done['completion_status'] == ('error' if fail else 'complete')
    assert not done['write_receipts'] and not trace.calls
    if fail:
        assert done['daily_plan_read']['result_kind'] == 'read_error'
        assert '今日计划草稿' not in saved.content


@pytest.mark.asyncio
async def test_retry_replays_same_snapshot_answer_without_reading_again(db, monkeypatch, owned_data, clock):
    from uuid import uuid4
    add_plan(db, owned_data.id, clock[0].date(), '今晚提早准备休息')
    trace = script_executor(db, monkeypatch, [])
    turn_id = str(uuid4())
    async def consume():
        return [e async for e in trace.executor.run_stream(
            owned_data.id, '给我今日计划', channel='typed', client_turn_id=turn_id)]
    first = await consume()
    def forbidden(*args):
        raise AssertionError('replay must not query a changed snapshot')
    monkeypatch.setattr('app.services.daily_plan_chat.read_daily_plan_snapshot', forbidden)
    second = await consume()
    a = next(e['data'] for e in reversed(first) if e['event'] == 'done')
    b = next(e['data'] for e in reversed(second) if e['event'] == 'done')
    assert a['message_id'] == b['message_id']
    assert b['replayed'] is True

@pytest.mark.parametrize('status', ['cancelled', 'completed'])
def test_inactive_snapshot_is_not_an_execution_instruction(status):
    from app.services.daily_plan_chat import render_daily_plan_snapshot
    reply = render_daily_plan_snapshot({'found': True, 'plan_date': '2026-10-10',
        'status': status, 'actions': [{'title': '不应展示成待办'}]})
    assert '不处于执行状态' in reply
    assert '不应展示成待办' not in reply


@pytest.mark.parametrize('actions', [{}, [None], [{'why': 'missing title'}]])
def test_corrupt_snapshot_fails_instead_of_claiming_no_actions(actions):
    from app.services.daily_plan_chat import render_daily_plan_snapshot
    with pytest.raises(ValueError):
        render_daily_plan_snapshot({'found': True, 'plan_date': '2026-10-10',
            'status': 'active', 'actions': actions})

@pytest.mark.asyncio
async def test_failed_read_can_retry_same_turn_without_write_recovery(db, monkeypatch, owned_data, clock):
    from uuid import uuid4
    from sqlalchemy.exc import SQLAlchemyError
    import app.services.daily_plan_chat as service
    add_plan(db, owned_data.id, clock[0].date(), '今晚提早准备休息')
    trace = script_executor(db, monkeypatch, [])
    original = service.read_daily_plan_snapshot
    def broken(*args):
        raise SQLAlchemyError('synthetic failure')
    monkeypatch.setattr(service, 'read_daily_plan_snapshot', broken)
    turn_id = str(uuid4())
    async def consume():
        events = [e async for e in trace.executor.run_stream(
            owned_data.id, '给我今日计划', channel='typed', client_turn_id=turn_id)]
        return next(e['data'] for e in reversed(events) if e['event'] == 'done')
    first = await consume()
    assert first['completion_status'] == 'error'
    monkeypatch.setattr(service, 'read_daily_plan_snapshot', original)
    second = await consume()
    assert second['completion_status'] == 'complete'
    assert second['daily_plan_read']['found']
    assert not second['write_receipts']

@pytest.mark.parametrize('actions', [None, {}, [None]])
def test_database_snapshot_corruption_is_preserved_for_validation(db, actions):
    from app.models.daily_operating_plan import DailyOperatingPlan
    from app.services.daily_plan_chat import read_daily_plan_snapshot, render_daily_plan_snapshot
    plan_id = add_plan(db, 1, date(2026, 10, 10), 'synthetic action')
    row = db.get(DailyOperatingPlan, plan_id)
    row.actions = actions
    db.commit()
    result = read_daily_plan_snapshot(db, 1, date(2026, 10, 10))
    with pytest.raises(ValueError):
        render_daily_plan_snapshot(result)

@pytest.mark.parametrize('hour', [8, 20, 23])
def test_generic_draft_covers_remaining_day_without_personal_health_claims(hour):
    from app.services.daily_plan_chat import render_daily_plan_draft
    now = datetime.fromisoformat(f'2026-10-10T{hour:02}:30:00+08:00')
    reply = render_daily_plan_draft(now)
    assert '今日计划草稿（未保存）' in reply
    assert '2026-10-10' in reply
    assert '1.' in reply and '2.' in reply and '3.' in reply
    assert '不依据病史、用药或设备读数制定' in reply
    assert '未读取其他健康记录' not in reply
    assert '未做个性化健康评估' in reply
    assert '没有保存计划或创建提醒' in reply
    if hour >= 20:
        assert '早餐' not in reply and '午餐' not in reply
        assert '补做' in reply
    assert 'HRV' not in reply and '恢复良好' not in reply


@pytest.mark.asyncio
async def test_missing_plan_returns_unsaved_draft_and_replays_without_business_writes(db, monkeypatch, owned_data, clock):
    from uuid import uuid4
    from app.models.agent_conversation import AgentMessage
    trace = script_executor(db, monkeypatch, [])
    def forbidden(*args, **kwargs):
        raise AssertionError('chat draft must not build or materialize a plan')
    monkeypatch.setattr('app.services.daily_operating_plan.build_daily_operating_plan', forbidden)
    sql = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        sql.append(statement)
    turn_id = str(uuid4())
    async def consume():
        events = [e async for e in trace.executor.run_stream(
            owned_data.id, '给我今日计划', channel='typed', client_turn_id=turn_id)]
        return next(e['data'] for e in reversed(events) if e['event'] == 'done')
    event.listen(db.get_bind(), 'before_cursor_execute', capture)
    try:
        first = await consume()
    finally:
        event.remove(db.get_bind(), 'before_cursor_execute', capture)
    message = db.get(AgentMessage, first['message_id'])
    assert '今日计划草稿（未保存）' in message.content
    assert '1.' in message.content and '3.' in message.content
    assert first['daily_plan_read']['found'] is False
    assert first['daily_plan_read']['result_kind'] == 'generic_draft'
    assert first['model_call_count'] == 0 and not trace.calls
    assert not first['write_receipts']
    mutations = [s for s in sql if s.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE'))]
    targets = [re.match(r'\s*(?:INSERT INTO|UPDATE|DELETE FROM)\s+([\w]+)', s, re.I)
               for s in mutations]
    assert all(target is not None for target in targets), mutations
    assert {target.group(1) for target in targets} <= {'agent_conversations', 'agent_messages'}, mutations
    monkeypatch.setattr('app.services.daily_plan_chat.read_daily_plan_snapshot', forbidden)
    original_content = message.content
    clock[0] += timedelta(days=1)
    second = await consume()
    assert second['replayed'] and first['message_id'] == second['message_id']
    assert db.get(AgentMessage, second['message_id']).content == original_content
