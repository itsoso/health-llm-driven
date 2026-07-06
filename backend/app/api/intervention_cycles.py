"""干预周期 API — 起始 / 复查 / 查询 (Personal Health OS P2, 交互稿 ②④).

- POST /intervention-cycles            开启代谢干预周期 (已有进行中则返回该周期)
- GET  /intervention-cycles            干预周期历史列表
- GET  /intervention-cycles/active     当前进行中的周期 (含 outcomes)
- GET  /intervention-cycles/{id}       指定周期
- PATCH /intervention-cycles/{id}      调整周期窗口/目标/停止条件
- POST /intervention-cycles/{id}/cancel  取消周期 (保留历史)
- POST /intervention-cycles/{id}/recheck  复查 (重算 delta/status)
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
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
from app.services.personal_models.outcome_readout import render_outcome_metric

router = APIRouter(prefix="/intervention-cycles", tags=["intervention-cycles"])


class StartCycleRequest(BaseModel):
    days: int = 90
    target_specs: Optional[list] = None  # [{code, target, direction}]; 缺省自动推导


class UpdateCycleRequest(BaseModel):
    days: Optional[int] = None
    target_specs: Optional[list] = None
    stop_conditions: Optional[list] = None


class CancelCycleRequest(BaseModel):
    reason: Optional[str] = None


def _outcome_dict(om) -> dict:
    # R16 P1:经唯一渲染权威出口 —— 门控(处方/激素)指标中和裸裁决 + 降级 clinician_review,
    # 非门控带 RCV 置信度 + 相关非因果。修此前裸 status/delta_pct 外吐的 R4 泄漏。
    out = render_outcome_metric(om)
    defn = get_definition(om.metric_code)  # 既有 definition 的 display 更丰富,优先
    if defn and defn.display:
        out["display"] = defn.display
    return out


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


@router.get("")
def list_cycles(
    status: str = Query(default="all", pattern="^(all|active|completed|abandoned)$"),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """列出当前用户干预周期历史,用于 Agent 和端上回顾。"""
    cycles = ics.list_cycles(db, current_user.id, status=status, limit=limit)
    return {"cycles": [_cycle_dict(c) for c in cycles]}


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


@router.patch("/{cycle_id}")
def update_cycle(
    cycle_id: int,
    body: UpdateCycleRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """调整进行中周期的窗口、目标或停止条件;不改历史基线。"""
    c = _get_owned_cycle(db, current_user.id, cycle_id)
    try:
        c = ics.update_cycle_params(
            db,
            c,
            days=body.days,
            target_specs=body.target_specs,
            stop_conditions=body.stop_conditions,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"cycle": _cycle_dict(c)}


@router.post("/{cycle_id}/cancel")
def cancel_cycle(
    cycle_id: int,
    body: CancelCycleRequest = CancelCycleRequest(),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """取消进行中的干预周期;保留历史记录,状态置为 abandoned。"""
    c = _get_owned_cycle(db, current_user.id, cycle_id)
    if c.status != "active":
        raise HTTPException(status_code=400, detail="只能取消进行中的干预周期")
    c = ics.complete_cycle(db, c, status="abandoned")
    response = {"cycle": _cycle_dict(c)}
    if body.reason:
        response["cancel_reason"] = body.reason
    return response


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
