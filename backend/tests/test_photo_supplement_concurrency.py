"""Real PostgreSQL contention; no SQLite claim of row-lock correctness."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy.orm import sessionmaker
from app.models.supplement import SupplementRecord
from app.models.write_intent import WriteIntent
from app.services import photo_supplement_intake as service
from tests.test_photo_supplement_intake import NOW, presented, scenario  # noqa: F401


def test_runtime_state_lock_is_held_through_record_flush(db, scenario, monkeypatch):
    if db.get_bind().dialect.name != 'postgresql':
        pytest.skip('requires real PostgreSQL row locks')
    from app.config import settings
    from app.services.agent_runtime_rollout import AgentRuntimeRolloutService
    from sqlalchemy import event, text
    from sqlalchemy.exc import OperationalError
    monkeypatch.setattr(settings, 'agent_runtime_mode', 'enforce')
    intent_id = presented(db, scenario).id
    AgentRuntimeRolloutService(db)._locked_state()
    db.commit()
    factory = sessionmaker(bind=db.get_bind())
    checked = []
    def during_flush(session, flush_context, instances):
        if checked or not any(isinstance(row, SupplementRecord) for row in session.new):
            return
        with factory() as other:
            other.execute(text("SET LOCAL lock_timeout = '100ms'"))
            with pytest.raises(OperationalError):
                AgentRuntimeRolloutService(other)._locked_state()
            other.rollback()
        checked.append(True)
    event.listen(db, 'before_flush', during_flush)
    try:
        assert service.confirm(db, scenario[0], intent_id, now=NOW)['status'] == 'executed'
    finally:
        event.remove(db, 'before_flush', during_flush)
    assert checked == [True]
    with factory() as other:
        other.execute(text("SET LOCAL lock_timeout = '100ms'"))
        state = AgentRuntimeRolloutService(other)._locked_state()
        state.status, state.reason_code = 'paused', 'manual_pause'
        other.commit()


@pytest.mark.parametrize('operation', ['propose', 'confirm', 'confirm_dismiss', 'api_confirm'])
def test_two_connections_serialize_photo_intent(db, scenario, operation, monkeypatch):
    monkeypatch.setattr(service, "_clock", lambda: NOW)
    if db.get_bind().dialect.name != 'postgresql':
        pytest.skip('requires real PostgreSQL row locks')
    uid, mid, candidates = scenario
    intent_id = None if operation == 'propose' else presented(db, scenario).id
    factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    db.rollback()
    start = Barrier(2)

    def run(index):
        with factory() as session:
            preloaded = session.get(WriteIntent, intent_id) if operation == 'api_confirm' else None
            start.wait(timeout=10)
            if operation == 'api_confirm':
                from app.services import write_intent_service
                assert preloaded.status == 'pending'
                return write_intent_service.confirm(session, uid, intent_id)
            if operation == 'propose':
                return service.propose(session, uid, mid, candidates, now=NOW).id
            if operation == 'confirm_dismiss' and index == 1:
                return service.dismiss(session, uid, intent_id, now=NOW)
            return service.confirm(session, uid, intent_id, now=NOW)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run, i) for i in range(2)]
        results = [f.result(timeout=20) for f in futures]
    db.expire_all()
    assert db.query(WriteIntent).filter_by(user_id=uid, kind=service.KIND).count() == 1
    if operation == 'propose':
        assert results[0] == results[1]
        assert db.query(SupplementRecord).count() == 0
    else:
        assert results[0]['status'] == results[1]['status']
        assert results[0]['write_receipts'] == results[1]['write_receipts']
        count = 4 if results[0]['status'] == 'executed' else 0
        assert db.query(SupplementRecord).count() == count
        if operation in ('confirm', 'api_confirm'):
            assert count == 4


def test_two_source_plans_cannot_overwrite_same_day(db, scenario):
    if db.get_bind().dialect.name != 'postgresql':
        pytest.skip('requires real PostgreSQL row locks')
    from app.models.agent_conversation import AgentMessage
    uid, mid, candidates = scenario
    first_id = presented(db, scenario).id
    source = db.get(AgentMessage, mid)
    second_source = AgentMessage(
        conversation_id=source.conversation_id, role='user', client_turn_id='second-photo-turn',
        content=source.content, image_url=source.image_url, created_at=source.created_at,
    )
    db.add(second_source)
    db.commit()
    second_id = presented(db, (uid, second_source.id, candidates)).id
    factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    db.rollback()
    start = Barrier(2)

    def run(intent_id):
        with factory() as session:
            start.wait(timeout=10)
            try:
                return service.confirm(session, uid, intent_id, now=NOW)['status']
            except ValueError as exc:
                assert 'existing daily record' in str(exc)
                return 'conflict'

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run, intent_id) for intent_id in (first_id, second_id)]
        results = [f.result(timeout=20) for f in futures]
    db.expire_all()
    assert sorted(results) == ['conflict', 'executed']
    assert db.query(SupplementRecord).count() == 4
    assert sorted(w.status for w in db.query(WriteIntent).all()) == ['executed', 'pending']
