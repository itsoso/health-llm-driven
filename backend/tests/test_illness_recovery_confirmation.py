"""Collective replies continue only a bounded, reviewed illness recovery plan."""
from datetime import datetime, date, timedelta, timezone
import pytest

NOW = datetime(2026, 10, 26, 6, 0, tzinfo=timezone.utc)


def seed(db, user):
    from app.models.agent_conversation import AgentConversation, AgentMessage
    from app.models.illness import IllnessEpisode
    from app.models.user import User
    other = User(name='Synthetic other', email='recovery-other@example.test')
    db.add(other)
    db.flush()
    rows = [IllnessEpisode(user_id=user.id, name='合成病症甲', start_date=date(2026, 10, 20), status='active'),
            IllnessEpisode(user_id=user.id, name='合成病症乙', start_date=date(2026, 10, 22), status='improving'),
            IllnessEpisode(user_id=user.id, name='其他病症', start_date=date(2026, 10, 23), status='active'),
            IllnessEpisode(user_id=other.id, name='合成病症甲', start_date=date(2026, 10, 20), status='active')]
    db.add_all(rows)
    conv = AgentConversation(user_id=user.id, title='synthetic recovery')
    db.add(conv)
    db.flush()
    db.add(AgentMessage(conversation_id=conv.id, role='user', content='请更新我的病症状态'))
    db.add(AgentMessage(conversation_id=conv.id, role='assistant', content=(
        '尚未写入，请确认：\n1. **合成病症甲** — 起病 2026-10-20\n'
        '2. **合成病症乙** — 起病 2026-10-22\n两条都好了？痊愈日期是哪天？'),
        meta={'tools_used': ['health_manage'], 'client_turn_finalized': True}, created_at=NOW.replace(tzinfo=None)))
    db.commit()
    return conv, rows


def turn(db, user, conv, text, now=NOW, blocked=None):
    from app.models.agent_conversation import AgentMessage
    from app.services.illness_recovery_confirmation import resolve_turn
    source = AgentMessage(conversation_id=conv.id, role='user', content=text, created_at=now.replace(tzinfo=None))
    db.add(source)
    db.commit()
    result = resolve_turn(db, user_id=user.id, source_message_id=source.id, reference_now=now,
                          timezone_name='Asia/Shanghai', runtime_write_block_reason=blocked)
    if result is not None:
        db.add(AgentMessage(conversation_id=conv.id, role='assistant', content=result['reply'],
                           meta={**result.get('meta', {}), 'client_turn_finalized': True},
                           created_at=now.replace(tzinfo=None)))
        db.commit()
    return result


