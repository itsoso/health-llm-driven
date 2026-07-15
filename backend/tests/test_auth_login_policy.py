"""Login policy must be identical across form and JSON entry points."""

import uuid

from app.models.user import User
from app.services.auth import auth_service


def test_json_login_rejects_unapproved_account(client, db):
    password = "review-policy-test-password"
    username = f"pending_{uuid.uuid4().hex[:10]}"
    user = User(
        username=username,
        email=f"{username}@example.test",
        hashed_password=auth_service.get_password_hash(password),
        name="Pending review user",
        is_active=True,
        is_approved=False,
    )
    db.add(user)
    db.commit()

    response = client.post(
        "/api/v1/auth/login/json",
        json={"username": username, "password": password},
    )

    assert response.status_code == 403
    assert "审核" in response.json()["detail"]
