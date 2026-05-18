import uuid
from datetime import date


def _create_user(db, *, approved: bool = True):
    from app.models.user import User

    user = User(
        username=f"testuser_{uuid.uuid4().hex[:8]}",
        email=f"test_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="hashed_password",
        name="测试用户",
        birth_date=date(1990, 1, 1),
        gender="男",
        is_active=True,
        is_approved=approved,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _auth_headers_for_user(db, user_id: int):
    from app.services.auth import auth_service

    token = auth_service.create_access_token({"sub": str(user_id)})
    return {"Authorization": f"Bearer {token}"}


def test_wechat_update_user_info_requires_auth(client):
    resp = client.put("/api/v1/wechat/user/info", json={"nickname": "新昵称"})
    assert resp.status_code == 401


def test_wechat_update_user_info_updates_current_user_fields(client, db):
    user = _create_user(db)
    headers = _auth_headers_for_user(db, user.id)

    payload = {
        "nickname": "小明",
        "avatar_url": "https://example.com/avatar.png",
        "gender": "女",
        "phone": "13900000000",
    }
    resp = client.put("/api/v1/wechat/user/info", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["user"]["user_id"] == user.id
    assert data["user"]["nickname"] == "小明"
    assert data["user"]["avatar_url"] == "https://example.com/avatar.png"
    assert data["user"]["gender"] == "女"
    assert data["user"]["phone"] == "13900000000"

    db.refresh(user)
    assert user.name == "小明"
    assert user.avatar_url == "https://example.com/avatar.png"
    assert user.gender == "女"
    assert user.phone == "13900000000"


def test_wechat_check_garmin_binding_requires_auth(client, db):
    user = _create_user(db)
    resp = client.get(f"/api/v1/wechat/check-bindding/{user.id}")
    assert resp.status_code == 401


def test_wechat_check_garmin_binding_blocks_other_user(client, db):
    user_a = _create_user(db)
    user_b = _create_user(db)

    headers_a = _auth_headers_for_user(db, user_a.id)
    resp = client.get(f"/api/v1/wechat/check-bindding/{user_b.id}", headers=headers_a)
    assert resp.status_code == 403


def test_wechat_check_garmin_binding_returns_status_for_self(client, db):
    from app.models.user import GarminCredential

    user = _create_user(db)
    db.add(
        GarminCredential(
            user_id=user.id,
            garmin_email="test@example.com",
            encrypted_password="encrypted",
            sync_enabled=True,
            credentials_valid=False,
        )
    )
    db.commit()

    headers = _auth_headers_for_user(db, user.id)
    resp = client.get(f"/api/v1/wechat/check-bindding/{user.id}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_garmin"] is True
    assert data["garmin_email"] == "test@example.com"
    assert data["sync_enabled"] is True
    assert data["credentials_valid"] is False
