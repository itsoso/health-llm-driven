"""女性健康 API"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional, List
from pydantic import BaseModel

from app.database import get_db
from app.models.user import User
from app.api.deps import get_current_user_required
from app.services.womens_health_service import womens_health_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/womens-health", tags=["女性健康"])


class PeriodStartRequest(BaseModel):
    start_date: str
    flow_intensity: str = "moderate"


class PeriodEndRequest(BaseModel):
    end_date: str


class SymptomRequest(BaseModel):
    record_date: str
    symptom_type: str
    severity: int = 1
    notes: Optional[str] = None


@router.post("/period/start")
async def start_period(
    data: PeriodStartRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """记录经期开始"""
    logger.info(f"[WomensHealthAPI] 用户 {current_user.id} 记录经期开始")
    from datetime import date as dt_date
    cycle = womens_health_service.start_period(
        db=db,
        user_id=current_user.id,
        start_date=dt_date.fromisoformat(data.start_date),
        flow_intensity=data.flow_intensity,
    )
    return _serialize_cycle(cycle)


@router.post("/period/{cycle_id}/end")
async def end_period(
    cycle_id: int,
    data: PeriodEndRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """记录经期结束"""
    logger.info(f"[WomensHealthAPI] 用户 {current_user.id} 结束经期: {cycle_id}")
    from datetime import date as dt_date
    cycle = womens_health_service.end_period(
        db=db,
        user_id=current_user.id,
        cycle_id=cycle_id,
        end_date=dt_date.fromisoformat(data.end_date),
    )
    if not cycle:
        raise HTTPException(status_code=404, detail="周期记录不存在")
    return _serialize_cycle(cycle)


@router.get("/cycles/me")
async def get_my_cycles(
    limit: int = Query(default=12, le=50),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取我的周期列表"""
    cycles = womens_health_service.get_cycles(db, current_user.id, limit)
    return [_serialize_cycle(c) for c in cycles]


@router.get("/predict/me")
async def predict_next_period(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """预测下次经期"""
    prediction = womens_health_service.predict_next_period(db, current_user.id)
    if not prediction:
        return {"prediction": None, "message": "数据不足，无法预测"}
    return {"prediction": prediction}


@router.post("/symptoms")
async def log_symptom(
    data: SymptomRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """记录症状"""
    logger.info(f"[WomensHealthAPI] 用户 {current_user.id} 记录症状: {data.symptom_type}")
    symptom = womens_health_service.log_symptom(
        db=db,
        user_id=current_user.id,
        data=data.model_dump(),
    )
    return {
        "id": symptom.id,
        "record_date": str(symptom.record_date),
        "symptom_type": symptom.symptom_type,
        "severity": symptom.severity,
        "notes": symptom.notes,
    }


@router.get("/stats/me")
async def get_cycle_stats(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取周期统计"""
    return womens_health_service.get_cycle_stats(db, current_user.id)


@router.get("/calendar/me")
async def get_calendar(
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取日历数据"""
    return womens_health_service.get_calendar(db, current_user.id, year, month)


@router.get("/symptoms/me")
async def get_my_symptoms(
    cycle_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取我的症状列表"""
    from datetime import date as dt_date
    sd = dt_date.fromisoformat(start_date) if start_date else None
    ed = dt_date.fromisoformat(end_date) if end_date else None
    symptoms = womens_health_service.get_symptoms(
        db, current_user.id, cycle_id=cycle_id, start_date=sd, end_date=ed,
    )
    return [{
        "id": s.id,
        "cycle_id": s.cycle_id,
        "record_date": str(s.record_date),
        "symptom_type": s.symptom_type,
        "severity": s.severity,
        "notes": s.notes,
    } for s in symptoms]


def _serialize_cycle(cycle) -> Dict[str, Any]:
    return {
        "id": cycle.id,
        "user_id": cycle.user_id,
        "start_date": str(cycle.start_date),
        "end_date": str(cycle.end_date) if cycle.end_date else None,
        "cycle_length": cycle.cycle_length,
        "period_length": cycle.period_length,
        "flow_intensity": cycle.flow_intensity,
        "notes": cycle.notes,
        "created_at": str(cycle.created_at) if cycle.created_at else None,
    }
