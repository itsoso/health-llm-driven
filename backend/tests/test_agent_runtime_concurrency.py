from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import gc
import hashlib
from threading import Barrier, Event
import weakref

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.agent_conversation import AgentConversation
from app.models.agent_runtime import AgentRun, AgentRunEvent, AgentToolOperation
from app.services.agent_runtime import AgentRuntimeCoordinator, RunBusyError


def test_sqlite_runtime_lock_does_not_leak_across_engine_lifetimes():
    from app.services.agent_runtime import (
        _SQLITE_ENGINE_LOCKS,
        _sqlite_runtime_lock,
    )

    engine = create_engine("sqlite:///:memory:")
    engine_ref = weakref.ref(engine)
    with _sqlite_runtime_lock(engine):
        assert engine in _SQLITE_ENGINE_LOCKS

    engine.dispose()
    del engine
    gc.collect()

    assert engine_ref() is None


def test_distinct_concurrent_turns_admit_exactly_one_run(db, auth_user_and_headers):
    user, _headers = auth_user_and_headers
    conversation = AgentConversation(
        user_id=user.id,
        title="runtime-concurrency",
        session_key="runtime-concurrency",
    )
    db.add(conversation)
    db.commit()
    conversation_id = conversation.id
    user_id = user.id
    # The default test engine is one in-memory SQLite connection shared through
    # StaticPool. Accessing expired ids after commit opens a new transaction on
    # that connection; close it before worker sessions exercise admission.
    db.rollback()
    Session = sessionmaker(bind=db.get_bind(), autocommit=False, autoflush=False)
    barrier = Barrier(2)

    def admit(index: int):
        session = Session()
        try:
            barrier.wait(timeout=5)
            admission = AgentRuntimeCoordinator(session).create_or_resume_run(
                run_id=f"run-concurrent-{index}",
                attempt_id=f"attempt-concurrent-{index}",
                user_id=user_id,
                conversation_id=conversation_id,
                client_turn_id=f"turn-concurrent-{index}",
                origin="test",
            )
            return "admitted", admission.context.run_id
        except RunBusyError as exc:
            return "busy", exc.active_run_id
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(admit, (1, 2)))

    assert sorted(status for status, _run_id in outcomes) == ["admitted", "busy"]
    db.expire_all()
    active = db.query(AgentRun).filter(
        AgentRun.conversation_id == conversation_id,
        AgentRun.status.in_(("queued", "running")),
    ).all()
    assert len(active) == 1


def test_postgres_concurrent_first_pause_creates_one_transition(
    db, auth_user_and_headers
):
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("requires PostgreSQL row locking")

    from app.models.agent_runtime import AgentRuntimeRolloutEvent
    from app.services.agent_runtime_rollout import AgentRuntimeRolloutService

    user, _headers = auth_user_and_headers
    user_id = user.id
    db.rollback()
    Session = sessionmaker(bind=db.get_bind(), autocommit=False, autoflush=False)
    barrier = Barrier(2)

    def pause(_index: int):
        session = Session()
        try:
            barrier.wait(timeout=5)
            transition = AgentRuntimeRolloutService(session).pause(
                actor_kind="admin",
                reason_code="manual_pause",
                actor_user_id=user_id,
            )
            return transition.changed
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        changed = list(pool.map(pause, (1, 2)))

    assert sorted(changed) == [False, True]
    db.expire_all()
    assert db.query(AgentRuntimeRolloutEvent).count() == 1


def test_postgres_pause_waits_for_inflight_managed_admission(
    db, auth_user_and_headers, monkeypatch
):
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("requires PostgreSQL row locking")

    from app.config import settings
    from app.services.agent_runtime_rollout import AgentRuntimeRolloutService

    user, _headers = auth_user_and_headers
    user_id = user.id
    monkeypatch.setattr(settings, "agent_runtime_mode", "enforce")
    db.rollback()
    Session = sessionmaker(bind=db.get_bind(), autocommit=False, autoflush=False)
    admission_entered = Event()
    release_admission = Event()
    pause_started = Event()
    original_admit = AgentRuntimeCoordinator.create_or_resume_run

    def delayed_admit(self, **kwargs):
        admission_entered.set()
        assert release_admission.wait(timeout=5)
        return original_admit(self, **kwargs)

    monkeypatch.setattr(
        AgentRuntimeCoordinator,
        "create_or_resume_run",
        delayed_admit,
    )

    def admit():
        session = Session()
        try:
            return AgentRuntimeRolloutService(session).admit_run(
                run_id="run-pause-race",
                attempt_id="attempt-pause-race",
                user_id=user_id,
                conversation_id=None,
                client_turn_id="turn-pause-race",
                origin="test",
                deadline_at=None,
            )
        finally:
            session.close()

    def pause():
        session = Session()
        try:
            pause_started.set()
            return AgentRuntimeRolloutService(session).pause(
                actor_kind="admin",
                reason_code="manual_pause",
                actor_user_id=user_id,
            )
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        admission_future = pool.submit(admit)
        assert admission_entered.wait(timeout=5)
        pause_future = pool.submit(pause)
        assert pause_started.wait(timeout=5)
        assert pause_future.done() is False
        release_admission.set()
        admission = admission_future.result(timeout=5)
        paused = pause_future.result(timeout=5)

    assert admission.admission is not None
    assert paused.changed is True
    db.expire_all()
    assert db.query(AgentRun).filter_by(run_id="run-pause-race").count() == 1


