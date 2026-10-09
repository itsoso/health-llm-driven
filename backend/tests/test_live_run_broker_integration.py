"""Opt-in real Redis publishing contract; no worker or health task is executed."""

import os
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse
from uuid import uuid4

import pytest
from celery import Celery
from kombu import Queue


def _local_test_broker_url(value):
    parsed = urlparse(value)
    if (
        parsed.scheme != "redis"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path != "/15"
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("TEST_LIVE_RUN_BROKER_URL must target a credential-free loopback Redis DB 15")
    return value


@pytest.mark.parametrize("value", [
    "redis://example.com:6379/15", "redis://127.0.0.1:6379/0",
    "redis://user:secret@127.0.0.1:6379/15", "memory://",
    "redis://127.0.0.1:6379/15?socket_timeout=99",
])
def test_broker_contract_rejects_nonisolated_targets(value):
    with pytest.raises(ValueError):
        _local_test_broker_url(value)


def test_actual_live_run_publishers_on_ephemeral_redis(monkeypatch):
    value = os.environ.get("TEST_LIVE_RUN_BROKER_URL")
    if not value:
        pytest.skip("requires explicit isolated TEST_LIVE_RUN_BROKER_URL")
    broker = _local_test_broker_url(value)
    from app.tasks.live_run_narrative import generate_narrative
    from app.tasks.live_run_hr_replay import replay_hr_rules

    queue_name = f"test-live-run-{uuid4().hex}"
    queue = Queue(queue_name, routing_key=queue_name)
    app = Celery("live_run_publisher_contract", broker=broker, set_as_current=False)
    app.conf.update(
        task_default_queue=queue_name,
        task_queues=(queue,),
        task_publish_retry=False,
        broker_connection_retry=False,
        broker_connection_timeout=2,
        broker_transport_options={"socket_timeout": 2, "socket_connect_timeout": 2, "max_retries": 0},
        task_ignore_result=True,
        task_serializer="json",
        accept_content=["json"],
    )
    # Patch only the two task instances, never the production app configuration.
    for task in (generate_narrative, replay_hr_rules):
        task = task._get_current_object() if hasattr(task, "_get_current_object") else task
        monkeypatch.setattr(task, "_get_app", lambda: app)
        monkeypatch.setattr(task, "_backend", app.backend)
        # Task execution options cache includes routing from its original app.
        monkeypatch.setattr(task, "_exec_options", None)
    try:
        with app.connection_for_write() as connection:
            connection.ensure_connection(max_retries=0)
            bound_queue = queue(connection)
            bound_queue.declare()
            try:
                before = datetime.now(UTC)
                narrative_result = generate_narrative.delay(12345)
                replay_result = replay_hr_rules.apply_async(args=[12345], countdown=300)
                after = datetime.now(UTC)
                messages = [bound_queue.get(no_ack=False), bound_queue.get(no_ack=False)]
                assert all(message is not None for message in messages)
                by_task = {message.headers["task"]: message for message in messages}
                assert set(by_task) == {generate_narrative.name, replay_hr_rules.name}
                for task, result in ((generate_narrative, narrative_result), (replay_hr_rules, replay_result)):
                    message = by_task[task.name]
                    assert message.headers["id"] == result.id
                    assert message.payload[0] == [12345]
                    assert message.payload[1] == {}
                    assert message.delivery_info["routing_key"] == queue_name
                    message.ack()
                assert by_task[generate_narrative.name].headers["eta"] is None
                eta = datetime.fromisoformat(by_task[replay_hr_rules.name].headers["eta"])
                assert before + timedelta(seconds=300) <= eta <= after + timedelta(seconds=300)
                assert bound_queue.get(no_ack=False) is None
            finally:
                # Delete only this unique queue; never flush any Redis database.
                bound_queue.delete()
    finally:
        app.close()
