"""干预周期 API — 起始 / 复查 / 查询 (Personal Health OS P2, 交互稿 ②④).

- POST /intervention-cycles            开启代谢干预周期 (已有进行中则返回该周期)
- GET  /intervention-cycles/active     当前进行中的周期 (含 outcomes)
- GET  /intervention-cycles/{id}       指定周期
- POST /intervention-cycles/{id}/recheck  复查 (重算 delta/status)
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.models.intervention_cycle import InterventionCycle
from app.biomarkers import get_definition
from app.twin.builder import build_twin
from app.services import intervention_cycle_service as ics
from app.services.biomarker_sync import sync_indicators_to_biomarkers

router = APIRouter(prefix="/intervention-cycles", tags=["intervention-cycles"])


class StartCycleRequest(BaseModel):
    days: int = 90
    target_specs: Optional[list] = None  # [{code, target, direction}]; 缺省自动推导


def _outcome_dict(om) -> dict:
    defn = get_definition(om.metric_code)
    return {
        "metric_code": om.metric_code,
        "display": defn.display if defn else om.metric_code,
        "unit": om.unit,
        "baseline_value": om.baseline_value,
        "target_value": om.target_value,
        "latest_value": om.latest_value,
        "delta": om.delta,
        "delta_pct": om.delta_pct,
        "direction": om.direction,
        "status": om.status,
    }


def _cycle_dict(c: InterventionCycle) -> dict:
    return {
        "id": c.id,
        "cycle_type": c.cycle_type,
        "status": c.status,
        "start_date": c.start_date.isoformat() if c.start_date else None,
        "planned_end_date": c.planned_end_date.isoformat() if c.planned_end_date else None,
        "baseline_snapshot_id": c.baseline_snapshot_id,
        "latest_snapshot_id": c.latest_snapshot_id,
        "target_metrics": c.target_metrics,
        "stop_conditions": c.stop_conditions,
        "outcomes": [_outcome_dict(om) for om in c.outcomes],
    }


def _get_owned_cycle(db: Session, user_id: int, cycle_id: int) -> InterventionCycle:
    c = db.query(InterventionCycle).filter(
        InterventionCycle.id == cycle_id, InterventionCycle.user_id == user_id
    ).first()
    if c is None:
        raise HTTPException(status_code=404, detail="周期不存在")
    return c


@router.post("")
def start_cycle(
    body: StartCycleRequest = StartCycleRequest(),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """开启代谢干预周期。已有进行中的周期则直接返回它 (不重复开)。"""
    existing = ics.get_active_cycle(db, current_user.id)
    if existing is not None:
        return {"created": False, "cycle": _cycle_dict(existing)}
    twin = build_twin(db, current_user.id)
    cycle = ics.start_metabolic_cycle(
        db, current_user.id, twin, days=body.days, target_specs=body.target_specs
    )
    return {"created": True, "cycle": _cycle_dict(cycle)}


@router.get("/active")
def active_cycle(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    c = ics.get_active_cycle(db, current_user.id)
    return {"cycle": _cycle_dict(c) if c else None}


@router.get("/{cycle_id}")
def get_cycle(
    cycle_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    return {"cycle": _cycle_dict(_get_owned_cycle(db, current_user.id, cycle_id))}


@router.post("/{cycle_id}/recheck")
def recheck_cycle(
    cycle_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """复查: 用最新 Twin + biomarker 重算每个指标的 delta/status。"""
    c = _get_owned_cycle(db, current_user.id, cycle_id)
    # 复查前先把 OCR/手录入库的 medical_indicators 归一进 biomarker_observations:
    # record_recheck 只读 biomarker,不先同步则 latest_value 仍是旧值 —— 用户刚传完化验、
    # 点「复查」却看到没变化(假装成功型坑)。失败不吞,让调用方感知,绝不在可能过期的
    # 数据上给出复查裁决。
    sync_indicators_to_biomarkers(db, current_user.id)
    twin = build_twin(db, current_user.id)
    c = ics.record_recheck(db, c, twin)
    return {"cycle": _cycle_dict(c)}