def test_postgres_resume_does_not_hide_older_late_reconciliation_commit(
    db, auth_user_and_headers, monkeypatch
):
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("requires PostgreSQL row locking")

    from datetime import UTC, datetime, timedelta

    from app.config import settings
    from app.services.agent_runtime_rollout import AgentRuntimeRolloutService

    user, _headers = auth_user_and_headers
    user_id = user.id
    monkeypatch.setattr(settings, "agent_runtime_mode", "canary")
    monkeypatch.setattr(settings, "agent_runtime_canary_percent", 100)
    rollout = AgentRuntimeRolloutService(db)
    rollout.get_state()
    rollout.pause(
        actor_kind="admin",
        reason_code="manual_pause",
        actor_user_id=user_id,
    )
    db.rollback()

    Session = sessionmaker(bind=db.get_bind(), autocommit=False, autoflush=False)
    resume_has_lock = Event()
    release_resume = Event()
    reconciliation_started = Event()
    old_finished_at = datetime.now(UTC) - timedelta(minutes=1)

    def resume():
        session = Session()
        original_commit = session.commit

        def delayed_commit():
            resume_has_lock.set()
            assert release_resume.wait(timeout=5)
            original_commit()

        session.commit = delayed_commit
        try:
            return AgentRuntimeRolloutService(session).resume(
                actor_user_id=user_id,
                expected_reconciliation_generation=0,
            )
        finally:
            session.close()

    def commit_reconciliation():
        session = Session()
        try:
            session.add(
                AgentRun(
                    run_id="run-late-reconciliation-commit",
                    user_id=user_id,
                    client_turn_id="turn-late-reconciliation-commit",
                    status="reconciliation_required",
                    current_attempt_id="attempt-late-reconciliation-commit",
                    origin="test",
                    privacy_mode="cloud",
                    created_at=old_finished_at,
                    started_at=old_finished_at,
                    finished_at=old_finished_at,
                    error_code="write_uncertain",
                )
            )
            reconciliation_started.set()
            AgentRuntimeRolloutService(session).record_reconciliation()
            session.commit()
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        resume_future = pool.submit(resume)
        assert resume_has_lock.wait(timeout=5)
        reconciliation_future = pool.submit(commit_reconciliation)
        assert reconciliation_started.wait(timeout=5)
        assert reconciliation_future.done() is False
        release_resume.set()
        resumed = resume_future.result(timeout=5)
        reconciliation_future.result(timeout=5)

    assert resumed.status == "active"
    db.expire_all()
    evaluation = AgentRuntimeRolloutService(db).evaluate_and_maybe_pause()
    assert evaluation.reason_code == "reconciliation_detected"
    assert evaluation.transition.status == "paused"


def test_different_conversations_can_each_hold_an_active_run(db, auth_user_and_headers):
    user, _headers = auth_user_and_headers
    conversations = [
        AgentConversation(
            user_id=user.id,
            title=f"conversation-{index}",
            session_key=f"runtime-parallel-{index}",
        )
        for index in (1, 2)
    ]
    db.add_all(conversations)
    db.commit()
    runtime = AgentRuntimeCoordinator(db)

    for index, conversation in enumerate(conversations, start=1):
        runtime.create_or_resume_run(
            run_id=f"run-parallel-{index}",
            attempt_id=f"attempt-parallel-{index}",
            user_id=user.id,
            conversation_id=conversation.id,
            client_turn_id=f"turn-parallel-{index}",
            origin="test",
        )

    assert db.query(AgentRun).filter(AgentRun.status == "queued").count() == 2


