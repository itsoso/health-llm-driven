from datetime import datetime, timezone, timedelta

import pytest

NOW = datetime(2026, 10, 2, 12, tzinfo=timezone(timedelta(hours=8)))


def test_ambiguous_lower_bound_is_not_an_exact_write():
    from app.services.water_backfill import parse_water_backfill
    draft = parse_water_backfill('补充记录最近几天的饮水，每天都在1800毫升以上', reference_now=NOW)
    assert draft is not None
    assert not draft.items
    assert '具体日期' in draft.clarification
    assert '准确' in draft.clarification


def test_recent_dates_are_explicit_and_total_not_increment():
    from app.services.water_backfill import parse_water_backfill
    draft = parse_water_backfill('补记最近3天饮水，每天总量1800ml', reference_now=NOW)
    assert [(x['date'], x['total_ml']) for x in draft.items] == [
        ('2026-09-30', 1800), ('2026-10-01', 1800), ('2026-10-02', 1800)]
    assert '包含今天' in draft.date_note


@pytest.mark.parametrize('message', [
    '不要补记最近3天饮水，每天1800ml',
    '他说“补记最近3天饮水，每天1800ml”',
    '查看最近3天饮水记录，每天1800ml',
    '帮爸爸补记最近3天饮水，每天1800ml',
])
def test_non_authorizing_requests_never_propose(message):
    from app.services.water_backfill import parse_water_backfill
    assert parse_water_backfill(message, reference_now=NOW) is None


def _source(db, user):
    from app.models.agent_conversation import AgentConversation, AgentMessage
    conv = AgentConversation(user_id=user.id, title='water test')
    db.add(conv)
    db.flush()
    source = AgentMessage(conversation_id=conv.id, role='user', content='补记最近3天饮水，每天总量1800ml')
    db.add(source)
    db.commit()
    return conv, source


def _present(db, wi, conv):
    from app.models.agent_conversation import AgentMessage
    from app.services.water_backfill import preview_text
    assistant = AgentMessage(conversation_id=conv.id, role='assistant', content=preview_text(wi), meta={
        'water_backfill_intent_id': wi.id, 'water_backfill_plan': wi.payload,
        'client_turn_finalized': True,
    })
    db.add(assistant)
    db.commit()


def test_confirm_checks_existing_totals_and_replays(db, auth_user_and_headers):
    from app.models.daily_health import WaterIntake
    from app.services.water_backfill import propose_water_backfill, confirm_water_backfill
    user, _ = auth_user_and_headers
    conv, source = _source(db, user)
    db.add(WaterIntake(user_id=user.id, record_date=NOW.date(), amount_ml=500))
    db.commit()
    wi = propose_water_backfill(db, user_id=user.id, source_message_id=source.id, reference_now=NOW)
    assert wi.payload['items'][-1]['existing_ml'] == 500
    assert wi.payload['items'][-1]['add_ml'] == 1300
    _present(db, wi, conv)
    first = confirm_water_backfill(db, user.id, wi.id, reference_now=NOW)
    second = confirm_water_backfill(db, user.id, wi.id, reference_now=NOW)
    assert first['status'] == second['status'] == 'executed'
    assert first['write_receipts'] == second['write_receipts']
    assert second['idempotent'] is True
    assert db.query(WaterIntake).count() == 4


def test_confirm_requires_presented_owned_unchanged_plan(db, auth_user_and_headers):
    from app.models.daily_health import WaterIntake
    from app.services.water_backfill import propose_water_backfill, confirm_water_backfill, WaterBackfillConflict
    user, _ = auth_user_and_headers
    conv, source = _source(db, user)
    wi = propose_water_backfill(db, user_id=user.id, source_message_id=source.id, reference_now=NOW)
    with pytest.raises(WaterBackfillConflict, match='presented'):
        confirm_water_backfill(db, user.id, wi.id, reference_now=NOW)
    with pytest.raises(LookupError):
        confirm_water_backfill(db, user.id + 999, wi.id, reference_now=NOW)
    _present(db, wi, conv)
    db.add(WaterIntake(user_id=user.id, record_date=NOW.date(), amount_ml=300))
    db.commit()
    with pytest.raises(WaterBackfillConflict, match='changed'):
        confirm_water_backfill(db, user.id, wi.id, reference_now=NOW)
    assert db.query(WaterIntake).count() == 1
    db.refresh(wi)
    assert wi.status == 'pending'


