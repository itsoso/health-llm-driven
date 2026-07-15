def test_private_health_file_never_uses_the_public_download_route(client, tmp_path, monkeypatch):
    from app.api import upload as upload_api

    monkeypatch.setattr(upload_api, "UPLOAD_DIR", str(tmp_path))
    diet_dir = tmp_path / "diet"
    diet_dir.mkdir(parents=True)
    (diet_dir / "legacy.jpg").write_bytes(b"legacy-diet-image")

    assert client.get("/api/v1/upload/files/diet/legacy.jpg").status_code == 401


def test_avatar_remains_public(client, tmp_path, monkeypatch):
    from app.api import upload as upload_api

    monkeypatch.setattr(upload_api, "UPLOAD_DIR", str(tmp_path))
    avatar_dir = tmp_path / "avatar"
    avatar_dir.mkdir(parents=True)
    (avatar_dir / "profile.jpg").write_bytes(b"public-avatar")

    response = client.get("/api/v1/upload/files/avatar/profile.jpg")
    assert response.status_code == 200
    assert response.content == b"public-avatar"


def test_chat_image_requires_its_owner(client, db, auth_user_and_headers, tmp_path, monkeypatch):
    from app.api import upload as upload_api
    from tests.conftest import create_authenticated_user

    owner, owner_headers = auth_user_and_headers
    other, other_token = create_authenticated_user(db)
    monkeypatch.setattr(upload_api, "UPLOAD_DIR", str(tmp_path))
    owner_dir = tmp_path / "chat" / str(owner.id)
    owner_dir.mkdir(parents=True)
    (owner_dir / "meal.jpg").write_bytes(b"private-health-image")
    url = f"/api/v1/upload/files/chat/{owner.id}/meal.jpg"

    assert client.get(url).status_code == 401
    assert client.get(
        url,
        headers={"Authorization": f"Bearer {other_token}"},
    ).status_code == 403
    response = client.get(url, headers=owner_headers)
    assert response.status_code == 200
    assert response.content == b"private-health-image"

    from app.services.chat_utils import build_signed_chat_image_url

    signed_url = build_signed_chat_image_url(owner.id, "meal.jpg")
    signed_response = client.get(signed_url)
    assert signed_response.status_code == 200
    assert signed_response.content == b"private-health-image"
    assert client.get(f"{signed_url}broken").status_code == 401
    from time import time
    from urllib.parse import parse_qs, urlparse

    expires = int(parse_qs(urlparse(signed_url).query)["expires"][0])
    # 客户端(mac/web/mobile)缓存整段会话并从缓存重渲染 transcript,5 分钟 TTL 会被
    # 缓存渲染撞过期 → WebView 401 → 图片 broken(2026-07-15 founder 实测)。chat 走
    # 7 天 capability 窗口覆盖缓存回放缝(chat 可含 L3 医疗影像 + 公开分享撤销窗口,
    # 故不给更长)。
    assert 6 * 24 * 60 * 60 < expires - int(time()) <= 7 * 24 * 60 * 60


def test_legacy_chat_image_is_never_served_by_the_public_route(client, tmp_path, monkeypatch):
    from app.api import upload as upload_api

    monkeypatch.setattr(upload_api, "UPLOAD_DIR", str(tmp_path))
    legacy_dir = tmp_path / "chat"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "legacy.jpg").write_bytes(b"legacy-health-image")

    assert client.get("/api/v1/upload/files/chat/legacy.jpg").status_code == 401


def test_diet_image_requires_owner_or_short_lived_capability(
    client, db, auth_user_and_headers, tmp_path, monkeypatch
):
    from app.api import upload as upload_api
    from app.services.private_uploads import build_signed_private_upload_url
    from tests.conftest import create_authenticated_user

    owner, owner_headers = auth_user_and_headers
    _, other_token = create_authenticated_user(db)
    monkeypatch.setattr(upload_api, "UPLOAD_DIR", str(tmp_path))
    owner_dir = tmp_path / "diet" / str(owner.id)
    owner_dir.mkdir(parents=True)
    (owner_dir / "meal.jpg").write_bytes(b"private-diet-image")
    url = f"/api/v1/upload/files/diet/{owner.id}/meal.jpg"

    assert client.get(url).status_code == 401
    assert client.get(
        url,
        headers={"Authorization": f"Bearer {other_token}"},
    ).status_code == 403
    owner_response = client.get(url, headers=owner_headers)
    assert owner_response.status_code == 200
    assert owner_response.content == b"private-diet-image"

    signed_url = build_signed_private_upload_url("diet", owner.id, "meal.jpg")
    signed_response = client.get(signed_url)
    assert signed_response.status_code == 200
    assert signed_response.content == b"private-diet-image"