def test_collective_reply_asks_only_missing_date_then_atomically_confirms(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    conv, rows = seed(db, user)
    selected = turn(db, user, conv, '都好了')
    assert selected['status'] == 'clarification'
    assert '日期' in selected['reply'] and '没有授权' not in selected['reply']
    assert all(r.status != 'resolved' for r in rows)
    preview = turn(db, user, conv, '今天')
    assert preview['status'] == 'pending'
    assert '2026-10-26' in preview['reply']
    done = turn(db, user, conv, '确认')
    assert done['status'] == 'verified'
    assert len(done['write_receipts']) == 2
    for row in rows:
        db.refresh(row)
    assert [(r.status, r.end_date) for r in rows[:2]] == [('resolved', date(2026, 10, 26))] * 2
    assert rows[2].status == rows[3].status == 'active'
    from app.services.illness_recovery_confirmation import confirm
    replay = confirm(db, user.id, preview['meta']['illness_recovery_intent_id'], reference_now=NOW)
    assert replay['idempotent'] and replay['write_receipts'] == done['write_receipts']


@pytest.mark.parametrize('text', ['都快好了', '都好了吗？', '可能都好了', '他说都好了', '“都好了”',
                                  '都好了，不要记录', '我妈妈都好了', '都好了，停药吧'])
def test_non_authorizing_reply_never_creates_plan(db, auth_user_and_headers, text):
    from app.models.write_intent import WriteIntent
    user, _ = auth_user_and_headers
    conv, rows = seed(db, user)
    assert turn(db, user, conv, text) is None
    assert db.query(WriteIntent).count() == 0
    assert all(r.status != 'resolved' for r in rows)


@pytest.mark.parametrize('change', ['owner', 'duplicate', 'changed', 'expired', 'intervening', 'unsigned', 'no_context'])
def test_context_cannot_expand_or_reuse_stale_selection(db, auth_user_and_headers, change):
    from app.models.agent_conversation import AgentMessage
    from app.models.illness import IllnessEpisode
    from app.models.write_intent import WriteIntent
    user, _ = auth_user_and_headers
    conv, rows = seed(db, user)
    if change == 'owner':
        rows[1].user_id = rows[3].user_id
    elif change == 'duplicate':
        db.add(IllnessEpisode(user_id=user.id, name=rows[0].name, start_date=rows[0].start_date, status='active'))
    elif change == 'no_context':
        db.query(AgentMessage).filter_by(conversation_id=conv.id).delete()
    db.commit()
    first = turn(db, user, conv, '都好了')
    if change in {'owner', 'duplicate', 'no_context'}:
        assert first['status'] == 'clarification' and not first.get('meta')
        return
    if change == 'changed':
        rows[0].notes = 'changed after selection'
    elif change == 'unsigned':
        answer = db.query(AgentMessage).order_by(AgentMessage.id.desc()).first()
        meta = dict(answer.meta)
        selection = dict(meta['illness_recovery_selection'])
        selection['items'] = [*selection['items'], {'id': rows[2].id}]
        meta['illness_recovery_selection'] = selection
        answer.meta = meta
    elif change == 'intervening':
        db.add(AgentMessage(conversation_id=conv.id, role='assistant', content='其他话题'))
    db.commit()
    result = turn(db, user, conv, '今天', now=NOW + timedelta(hours=1) if change == 'expired' else NOW)
    assert result is None or result['status'] == 'clarification'
    assert db.query(WriteIntent).count() == 0
    assert all(r.status != 'resolved' for r in rows)


@pytest.mark.parametrize('date_text', ['明天', '2026-02-30', '2026-10-01'])
def test_invalid_or_before_onset_date_never_prepares_write(db, auth_user_and_headers, date_text):
    from app.models.write_intent import WriteIntent
    user, _ = auth_user_and_headers
    conv, _ = seed(db, user)
    turn(db, user, conv, '都好了')
    result = turn(db, user, conv, date_text)
    assert result['status'] == 'clarification'
    assert db.query(WriteIntent).count() == 0


def test_changed_record_prevents_whole_batch_and_runtime_pause_prevents_write(db, auth_user_and_headers):
    from app.services.illness_recovery_confirmation import confirm, RecoveryConflict
    user, _ = auth_user_and_headers
    conv, rows = seed(db, user)
    turn(db, user, conv, '都好了')
    preview = turn(db, user, conv, '昨天')
    assert turn(db, user, conv, '确认', blocked='paused')['status'] == 'error'
    rows[1].severity = 4
    db.commit()
    with pytest.raises(RecoveryConflict):
        confirm(db, user.id, preview['meta']['illness_recovery_intent_id'], reference_now=NOW)
    db.expire_all()
    assert rows[0].status == 'active' and rows[1].status == 'improving'


@pytest.mark.asyncio
async def test_stream_continuation_saves_receipts_without_model_inventing_authority(
    db, auth_user_and_headers, isolated_agent_protocol_transport, monkeypatch,
):
    from app.services.agent_executor import AgentExecutor
    from app.services.agent_kernel.types import ExecutionContext
    from app.models.agent_conversation import AgentMessage
    user, _ = auth_user_and_headers
    conv, rows = seed(db, user)
    original_clock = ExecutionContext.now.__func__
    monkeypatch.setattr(ExecutionContext, 'now', classmethod(
        lambda cls, **kw: original_clock(cls, **{**kw, 'now_utc': NOW})))

    async def no_model(*args, **kwargs):
        pytest.fail('Bounded confirmation must not ask the model to select records')
        yield

    for index, text in enumerate(['都好了', '今天', '确认']):
        executor = AgentExecutor(db)
        monkeypatch.setattr(executor, '_call_llm_stream', no_model)
        events = [event async for event in executor.run_stream(
            user.id, text, conversation_id=conv.id, client_turn_id=f'recovery-continuation-{index}')]
        done = next(e['data'] for e in reversed(events) if e.get('event') == 'done')
        saved = db.get(AgentMessage, done['message_id'])
        assert saved.meta['mode'] == 'illness_recovery_confirmation'
        assert '没有授权' not in saved.content
        if index < 2:
            assert done['turn_outcome']['status'] == 'waiting_for_user'
            assert not done['write_receipts']
        else:
            assert len(done['write_receipts']) == 2
            assert saved.meta['write_receipts'] == done['write_receipts']
    for row in rows:
        db.refresh(row)
    assert rows[0].status == rows[1].status == 'resolved'
    assert rows[2].status == rows[3].status == 'active'


@pytest.mark.parametrize('boundary', ['unpresented', 'foreign_owner', 'auto', 'expired', 'tampered', 'runtime'])
def test_confirmation_boundaries_fail_closed(db, auth_user_and_headers, monkeypatch, boundary):
    from app.models.agent_conversation import AgentMessage
    from app.models.write_intent import WriteIntent
    from app.services import illness_recovery_confirmation as recovery, write_intent_service
    user, _ = auth_user_and_headers
    conv, rows = seed(db, user)
    turn(db, user, conv, '都好了')
    preview = turn(db, user, conv, '今天')
    intent_id = preview['meta']['illness_recovery_intent_id']
    if boundary == 'unpresented':
        db.query(AgentMessage).filter_by(role='assistant', content=preview['reply']).delete()
    elif boundary == 'tampered':
        wi = db.get(WriteIntent, intent_id)
        wi.payload = {**wi.payload, 'plan': {**wi.payload['plan'], 'end_date': '2026-10-25'}}
    elif boundary == 'runtime':
        def paused(*args):
            raise recovery.RecoveryConflict('runtime_write_blocked')
        monkeypatch.setattr(recovery, '_lock_runtime_admission', paused)
    db.commit()
    with pytest.raises((recovery.RecoveryConflict, LookupError, ValueError)):
        if boundary == 'auto':
            write_intent_service.confirm(db, user.id, intent_id, trust_tier='auto')
        else:
            recovery.confirm(db, user.id + 999 if boundary == 'foreign_owner' else user.id, intent_id,
                             reference_now=NOW + timedelta(hours=1) if boundary == 'expired' else NOW)
    db.expire_all()
    assert all(row.status != 'resolved' for row in rows)


def test_postgres_simultaneous_confirm_is_atomic_and_idempotent(db, auth_user_and_headers):
    if db.get_bind().dialect.name != 'postgresql':
        pytest.skip('PostgreSQL row locking required')
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy.orm import Session
    from app.services.illness_recovery_confirmation import confirm
    user, _ = auth_user_and_headers
    conv, rows = seed(db, user)
    turn(db, user, conv, '都好了')
    preview = turn(db, user, conv, '今天')
    intent_id, user_id, engine = preview['meta']['illness_recovery_intent_id'], user.id, db.get_bind()
    db.commit()
    start = Barrier(2)
    def worker():
        with Session(engine) as session:
            start.wait(timeout=10)
            return confirm(session, user_id, intent_id, reference_now=NOW)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: worker(), range(2)))
    assert sorted(result['idempotent'] for result in results) == [False, True]
    assert results[0]['write_receipts'] == results[1]['write_receipts']


