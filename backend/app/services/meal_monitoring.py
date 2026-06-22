"""Meal monitoring (准视频 periodic-sampling) service.

Flow (R4: RECORD + FOLLOW-UP only, never diagnose/prescribe/adjust):
start -> frame(s) -> finish (batch vision -> DRAFT) -> confirm (writes DietRecord
via the existing R4 draft gate, ONLY on explicit user confirm) / abort (purge).

Frames are ``VisualInputEvent`` rows linked via ``meta.meal_session_id`` (reuse the
draft-stated table, no heavy frames table). Throttle: <= MAX_FRAMES_PER_SESSION
per session, <= MAX_SESSIONS_PER_DAY per user/day -> ``MealThrottleError`` (429),
never a silent drop. Raw frame images are purged at ``raw_media_delete_at`` (+7d)
or inline on confirm/abort (see ``meal_privacy``); analysis notes persist. Every
vision call + frame ingest writes an ``agent_audit_log`` row.
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
from app.services.meal_privacy import (
    purge_expired_raw_media,  # re-exported (Celery task / tests use this name)
    purge_raw_media as _purge_raw_media,
)

logger = logging.getLogger(__name__)

MAX_FRAMES_PER_SESSION = 30
MAX_SESSIONS_PER_DAY = 5
RAW_MEDIA_TTL_DAYS = 7
# council #11: single-shot /visual-inputs food_scan path has no session lifecycle,
# so it needs its own per-user/day cap (the meal-session path is throttled by
# MAX_SESSIONS_PER_DAY × MAX_FRAMES_PER_SESSION). Cap generously — this is the
# casual "snap one photo" path, not a video stream.
MAX_FOOD_SCANS_PER_DAY = 50

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


class MealSessionAnalysisError(MealSessionError):
    """Finish-time analysis failed; session reset to 'active' so finish can be
    retried (mapped to 503). Never leaves the session stuck in 'analyzing'."""


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
    # council #6: exclude `aborted` sessions from the quota. abort is the
    # privacy-friendly exit (immediate raw-media purge); counting abandons
    # against MAX_SESSIONS_PER_DAY would let 5 quick aborts lock the user out
    # for 24h. Only sessions the user actually carried forward count.
    today_count = (
        db.query(MealMonitoringSession)
        .filter(
            MealMonitoringSession.user_id == user_id,
            MealMonitoringSession.started_at >= day_start,
            MealMonitoringSession.status != "aborted",
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


def check_food_scan_quota(db: Session, user_id: int) -> None:
    """Throttle the single-shot ``/visual-inputs`` food_scan path per user/day.

    council #11: this path has no session lifecycle and was completely
    unthrottled — a buggy/abusive client could write unbounded VisualInputEvent
    rows (and, with confirmed_by_user, DietRecords). Raises ``MealThrottleError``
    (mapped to 429) over-limit — never a silent drop. Counts this user's
    food_scan visual-inputs in the last 24h.
    """
    day_start = datetime.now(timezone.utc) - timedelta(days=1)
    today_count = (
        db.query(VisualInputEvent)
        .filter(
            VisualInputEvent.user_id == user_id,
            VisualInputEvent.intent == "food_scan",
            VisualInputEvent.created_at >= day_start,
        )
        .count()
    )
    if today_count >= MAX_FOOD_SCANS_PER_DAY:
        raise MealThrottleError(
            f"daily food-scan limit reached ({MAX_FOOD_SCANS_PER_DAY}/24h)"
        )


def get_session(
    db: Session, user_id: int, session_id: int, *, for_update: bool = False
) -> MealMonitoringSession:
    query = db.query(MealMonitoringSession).filter(
        MealMonitoringSession.id == session_id
    )
    if for_update:
        # council #2: lock the session row so append_frame and abort_session
        # serialize — prevents a frame inserted after abort's purge query but
        # before its commit from surviving the purge (Postgres; SQLite no-ops).
        query = query.with_for_update()
    session = query.first()
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
    session = get_session(db, user_id, session_id, for_update=True)
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


def _representative_capture_time(
    db: Session, user_id: int, session_id: int
) -> Optional[datetime]:
    """Earliest frame ``captured_at`` for a session (the meal's actual shot time).

    Used to date the confirmed DietRecord to when the food was captured, not when
    the user got around to confirming it. Returns ``None`` when there are no frames
    with a capture time (caller falls back to the session's ``started_at``).
    """
    row = (
        db.query(VisualInputEvent.captured_at)
        .filter(
            VisualInputEvent.user_id == user_id,
            VisualInputEvent.target_type == "meal_frame",
            VisualInputEvent.target_id == session_id,
            VisualInputEvent.captured_at.isnot(None),
        )
        .order_by(VisualInputEvent.captured_at.asc())
        .first()
    )
    return row[0] if row else None


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
    # council #4: lock the session row so finish serializes against a concurrent
    # confirm/abort — without it, finish could read a stale snapshot and overwrite
    # a confirm's/abort's state transition.
    session = get_session(db, user_id, session_id, for_update=True)
    if session.status == "confirmed":
        raise MealSessionState("session already confirmed")
    if session.status == "aborted":
        raise MealSessionState("session already aborted")

    session.status = "analyzing"
    session.ended_at = datetime.now(timezone.utc)
    db.commit()

    # council #3: if analysis raises, never leave the session stuck in
    # 'analyzing' (the user could neither confirm — 409 — nor would think to
    # abort). Reset to 'active' so finish can be retried, then re-raise a
    # recoverable error. Fail-loud: the caller surfaces the failure, we don't
    # fake a summary.
    try:
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
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        recover = get_session(db, user_id, session_id, for_update=True)
        if recover.status == "analyzing":
            recover.status = "active"
            recover.ended_at = None
            db.commit()
        audit._write(
            db,
            user_id=user_id,
            agent_type="meal_monitoring",
            action="session_finish_failed",
            result_summary=f"session {session_id} analysis failed, reset to active: {exc}",
            result_detail={"session_id": session_id, "error": str(exc)},
        )
        raise MealSessionAnalysisError(
            f"meal analysis failed for session {session_id}; retry finish"
        ) from exc

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
    # council #4: lock the row so confirm serializes against a concurrent
    # abort/finish — without the lock, confirm could read a stale snapshot and
    # write a DietRecord while abort is purging (or vice versa).
    session = get_session(db, user_id, session_id, for_update=True)
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
    # council #7: the DietRecord's record_date / meal_type / meal_time are derived
    # from the confirm event's captured_at (see create_food_diet_record_from_visual_event).
    # Default-now() would land a cross-day confirm (shot 23:50, confirmed 00:10) on
    # the wrong day. Use the actual capture time — the earliest frame's captured_at,
    # falling back to the session's started_at.
    captured_at = _representative_capture_time(db, user_id, session_id) or session.started_at
    event = ambient_svc.create_visual_input_event(
        db,
        user_id,
        intent="food_scan",
        source=session.source,
        device_type=session.device_type,
        recognition_result=recognition,
        captured_at=captured_at,
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
    # council #5: record WHEN raw media was purged so (a) the audit trail shows
    # the L3 images were deleted and (b) the daily Celery sweep stops re-scanning
    # this session forever (it filters on raw_media_deleted_at.is_(None)).
    session.raw_media_deleted_at = datetime.now(timezone.utc)
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
    session = get_session(db, user_id, session_id, for_update=True)
    if session.status == "confirmed":
        raise MealSessionState("cannot abort a confirmed session")
    session.status = "aborted"
    session.ended_at = datetime.now(timezone.utc)
    _purge_raw_media(db, user_id, session_id)
    # council #5: same as confirm — mark the purge time so the audit trail is
    # complete and the daily sweep doesn't re-scan this aborted session forever.
    session.raw_media_deleted_at = datetime.now(timezone.utc)
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


# Raw-media purge logic lives in ``meal_privacy`` (complexity budget — the cohesive
# L3 image lifecycle concern). ``purge_expired_raw_media`` is re-exported above for
# the stable ``meal_monitoring.purge_expired_raw_media`` entry point (Celery / tests);
# ``_purge_raw_media`` is the internal alias used by confirm/abort.