@pytest.mark.parametrize('message', [
    '补记最近3天饮水，每天1800ml以上',
    '补记最近3天饮水，每天1800.1ml',
    '补记最近99天饮水，每天1800ml',
    '补记2026-10-03饮水1800ml',
    '补记最近3天饮水，每天总量1800ml并添加药物',
    '补记昨天饮水1800ml，今天再加300ml',
])
def test_uncertainty_or_unconsumed_instruction_never_proposes(message):
    from app.services.water_backfill import parse_water_backfill
    draft = parse_water_backfill(message, reference_now=NOW)
    assert draft is None or (not draft.items and draft.clarification)


def test_expiry_and_tamper_do_not_write(db, auth_user_and_headers):
    from app.services.water_backfill import propose_water_backfill, confirm_water_backfill, WaterBackfillConflict
    from app.models.daily_health import WaterIntake
    user, _ = auth_user_and_headers
    conv, source = _source(db, user)
    wi = propose_water_backfill(db, user_id=user.id, source_message_id=source.id, reference_now=NOW)
    _present(db, wi, conv)
    with pytest.raises(WaterBackfillConflict, match='expired'):
        confirm_water_backfill(db, user.id, wi.id, reference_now=NOW + timedelta(minutes=31))
    changed = dict(wi.payload)
    changed['items'] = [{**item, 'total_ml': 1900} for item in changed['items']]
    wi.payload = changed
    db.commit()
    with pytest.raises(WaterBackfillConflict, match='invalid'):
        confirm_water_backfill(db, user.id, wi.id, reference_now=NOW)
    assert db.query(WaterIntake).count() == 0


@pytest.mark.asyncio
async def test_chat_preview_then_confirmation_writes_and_reports_receipts(db, auth_user_and_headers, monkeypatch):
    import json
    from app.services.agent_executor import AgentExecutor
    from app.models.daily_health import WaterIntake
    from app.models.agent_conversation import AgentMessage
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    monkeypatch.setattr(executor, '_agent_kernel_reference_now', lambda: NOW)
    async def forbid_llm(*args, **kwargs):
        raise AssertionError('water backfill should resolve before LLM')
    async def forbid_stream(*args, **kwargs):
        raise AssertionError('water backfill should resolve before LLM')
        yield
    monkeypatch.setattr(executor, '_call_llm', forbid_llm)
    monkeypatch.setattr(executor, '_call_llm_stream', forbid_stream)
    events = [e async for e in executor.run_stream(user_id=user.id, message='补记最近3天饮水，每天总量1800ml', user_auth_token='test-token', extra_context=json.dumps({'multi_model': True}))]
    done = next(e['data'] for e in events if e.get('event') == 'done')
    assert done['mode'] == 'water_backfill'
    assert done['turn_outcome']['confirmation_required'] is True
    assert db.query(WaterIntake).count() == 0
    conv_id = done['conversation_id']
    events = [e async for e in executor.run_stream(user_id=user.id, message='确认', conversation_id=conv_id, user_auth_token='test-token')]
    done = next(e['data'] for e in events if e.get('event') == 'done')
    assert done['turn_outcome']['verified_receipt_count'] == 3
    assert db.query(WaterIntake).count() == 3
    latest = db.query(AgentMessage).filter_by(role='assistant').order_by(AgentMessage.id.desc()).first()
    assert len(latest.meta['write_receipts']) == 3


def test_batch_insert_failure_rolls_back_whole_plan(db, auth_user_and_headers, monkeypatch):
    from app.models.daily_health import WaterIntake
    from app.services.water_backfill import propose_water_backfill, confirm_water_backfill
    user, _ = auth_user_and_headers
    conv, source = _source(db, user)
    wi = propose_water_backfill(db, user_id=user.id, source_message_id=source.id, reference_now=NOW)
    _present(db, wi, conv)
    original_flush = db.flush
    seen = 0
    def fail_second(*args, **kwargs):
        nonlocal seen
        if any(isinstance(row, WaterIntake) for row in db.new):
            seen += 1
            if seen == 2:
                raise RuntimeError('synthetic insert failure')
        return original_flush(*args, **kwargs)
    monkeypatch.setattr(db, 'flush', fail_second)
    with pytest.raises(RuntimeError, match='synthetic'):
        confirm_water_backfill(db, user.id, wi.id, reference_now=NOW)
    assert db.query(WaterIntake).count() == 0
    db.refresh(wi)
    assert wi.status == 'pending'


