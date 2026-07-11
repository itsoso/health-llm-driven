from datetime import datetime, timedelta, timezone

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
    db.refresh(draft)
    assert draft.status == "expired"
    assert draft.image_url is None
    assert not image_path.exists()


def test_diet_photo_draft_purge_uses_existing_daily_cleanup_schedule():
    from app.celery_app import celery_app

    entry = celery_app.conf.beat_schedule.get("cleanup-expired-data")
    assert entry is not None
    assert entry["task"] == "app.tasks.maintenance.cleanup_expired_data"
    assert entry["schedule"] == crontab(hour=3, minute=0)
