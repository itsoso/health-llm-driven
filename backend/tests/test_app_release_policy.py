"""Remote Config 发布策略 API 的合同测试。"""

from datetime import UTC, datetime, timedelta
import uuid

from app.models.user import User
from app.models.agent_audit_log import AgentAuditLog
from app.services.auth import auth_service


def _headers(user: User) -> dict[str, str]:
    token = auth_service.create_access_token({"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


def _user(db, *, is_admin: bool = False) -> User:
    user = User(
        username=f"release_{uuid.uuid4().hex[:8]}",
        email=f"release_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="hashed_password",
        name="Release Admin" if is_admin else "Release User",
        is_active=True,
        is_approved=True,
        is_admin=is_admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _policy_payload(**overrides):
    payload = {
        "platform": "ios",
        "channel": "production",
        "expected_config_version": 0,
        "ota_enabled": True,
        "rollout_percent": 25,
        "minimum_native_build": "227",
        "recommended_native_build": "228",
        "forced_update": False,
        "kill_switches": {"dynamic_cards": True},
        "rollback_update_id": "019f-good-update",
        "expires_at": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
    }
    payload.update(overrides)
    return payload


def test_client_gets_safe_default_when_no_policy_exists(client, db):
    user = _user(db)

    response = client.get(
        "/api/v1/app-release-policy?platform=ios&channel=production",
        headers=_headers(user),
    )

    assert response.status_code == 200
    assert response.json() == {
        "config_version": 0,
        "platform": "ios",
        "channel": "production",
        "ota_enabled": True,
        "rollout_percent": 100,
        "minimum_native_build": None,
        "recommended_native_build": None,
        "forced_update": False,
        "kill_switches": {},
        "rollback_update_id": None,
        "expires_at": None,
        "source": "safe_default",
    }


def test_admin_publishes_versioned_policy_and_client_reads_it(client, db):
    admin = _user(db, is_admin=True)
    user = _user(db)

    response = client.put(
        "/api/v1/admin/app-release-policy",
        headers=_headers(admin),
        json=_policy_payload(),
    )

    assert response.status_code == 200
    assert response.json()["config_version"] == 1
    assert response.json()["rollout_percent"] == 25
    audit = db.query(AgentAuditLog).filter(
        AgentAuditLog.agent_type == "release_control_plane",
        AgentAuditLog.action == "release_policy_published",
    ).one()
    assert audit.user_id == admin.id
    assert audit.result_detail["channel"] == "production"
    assert "health" not in str(audit.result_detail).lower()

    client_response = client.get(
        "/api/v1/app-release-policy?platform=ios&channel=production",
        headers=_headers(user),
    )
    assert client_response.status_code == 200
    assert client_response.json()["source"] == "remote"
    assert client_response.json()["kill_switches"] == {"dynamic_cards": True}


def test_non_admin_cannot_publish_policy(client, db):
    user = _user(db)

    response = client.put(
        "/api/v1/admin/app-release-policy",
        headers=_headers(user),
        json=_policy_payload(),
    )

    assert response.status_code == 403


def test_admin_rejects_non_boolean_kill_switch(client, db):
    admin = _user(db, is_admin=True)

    response = client.put(
        "/api/v1/admin/app-release-policy",
        headers=_headers(admin),
        json=_policy_payload(kill_switches={"dynamic_cards": "true"}),
    )

    assert response.status_code == 422


def test_admin_cannot_remote_control_medical_rules(client, db):
    admin = _user(db, is_admin=True)

    response = client.put(
        "/api/v1/admin/app-release-policy",
        headers=_headers(admin),
        json=_policy_payload(kill_switches={"medical_rules": True}),
    )

    assert response.status_code == 422


def test_stale_expected_version_is_rejected_without_new_policy(client, db):
    admin = _user(db, is_admin=True)
    headers = _headers(admin)

    first = client.put(
        "/api/v1/admin/app-release-policy",
        headers=headers,
        json=_policy_payload(),
    )
    assert first.status_code == 200

    stale = client.put(
        "/api/v1/admin/app-release-policy",
        headers=headers,
        json=_policy_payload(expected_config_version=0, rollout_percent=50),
    )

    assert stale.status_code == 409
    assert stale.json()["detail"] == "配置版本已变化，请刷新后重试"


def test_expired_policy_falls_back_to_safe_default(client, db):
    admin = _user(db, is_admin=True)
    user = _user(db)

    response = client.put(
        "/api/v1/admin/app-release-policy",
        headers=_headers(admin),
        json=_policy_payload(
            expires_at=(datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
            ota_enabled=False,
            rollout_percent=0,
        ),
    )
    assert response.status_code == 200

    client_response = client.get(
        "/api/v1/app-release-policy?platform=ios&channel=production",
        headers=_headers(user),
    )
    assert client_response.status_code == 200
    assert client_response.json()["source"] == "safe_default"
    assert client_response.json()["ota_enabled"] is True
