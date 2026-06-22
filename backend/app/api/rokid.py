"""Rokid device integrations."""
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.rokid_pushup import RokidPushupSession
from app.models.user import User
from app.schemas.rokid_pushup import (
    RokidPushupEventCreate,
    RokidPushupEventListResponse,
    RokidPushupEventResponse,
    RokidPushupSessionCreate,
    RokidPushupSessionCreateResponse,
    RokidPushupSessionFinishResponse,
    RokidPushupSessionResponse,
    RokidPushupSessionReviewResponse,
)
from app.services import rokid_pushup as svc
from app.services import rokid_pushup_review as review_svc

router = APIRouter(prefix="/devices/rokid", tags=["rokid"])


def _events_url(request: Request, session_id: int) -> str:
    return str(request.url_for("ingest_rokid_pushup_event", session_id=session_id))


def _session_open_url(
    *,
    session_id: int,
    target_reps: int,
    ingest_url: str,
    ingest_token: str,
) -> str:
    query = urlencode({
        "session_id": session_id,
        "target_reps": target_reps,
        "ingest_url": ingest_url,
        "ingest_token": ingest_token,
    })
    return f"reva://rokid/pushup?{query}"


@router.post(
    "/pushup-sessions",
    response_model=RokidPushupSessionCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_rokid_pushup_session(
    body: RokidPushupSessionCreate,
    request: Request,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    session, ingest_token = svc.create_pushup_session(
        db,
        user_id=current_user.id,
        target_reps=body.target_reps,
        source_device=body.source_device,
        meta=body.meta,
    )
    db.commit()
    db.refresh(session)
    ingest_url = _events_url(request, session.id)
    return RokidPushupSessionCreateResponse(
        id=session.id,
        user_id=session.user_id,
        status=session.status,
        target_reps=session.target_reps,
        source_device=session.source_device,
        ingest_token=ingest_token,
        ingest_url=ingest_url,
        events_url=ingest_url,
        open_url=_session_open_url(
            session_id=session.id,
            target_reps=session.target_reps,
            ingest_url=ingest_url,
            ingest_token=ingest_token,
        ),
        created_at=session.created_at,
    )


@router.post(
    "/pushup-sessions/{session_id}/events",
    response_model=RokidPushupEventResponse,
    status_code=status.HTTP_201_CREATED,
)
def ingest_rokid_pushup_event(
    session_id: int,
    body: RokidPushupEventCreate,
    x_reva_rokid_session_token: str | None = Header(
        default=None,
        alias="X-Reva-Rokid-Session-Token",
    ),
    db: Session = Depends(get_db),
):
    session = db.query(RokidPushupSession).filter(RokidPushupSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="pushup session not found")
    if not x_reva_rokid_session_token or not svc.token_matches(
        x_reva_rokid_session_token,
        session.ingest_token_hash,
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid rokid session token")

    event = svc.add_pushup_event(db, session=session, body=body)
    db.commit()
    db.refresh(event)
    return RokidPushupEventResponse.model_validate(event)


@router.get(
    "/pushup-sessions/{session_id}/events",
    response_model=RokidPushupEventListResponse,
)
def list_rokid_pushup_events(
    session_id: int,
    after_id: int = 0,
    limit: int = 200,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    session = svc.get_owned_session(db, session_id=session_id, user_id=current_user.id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="pushup session not found")
    events = svc.list_events(
        db,
        session_id=session.id,
        user_id=current_user.id,
        after_id=after_id,
        limit=min(max(limit, 1), 500),
    )
    return RokidPushupEventListResponse(
        events=[RokidPushupEventResponse.model_validate(event) for event in events],
    )


@router.post(
    "/pushup-sessions/{session_id}/finish",
    response_model=RokidPushupSessionFinishResponse,
)
def finish_rokid_pushup_session(
    session_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    session = svc.get_owned_session(db, session_id=session_id, user_id=current_user.id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="pushup session not found")
    svc.finish_session(session)
    db.commit()
    db.refresh(session)
    return RokidPushupSessionFinishResponse(
        session=RokidPushupSessionResponse.model_validate(session),
    )


@router.get(
    "/pushup-sessions/{session_id}/review",
    response_model=RokidPushupSessionReviewResponse,
)
def get_rokid_pushup_session_review(
    session_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """赛后复盘 (R4 观察性): 本组质量指标 + 训练负荷上下文 + 动作要领链接。

    用户隔离: 非本人或不存在的 session → 404。无足够训练负荷数据时降级返回
    session_quality + 中性观察, 不伪造成功也不 500。
    """
    session = svc.get_owned_session(db, session_id=session_id, user_id=current_user.id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="pushup session not found")
    events = svc.list_all_events(db, session_id=session.id, user_id=current_user.id)
    review = review_svc.build_review(db, current_user.id, session, events)
    return RokidPushupSessionReviewResponse(**review)