def test_legacy_diet_image_requires_server_issued_capability_even_with_a_record(
    client, db, auth_user_and_headers, tmp_path, monkeypatch
):
    from datetime import date

    from app.api import upload as upload_api
    from app.models.daily_health import DietRecord
    from app.services.private_uploads import build_signed_private_upload_url

    owner, owner_headers = auth_user_and_headers
    monkeypatch.setattr(upload_api, "UPLOAD_DIR", str(tmp_path))
    legacy_dir = tmp_path / "diet"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "legacy-meal.jpg").write_bytes(b"legacy-private-diet-image")
    legacy_url = "/api/v1/upload/files/diet/legacy-meal.jpg"
    db.add(DietRecord(
        user_id=owner.id,
        record_date=date.today(),
        meal_type="lunch",
        food_name="旧午餐",
        food_items="旧午餐",
        image_url=legacy_url,
    ))
    db.commit()

    assert client.get(legacy_url, headers=owner_headers).status_code == 404
    records_response = client.get("/api/v1/diet/records/me", headers=owner_headers)
    assert records_response.status_code == 200
    assert records_response.json()[0]["image_url"] is None
    signed_url = build_signed_private_upload_url(
        "diet",
        owner.id,
        "legacy-meal.jpg",
        legacy=True,
    )
    signed_response = client.get(signed_url)
    assert signed_response.status_code == 200
    assert signed_response.content == b"legacy-private-diet-image"


def test_legacy_medical_image_uses_report_ownership_and_other_uses_capability(
    client, db, auth_user_and_headers, tmp_path, monkeypatch
):
    from datetime import date

    from app.api import upload as upload_api
    from app.models.family_health import MedicalReport
    from app.services.private_uploads import build_signed_private_upload_url
    from tests.conftest import create_authenticated_user

    owner, owner_headers = auth_user_and_headers
    _, other_token = create_authenticated_user(db)
    monkeypatch.setattr(upload_api, "UPLOAD_DIR", str(tmp_path))
    medical_dir = tmp_path / "medical"
    other_dir = tmp_path / "other"
    medical_dir.mkdir(parents=True)
    other_dir.mkdir(parents=True)
    (medical_dir / "legacy-report.jpg").write_bytes(b"medical")
    (other_dir / "legacy-other.jpg").write_bytes(b"other")
    db.add(MedicalReport(
        user_id=owner.id,
        report_date=date.today(),
        image_urls=["/api/v1/upload/files/medical/legacy-report.jpg"],
    ))
    db.commit()

    medical_url = "/api/v1/upload/files/medical/legacy-report.jpg"
    assert client.get(medical_url, headers=owner_headers).content == b"medical"
    assert client.get(
        medical_url,
        headers={"Authorization": f"Bearer {other_token}"},
    ).status_code == 404

    signed_other = build_signed_private_upload_url(
        "other",
        owner.id,
        "legacy-other.jpg",
        legacy=True,
    )
    assert client.get(signed_other).content == b"other"


def test_private_upload_filename_contains_owner_scope(auth_user_and_headers):
    from app.api.upload import generate_filename

    owner, _ = auth_user_and_headers
    assert generate_filename("jpeg", "diet", owner.id).startswith(f"diet/{owner.id}/")
    assert generate_filename("jpeg", "medical", owner.id).startswith(f"medical/{owner.id}/")
    assert generate_filename("jpeg", "other", owner.id).startswith(f"other/{owner.id}/")
    assert generate_filename("jpeg", "avatar", owner.id).startswith("avatar/")
