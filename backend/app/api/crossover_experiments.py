"""R16 P4 交叉实验 API —— 建实验 / 串 on-off 相 / 查重复感知裁决。

- POST /crossover-experiments            建实验 {metric_code, direction}
- POST /crossover-experiments/{id}/phases 串一个 cycle 作 on/off 相 {cycle_id, arm}
- GET  /crossover-experiments/{id}       查实验 + 重复感知裁决
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.crossover_experiment import CrossoverExperiment
from app.models.user import User
from app.services import crossover_service as cx

router = APIRouter(prefix="/crossover-experiments", tags=["crossover-experiments"])


class CreateReq(BaseModel):
    metric_code: str
    direction: str = "down"


class AddPhaseReq(BaseModel):
    cycle_id: int
    arm: str  # on / off


def _get(db: Session, user_id: int, eid: int) -> CrossoverExperiment:
    exp = (
        db.query(CrossoverExperiment)
        .filter(CrossoverExperiment.id == eid, CrossoverExperiment.user_id == user_id)
        .first()
    )
    if exp is None:
        raise HTTPException(status_code=404, detail="交叉实验不存在")
    return exp


@router.post("")
def create(
    req: CreateReq,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    return cx.serialize(cx.create_experiment(db, user.id, req.metric_code, req.direction))


@router.post("/{eid}/phases")
def add_phase(
    eid: int,
    req: AddPhaseReq,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    exp = _get(db, user.id, eid)
    try:
        exp = cx.add_phase(db, exp, req.cycle_id, req.arm)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return cx.serialize(exp)


@router.get("/{eid}")
def get(
    eid: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_required),
):
    return cx.serialize(_get(db, user.id, eid))
