from datetime import UTC, datetime, timedelta

import pytest


def test_agent_capacity_enforces_per_user_and_release(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.config import settings
    from app.services.agent_capacity import AgentCapacityController, AgentCapacityExceeded

    user, _ = auth_user_and_headers
    monkeypatch.setattr(settings, "agent_max_active_runs_per_user", 1)
    monkeypatch.setattr(settings, "agent_max_active_runs_global", 100)
    controller = AgentCapacityController(db)

    lease = controller.acquire(user_id=user.id, origin="agent_stream")
    with pytest.raises(AgentCapacityExceeded) as exc_info:
        controller.acquire(user_id=user.id, origin="agent_send")

    assert exc_info.value.scope == "user"
    controller.release(lease.lease_id, user_id=user.id)
    replacement = controller.acquire(user_id=user.id, origin="agent_send")
    assert replacement.user_id == user.id


def test_agent_capacity_enforces_global_limit_across_users(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.config import settings
    from app.services.agent_capacity import AgentCapacityController, AgentCapacityExceeded
    from tests.conftest import create_authenticated_user

    user, _ = auth_user_and_headers
    other, _ = create_authenticated_user(db)
    monkeypatch.setattr(settings, "agent_max_active_runs_per_user", 2)
    monkeypatch.setattr(settings, "agent_max_active_runs_global", 1)
    controller = AgentCapacityController(db)

    controller.acquire(user_id=user.id, origin="agent_stream")
    with pytest.raises(AgentCapacityExceeded) as exc_info:
        controller.acquire(user_id=other.id, origin="agent_stream")

    assert exc_info.value.scope == "global"


def test_expired_agent_capacity_lease_does_not_block_admission(
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.config import settings
    from app.models.agent_capacity import AgentCapacityLease
    from app.services.agent_capacity import AgentCapacityController

    user, _ = auth_user_and_headers
    monkeypatch.setattr(settings, "agent_max_active_runs_per_user", 1)
    monkeypatch.setattr(settings, "agent_max_active_runs_global", 1)
    db.add(
        AgentCapacityLease(
            lease_id="expired-capacity-lease",
            user_id=user.id,
            origin="agent_stream",
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
    )
    db.commit()

    lease = AgentCapacityController(db).acquire(
        user_id=user.id,
        origin="agent_stream",
    )
    assert lease.lease_id != "expired-capacity-lease"


def test_agent_capacity_release_is_scoped_to_owner(db, auth_user_and_headers):
    from app.models.agent_capacity import AgentCapacityLease
    from app.services.agent_capacity import AgentCapacityController
    from tests.conftest import create_authenticated_user

    user, _ = auth_user_and_headers
    other, _ = create_authenticated_user(db)
    controller = AgentCapacityController(db)
    lease = controller.acquire(user_id=user.id, origin="agent_send")

    assert controller.release(lease.lease_id, user_id=other.id) is False
    db.refresh(lease)
    assert lease.released_at is None
    assert controller.release(lease.lease_id, user_id=user.id) is True
    db.refresh(lease)
    assert lease.released_at is not None


@pytest.mark.parametrize("endpoint", ["send", "stream"])
def test_agent_api_rejects_when_user_capacity_is_full(
    endpoint,
    client,
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.config import settings
    from app.models.agent_runtime import AgentRun
    from app.services.agent_capacity import AgentCapacityController

    user, headers = auth_user_and_headers
    monkeypatch.setattr(settings, "agent_runtime_mode", "enforce")
    monkeypatch.setattr(settings, "agent_max_active_runs_per_user", 1)
    monkeypatch.setattr(settings, "agent_max_active_runs_global", 100)
    AgentCapacityController(db).acquire(user_id=user.id, origin="existing")

    response = client.post(
        f"/api/v1/agent/{endpoint}",
        headers=headers,
        json={
            "message": f"capacity test {endpoint}",
            "client_turn_id": f"capacity-full-{endpoint}",
        },
    )

    assert response.status_code == 429
    assert "正在处理" in response.json()["detail"]
    run = db.query(AgentRun).filter(
        AgentRun.user_id == user.id,
        AgentRun.client_turn_id == f"capacity-full-{endpoint}",
    ).one()
    assert run.status == "failed"
    assert run.retryable is True
    assert run.error_code == "capacity_unavailable"


def test_agent_send_releases_capacity_after_completion(
    client,
    db,
    auth_user_and_headers,
    monkeypatch,
):
    from app.models.agent_capacity import AgentCapacityLease

    _, headers = auth_user_and_headers

    async def fake_run_stream(self, **kwargs):
        yield {"event": "token", "data": {"content": "done"}}
        yield {
            "event": "done",
            "data": {
                "conversation_id": 1,
                "message_id": 2,
                "elapsed_ms": 1,
            },
        }

    monkeypatch.setattr(
        "app.services.agent_executor.AgentExecutor.run_stream",
        fake_run_stream,
    )
    response = client.post(
        "/api/v1/agent/send",
        headers=headers,
        json={"message": "capacity release test"},
    )

    assert response.status_code == 200
    leases = db.query(AgentCapacityLease).all()
    assert len(leases) == 1
    assert leases[0].released_at is not None