def test_dismiss_after_execution_returns_verified_receipts(db, auth_user_and_headers):
    from app.services import illness_recovery_confirmation as recovery, write_intent_service
    user, _ = auth_user_and_headers
    conv, _ = seed(db, user)
    turn(db, user, conv, '都好了')
    preview = turn(db, user, conv, '今天')
    intent_id = preview['meta']['illness_recovery_intent_id']
    executed = recovery.confirm(db, user.id, intent_id, reference_now=NOW)
    dismissed = write_intent_service.dismiss(db, user.id, intent_id)
    assert dismissed['status'] == 'executed'
    assert dismissed['write_receipts'] == executed['write_receipts']


def test_flush_failure_rolls_back_every_episode_and_intent(db, auth_user_and_headers):
    from sqlalchemy import event
    from app.models.illness import IllnessEpisode
    from app.models.write_intent import WriteIntent
    from app.services.illness_recovery_confirmation import confirm
    user, _ = auth_user_and_headers
    conv, rows = seed(db, user)
    turn(db, user, conv, '都好了')
    preview = turn(db, user, conv, '今天')
    intent_id = preview['meta']['illness_recovery_intent_id']
    def fail_after_flush(session, context):
        if any(isinstance(row, IllnessEpisode) and row.status == 'resolved' for row in session.dirty):
            raise RuntimeError('synthetic transaction failure')
    event.listen(db, 'after_flush', fail_after_flush)
    try:
        with pytest.raises(RuntimeError, match='synthetic transaction failure'):
            confirm(db, user.id, intent_id, reference_now=NOW)
    finally:
        event.remove(db, 'after_flush', fail_after_flush)
    db.expire_all()
    assert [row.status for row in rows] == ['active', 'improving', 'active', 'active']
    wi = db.get(WriteIntent, intent_id)
    assert wi.status == 'pending' and not wi.payload.get('write_receipts')


