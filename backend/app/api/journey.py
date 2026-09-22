"""Authenticated journey endpoints; errors never log city or source payloads."""
import logging
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.schemas.journey import (
    JourneyKind, JourneyWrite, JourneyPlaceResponse, JourneySourcesResponse,
    JourneyMonthResponse, JourneyExportRequest, JourneyExportResponse,
    validated_timezone, month_dates,
)
from app.services import journey
from app.services.journey_sources import list_sources

router = APIRouter(prefix="/journey", tags=["journey"])
logger = logging.getLogger(__name__)


def run(db, operation, *args):
    try:
        return operation(db, *args)
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.error("journey operation failed error_type=%s", type(exc).__name__)
    raise HTTPException(503, "暂时无法处理，请稍后重试") from None


def check_month(month):
    try:
        month_dates(month)
    except ValueError:
        raise HTTPException(422, "月份格式无效") from None


@router.get("/sources", response_model=JourneySourcesResponse)
def sources(kind: JourneyKind, month: str, timezone: str = "Asia/Shanghai", offset: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100), user: User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    check_month(month)
    try:
        validated_timezone(timezone)
    except ValueError:
        raise HTTPException(422, "时区无效") from None
    return run(db, list_sources, user.id, kind, month, timezone, offset, limit)


@router.put("/places/{kind}/{source_id}", response_model=JourneyPlaceResponse)
def put(kind: JourneyKind, source_id: int, payload: JourneyWrite, user: User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    return run(db, journey.put_place, user.id, kind, source_id, payload)


@router.get("/month", response_model=JourneyMonthResponse)
def month(month: str, offset: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100), user: User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    check_month(month)
    return run(db, journey.list_month, user.id, month, offset, limit)


@router.delete("/places/{place_id}", status_code=204)
def delete(place_id: int, expected_version: int = Query(..., gt=0), user: User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    run(db, journey.delete_place, user.id, place_id, expected_version)
    return Response(status_code=204)


@router.post("/export-preview", response_model=JourneyExportResponse)
def export(payload: JourneyExportRequest, user: User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    return run(db, journey.export_preview, user.id, payload)
