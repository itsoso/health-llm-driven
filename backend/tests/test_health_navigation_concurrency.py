"""PostgreSQL semantics for concurrent本人 confirmation retries.

Each HTTP request owns a distinct Session/connection. SQLite cannot establish
row-lock serialization, so these cases deliberately require PostgreSQL.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier, Lock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api import health_navigation
from app.config import settings
from app.database import get_db
from app.models.daily_operating_plan import DailyOperatingPlan
from app.models.health_navigation import HealthNavigationOccurrence, HealthNavigationOperation
from app.models.intervention_event import InterventionEvent
from app.services.health_week_navigation import materialize_plan, resolve_action
from app.utils.timezone import get_user_today


@pytest.fixture
def concurrent_navigation(db, auth_user_and_headers, monkeypatch):
    if db.get_bind().dialect.name != 'postgresql':
        pytest.skip('Requires PostgreSQL row locks and independent connections')
    user, headers = auth_user_and_headers
    user_id = user.id
    monkeypatch.setattr(settings, 'health_navigation_enabled', True)
    today = get_user_today(db, user_id)
    source = DailyOperatingPlan(user_id=user_id, plan_date=today, actions=[{
        'action_key': 'movement.moderate_activity', 'title': '合成活动行动',
        'navigation_safety_state': 'allowed',
    }])
    db.add(source)
    db.flush()
    materialize_plan(db, source, now=datetime.now(timezone.utc))
    db.commit()
    occurrence = db.query(HealthNavigationOccurrence).filter_by(user_id=user_id).one()
    ref = occurrence.id
    revision = resolve_action(db, user_id, ref)['action_revision']
    bind = db.get_bind()
    # Do not keep the preparation/auth fixture's transaction open while requests run.
    db.rollback()
    source_calls = []
    calls_lock = Lock()

    def source_writer(session, target_user_id, plan_date, *, commit=True):
        assert commit is False, 'Safety refresh must not commit the confirmation transaction'
        with calls_lock:
            source_calls.append(target_user_id)
        plan = session.query(DailyOperatingPlan).filter_by(
            user_id=target_user_id, plan_date=plan_date,
        ).one()
        materialize_plan(session, plan)
        return {'id': plan.id}

    monkeypatch.setattr(health_navigation, 'build_daily_operating_plan', source_writer)
    app = FastAPI()
    app.include_router(health_navigation.router, prefix='/api/v1')

    def request_db():
        with Session(bind=bind, autoflush=False) as session:
            try:
                yield session
            except Exception:
                session.rollback()
                raise

    app.dependency_overrides[get_db] = request_db
    with TestClient(app) as client:
        yield client, headers, user_id, ref, revision, source_calls


def _concurrent_posts(client, path, headers, payloads):
    barrier = Barrier(len(payloads))

    def submit(body):
        barrier.wait(timeout=10)
        return client.post(path, headers=headers, json=body)

    with ThreadPoolExecutor(max_workers=len(payloads)) as pool:
        futures = [pool.submit(submit, payload) for payload in payloads]
        return [future.result(timeout=30) for future in futures]


@pytest.mark.timeout(45)
def test_postgresql_concurrent_same_operation_creates_one_event(db, concurrent_navigation):
    client, headers, user_id, ref, revision, source_calls = concurrent_navigation
    payload = {'operation_id': str(uuid4()), 'event_type': 'completed',
               'expected_revision': revision}
    responses = _concurrent_posts(client, f'/api/v1/health-navigation/actions/{ref}/events',
                                  headers, [payload, payload])
    assert [response.status_code for response in responses] == [200, 200], [r.text for r in responses]
    assert sorted(response.json()['idempotent'] for response in responses) == [False, True]
    db.expire_all()
    assert db.query(InterventionEvent).filter_by(user_id=user_id).count() == 1
    assert db.query(HealthNavigationOperation).filter_by(
        user_id=user_id, operation_id=payload['operation_id'],
    ).count() == 1
    occurrence = db.query(HealthNavigationOccurrence).filter_by(id=ref, user_id=user_id).one()
    event = db.query(InterventionEvent).filter_by(user_id=user_id).one()
    assert occurrence.execution_status == 'completed'
    assert occurrence.last_event_id == event.id
    assert source_calls == [user_id]


@pytest.mark.timeout(45)
def test_postgresql_concurrent_same_operation_different_content_conflicts(db, concurrent_navigation):
    client, headers, user_id, ref, revision, _ = concurrent_navigation
    operation_id = str(uuid4())
    payload = {'operation_id': operation_id, 'event_type': 'completed',
               'expected_revision': revision}
    responses = _concurrent_posts(client, f'/api/v1/health-navigation/actions/{ref}/events',
                                  headers, [payload, {**payload, 'event_type': 'skipped'}])
    assert sorted(response.status_code for response in responses) == [200, 409], [r.text for r in responses]
    db.expire_all()
    assert db.query(InterventionEvent).filter_by(user_id=user_id).count() == 1
    assert db.query(HealthNavigationOperation).filter_by(user_id=user_id, operation_id=operation_id).count() == 1


@pytest.mark.timeout(15)
def test_postgresql_owner_serialization_allows_source_foreign_key_inserts(db, auth_user_and_headers):
    """The owner lock must coexist with KEY SHARE locks from child FK inserts.

    A source writer can already own its plan while a confirmation serializes the
    owner. FOR UPDATE on User would block its child inserts and form the reverse
    edge of a plan/User lock cycle; FOR NO KEY UPDATE keeps them compatible.
    """
    if db.get_bind().dialect.name != 'postgresql':
        pytest.skip('Requires PostgreSQL foreign-key KEY SHARE locks')
    from sqlalchemy import select, text
    from sqlalchemy.dialects import postgresql
    from app.models.user import User
    user, _ = auth_user_and_headers
    user_id = user.id
    today = get_user_today(db, user_id)
    plan = DailyOperatingPlan(user_id=user_id, plan_date=today, actions=[{
        'action_key': 'movement.moderate_activity', 'title': '合成行动',
        'navigation_safety_state': 'allowed',
    }])
    db.add(plan)
    db.commit()
    plan_id = plan.id
    bind = db.get_bind()
    db.rollback()
    statement = select(User).where(User.id == user_id).with_for_update(key_share=True)
    assert 'FOR NO KEY UPDATE' in str(statement.compile(dialect=postgresql.dialect()))

    def source_insert():
        with Session(bind=bind) as source_db:
            source_db.execute(text("SET LOCAL statement_timeout = '3000ms'"))
            source_plan = source_db.query(DailyOperatingPlan).filter_by(id=plan_id).one()
            materialize_plan(source_db, source_plan)
            source_db.commit()

    with Session(bind=bind) as owner_lock:
        owner_lock.execute(statement).scalar_one()
        with ThreadPoolExecutor(max_workers=1) as pool:
            # Complete while owner_lock is still held; do not release it to fake
            # compatibility. The worker timeout makes the old FOR UPDATE fail.
            pool.submit(source_insert).result(timeout=6)
        owner_lock.rollback()
    db.expire_all()
    assert db.query(HealthNavigationOccurrence).filter_by(user_id=user_id, plan_id=plan_id).count() == 1