def test_same_client_turn_lifecycle_is_serialized(db, auth_user_and_headers):
    user, _headers = auth_user_and_headers
    conversation = AgentConversation(
        user_id=user.id,
        title="runtime-same-turn",
        session_key="runtime-same-turn",
    )
    db.add(conversation)
    db.commit()
    runtime = AgentRuntimeCoordinator(db)
    admission = runtime.create_or_resume_run(
        run_id="run-same-turn",
        attempt_id="attempt-same-turn",
        user_id=user.id,
        conversation_id=conversation.id,
        client_turn_id="turn-same-turn",
        origin="test",
    )
    context = admission.context
    db.rollback()
    Session = sessionmaker(bind=db.get_bind(), autocommit=False, autoflush=False)

    def run_concurrently(action):
        barrier = Barrier(2)

        def invoke(_index: int):
            session = Session()
            try:
                barrier.wait(timeout=5)
                coordinator = AgentRuntimeCoordinator(session)
                if action == "start":
                    coordinator.mark_running(context)
                else:
                    coordinator.complete(context, status="succeeded")
                return None
            except Exception as exc:  # asserted below with the concrete failures
                return exc
            finally:
                session.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(invoke, (1, 2)))

    assert run_concurrently("start") == [None, None]
    assert run_concurrently("complete") == [None, None]

    db.expire_all()
    run = db.query(AgentRun).filter(AgentRun.run_id == context.run_id).one()
    event_names = [
        row.event_name
        for row in db.query(AgentRunEvent)
        .filter(AgentRunEvent.run_id == context.run_id)
        .order_by(AgentRunEvent.sequence_no)
        .all()
    ]
    assert run.status == "succeeded"
    assert event_names == ["run.created", "run.started", "run.succeeded"]


def test_concurrent_write_claims_have_one_owner_without_poisoning_receipt(
    db, auth_user_and_headers
):
    user, _headers = auth_user_and_headers
    runtime = AgentRuntimeCoordinator(db)
    admission = runtime.create_or_resume_run(
        run_id="run-concurrent-tool",
        attempt_id="attempt-concurrent-tool",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-concurrent-tool",
        origin="test",
    )
    runtime.mark_running(admission.context)
    context = admission.context
    fingerprint = hashlib.sha256(b"concurrent-write").hexdigest()
    db.rollback()
    Session = sessionmaker(bind=db.get_bind(), autocommit=False, autoflush=False)
    barrier = Barrier(2)

    def claim(_index: int):
        session = Session()
        try:
            barrier.wait(timeout=5)
            result = AgentRuntimeCoordinator(session).claim_tool_operation(
                context,
                tool_name="health_record",
                effect_class="write",
                operation_fingerprint=fingerprint,
            )
            return result.disposition, result.operation_id
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(claim, (1, 2)))

    assert sorted(disposition for disposition, _ in claims) == [
        "execute",
        "reconcile",
    ]
    assert len({operation_id for _, operation_id in claims}) == 1

    finalize_session = Session()
    try:
        coordinator = AgentRuntimeCoordinator(finalize_session)
        coordinator.finalize_tool_operation(
            context,
            operation_id=claims[0][1],
            status="succeeded",
            resource_type="diet_record",
            resource_id="829",
        )
    finally:
        finalize_session.close()

    db.expire_all()
    operation = db.query(AgentToolOperation).one()
    assert operation.status == "succeeded"
    assert operation.resource_id == "829"


def test_retry_with_conversation_locks_client_turn_before_conversation(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    user, _headers = auth_user_and_headers
    conversation = AgentConversation(
        user_id=user.id,
        title="runtime-retry-lock-order",
        session_key="runtime-retry-lock-order",
    )
    db.add(conversation)
    db.commit()
    runtime = AgentRuntimeCoordinator(db)
    first = runtime.create_or_resume_run(
        run_id="run-retry-lock-order",
        attempt_id="attempt-retry-lock-order-1",
        user_id=user.id,
        conversation_id=None,
        client_turn_id="turn-retry-lock-order",
        origin="test",
    )
    runtime.complete(
        first.context,
        status="failed",
        error_code="request_not_persisted",
        retryable=True,
    )

    acquired_scopes: list[str] = []

    @contextmanager
    def record_lock(_user_id: int, scope: str):
        acquired_scopes.append(scope)
        yield

    monkeypatch.setattr(runtime, "_admission_lock", record_lock)
    runtime.create_or_resume_run(
        run_id="ignored-retry-lock-order",
        attempt_id="attempt-retry-lock-order-2",
        user_id=user.id,
        conversation_id=conversation.id,
        client_turn_id="turn-retry-lock-order",
        origin="test",
    )

    assert acquired_scopes == [
        "client_turn:turn-retry-lock-order",
        f"conversation:{conversation.id}",
    ]
