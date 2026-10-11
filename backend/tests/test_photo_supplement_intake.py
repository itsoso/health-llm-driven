from datetime import UTC, datetime, timedelta
import pytest
from app.models.agent_conversation import AgentConversation, AgentMessage
from app.models.supplement import SupplementDefinition, SupplementRecord
from app.models.write_intent import WriteIntent
from tests.conftest import create_authenticated_user
from app.services import photo_supplement_intake as service

NOW = datetime(2026, 10, 10, 15, 55, tzinfo=UTC)

@pytest.fixture
def scenario(db, monkeypatch):
    user, _ = create_authenticated_user(db)
    conv = AgentConversation(user_id=user.id)
    db.add(conv); db.flush()
    msg = AgentMessage(conversation_id=conv.id, role='user', client_turn_id=f'turn-{user.id}', content='记录四种补剂 NAC 2粒 其他各1粒', image_url='["/uploads/chat/test.jpg"]', created_at=NOW.replace(tzinfo=None))
    db.add(msg)
    names = ['NAC', '维生素D3+K2', '鱼油', '槲皮素']
    db.add_all([SupplementDefinition(user_id=user.id, name=n, is_active=True) for n in names]); db.commit()
    monkeypatch.setattr(service, 'read_owned_chat_image_data_uri', lambda url, uid: 'data:image/jpeg;base64,YWJj')
    return user.id, msg.id, [{'name': n} for n in names]

def presented(db, scenario):
    uid, mid, candidates = scenario
    intent = service.propose(db, uid, mid, candidates, now=NOW)
    source = db.get(AgentMessage, mid)
    assistant = AgentMessage(conversation_id=source.conversation_id, role='assistant', client_turn_id=source.client_turn_id, content='请核对后确认', meta={'client_turn_finalized': True, 'completion_status': 'complete', 'cards': [service.build_card(intent)]})
    db.add(assistant); db.commit()
    return intent


@pytest.mark.parametrize('prefix', ['    ', '\t', '> '])
def test_material_source_cannot_create_a_confirmation_plan(db, scenario, prefix):
    uid, mid, candidates = scenario
    source = db.get(AgentMessage, mid)
    source.content = prefix + source.content
    db.commit()
    with pytest.raises(service.PhotoSupplementConflict, match='unresolved'):
        service.propose(db, uid, mid, candidates, now=NOW)
    assert db.query(WriteIntent).count() == 0
    assert db.query(SupplementRecord).count() == 0

def test_confirm_requires_durable_exact_card(db, scenario):
    uid, mid, candidates = scenario
    wi = service.propose(db, uid, mid, candidates, now=NOW)
    with pytest.raises(ValueError, match='presented'):
        service.confirm(db, uid, wi.id, now=NOW)
    assert db.query(SupplementRecord).count() == 0

@pytest.mark.parametrize('unavailable', [False, True])
def test_confirmation_rechecks_current_runtime_control(db, scenario, monkeypatch, unavailable):
    from app.config import settings
    from app.services.agent_runtime_rollout import AgentRuntimeRolloutService
    from sqlalchemy.exc import OperationalError
    wi = presented(db, scenario)
    monkeypatch.setattr(settings, 'agent_runtime_mode', 'enforce')
    if unavailable:
        def fail(*args):
            raise OperationalError('synthetic', {}, Exception('unavailable'))
        monkeypatch.setattr(AgentRuntimeRolloutService, '_locked_state', fail)
    else:
        rollout = AgentRuntimeRolloutService(db)
        state = rollout._locked_state()
        state.status, state.reason_code = 'paused', 'manual_pause'
        db.commit()
    with pytest.raises(service.PhotoSupplementConflict, match='runtime'):
        service.confirm(db, scenario[0], wi.id, now=NOW)
    assert db.query(SupplementRecord).count() == 0
    assert db.get(WriteIntent, wi.id).status == 'pending'

def test_executed_receipts_replay_when_runtime_pauses(db, scenario, monkeypatch):
    from app.config import settings
    from app.services.agent_runtime_rollout import AgentRuntimeRolloutService
    wi = presented(db, scenario)
    original = service.confirm(db, scenario[0], wi.id, now=NOW)
    monkeypatch.setattr(settings, 'agent_runtime_mode', 'enforce')
    state = AgentRuntimeRolloutService(db)._locked_state()
    state.status, state.reason_code = 'paused', 'manual_pause'
    db.commit()
    replay = service.confirm(db, scenario[0], wi.id, now=NOW)
    assert replay['write_receipts'] == original['write_receipts']
    assert db.query(SupplementRecord).count() == 4

