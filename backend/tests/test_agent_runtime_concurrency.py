from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Barrier

from sqlalchemy.orm import sessionmaker

from app.models.agent_conversation import AgentConversation
from app.models.agent_runtime import AgentRun, AgentRunEvent
from app.services.agent_runtime import AgentRuntimeCoordinator, RunBusyError


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