def test_real_runtime_pause_blocks_atomic_confirmation(db, auth_user_and_headers, monkeypatch):
    from app.config import settings
    from app.services.agent_runtime_rollout import AgentRuntimeRolloutService
    from app.services.illness_recovery_confirmation import confirm, RecoveryConflict
    user, _ = auth_user_and_headers
    conv, rows = seed(db, user)
    turn(db, user, conv, '都好了')
    preview = turn(db, user, conv, '今天')
    monkeypatch.setattr(settings, 'agent_runtime_mode', 'enforce')
    state = AgentRuntimeRolloutService(db)._locked_state()
    state.status, state.reason_code = 'paused', 'manual_pause'
    db.commit()
    with pytest.raises(RecoveryConflict):
        confirm(db, user.id, preview['meta']['illness_recovery_intent_id'], reference_now=NOW)
    db.expire_all()
    assert all(row.status != 'resolved' for row in rows)


@pytest.mark.asyncio
async def test_api_confirmation_enforces_owner_and_returns_safe_conflict(db, auth_user_and_headers):
    from fastapi import HTTPException
    from types import SimpleNamespace
    from app.api.write_intents import confirm_write_intent
    user, _ = auth_user_and_headers
    conv, rows = seed(db, user)
    turn(db, user, conv, '都好了')
    preview = turn(db, user, conv, '今天')
    intent_id = preview['meta']['illness_recovery_intent_id']
    with pytest.raises(HTTPException) as error:
        await confirm_write_intent(intent_id, current_user=SimpleNamespace(id=rows[3].user_id), db=db)
    assert error.value.status_code == 404
    rows[0].notes = 'changed before API confirm'
    db.commit()
    with pytest.raises(HTTPException) as error:
        await confirm_write_intent(intent_id, current_user=user, db=db)
    assert error.value.status_code == 409
    assert rows[0].name not in error.value.detail
    assert all(row.status != 'resolved' for row in rows)