def test_acknowledged_scoped_pause_keeps_existing_admission(db, scenario, monkeypatch):
    from app.config import settings
    from app.services.agent_runtime_rollout import AgentRuntimeRolloutService
    wi = presented(db, scenario)
    monkeypatch.setattr(settings, 'agent_runtime_mode', 'enforce')
    state = AgentRuntimeRolloutService(db)._locked_state()
    state.status, state.reason_code = 'paused', 'reconciliation_detected'
    state.reconciliation_generation = state.reconciliation_acknowledged_generation = 1
    db.commit()
    assert service.confirm(db, scenario[0], wi.id, now=NOW)['status'] == 'executed'

def test_atomic_write_replay_original_day_and_quantities(db, scenario):
    wi = presented(db, scenario)
    result = service.confirm(db, scenario[0], wi.id, now=NOW + timedelta(minutes=10))
    assert len(result['write_receipts']) == 4
    rows = db.query(SupplementRecord).all()
    assert sorted(r.actual_dosage for r in rows) == ['1粒', '1粒', '1粒', '2粒']
    assert {r.record_date.isoformat() for r in rows} == {'2026-10-10'}
    assert service.confirm(db, scenario[0], wi.id, now=NOW + timedelta(days=2))['write_receipts'] == result['write_receipts']
    assert db.query(SupplementRecord).count() == 4

@pytest.mark.parametrize('mode', ['source', 'image', 'card', 'hash', 'definition'])
def test_tampering_never_writes(db, scenario, monkeypatch, mode):
    wi = presented(db, scenario)
    if mode == 'source': db.get(AgentMessage, scenario[1]).content += '修改'
    if mode == 'image': monkeypatch.setattr(service, 'read_owned_chat_image_data_uri', lambda *a: 'changed')
    if mode == 'card':
        a = db.query(AgentMessage).filter_by(role='assistant').one(); a.meta = {'cards': []}
    if mode == 'hash': db.get(WriteIntent, wi.id).payload = {**wi.payload, 'plan_sha256': 'bad'}
    if mode == 'definition': db.query(SupplementDefinition).first().is_active = False
    db.commit()
    with pytest.raises(ValueError): service.confirm(db, scenario[0], wi.id, now=NOW)
    assert db.query(SupplementRecord).count() == 0

def test_owner_isolation(db, scenario):
    wi = presented(db, scenario)
    other, _ = create_authenticated_user(db)
    with pytest.raises(LookupError): service.confirm(db, other.id, wi.id, now=NOW)
    with pytest.raises(LookupError): service.propose(db, other.id, scenario[1], scenario[2], now=NOW)

def test_expiry_and_dismiss_are_terminal(db, scenario):
    wi = presented(db, scenario)
    result = service.confirm(db, scenario[0], wi.id, now=NOW + timedelta(minutes=30))
    assert result['status'] == 'expired'
    assert db.query(SupplementRecord).count() == 0
    assert service.dismiss(db, scenario[0], wi.id, now=NOW)['status'] == 'expired'

def test_existing_record_never_overwritten(db, scenario):
    wi = presented(db, scenario)
    item = wi.payload['items'][0]
    from datetime import date
    db.add(SupplementRecord(user_id=scenario[0], supplement_id=item['supplement_id'], record_date=date(2026,10,10), taken=True, actual_dosage='3粒')); db.commit()
    with pytest.raises(ValueError, match='existing'): service.confirm(db, scenario[0], wi.id, now=NOW)
    assert db.query(SupplementRecord).count() == 1
    assert db.get(WriteIntent, wi.id).status == 'pending'

def test_unknown_candidate_and_duplicate_definition_rejected(db, scenario):
    uid, mid, candidates = scenario
    with pytest.raises(ValueError): service.propose(db, uid, mid, candidates[:-1]+[{'name':'未知'}], now=NOW)
    db.add(SupplementDefinition(user_id=uid, name='NAC', is_active=True)); db.commit()
    with pytest.raises(ValueError, match='unique'): service.propose(db, uid, mid, candidates, now=NOW)
    assert db.query(WriteIntent).count() == 0

def test_repeat_propose_same_intent(db, scenario):
    uid, mid, candidates = scenario
    a = service.propose(db, uid, mid, candidates, now=NOW)
    b = service.propose(db, uid, mid, candidates, now=NOW)
    assert a.id == b.id