def test_pg_other_writer_during_confirmation_is_rechecked(db, auth_user_and_headers):
    if db.get_bind().dialect.name != 'postgresql':
        pytest.skip('PostgreSQL lock semantics')
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from sqlalchemy.orm import Session
    from app.models.daily_health import WaterIntake
    from app.services.water_backfill import propose_water_backfill, confirm_water_backfill, WaterBackfillConflict
    user, _ = auth_user_and_headers
    conv, source = _source(db, user)
    wi = propose_water_backfill(db, user_id=user.id, source_message_id=source.id, reference_now=NOW)
    _present(db, wi, conv)
    user_id, intent_id = user.id, wi.id
    engine = db.get_bind()
    writer = Session(engine)
    writer.add(WaterIntake(user_id=user_id, record_date=NOW.date(), amount_ml=300))
    writer.flush()
    entered = Event()
    def confirm():
        with Session(engine) as session:
            entered.set()
            return confirm_water_backfill(session, user_id, intent_id, reference_now=NOW)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(confirm)
        assert entered.wait(2)
        writer.commit()
        with pytest.raises(WaterBackfillConflict, match='baseline_changed'):
            future.result(timeout=10)
    writer.close()
    assert db.query(WaterIntake).count() == 1


def test_pg_concurrent_confirmations_write_once(db, auth_user_and_headers):
    if db.get_bind().dialect.name != 'postgresql':
        pytest.skip('PostgreSQL lock semantics')
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy.orm import Session
    from app.models.daily_health import WaterIntake
    from app.services.water_backfill import propose_water_backfill, confirm_water_backfill
    user, _ = auth_user_and_headers
    conv, source = _source(db, user)
    wi = propose_water_backfill(db, user_id=user.id, source_message_id=source.id, reference_now=NOW)
    _present(db, wi, conv)
    user_id, intent_id = user.id, wi.id
    engine = db.get_bind()
    barrier = Barrier(2)
    def confirm():
        with Session(engine) as session:
            barrier.wait(timeout=5)
            return confirm_water_backfill(session, user_id, intent_id, reference_now=NOW)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(confirm) for _ in range(2)]
        results = [future.result(timeout=10) for future in futures]
    assert sorted(result['idempotent'] for result in results) == [False, True]
    assert results[0]['write_receipts'] == results[1]['write_receipts']
    assert db.query(WaterIntake).count() == 3


def test_pg_lock_timeout_rolls_back_and_can_retry(db, auth_user_and_headers):
    if db.get_bind().dialect.name != 'postgresql':
        pytest.skip('PostgreSQL lock semantics')
    from sqlalchemy.orm import Session
    from sqlalchemy.exc import OperationalError
    from app.models.daily_health import WaterIntake
    from app.services.water_backfill import propose_water_backfill, confirm_water_backfill
    user, _ = auth_user_and_headers
    conv, source = _source(db, user)
    wi = propose_water_backfill(db, user_id=user.id, source_message_id=source.id, reference_now=NOW)
    _present(db, wi, conv)
    user_id, intent_id = user.id, wi.id
    with Session(db.get_bind()) as writer:
        writer.add(WaterIntake(user_id=user_id, record_date=NOW.date(), amount_ml=300))
        writer.flush()
        with pytest.raises(OperationalError, match='lock timeout'):
            confirm_water_backfill(db, user_id, intent_id, reference_now=NOW)
        writer.rollback()
    db.refresh(wi)
    assert wi.status == 'pending'
    assert db.query(WaterIntake).count() == 0
    assert confirm_water_backfill(db, user_id, intent_id, reference_now=NOW)['status'] == 'executed'


