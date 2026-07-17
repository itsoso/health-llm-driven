from app.models.agent_audit_log import AgentAuditLog
from app.models.account_deletion_request import AccountDeletionRequest


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
    assert isinstance(body["request_id"], int)
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

    request = db.query(AccountDeletionRequest).filter_by(user_id=user.id).one()
    assert request.id == body["request_id"]
    assert request.active_user_id == user.id
    assert request.status == "requested"


def test_account_deletion_request_is_idempotent_and_queryable(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers

    first = client.post("/api/v1/auth/me/deletion-request", headers=headers)
    second = client.post("/api/v1/auth/me/deletion-request", headers=headers)
    status_response = client.get("/api/v1/auth/me/deletion-request", headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert status_response.status_code == 200
    assert second.json()["request_id"] == first.json()["request_id"]
    assert second.json()["existing"] is True
    assert status_response.json()["request_id"] == first.json()["request_id"]
    assert status_response.json()["status"] == "requested"
    assert db.query(AccountDeletionRequest).filter_by(user_id=user.id).count() == 1
    assert (
        db.query(AgentAuditLog)
        .filter_by(user_id=user.id, action="account_deletion_requested")
        .count()
        == 1
    )


def test_account_deletion_request_admin_can_claim_processing(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    user.is_admin = True
    db.commit()

    created = client.post("/api/v1/auth/me/deletion-request", headers=headers)
    request_id = created.json()["request_id"]

    listing = client.get("/api/v1/admin/account-deletion-requests", headers=headers)
    claimed = client.patch(
        f"/api/v1/admin/account-deletion-requests/{request_id}",
        headers=headers,
        json={"status": "processing", "note": "已进入人工核验"},
    )

    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["requests"][0]["request_id"] == request_id
    assert claimed.status_code == 200
    assert claimed.json()["status"] == "processing"
    db.refresh(db.query(AccountDeletionRequest).filter_by(id=request_id).one())
    request = db.query(AccountDeletionRequest).filter_by(id=request_id).one()
    assert request.processing_admin_id == user.id
    assert request.processing_note == "已进入人工核验"


def test_account_deletion_request_cannot_complete_without_verified_purge(client, db, auth_user_and_headers, monkeypatch):
    user, headers = auth_user_and_headers
    user.is_admin = True
    db.commit()

    created = client.post("/api/v1/auth/me/deletion-request", headers=headers)
    request_id = created.json()["request_id"]
    client.patch(
        f"/api/v1/admin/account-deletion-requests/{request_id}",
        headers=headers,
        json={"status": "processing", "note": "正在执行删除清单"},
    )

    unverified = client.patch(
        f"/api/v1/admin/account-deletion-requests/{request_id}",
        headers=headers,
        json={"status": "completed", "note": "完成"},
    )
    monkeypatch.setattr(
        "app.api.admin.build_deletion_verification_report",
        lambda db, user_id: {"can_finalize": True, "scope_digest": "a" * 64},
    )
    verified = client.patch(
        f"/api/v1/admin/account-deletion-requests/{request_id}",
        headers=headers,
        json={
            "status": "completed",
            "note": "已按删除清单核验",
            "data_deletion_verified": True,
            "verification_reference": "ops-20260714-42",
        },
    )

    assert unverified.status_code == 409
    assert "清除核验" in unverified.json()["detail"]
    assert verified.status_code == 200
    assert verified.json()["status"] == "completed"
    assert verified.json()["verification_reference"] == "ops-20260714-42"
