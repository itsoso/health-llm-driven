"""Meal monitoring (准视频 periodic-sampling) service.

Flow (R4: RECORD + FOLLOW-UP only, never diagnose/prescribe/adjust):

  start  -> POST /ambient/meal-sessions          (requires explicit consent)
  frame  -> POST /ambient/meal-sessions/{id}/frames   (one base64 frame, throttled)
  finish -> POST /ambient/meal-sessions/{id}/finish   (batch vision -> DRAFT)
  confirm-> POST /ambient/meal-sessions/{id}/confirm  (writes DietRecord via the
            existing R4 draft gate, ONLY on explicit user confirm)

Frames are stored as ``VisualInputEvent`` rows linked back via
``meta.meal_session_id`` — we reuse that draft-stated table instead of a heavy
new frames table. The session row only tracks lifecycle, consent, frame count,
raw-media TTL and the observational summary.

Throttle: <= MAX_FRAMES_PER_SESSION frames per session and
<= MAX_SESSIONS_PER_DAY sessions per user/day. Over-limit raises
``MealThrottleError`` (mapped to 429) — never a silent drop.

Privacy: raw frame images (``VisualInputEvent.image_uri``) are purged at the
session's ``raw_media_delete_at`` (+7d). Analysis notes / summary persist.

Every vision call + frame ingest writes an ``agent_audit_log`` row (not a silent
batch). The post-meal summary text is run through ``guidance_validator`` AND the
SafetyGuardian guidance red-line rules before it is returned.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.agents import audit
from app.models.ambient_wearable import MealMonitoringSession, VisualInputEvent
from app.models.daily_health import DietRecord
from app.services import ambient_wearables as ambient_svc
from app.services import meal_analysis

logger = logging.getLogger(__name__)

MAX_FRAMES_PER_SESSION = 30
MAX_SESSIONS_PER_DAY = 5
RAW_MEDIA_TTL_DAYS = 7

_ACTIVE_STATUSES = {"active", "analyzing"}


class MealSessionError(Exception):
    """Base error for meal-session operations."""


class MealThrottleError(MealSessionError):
    """Throttle limit hit (mapped to HTTP 429)."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class MealSessionNotFound(MealSessionError):
    """Session does not exist or belongs to another user (mapped to 403/404)."""


class MealSessionState(MealSessionError):
    """Operation invalid for the current session status (mapped to 409)."""


# ─────────────────────── lifecycle ───────────────────────


