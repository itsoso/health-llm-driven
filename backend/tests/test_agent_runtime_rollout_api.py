from app.config import settings
from app.models.agent_runtime import AgentRuntimeRolloutEvent


def _configure(monkeypatch):
    monkeypatch.setattr(settings, "agent_runtime_mode", "canary")
    monkeypatch.setattr(settings, "agent_runtime_canary_percent", 5)
    monkeypatch.setattr(settings, "agent_runtime_canary_user_ids", "11,12")
    monkeypatch.setattr(settings, "agent_runtime_rollout_window_minutes", 15)
    monkeypatch.setattr(settings, "agent_runtime_rollout_min_terminal_runs", 20)
    monkeypatch.setattr(settings, "agent_runtime_rollout_failure_rate_percent", 10)


def test_rollout_monitoring_requires_admin(
    client,
    auth_user_and_headers,
    monkeypatch,
):
    _user, headers = auth_user_and_headers
    _configure(monkeypatch)

    status = client.get(
        "/api/v1/monitoring/agent-runtime/rollout",
        headers=headers,
    )
    pause = client.post(
        "/api/v1/monitoring/agent-runtime/pause",
        headers=headers,
    )
    resume = client.post(
        "/api/v1/monitoring/agent-runtime/resume",
        headers=headers,
    )

    assert status.status_code == 403
    assert pause.status_code == 403
    assert resume.status_code == 403


def test_admin_can_observe_pause_and_resume_without_user_level_data(
    client,
    db,
    auth_user_and_headers,
    monkeypatch,
):
    user, headers = auth_user_and_headers
    user.is_admin = True
    db.commit()
    _configure(monkeypatch)

    initial = client.get(
        "/api/v1/monitoring/agent-runtime/rollout",
        headers=headers,
    )
    first_pause = client.post(
        "/api/v1/monitoring/agent-runtime/pause",
        headers=headers,
    )
    second_pause = client.post(
        "/api/v1/monitoring/agent-runtime/pause",
        headers=headers,
    )
    first_resume = client.post(
        "/api/v1/monitoring/agent-runtime/resume",
        headers=headers,
    )
    second_resume = client.post(
        "/api/v1/monitoring/agent-runtime/resume",
        headers=headers,
    )

    assert initial.status_code == 200
    payload = initial.json()
    assert payload["mode"] == "canary"
    assert payload["canary_percent"] == 5
    assert payload["allowlist_count"] == 2
    assert payload["circuit"]["status"] == "active"
    assert payload["thresholds"] == {
        "window_minutes": 15,
        "min_terminal_runs": 20,
        "failure_rate_percent": 10,
        "reconciliation_runs": 1,
        "stale_active_runs": 1,
    }
    assert payload["snapshot"]["terminal_runs"] == 0
    serialized = repr(payload)
    assert "user_id" not in serialized
    assert "run_id" not in serialized
    assert "prompt" not in serialized
    assert "response" not in serialized

    assert first_pause.status_code == 200
    assert first_pause.json() == {
        "changed": True,
        "status": "paused",
        "reason_code": "manual_pause",
    }
    assert second_pause.json()["changed"] is False
    assert first_resume.status_code == 200
    assert first_resume.json() == {
        "changed": True,
        "status": "active",
        "reason_code": None,
    }
    assert second_resume.json()["changed"] is False
    assert db.query(AgentRuntimeRolloutEvent).count() == 2


def test_rollout_admin_api_has_typed_openapi_responses():
    from main import app

    app.openapi_schema = None
    document = app.openapi()
    paths = document["paths"]

    rollout_schema = paths["/api/v1/monitoring/agent-runtime/rollout"]["get"][
        "responses"
    ]["200"]["content"]["application/json"]["schema"]
    pause_schema = paths["/api/v1/monitoring/agent-runtime/pause"]["post"][
        "responses"
    ]["200"]["content"]["application/json"]["schema"]

    assert rollout_schema["$ref"].endswith("/AgentRuntimeRolloutStatusResponse")
    assert pause_schema["$ref"].endswith("/AgentRuntimeRolloutTransitionResponse")
