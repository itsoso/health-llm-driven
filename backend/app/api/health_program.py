"""健康项目 API(第 4 个一等对象)。串 Problem→Protocol→outcome 的 8–12 周容器。"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.models.user import User
from app.api.deps import get_current_user_required
from app.services import health_program_service as svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/programs", tags=["健康项目"])


class ProgramCreate(BaseModel):
    name: str
    program_type: str
    status: str = "active"
    problem_id: Optional[int] = None
    primary_metrics: Optional[List[str]] = None
    secondary_metrics: Optional[List[str]] = None
    baseline: Optional[Dict[str, Any]] = None
    target: Optional[Dict[str, Any]] = None
    target_end_on: Optional[str] = None
    notes: Optional[str] = None


@router.post("")
async def create_program(
    data: ProgramCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    try:
        g = svc.create_program(db, current_user.id, data.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return svc.serialize_program(g)


@router.get("/me")
async def list_my_programs(
    active_only: bool = True,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    return [svc.serialize_program(g) for g in svc.list_programs(db, current_user.id, active_only)]


@router.get("/{program_id}/progress")
async def program_progress(
    program_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    r = svc.progress(db, program_id, current_user.id)
    if r is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return r


@router.post("/{program_id}/attach-protocol/{protocol_id}")
async def attach_protocol(
    program_id: int,
    protocol_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    try:
        svc.attach_protocol(db, program_id, protocol_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"program_id": program_id, "protocol_id": protocol_id, "attached": True}


@router.post("/from-problem/{problem_id}")
async def from_problem(
    problem_id: int,
    program_type: str = Query(...),
    name: Optional[str] = None,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    try:
        g = svc.create_from_problem(db, current_user.id, problem_id, program_type, name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return svc.serialize_program(g)


@router.post("/{program_id}/status")
async def set_status(
    program_id: int,
    status: str = Query(...),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    try:
        g = svc.set_status(db, program_id, current_user.id, status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if g is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return svc.serialize_program(g)
