"""Server operator resume acknowledges future admission, never old effects."""
import pytest
from datetime import UTC, datetime
from tests.test_agent_runtime_rollout import _runtime_row, _configure
from app.models.agent_runtime import AgentRun, AgentRuntimeRolloutEvent
from app.services.agent_runtime_rollout import AgentRuntimeRolloutService
from app.services import agent_runtime_operator as operator


def _paused(db, monkeypatch, user):
    _configure(monkeypatch, mode='enforce')
    _runtime_row(db, user_id=user.id, suffix='operator-unknown', status='reconciliation_required', now=datetime.now(UTC))
    AgentRuntimeRolloutService(db).evaluate_and_maybe_pause()
    monkeypatch.setattr(operator.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(operator.sys, 'platform', 'linux')
    return operator.ServerRuntimeRecovery(db)


def test_operator_requires_authenticated_server_root(db, monkeypatch):
    monkeypatch.setattr(operator.os, 'geteuid', lambda: 1000)
    with pytest.raises(PermissionError):
        operator.ServerRuntimeRecovery(db).review()


def test_operator_restores_future_admission_preserving_unknown(db, monkeypatch, auth_user_and_headers):
    user, _ = auth_user_and_headers
    recovery = _paused(db, monkeypatch, user)
    review = recovery.review()
    result = recovery.resume(review)
    assert result.status == 'active'
    assert db.query(AgentRun).one().status == 'reconciliation_required'
    assert AgentRuntimeRolloutService(db).admission_decision(user.id).managed
    event = db.query(AgentRuntimeRolloutEvent).order_by(AgentRuntimeRolloutEvent.id.desc()).first()
    assert event.actor_kind == 'operator'
    assert event.actor_user_id is None
    assert event.operator_review == review


def test_changed_generation_rejects_stale_review(db, monkeypatch, auth_user_and_headers):
    user, _ = auth_user_and_headers
    recovery = _paused(db, monkeypatch, user)
    review = recovery.review()
    _runtime_row(db, user_id=user.id, suffix='operator-new', status='reconciliation_required', now=datetime.now(UTC))
    with pytest.raises(ValueError, match='review_changed'):
        recovery.resume(review)
    assert AgentRuntimeRolloutService(db).get_state().status == 'paused'


def test_new_incident_after_resume_still_pauses(db, monkeypatch, auth_user_and_headers):
    user, _ = auth_user_and_headers
    recovery = _paused(db, monkeypatch, user)
    recovery.resume(recovery.review())
    _runtime_row(db, user_id=user.id, suffix='operator-next', status='reconciliation_required', now=datetime.now(UTC))
    AgentRuntimeRolloutService(db).evaluate_and_maybe_pause()
    assert not AgentRuntimeRolloutService(db).admission_decision(user.id).managed


def test_operator_idempotent_same_review_only(db, monkeypatch, auth_user_and_headers):
    user, _ = auth_user_and_headers
    recovery = _paused(db, monkeypatch, user)
    reviewed = recovery.review()
    assert recovery.resume(reviewed).changed
    count = db.query(AgentRuntimeRolloutEvent).count()
    assert not recovery.resume(reviewed).changed
    assert db.query(AgentRuntimeRolloutEvent).count() == count


def test_operator_cannot_restore_other_pause(db, monkeypatch):
    from app.models.agent_runtime import AgentRuntimeRolloutState
    monkeypatch.setattr(operator.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(operator.sys, 'platform', 'linux')
    state = AgentRuntimeRolloutService(db).get_state()
    state.status = 'paused'
    state.reason_code = 'manual_pause'
    db.commit()
    with pytest.raises(ValueError, match='requires_reconciliation_pause'):
        operator.ServerRuntimeRecovery(db).review()


def test_operator_event_requires_review_and_no_fake_admin(db):
    from sqlalchemy.exc import IntegrityError
    db.add(AgentRuntimeRolloutEvent(action='resume', actor_kind='operator', reason_code='manual_resume'))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


@pytest.mark.parametrize('review', [None, [], 1, True, 'audit'])
def test_database_rejects_non_object_operator_review(db, review):
    from sqlalchemy.exc import IntegrityError
    db.add(AgentRuntimeRolloutEvent(action='resume', actor_kind='operator', reason_code='manual_resume', operator_review=review))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_bool_generation_is_not_integer_review(db, monkeypatch, auth_user_and_headers):
    user, _ = auth_user_and_headers
    recovery = _paused(db, monkeypatch, user)
    review = recovery.review()
    review['generation'] = True
    with pytest.raises(ValueError, match='invalid_operator_review'):
        recovery.resume(review)
    assert AgentRuntimeRolloutService(db).get_state().status == 'paused'


def test_postgres_resume_holds_generation_lock_through_audit_commit(db, monkeypatch, auth_user_and_headers):
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.orm import Session
    from app.models.agent_runtime import AgentRuntimeRolloutState
    if db.get_bind().dialect.name != 'postgresql':
        pytest.skip('requires PostgreSQL row locks')
    user, _ = auth_user_and_headers
    recovery = _paused(db, monkeypatch, user)
    reviewed = recovery.review()
    original = recovery._manifest
    with Session(db.get_bind()) as other:
        def manifest_under_lock(state):
            other.execute(text("SET LOCAL lock_timeout = '80ms'"))
            with pytest.raises(OperationalError):
                other.query(AgentRuntimeRolloutState).filter_by(id=1).with_for_update().one()
            other.rollback()
            return original(state)
        monkeypatch.setattr(recovery, '_manifest', manifest_under_lock)
        recovery.resume(reviewed)
        assert other.query(AgentRuntimeRolloutState).filter_by(id=1).with_for_update().one().status == 'active'
        other.rollback()
