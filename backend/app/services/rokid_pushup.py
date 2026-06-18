"""Services for Rokid glasses push-up real-data sessions."""
from datetime import UTC, datetime
import hashlib
import secrets

from sqlalchemy.orm import Session

from app.models.rokid_pushup import RokidPushupEvent, RokidPushupSession
from app.schemas.rokid_pushup import RokidPushupEventCreate


def create_ingest_token() -> str:
    return secrets.token_urlsafe(32)


def hash_ingest_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_matches(token: str, token_hash: str) -> bool:
    return secrets.compare_digest(hash_ingest_token(token), token_hash)


def create_pushup_session(
    db: Session,
    *,
    user_id: int,
    target_reps: int,
    source_device: str,
    meta: dict | None = None,
) -> tuple[RokidPushupSession, str]:
    token = create_ingest_token()
    session = RokidPushupSession(
        user_id=user_id,
        target_reps=target_reps,
        source_device=source_device,
        ingest_token_hash=hash_ingest_token(token),
        meta=meta,
    )
    db.add(session)
    return session, token


def get_owned_session(db: Session, *, session_id: int, user_id: int) -> RokidPushupSession | None:
    return (
        db.query(RokidPushupSession)
        .filter(
            RokidPushupSession.id == session_id,
            RokidPushupSession.user_id == user_id,
        )
        .first()
    )


def add_pushup_event(
    db: Session,
    *,
    session: RokidPushupSession,
    body: RokidPushupEventCreate,
) -> RokidPushupEvent:
    occurred_at = body.occurred_at or datetime.now(UTC)
    event = RokidPushupEvent(
        session_id=session.id,
        user_id=session.user_id,
        event_type=body.event_type,
        reps=body.reps,
        phase=body.phase,
        elbow_angle_deg=body.elbow_angle_deg,
        shoulder_hip_ankle_angle_deg=body.shoulder_hip_ankle_angle_deg,
        visibility=body.visibility,
        quality_score=body.quality_score,
        payload=body.payload,
        occurred_at=occurred_at,
    )
    session.last_event_at = occurred_at
    db.add(event)
    return event


def list_events(
    db: Session,
    *,
    session_id: int,
    user_id: int,
    after_id: int = 0,
    limit: int = 200,
) -> list[RokidPushupEvent]:
    return (
        db.query(RokidPushupEvent)
        .filter(
            RokidPushupEvent.session_id == session_id,
            RokidPushupEvent.user_id == user_id,
            RokidPushupEvent.id > after_id,
        )
        .order_by(RokidPushupEvent.id.asc())
        .limit(limit)
        .all()
    )


def finish_session(session: RokidPushupSession) -> RokidPushupSession:
    session.status = "finished"
    session.ended_at = datetime.now(UTC)
    return session
