from pathlib import Path

from app.models.agent_audit_log import AgentAuditLog
from app.models.user import User
from app.services.auth import auth_service


def _auth_headers(user: User) -> dict[str, str]:
    token = auth_service.create_access_token({"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


def test_health_data_export_writes_persistent_audit(client, db, auth_user_and_headers) -> None:
    user, headers = auth_user_and_headers

    response = client.get("/api/v1/export/health-data?data_type=all&format=json", headers=headers)

    assert response.status_code == 200
    audit = db.query(AgentAuditLog).filter_by(
        user_id=user.id,
        action="health_data_exported",
    ).one()
    assert audit.result_detail["format"] == "json"
    assert audit.result_detail["data_type"] == "all"
    assert "content" not in audit.result_detail


def test_doctor_report_export_writes_persistent_audit(client, db, auth_user_and_headers) -> None:
    user, headers = auth_user_and_headers

    response = client.get("/api/v1/doctor-report/export?days=30", headers=headers)

    assert response.status_code == 200
    audit = db.query(AgentAuditLog).filter_by(
        user_id=user.id,
        action="doctor_report_exported",
    ).one()
    assert audit.result_detail == {"days": 30}


def test_admin_mutation_authorization_writes_persistent_audit(client, db) -> None:
    admin = User(
        username="security_admin",
        email="security-admin@example.com",
        hashed_password="unused",
        name="Security Admin",
        is_active=True,
        is_approved=True,
        is_admin=True,
    )
    target = User(
        username="security_target",
        email="security-target@example.com",
        hashed_password="unused",
        name="Security Target",
        is_active=True,
        is_approved=True,
        is_admin=False,
    )
    db.add_all([admin, target])
    db.commit()

    response = client.put(
        f"/api/v1/admin/users/{target.id}/active",
        headers=_auth_headers(admin),
        json={"is_active": False},
    )

    assert response.status_code == 200
    audit = db.query(AgentAuditLog).filter_by(
        user_id=admin.id,
        action="privileged_request_authorized",
    ).one()
    assert audit.result_detail["method"] == "PUT"
    assert audit.result_detail["path"].endswith(f"/admin/users/{target.id}/active")
    assert "body" not in audit.result_detail


def test_sensitive_values_are_not_formatted_into_application_logs() -> None:
    root = Path(__file__).resolve().parents[1]
    prohibited = {
        "app/api/siri.py": ("body_preview={raw[:200]}", "msg={message[:60]}"),
        "app/api/shared_conversation.py": ("-> {share_token}", "-> {shared.share_token}"),
        "app/api/diet.py": ("token=%s error=%s",),
        "app/services/agent_executor.py": (
            "preview={str(response)[:200]}",
            "result={result[:200]}",
            "tap_result[:120]",
        ),
        "app/services/notification/wechat_push.py": (
            "获取微信 access_token 失败: {data}",
            "data={template_data}",
        ),
        "app/services/device_adapters/withings.py": (
            "Withings token exchange failed: {result}",
            "Withings token refresh failed: {result}",
        ),
        "app/api/vision.py": ("raw[:300]",),
        "app/services/pdf_parser.py": ("result_text[:500]", "result_text[:1000]"),
        "app/services/insight_generator.py": ("result_text[:150]",),
        "app/services/memory_dialog_extractor.py": ("raw={raw[:200]!r}",),
    }

    for relative_path, needles in prohibited.items():
        source = (root / relative_path).read_text()
        for needle in needles:
            assert needle not in source, f"sensitive logging remains in {relative_path}: {needle}"