def test_record_failure_rolls_back_claim_rows_and_terminal(db, scenario, monkeypatch):
    wi = presented(db, scenario)
    original = db.flush
    def fail_on_second(*args, **kwargs):
        if any(isinstance(x, SupplementRecord) and x.actual_dosage == '1粒' for x in db.new):
            raise RuntimeError('injected record failure')
        return original(*args, **kwargs)
    monkeypatch.setattr(db, 'flush', fail_on_second)
    with pytest.raises(RuntimeError, match='injected'):
        service.confirm(db, scenario[0], wi.id, now=NOW)
    monkeypatch.setattr(db, 'flush', original)
    assert db.query(SupplementRecord).count() == 0
    assert db.get(WriteIntent, wi.id).status == 'pending'
    assistant = db.query(AgentMessage).filter_by(role='assistant').one()
    assert assistant.meta['cards'][0]['data']['decision_status'] == 'pending'

def test_dismiss_never_writes_and_cannot_confirm(db, scenario):
    wi = presented(db, scenario)
    assert service.dismiss(db, scenario[0], wi.id, now=NOW)['status'] == 'dismissed'
    assert service.confirm(db, scenario[0], wi.id, now=NOW)['status'] == 'dismissed'
    assert db.query(SupplementRecord).count() == 0

def test_unreadable_image_is_unsupported(db, scenario, monkeypatch):
    def unavailable(*args): raise ValueError('owned image unavailable')
    monkeypatch.setattr(service, 'read_owned_chat_image_data_uri', unavailable)
    with pytest.raises(ValueError, match='unavailable'):
        service.propose(db, *scenario, now=NOW)
    assert db.query(WriteIntent).count() == 0

def test_confirmation_action_removed_cannot_execute(db, scenario):
    wi = presented(db, scenario)
    assistant = db.query(AgentMessage).filter_by(role='assistant').one()
    import copy
    meta = copy.deepcopy(assistant.meta)
    meta['cards'][0]['actions'] = []
    assistant.meta = meta; db.commit()
    with pytest.raises(ValueError, match='presented'): service.confirm(db, scenario[0], wi.id, now=NOW)
    assert db.query(SupplementRecord).count() == 0

@pytest.mark.parametrize('change', ['deleted', 'dose', 'owner', 'taken', 'date'])
def test_replay_verifies_real_records(db, scenario, change):
    wi = presented(db, scenario)
    service.confirm(db, scenario[0], wi.id, now=NOW)
    row = db.query(SupplementRecord).first()
    if change == 'deleted': db.delete(row)
    if change == 'dose': row.actual_dosage = '9粒'
    if change == 'owner':
        other, _ = create_authenticated_user(db); row.user_id = other.id
    if change == 'taken': row.taken = False
    if change == 'date': row.record_date += timedelta(days=1)
    db.commit()
    with pytest.raises(ValueError, match='receipt'):
        service.confirm(db, scenario[0], wi.id, now=NOW)

@pytest.mark.parametrize('change', ['source', 'candidates'])
def test_repropose_rejects_changed_facts(db, scenario, change):
    uid, mid, candidates = scenario
    service.propose(db, uid, mid, candidates, now=NOW)
    if change == 'source':
        db.get(AgentMessage, mid).content = '记录四种补剂 NAC 3粒 其他各1粒'; db.commit()
    if change == 'candidates': candidates = list(reversed(candidates))
    with pytest.raises(ValueError): service.propose(db, uid, mid, candidates, now=NOW)

@pytest.mark.parametrize('change', ['unfinished', 'failed', 'other_turn', 'no_turn'])
def test_requires_finalized_same_turn(db, scenario, change):
    wi = presented(db, scenario)
    row = db.query(AgentMessage).filter_by(role='assistant').one()
    if change == 'unfinished': row.meta = {**row.meta, 'client_turn_finalized': False}
    if change == 'failed': row.meta = {**row.meta, 'completion_status': 'failed'}
    if change == 'other_turn': row.client_turn_id = 'different'
    if change == 'no_turn': row.client_turn_id = None
    db.commit()
    with pytest.raises(ValueError, match='presented'): service.confirm(db, scenario[0], wi.id, now=NOW)
    assert db.query(SupplementRecord).count() == 0

def test_replay_and_repropose_release_read_transaction(db, scenario):
    uid, mid, candidates = scenario
    wi = presented(db, scenario)
    wid = wi.id
    service.propose(db, uid, mid, candidates, now=NOW)
    assert not db.in_transaction()
    service.confirm(db, uid, wid, now=NOW)
    service.confirm(db, uid, wid, now=NOW)
    assert not db.in_transaction()
    service.dismiss(db, uid, wid, now=NOW)
    assert not db.in_transaction()