def test_distinct_totals_stay_attached_to_dates():
    from app.services.water_backfill import parse_water_backfill
    draft = parse_water_backfill('补记饮水，2026-09-30 1700ml，2026-10-01 1900ml', reference_now=NOW)
    assert list(draft.items) == [{'date': '2026-09-30', 'total_ml': 1700}, {'date': '2026-10-01', 'total_ml': 1900}]


def test_cancelled_plan_cannot_be_confirmed(db, auth_user_and_headers):
    from app.services.water_backfill import propose_water_backfill, confirm_water_backfill
    from app.services.write_intent_service import dismiss
    from app.models.daily_health import WaterIntake
    user, _ = auth_user_and_headers
    conv, source = _source(db, user)
    wi = propose_water_backfill(db, user_id=user.id, source_message_id=source.id, reference_now=NOW)
    _present(db, wi, conv)
    assert dismiss(db, user.id, wi.id)['status'] == 'dismissed'
    assert confirm_water_backfill(db, user.id, wi.id, reference_now=NOW)['status'] == 'dismissed'
    assert db.query(WaterIntake).count() == 0


def test_api_uses_same_manual_plan_and_receipts(client, db, auth_user_and_headers, monkeypatch):
    from app.services.water_backfill import propose_water_backfill
    from app.models.daily_health import WaterIntake
    user, headers = auth_user_and_headers
    conv, source = _source(db, user)
    wi = propose_water_backfill(db, user_id=user.id, source_message_id=source.id, reference_now=NOW)
    monkeypatch.setattr('app.services.water_backfill.get_china_now', lambda: NOW)
    assert client.post(f'/api/v1/write-intents/{wi.id}/confirm', headers=headers).status_code == 409
    _present(db, wi, conv)
    result = client.post(f'/api/v1/write-intents/{wi.id}/confirm', headers=headers)
    assert result.status_code == 200
    assert len(result.json()['write_receipts']) == 3
    replay = client.post(f'/api/v1/write-intents/{wi.id}/confirm', headers=headers)
    assert replay.status_code == 200
    assert replay.json()['idempotent'] is True
    assert db.query(WaterIntake).count() == 3


def test_noop_replay_requires_current_baseline(db, auth_user_and_headers):
    from app.models.daily_health import WaterIntake
    from app.services.water_backfill import propose_water_backfill, confirm_water_backfill, WaterBackfillConflict
    user, _ = auth_user_and_headers
    conv, source = _source(db, user)
    for offset in range(3):
        db.add(WaterIntake(user_id=user.id, record_date=NOW.date() - timedelta(days=offset), amount_ml=1800))
    db.commit()
    wi = propose_water_backfill(db, user_id=user.id, source_message_id=source.id, reference_now=NOW)
    _present(db, wi, conv)
    result = confirm_water_backfill(db, user.id, wi.id, reference_now=NOW)
    assert result['verified_no_change'] is True
    assert result['write_receipts'] == []
    row = db.query(WaterIntake).first()
    row.amount_ml = 1000
    db.commit()
    with pytest.raises(WaterBackfillConflict, match='receipt_changed'):
        confirm_water_backfill(db, user.id, wi.id, reference_now=NOW)
    assert db.query(WaterIntake).count() == 3


def test_replay_describes_history_even_if_other_existing_records_changed(db, auth_user_and_headers):
    from app.models.daily_health import WaterIntake
    from app.models.agent_conversation import AgentMessage
    from app.services.water_backfill import propose_water_backfill, confirm_water_backfill, resolve_water_backfill_turn
    user, _ = auth_user_and_headers
    conv, source = _source(db, user)
    baseline = WaterIntake(user_id=user.id, record_date=NOW.date(), amount_ml=500)
    db.add(baseline)
    db.commit()
    wi = propose_water_backfill(db, user_id=user.id, source_message_id=source.id, reference_now=NOW)
    _present(db, wi, conv)
    confirm_water_backfill(db, user.id, wi.id, reference_now=NOW)
    baseline.amount_ml = 700
    replay_source = AgentMessage(conversation_id=conv.id, role='user', content=f'确认饮水补记 {wi.id}')
    db.add(replay_source)
    db.commit()
    result = resolve_water_backfill_turn(db, user_id=user.id, source_message_id=replay_source.id, reference_now=NOW)
    assert '原计划全天目标' in result['reply']
    assert '不代表当前总量' in result['reply']
    assert db.query(WaterIntake).count() == 4


