"""Private no-store daily GPS endpoints; validation never echoes a location."""

import logging
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.schemas.daily_journey import (
    JourneyStart,
    JourneyStateChange,
    JourneyBatch,
    JourneyAnnotations,
    JourneySessionResponse,
    JourneySessionList,
    JourneyUploadResponse,
    JourneyReview,
)
from app.services import daily_journey as service

logger = logging.getLogger(__name__)


class PrivateJourneyRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request):
            try:
                response = await original(request)
            except RequestValidationError:
                response = JSONResponse(
                    status_code=422, content={"detail": "行程参数无效，请检查后重试"}
                )
            except HTTPException as exc:
                response = JSONResponse(
                    status_code=exc.status_code,
                    content={"detail": exc.detail},
                    headers=exc.headers,
                )
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
            return response

        return handler


router = APIRouter(
    prefix="/daily-journeys", tags=["daily-journeys"], route_class=PrivateJourneyRoute
)


def run(db, fn, *args):
    try:
        return fn(db, *args)
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.error("daily journey operation failed error_type=%s", type(exc).__name__)
    raise HTTPException(503, "暂时无法处理行程，请稍后重试") from None


@router.post("/sessions", response_model=JourneySessionResponse)
def start(
    payload: JourneyStart,
    user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    return run(db, service.start_session, user.id, payload)


@router.get("/sessions", response_model=JourneySessionList)
def sessions(
    local_date: date = Query(..., alias="date"),
    user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    return run(db, service.list_sessions, user.id, local_date)


@router.get("/sessions/{session_id}", response_model=JourneySessionResponse)
def get(
    session_id: UUID,
    user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    return run(db, service.get_session, user.id, session_id)


@router.post("/sessions/{session_id}/state", response_model=JourneySessionResponse)
def state(
    session_id: UUID,
    payload: JourneyStateChange,
    user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    return run(db, service.change_state, user.id, session_id, payload)


@router.post("/sessions/{session_id}/points", response_model=JourneyUploadResponse)
def points(
    session_id: UUID,
    payload: JourneyBatch,
    user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    return run(db, service.upload_points, user.id, session_id, payload)


@router.get("/sessions/{session_id}/review", response_model=JourneyReview)
def review(
    session_id: UUID,
    user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    return run(db, service.review_session, user.id, session_id)


@router.patch(
    "/sessions/{session_id}/annotations", response_model=JourneySessionResponse
)
def annotations(
    session_id: UUID,
    payload: JourneyAnnotations,
    user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    return run(db, service.annotate_session, user.id, session_id, payload)


@router.delete("/sessions/{session_id}", status_code=204)
def delete(
    session_id: UUID,
    user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    run(db, service.delete_session, user.id, session_id)
    return Response(status_code=204)
