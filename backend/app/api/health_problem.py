"""医学问题登记 API(R13)。登记/随访/到期/升级,不替代医生。"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.models.user import User
from app.api.deps import get_current_user_required
from app.services import health_problem_service as svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/problems", tags=["医学问题登记"])


class ProblemCreate(BaseModel):
    name: str
    risk_level: str = "P1"
    status: str = "active"
    diagnosis: Optional[Dict[str, Any]] = None
    risk_stratification: Optional[str] = None
    red_lines: Optional[List[Dict[str, Any]]] = None
    responsible: Optional[str] = None
    follow_up: Optional[Dict[str, Any]] = None
    escalation_path: Optional[str] = None
    evidence_tier: Optional[str] = None
    notes: Optional[str] = None


@router.post("")
async def create_problem(
    data: ProblemCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    try:
        p = svc.create_problem(db, current_user.id, data.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return svc.serialize_problem(p)


@router.get("/me")
async def list_my_problems(
    active_only: bool = True,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    return [svc.serialize_problem(p) for p in svc.list_problems(db, current_user.id, active_only)]


@router.get("/due")
async def due_followups(
    within_days: int = Query(default=45, le=400),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """到期/即将到期的复查随访(driver of 复查日历)。"""
    return svc.due_followups(db, current_user.id, within_days)


@router.post("/seed/gastric-ulcer-hp-neg")
async def seed_gastric_ulcer(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """从病理报告登记胃溃疡(Hp 阴性)——锚点用户真实数据。"""
    return svc.serialize_problem(svc.create_gastric_ulcer_hp_negative(db, current_user.id))


@router.post("/{problem_id}/status")
async def set_status(
    problem_id: int,
    status: str = Query(...),   # active/monitoring/resolved
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    try:
        p = svc.set_status(db, problem_id, current_user.id, status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if p is None:
        raise HTTPException(status_code=404, detail="问题不存在")
    return svc.serialize_problem(p)