def test_expiry_clock_read_after_definition_lock(db, scenario, monkeypatch):
    wi = presented(db, scenario)
    from sqlalchemy import event
    locked = {'definitions': False}
    def observe(conn, cursor, stmt, params, context, many):
        if stmt.lstrip().startswith('SELECT') and 'supplement_definitions.id IN' in stmt:
            locked['definitions'] = True
    event.listen(db.bind, 'before_cursor_execute', observe)
    def clock():
        assert locked['definitions'], 'clock must be sampled after definition locks'
        return NOW + timedelta(minutes=31)
    monkeypatch.setattr(service, '_clock', clock, raising=False)
    try:
        result = service.confirm(db, scenario[0], wi.id)
        assert result['status'] == 'expired'
        assert db.query(SupplementRecord).count() == 0
    finally:
        event.remove(db.bind, 'before_cursor_execute', observe)

def test_terminal_projection_preserves_other_content_and_receipts(db, scenario):
    wi = presented(db, scenario)
    assistant = db.query(AgentMessage).filter_by(role='assistant').one()
    original = '补剂待确认。另一个操作尚未成功，不要重复操作。'
    other = {'operation_id': 'other:1', 'status': 'verified'}
    assistant.content = original
    assistant.meta = {**assistant.meta, 'write_receipts': [other], 'unrelated': {'keep': True}}
    db.commit()
    result = service.confirm(db, scenario[0], wi.id, now=NOW)
    db.refresh(assistant)
    assert assistant.content == original
    assert assistant.meta['unrelated'] == {'keep': True}
    assert assistant.meta['write_receipts'] == [other, *result['write_receipts']]

@pytest.mark.parametrize('change', ['dosage', 'product'])
def test_definition_spec_change_rejects_confirmation(db, scenario, change):
    wi = presented(db, scenario)
    definition = db.query(SupplementDefinition).first()
    if change == 'dosage': definition.dosage = '600mg'
    else:
        from app.models.supplement import SupplementProduct
        product = SupplementProduct(name='Different product', brand='Test')
        db.add(product); db.flush(); definition.product_id = product.id
    db.commit()
    with pytest.raises(ValueError, match='definition'):
        service.confirm(db, scenario[0], wi.id, now=NOW)
    assert db.query(SupplementRecord).count() == 0

def test_preview_displays_frozen_strength_and_product(db, scenario):
    uid, mid, candidates = scenario
    definition = db.query(SupplementDefinition).filter_by(name='NAC').one()
    definition.dosage = '600mg'; db.commit()
    wi = service.propose(db, uid, mid, candidates, now=NOW)
    item = service.build_card(wi)['data']['items'][0]
    assert item['observed_strength'] == '600mg'
    assert item['product_id'] is None
    assert wi.payload['items'][0]['definition_dosage'] == '600mg'


def test_persisted_attachment_caption_is_not_part_of_quantity_request(db, scenario):
    uid, mid, candidates = scenario
    source = db.get(AgentMessage, mid)
    source.content += '\n[附图: 1张]'
    db.commit()
    wi = service.propose(db, uid, mid, candidates, now=NOW)
    assert wi.payload['source_text'].endswith('[附图: 1张]')
    assert wi.payload['items'][0]['actual_dosage'] == '2粒'
    assert service.propose(db, uid, mid, candidates, now=NOW).id == wi.id


def test_incorrect_attachment_caption_is_not_removed(db, scenario):
    uid, mid, candidates = scenario
    db.get(AgentMessage, mid).content += '\n[附图: 2张]'
    db.commit()
    with pytest.raises(ValueError):
        service.propose(db, uid, mid, candidates, now=NOW)

@pytest.mark.parametrize('terminal', ['executed', 'dismissed', 'expired'])
def test_terminal_projection_clears_own_pending_index(db, scenario, terminal):
    wi = presented(db, scenario)
    assistant = db.query(AgentMessage).filter_by(role='assistant').one()
    assistant.meta = {**assistant.meta, 'mode': service.KIND,
        'pending_write_intent_ids': [wi.id], 'pending_write_intent_kinds': [service.KIND],
        'turn_outcome': {'status': 'waiting_for_user'}}
    db.commit()
    if terminal == 'dismissed':
        service.dismiss(db, scenario[0], wi.id, now=NOW)
    else:
        service.confirm(db, scenario[0], wi.id, now=NOW + timedelta(minutes=31 if terminal == 'expired' else 0))
    db.expire_all()
    assert assistant.meta['pending_write_intent_ids'] == []
    assert assistant.meta['pending_write_intent_kinds'] == []
    assert assistant.meta['turn_outcome']['status'] != 'waiting_for_user'
