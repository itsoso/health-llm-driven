from app.models.agent_audit_log import AgentAuditLog


def test_account_deletion_request_requires_auth(client):
    r = client.post("/api/v1/auth/me/deletion-request")

    assert r.status_code == 401


def test_account_deletion_request_records_audit(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers

    r = client.post("/api/v1/auth/me/deletion-request", headers=headers)

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "requested"
    assert body["user_id"] == user.id
    assert body["estimated_completion_days"] == 7

    audit = (
        db.query(AgentAuditLog)
        .filter(
            AgentAuditLog.user_id == user.id,
            AgentAuditLog.agent_type == "account_privacy",
            AgentAuditLog.action == "account_deletion_requested",
        )
        .one()
    )
    assert audit.result_summary == "用户已在 App 内发起账号与数据删除请求"
    assert audit.result_detail["requested_by"] == "self"
    assert audit.result_detail["channel"] == "mobile_app"
