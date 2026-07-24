from app.config import settings
from app.models.agent_runtime import AgentRuntimeRolloutEvent


def _legacy_reconciliation_operation(db, user_id: int, *, suffix: str):
    from app.services.agent_runtime import AgentRuntimeCoordinator

    runtime = AgentRuntimeCoordinator(db)
    admission = runtime.create_or_resume_run(
        run_id=f"run-api-reconcile-{suffix}",
        attempt_id=f"attempt-api-reconcile-{suffix}",
        user_id=user_id,
        conversation_id=None,
        client_turn_id=f"turn-api-reconcile-{suffix}",
        origin="test",
    )
    runtime.mark_running(admission.context)
    operation = runtime.claim_tool_operation(
        admission.context,
        tool_name="health_record",
        effect_class="write",
        operation_fingerprint=("a" if suffix == "admin" else "b") * 64,
    )
    runtime.interrupt_active(admission.context)
    return admission, operation


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


def test_runtime_reconciliation_resolution_requires_admin(
    client, db, auth_user_and_headers
):
    user, headers = auth_user_and_headers
    _admission, operation = _legacy_reconciliation_operation(
        db, user.id, suffix="member"
    )

    response = client.post(
        f"/api/v1/monitoring/agent-runtime/operations/{operation.operation_id}/resolve",
        headers=headers,
        json={
            "outcome": "verified_no_effect",
            "verification_method": "database_lookup",
            "reason_code": "record_not_found_after_grace",
        },
    )

    assert response.status_code == 403


def test_admin_can_resolve_legacy_runtime_operation_with_audit(
    client, db, auth_user_and_headers
):
    from app.models.agent_audit_log import AgentAuditLog
    from app.models.agent_runtime import AgentRun, AgentToolOperation

    user, headers = auth_user_and_headers
    user.is_admin = True
    db.commit()
    admission, operation = _legacy_reconciliation_operation(
        db, user.id, suffix="admin"
    )

    payload = {
        "outcome": "verified_no_effect",
        "verification_method": "database_lookup",
        "reason_code": "record_not_found_after_grace",
    }
    response = client.post(
        f"/api/v1/monitoring/agent-runtime/operations/{operation.operation_id}/resolve",
        headers=headers,
        json=payload,
    )
    repeated = client.post(
        f"/api/v1/monitoring/agent-runtime/operations/{operation.operation_id}/resolve",
        headers=headers,
        json=payload,
    )

    assert response.status_code == 200
    assert repeated.status_code == 200
    assert response.json() == {
        "operation_id": operation.operation_id,
        "disposition": "verified_no_effect",
        "reason_code": "reconciled_no_effect",
        "resource_type": None,
        "resource_id": None,
    }
    db.expire_all()
    run = db.query(AgentRun).filter_by(run_id=admission.context.run_id).one()
    stored = db.query(AgentToolOperation).filter_by(
        operation_id=operation.operation_id
    ).one()
    audits = db.query(AgentAuditLog).filter_by(
        agent_type="agent_runtime",
        action="tool_operation_reconciled",
    ).order_by(AgentAuditLog.id).all()
    assert run.status == "failed"
    assert run.retryable is True
    assert stored.status == "failed"
    assert stored.error_code == "reconciled_no_effect"
    assert len(audits) == 2
    assert all(audit.user_id == user.id for audit in audits)
    assert audits[0].result_detail == {
        "admin_user_id": user.id,
        "operation_id": operation.operation_id,
        "outcome": "verified_no_effect",
        "run_id": admission.context.run_id,
        "verification_method": "database_lookup",
        "reason_code": "record_not_found_after_grace",
    }


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
    assert payload["snapshot"]["integrity"] == {
        "window_runs": 0,
        "contract_snapshot_runs": 0,
        "contract_snapshot_coverage_percent": 100,
        "contract_versions": {},
        "settled_message_linkage_gaps": 0,
        "missing_current_attempt_runs": 0,
        "active_over_deadline_runs": 0,
        "waiting_over_24h_runs": 0,
    }
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