@pytest.mark.asyncio
@pytest.mark.parametrize('block_reason', ['circuit_paused', 'circuit_unavailable'])
async def test_chat_runtime_write_block_preserves_plan_for_retry(db, auth_user_and_headers, monkeypatch, block_reason):
    from app.services.agent_executor import AgentExecutor
    from app.models.daily_health import WaterIntake
    from app.models.write_intent import WriteIntent
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    monkeypatch.setattr(executor, '_agent_kernel_reference_now', lambda: NOW)
    async def run(message, conversation_id=None, reason=block_reason):
        events = [event async for event in executor.run_stream(
            user_id=user.id, message=message, conversation_id=conversation_id,
            user_auth_token='test-token', runtime_write_block_reason=reason,
        )]
        return next(event['data'] for event in events if event.get('event') == 'done')
    proposed = await run('补记最近3天饮水，每天总量1800ml')
    intent_id = proposed['water_backfill_intent_id']
    blocked = await run('确认', proposed['conversation_id'])
    assert db.query(WaterIntake).count() == 0
    assert db.get(WriteIntent, intent_id).status == 'pending'
    assert blocked['completion_status'] == 'error'
    assert blocked['turn_outcome']['status'] == 'failed'
    assert blocked['turn_outcome']['reason_code'] == 'runtime_control_unavailable'
    assert blocked['write_receipts'] == []
    assert blocked['water_backfill_intent_id'] == intent_id
    retried = await run('确认', proposed['conversation_id'], reason=None)
    assert retried['turn_outcome']['verified_receipt_count'] == 3
    assert db.query(WaterIntake).count() == 3
    assert db.query(WriteIntent).count() == 1


@pytest.mark.parametrize('message', ['确认', '取消'])
def test_runtime_block_does_not_claim_unrelated_generic_control(db, auth_user_and_headers, message):
    from app.models.agent_conversation import AgentMessage
    from app.services.water_backfill import resolve_water_backfill_turn
    user, _ = auth_user_and_headers
    conv, _ = _source(db, user)
    source = AgentMessage(conversation_id=conv.id, role='user', content=message)
    db.add(source)
    db.commit()
    assert resolve_water_backfill_turn(db, user_id=user.id, source_message_id=source.id,
                                      reference_now=NOW, runtime_write_block_reason='circuit_paused') is None


def test_runtime_block_allows_owned_water_cancellation(db, auth_user_and_headers):
    from app.models.agent_conversation import AgentMessage
    from app.models.daily_health import WaterIntake
    from app.services.water_backfill import propose_water_backfill, resolve_water_backfill_turn
    user, _ = auth_user_and_headers
    conv, source = _source(db, user)
    wi = propose_water_backfill(db, user_id=user.id, source_message_id=source.id, reference_now=NOW)
    _present(db, wi, conv)
    cancellation = AgentMessage(conversation_id=conv.id, role='user', content='取消')
    db.add(cancellation)
    db.commit()
    result = resolve_water_backfill_turn(db, user_id=user.id, source_message_id=cancellation.id,
                                        reference_now=NOW, runtime_write_block_reason='circuit_paused')
    assert result['status'] == 'cancelled'
    db.refresh(wi)
    assert wi.status == 'dismissed'
    assert db.query(WaterIntake).count() == 0


@pytest.mark.parametrize('constant, replacement', [('MAX_DAYS', 7), ('PLAN_TTL_MINUTES', 15)])
def test_water_contract_changes_with_scope_and_expiry(monkeypatch, constant, replacement):
    from app.services import water_backfill
    before = water_backfill.water_backfill_contract_payload()
    assert before == water_backfill.water_backfill_contract_payload()
    monkeypatch.setattr(water_backfill, constant, replacement)
    assert water_backfill.water_backfill_contract_payload() != before


def test_water_contract_changes_with_confirmation_behavior(monkeypatch):
    from app.services import water_backfill
    before = water_backfill.water_backfill_contract_payload()
    monkeypatch.setattr(water_backfill, 'resolve_water_backfill_turn', lambda *args, **kwargs: None)
    assert water_backfill.water_backfill_contract_payload()['behavior'] != before['behavior']
