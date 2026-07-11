from datetime import datetime, timedelta, timezone

import pytest
from celery.schedules import crontab

from app.models.daily_health import DietPhotoDraft
from app.models.user import User


def test_purge_expired_diet_photo_drafts_removes_private_images(
    db, tmp_path, monkeypatch
):
    from app.api import upload as upload_api
    from app.api.diet import purge_expired_diet_photo_drafts

    user = User(
        username="photo-draft-user",
        email="photo-draft@example.com",
        hashed_password="hashed",
        name="Photo Draft",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    upload_root = tmp_path / "uploads"
    image_path = upload_root / "diet" / str(user.id) / "expired.png"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n")
    monkeypatch.setattr(upload_api, "UPLOAD_DIR", str(upload_root))

    draft = DietPhotoDraft(
        token="expired-photo-draft-token-123456",
        user_id=user.id,
        image_url=f"/api/v1/upload/files/diet/{user.id}/expired.png",
        image_type="png",
        recognition_result={"success": True},
        status="pending",
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    db.add(draft)
    db.commit()

    purged = purge_expired_diet_photo_drafts(db)

    assert purged == 1
    assert db.query(DietPhotoDraft).filter(DietPhotoDraft.token == draft.token).first() is None
    assert not image_path.exists()


def test_purge_expired_diet_photo_drafts_keeps_retry_reference_on_delete_failure(
    db, tmp_path, monkeypatch
):
    from app.api import upload as upload_api
    from app.api import diet as diet_api

    user = User(
        username="photo-draft-retry-user",
        email="photo-draft-retry@example.com",
        hashed_password="hashed",
        name="Photo Draft Retry",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    upload_root = tmp_path / "uploads"
    image_path = upload_root / "diet" / str(user.id) / "retry.png"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"private-image")
    monkeypatch.setattr(upload_api, "UPLOAD_DIR", str(upload_root))
    draft = DietPhotoDraft(
        token="expired-photo-draft-retry-123456",
        user_id=user.id,
        image_url=f"/api/v1/upload/files/diet/{user.id}/retry.png",
        image_type="png",
        recognition_result={"success": True, "foods": [{"name": "隐私餐食"}]},
        status="pending",
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    db.add(draft)
    db.commit()

    monkeypatch.setattr(
        diet_api,
        "_remove_diet_image_file",
        lambda _path: (_ for _ in ()).throw(OSError("disk busy")),
    )

    with pytest.raises(RuntimeError, match="diet_photo_draft_image_purge_failed"):
        diet_api.purge_expired_diet_photo_drafts(db)

    db.expire_all()
    retained = db.query(DietPhotoDraft).filter(DietPhotoDraft.token == draft.token).one()
    assert retained.status == "expired"
    assert retained.recognition_result == {}
    assert retained.image_url.endswith("/retry.png")
    assert image_path.exists()


def test_purge_expired_diet_photo_drafts_never_deletes_consumed_image(
    db, tmp_path, monkeypatch
):
    from app.api import upload as upload_api
    from app.api.diet import purge_expired_diet_photo_drafts

    user = User(
        username="photo-draft-consumed-user",
        email="photo-draft-consumed@example.com",
        hashed_password="hashed",
        name="Photo Draft Consumed",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    upload_root = tmp_path / "uploads"
    image_path = upload_root / "diet" / str(user.id) / "consumed.png"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"record-owned-image")
    monkeypatch.setattr(upload_api, "UPLOAD_DIR", str(upload_root))
    draft = DietPhotoDraft(
        token="consumed-photo-draft-token-123456",
        user_id=user.id,
        image_url=f"/api/v1/upload/files/diet/{user.id}/consumed.png",
        image_type="png",
        recognition_result={"success": True},
        status="consumed",
        expires_at=datetime.now(timezone.utc) - timedelta(days=2),
    )
    db.add(draft)
    db.commit()

    assert purge_expired_diet_photo_drafts(db) == 0
    assert image_path.exists()
    assert db.query(DietPhotoDraft).filter(DietPhotoDraft.token == draft.token).one()


def test_cancelled_photo_draft_scrubs_payload_and_keeps_retry_reference_on_delete_failure(
    db, auth_user_and_headers, monkeypatch
):
    from fastapi import HTTPException

    from app.api import diet as diet_api

    test_user, _ = auth_user_and_headers
    draft = DietPhotoDraft(
        token="cancel-photo-draft-retry-123456",
        user_id=test_user.id,
        image_url=f"/api/v1/upload/files/diet/{test_user.id}/cancel-retry.png",
        image_type="png",
        recognition_result={"success": True, "foods": [{"name": "隐私餐食"}]},
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(draft)
    db.commit()
    monkeypatch.setattr(
        diet_api,
        "_remove_diet_image_file",
        lambda _path: (_ for _ in ()).throw(OSError("disk busy")),
    )

    with pytest.raises(HTTPException) as error:
        diet_api.discard_photo_draft(draft.token, current_user=test_user, db=db)

    assert error.value.status_code == 500
    db.expire_all()
    retained = db.query(DietPhotoDraft).filter(DietPhotoDraft.token == draft.token).one()
    assert retained.status == "cancelled"
    assert retained.recognition_result == {}
    assert retained.image_url.endswith("/cancel-retry.png")


def test_diet_photo_draft_purge_uses_existing_daily_cleanup_schedule():
    from app.celery_app import celery_app

    entry = celery_app.conf.beat_schedule.get("cleanup-expired-data")
    assert entry is not None
    assert entry["task"] == "app.tasks.maintenance.cleanup_expired_data"
    assert entry["schedule"] == crontab(hour=3, minute=0)
