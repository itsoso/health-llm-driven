"""通用症状记录 API.

与 disease_tracking 不同, 本 API 不绑 UserDiseaseProfile, 适合偶发症状的低门槛录入.
"""
from datetime import date, datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.symptom_entry import SymptomEntry
from app.models.user import User

router = APIRouter()

# UI / LLM 共享的部位枚举. 改这里时同步 mobile/app/symptom-record.tsx.
VALID_BODY_PARTS = {
    "eye", "respiratory", "skin", "digestive",
    "musculoskeletal", "head", "general", "other",
}


class SymptomCreate(BaseModel):
    body_part: str = Field(..., description="见 VALID_BODY_PARTS")
    description: str = Field(..., min_length=1, max_length=500)
    severity: Optional[int] = Field(None, ge=1, le=10)
    triggers: Optional[List[str]] = None
    duration_minutes: Optional[int] = Field(None, ge=0)
    occurred_at: Optional[datetime] = None
    source: str = Field("manual", pattern="^(manual|voice|siri)$")
    notes: Optional[str] = None


class SymptomUpdate(BaseModel):
    body_part: Optional[str] = Field(None, description="见 VALID_BODY_PARTS")
    description: Optional[str] = Field(None, min_length=1, max_length=500)
    severity: Optional[int] = Field(None, ge=1, le=10)
    triggers: Optional[List[str]] = None
    duration_minutes: Optional[int] = Field(None, ge=0)
    occurred_at: Optional[datetime] = None
    source: Optional[str] = Field(None, pattern="^(manual|voice|siri)$")
    notes: Optional[str] = None


class SymptomResponse(BaseModel):
    id: int
    user_id: int
    occurred_at: datetime
    body_part: str
    description: str
    severity: Optional[int] = None
    triggers: List[str] = []
    duration_minutes: Optional[int] = None
    source: str
    notes: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


def _to_response(e: SymptomEntry) -> SymptomResponse:
    return SymptomResponse(
        id=e.id,
        user_id=e.user_id,
        occurred_at=e.occurred_at,
        body_part=e.body_part,
        description=e.description,
        severity=e.severity,
        triggers=e.triggers or [],
        duration_minutes=e.duration_minutes,
        source=e.source or "manual",
        notes=e.notes,
        created_at=e.created_at,
    )


@router.post("", response_model=SymptomResponse, status_code=status.HTTP_201_CREATED)
def create_symptom(
    payload: SymptomCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    if payload.body_part not in VALID_BODY_PARTS:
        raise HTTPException(status_code=400, detail=f"body_part 必须是 {sorted(VALID_BODY_PARTS)} 之一")

    e = SymptomEntry(
        user_id=current_user.id,
        occurred_at=payload.occurred_at or datetime.utcnow(),
        body_part=payload.body_part,
        description=payload.description,
        severity=payload.severity,
        triggers=payload.triggers or [],
        duration_minutes=payload.duration_minutes,
        source=payload.source,
        notes=payload.notes,
    )
    db.add(e)
    db.commit()
    db.refresh(e)
    return _to_response(e)


@router.get("/me", response_model=List[SymptomResponse])
def list_my_symptoms(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    body_part: Optional[str] = None,
    limit: int = Query(default=50, le=500),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """默认拉最近 30 天."""
    if start_date is None:
        start_date = date.today() - timedelta(days=30)

    q = db.query(SymptomEntry).filter(SymptomEntry.user_id == current_user.id)
    q = q.filter(SymptomEntry.occurred_at >= datetime.combine(start_date, datetime.min.time()))
    if end_date:
        q = q.filter(SymptomEntry.occurred_at <= datetime.combine(end_date, datetime.max.time()))
    if body_part:
        q = q.filter(SymptomEntry.body_part == body_part)

    rows = q.order_by(desc(SymptomEntry.occurred_at)).limit(limit).all()
    return [_to_response(r) for r in rows]


@router.put("/{symptom_id}", response_model=SymptomResponse)
def update_symptom(
    symptom_id: int,
    payload: SymptomUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    e = db.query(SymptomEntry).filter(
        SymptomEntry.id == symptom_id,
        SymptomEntry.user_id == current_user.id,
    ).first()
    if e is None:
        raise HTTPException(status_code=404, detail="不存在")

    data = payload.model_dump(exclude_unset=True)
    if "body_part" in data and data["body_part"] not in VALID_BODY_PARTS:
        raise HTTPException(status_code=400, detail=f"body_part 必须是 {sorted(VALID_BODY_PARTS)} 之一")
    for key, value in data.items():
        setattr(e, key, value)
    e.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(e)
    return _to_response(e)


@router.delete("/{symptom_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_symptom(
    symptom_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    e = db.query(SymptomEntry).filter(SymptomEntry.id == symptom_id).first()
    if e is None:
        raise HTTPException(status_code=404, detail="不存在")
    if e.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权删除其他用户的数据")
    db.delete(e)
    db.commit()