def start_session(
    db: Session,
    user_id: int,
    *,
    consent: bool,
    source: str = "rokid_glasses",
    device_type: str = "glasses",
    meta: Optional[Dict[str, Any]] = None,
) -> MealMonitoringSession:
    """Start a meal monitoring session. Requires explicit ``consent=True``."""
    if not consent:
        raise MealSessionError("consent_required")

    now = datetime.now(timezone.utc)
    day_start = now - timedelta(days=1)
    today_count = (
        db.query(MealMonitoringSession)
        .filter(
            MealMonitoringSession.user_id == user_id,
            MealMonitoringSession.started_at >= day_start,
        )
        .count()
    )
    if today_count >= MAX_SESSIONS_PER_DAY:
        raise MealThrottleError(
            f"daily session limit reached ({MAX_SESSIONS_PER_DAY}/24h)"
        )

    session = MealMonitoringSession(
        user_id=user_id,
        status="active",
        source=source,
        device_type=device_type,
        started_at=now,
        consent_at=now,
        frame_count=0,
        privacy_class="health_l3",
        raw_media_delete_at=now + timedelta(days=RAW_MEDIA_TTL_DAYS),
        meta=meta,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    audit._write(
        db,
        user_id=user_id,
        agent_type="meal_monitoring",
        action="session_start",
        result_summary=f"meal session {session.id} started (consent)",
        result_detail={"session_id": session.id, "source": source},
    )
    return session


def get_session(db: Session, user_id: int, session_id: int) -> MealMonitoringSession:
    session = (
        db.query(MealMonitoringSession)
        .filter(MealMonitoringSession.id == session_id)
        .first()
    )
    if session is None:
        raise MealSessionNotFound("session not found")
    if session.user_id != user_id:
        # user isolation: never leak another user's session
        raise MealSessionNotFound("session not found")
    return session


def append_frame(
    db: Session,
    user_id: int,
    session_id: int,
    *,
    image_base64: Optional[str] = None,
    image_uri: Optional[str] = None,
    captured_at: Optional[datetime] = None,
    recognition_result: Optional[Dict[str, Any]] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> VisualInputEvent:
    """Append one frame to a session as a draft ``VisualInputEvent``.

    Throttles to ``MAX_FRAMES_PER_SESSION`` per session (429 over-limit, never a
    silent drop). The frame is stored draft (``status='captured'``) and linked
    back to the session via ``meta.meal_session_id``.
    """
    session = get_session(db, user_id, session_id)
    if session.status not in _ACTIVE_STATUSES:
        raise MealSessionState(f"cannot add frames to a {session.status} session")
    if session.frame_count >= MAX_FRAMES_PER_SESSION:
        raise MealThrottleError(
            f"frame limit reached ({MAX_FRAMES_PER_SESSION}/session)"
        )

    frame_meta = {**(meta or {}), "meal_session_id": session_id}
    if image_base64:
        # store the raw image inline (purged at raw_media_delete_at). Keep the
        # base64 in image_uri so the finish path can run vision on it.
        frame_meta["has_inline_image"] = True

    event = ambient_svc.create_visual_input_event(
        db,
        user_id,
        intent="food_scan",
        source=session.source,
        device_type=session.device_type,
        image_uri=image_uri or (f"inline-base64:{len(image_base64)}b" if image_base64 else None),
        recognition_result=recognition_result,
        captured_at=captured_at,
        status="captured",
        target_type="meal_frame",
        target_id=session_id,
        meta={**frame_meta, **({"image_base64": image_base64} if image_base64 else {})},
        flush=False,
    )
    session.frame_count = session.frame_count + 1
    db.commit()
    db.refresh(event)
    db.refresh(session)
    audit._write(
        db,
        user_id=user_id,
        agent_type="meal_monitoring",
        action="frame_ingest",
        result_summary=f"session {session_id} frame {session.frame_count}",
        result_detail={"session_id": session_id, "frame_event_id": event.id,
                       "has_recognition": recognition_result is not None},
    )
    return event


def list_frames(db: Session, user_id: int, session_id: int) -> List[VisualInputEvent]:
    get_session(db, user_id, session_id)  # isolation check
    return (
        db.query(VisualInputEvent)
        .filter(
            VisualInputEvent.user_id == user_id,
            VisualInputEvent.target_type == "meal_frame",
            VisualInputEvent.target_id == session_id,
        )
        .order_by(VisualInputEvent.captured_at.asc(), VisualInputEvent.id.asc())
        .all()
    )


# ─────────────────────── batch analysis ───────────────────────


async def finish_session(
    db: Session,
    user_id: int,
    session_id: int,
) -> Dict[str, Any]:
    """Batch-analyze the session's frames into a DRAFT summary.

    - Frames that already carry a ``recognition_result`` (client-side vision) are
      used as-is. Frames with an inline base64 image but no recognition are run
      through the existing vision provider (each vision call is audited).
    - Foods are deduped across frames; the meal total is computed once.
    - Produces a DRAFT food/nutrition summary (status -> needs_confirmation,
      target_type -> diet_draft). NO DietRecord is written here (R4).
    - Adds a FuelStrategist OBSERVATIONAL post-meal summary, sanitized + checked
      by the guidance red-line rules.

    Analysis details live in ``meal_analysis`` (kept separate for the complexity
    budget). Returns the draft summary dict (also persisted to ``session.summary``).
    """
    session = get_session(db, user_id, session_id)
    if session.status == "confirmed":
        raise MealSessionState("session already confirmed")
    if session.status == "aborted":
        raise MealSessionState("session already aborted")

    session.status = "analyzing"
    session.ended_at = datetime.now(timezone.utc)
    db.commit()

    frames = list_frames(db, user_id, session_id)
    per_frame, vision_calls = await meal_analysis.analyze_frames(
        db, user_id, session_id, frames
    )
    foods = meal_analysis.dedup_foods(per_frame)
    totals = meal_analysis.meal_totals(foods)

    summary = meal_analysis.build_finish_summary(
        db,
        user_id,
        session_id,
        foods=foods,
        totals=totals,
        frame_count=len(frames),
        vision_calls=vision_calls,
    )

    session.status = "needs_confirmation"
    session.summary = summary
    session.target_type = "diet_draft"
    db.commit()
    db.refresh(session)

    audit._write(
        db,
        user_id=user_id,
        agent_type="meal_monitoring",
        action="session_finish",
        result_summary=(
            f"session {session_id} -> needs_confirmation, "
            f"{len(foods)} foods, {vision_calls} vision calls"
        ),
        result_detail={
            "session_id": session_id,
            "foods": len(foods),
            "vision_calls": vision_calls,
            "guidance_sanitized": summary.get("guidance_sanitized"),
        },
    )
    return summary


# ─────────────────────── confirm / abort ───────────────────────


def confirm_session(
    db: Session,
    user_id: int,
    session_id: int,
    *,
    meal_type: Optional[str] = None,
) -> Tuple[MealMonitoringSession, Optional[DietRecord]]:
    """On explicit user confirm, write the DietRecord via the existing R4 gate.

    Reuses ``create_food_diet_record_from_visual_event`` with an explicit
    ``meta.confirmed_by_user`` — the ONLY sanctioned write path. The session's
    deduped foods/totals become the recognition payload for that gate.
    """
    session = get_session(db, user_id, session_id)
    if session.status != "needs_confirmation":
        raise MealSessionState(
            f"can only confirm a needs_confirmation session (is {session.status})"
        )
    summary = session.summary if isinstance(session.summary, dict) else {}
    foods = summary.get("foods") or []
    totals = summary.get("totals") or {}
    if not foods:
        raise MealSessionState("nothing to confirm (no recognized foods)")

    recognition = {
        "success": True,
        "foods": foods,
        "total_calories": totals.get("calories"),
        "total_protein": totals.get("protein"),
        "total_carbs": totals.get("carbs"),
        "total_fat": totals.get("fat"),
        "total_fiber": totals.get("fiber"),
    }
    if meal_type:
        recognition["meal_type"] = meal_type

    # A confirm event carrying the explicit user-confirmation signal.
    confirm_meta: Dict[str, Any] = {"confirmed_by_user": True, "meal_session_id": session_id}
    if meal_type:
        confirm_meta["meal_type"] = meal_type
    event = ambient_svc.create_visual_input_event(
        db,
        user_id,
        intent="food_scan",
        source=session.source,
        device_type=session.device_type,
        recognition_result=recognition,
        target_type="meal_session_confirm",
        target_id=session_id,
        meta=confirm_meta,
        flush=True,
    )
    record = ambient_svc.create_food_diet_record_from_visual_event(
        db, user_id, event, flush=True
    )

    session.status = "confirmed"
    session.target_type = "diet_record"
    session.target_id = record.id if record else None
    _purge_raw_media(db, user_id, session_id)  # confirmed: raw frames no longer needed
    db.commit()
    db.refresh(session)

    audit._write(
        db,
        user_id=user_id,
        agent_type="meal_monitoring",
        action="session_confirm",
        result_summary=f"session {session_id} confirmed -> diet_record {record.id if record else None}",
        result_detail={"session_id": session_id,
                       "diet_record_id": record.id if record else None},
    )
    return session, record


def abort_session(db: Session, user_id: int, session_id: int) -> MealMonitoringSession:
    session = get_session(db, user_id, session_id)
    if session.status == "confirmed":
        raise MealSessionState("cannot abort a confirmed session")
    session.status = "aborted"
    session.ended_at = datetime.now(timezone.utc)
    _purge_raw_media(db, user_id, session_id)
    db.commit()
    db.refresh(session)
    audit._write(
        db,
        user_id=user_id,
        agent_type="meal_monitoring",
        action="session_abort",
        result_summary=f"session {session_id} aborted",
        result_detail={"session_id": session_id},
    )
    return session


# ─────────────────────── privacy: raw-media purge ───────────────────────


def _purge_raw_media(db: Session, user_id: int, session_id: int) -> int:
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
        _purge_raw_media(db, session.user_id, session.id)
        session.raw_media_deleted_at = now
        count += 1
    if count:
        db.commit()
    return count
