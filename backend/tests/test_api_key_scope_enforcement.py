"""API keys must never inherit the full authority of a user JWT."""

import hashlib
import uuid

from main import app
from app.models.user import User
from app.models.user_api_key import UserApiKey


def _create_user(db, *, admin: bool = False) -> User:
    user = User(
        username=f"api_key_user_{uuid.uuid4().hex[:10]}",
        email=f"api_key_{uuid.uuid4().hex[:10]}@example.com",
        hashed_password="hashed_password",
        name="API Key 用户",
        is_active=True,
        is_approved=True,
        is_admin=admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _headers_for_key(db, user: User, scopes: str) -> tuple[dict[str, str], str]:
    raw_key = f"test-api-key-{uuid.uuid4().hex}"
    db.add(
        UserApiKey(
            user_id=user.id,
            name="security-test",
            api_key=hashlib.sha256(raw_key.encode()).hexdigest(),
            scopes=scopes,
            is_active=True,
        )
    )
    db.commit()
    return {"X-API-Key": raw_key}, raw_key


def test_read_only_key_can_read_own_health_data(client, db):
    user = _create_user(db)
    headers, _ = _headers_for_key(db, user, "read")

    response = client.get(f"/api/v1/diseases/user/{user.id}", headers=headers)

    assert response.status_code == 200
    assert response.json() == []


def test_read_only_key_cannot_write_health_data(client, db):
    user = _create_user(db)
    headers, _ = _headers_for_key(db, user, "read")

    response = client.post(
        "/api/v1/daily-health/water",
        headers=headers,
        json={"user_id": user.id, "record_date": "2026-07-21", "amount": 250},
    )

    assert response.status_code == 403
    assert "write" in response.json()["detail"]


def test_write_only_key_cannot_read_health_data(client, db):
    user = _create_user(db)
    headers, _ = _headers_for_key(db, user, "write")

    response = client.get(f"/api/v1/diseases/user/{user.id}", headers=headers)

    assert response.status_code == 403
    assert "read" in response.json()["detail"]


def test_write_key_can_write_ordinary_owned_health_data(client, db):
    user = _create_user(db)
    headers, _ = _headers_for_key(db, user, "write")

    response = client.post(
        "/api/v1/daily-health/water",
        headers=headers,
        json={"user_id": user.id, "record_date": "2026-07-21", "amount": 250},
    )

    assert response.status_code == 200


def test_api_key_cannot_change_account_password(client, db):
    user = _create_user(db)
    headers, _ = _headers_for_key(db, user, "read,write")

    response = client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"old_password": "old-password", "new_password": "new-password"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "该操作不允许使用 API Key"


def test_api_key_cannot_manage_api_keys(client, db):
    user = _create_user(db)
    headers, _ = _headers_for_key(db, user, "read,write")

    response = client.get("/api/v1/user-api-keys", headers=headers)

    assert response.status_code == 403
    assert response.json()["detail"] == "该操作不允许使用 API Key"


def test_admin_api_key_cannot_call_admin_endpoints(client, db):
    user = _create_user(db, admin=True)
    headers, _ = _headers_for_key(db, user, "read,write")

    response = client.get("/api/v1/admin/stats", headers=headers)

    assert response.status_code == 403
    assert response.json()["detail"] == "该操作不允许使用 API Key"


def test_disabled_user_api_key_cannot_ingest_health_events(client, db):
    user = _create_user(db)
    headers, _ = _headers_for_key(db, user, "write")
    user.is_active = False
    db.commit()

    response = client.post(
        "/api/v1/health-events/ingest",
        headers=headers,
        json={
            "event_type": "exercise",
            "source": "api",
            "raw_data": {"activity": "walking"},
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "账户已被禁用"


def test_disabled_user_api_key_cannot_read_external_health_data(client, db):
    user = _create_user(db)
    headers, _ = _headers_for_key(db, user, "read")
    user.is_active = False
    db.commit()

    response = client.get("/api/v1/external/health-data", headers=headers)

    assert response.status_code == 403
    assert response.json()["detail"] == "账户已被禁用"


def test_invalid_api_key_logs_do_not_include_key_material(client, caplog):
    raw_key = "visible-prefix-must-not-be-logged"

    response = client.get("/api/v1/diseases/user/1", headers={"X-API-Key": raw_key})

    assert response.status_code == 401
    assert raw_key not in caplog.text
    assert raw_key[:8] not in caplog.text


def test_api_key_entrypoints_keep_x_api_key_in_openapi_contract():
    document = app.openapi()

    for path, method in (
        ("/api/v1/health-events/ingest", "post"),
        ("/api/v1/workout/post-run-analyze-siri", "post"),
        ("/api/v1/external/health-data", "get"),
    ):
        parameters = document["paths"][path][method].get("parameters", [])
        header_names = {
            parameter["name"].lower()
            for parameter in parameters
            if parameter.get("in") == "header"
        }
        assert "x-api-key" in header_names, path
