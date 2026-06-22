"""Meal-monitoring raw-media privacy purge (L3 image lifecycle).

Split out of ``meal_monitoring`` for the complexity budget: this is the cohesive
privacy concern — strip raw frame images (``image_uri`` + inline base64) while
keeping analysis notes (``recognition_result``). Used both inline on
confirm/abort and by the daily Celery sweep.

Fail-loud: exceptions propagate to the caller; nothing is silently swallowed.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.ambient_wearable import MealMonitoringSession, VisualInputEvent


def purge_raw_media(db: Session, user_id: int, session_id: int) -> int:
    """Strip raw frame images for a session's frames. Returns frames purged.

    Removes ``image_uri`` and any inline base64 from ``meta`` — analysis notes
    (recognition_result) persist, raw images do not.
    """
    frames = (
        db.query(VisualInputEvent)
        .filter(
            VisualInputEvent.user_id == user_id,
            VisualInputEvent.target_type == "meal_frame",
            VisualInputEvent.target_id == session_id,
        )
        .all()
    )
    purged = 0
    for frame in frames:
        changed = False
        if frame.image_uri is not None:
            frame.image_uri = None
            changed = True
        if isinstance(frame.meta, dict) and "image_base64" in frame.meta:
            new_meta = {k: v for k, v in frame.meta.items() if k != "image_base64"}
            new_meta["raw_media_purged"] = True
            frame.meta = new_meta
            changed = True
        if changed:
            purged += 1
    return purged


def purge_expired_raw_media(db: Session, now: Optional[datetime] = None) -> int:
    """Cleanup hook: purge raw frame images for sessions past raw_media_delete_at.

    Wired minimally — intended to be called by a Celery beat task. Returns the
    number of sessions purged. Fail-loud: exceptions propagate to the caller.

    Sessions whose raw media was already purged inline (confirm/abort set
    ``raw_media_deleted_at``) are skipped via the ``is_(None)`` filter.
    """
    now = now or datetime.now(timezone.utc)
    due = (
        db.query(MealMonitoringSession)
        .filter(
            MealMonitoringSession.raw_media_delete_at.isnot(None),
            MealMonitoringSession.raw_media_delete_at <= now,
            MealMonitoringSession.raw_media_deleted_at.is_(None),
        )
        .all()
    )
    count = 0
    for session in due:
        purge_raw_media(db, session.user_id, session.id)
        session.raw_media_deleted_at = now
        count += 1
    if count:
        db.commit()
    return count
